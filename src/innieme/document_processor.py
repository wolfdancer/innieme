import asyncio
import fnmatch
import glob
import logging
import os
import time
from typing import Dict, List, Optional, Union

import docx
import pypdf
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import SecretStr

from .embeddings_factory import EmbeddingsFactory
from .index_status import FileStamp, IndexFreshness, IndexSnapshot
from .vector_store_factory import VectorStoreFactory

logger = logging.getLogger(__name__)

# CLAUDE.md is agent instructions by convention, not subject-matter content.
# Ingesting instructions into the knowledge base means the model can retrieve
# directives meant for a different task and follow them as if they applied to
# answering the question.
DEFAULT_DOCS_EXCLUDE = ["CLAUDE.md"]


class DocumentProcessor:
    # How long a freshness check is reused. Per-query checks would otherwise
    # re-glob the directory for every message; a note edited seconds ago being
    # reported a half-minute late is harmless. 0 disables the cache.
    FRESHNESS_CACHE_SECONDS = 30

    def __init__(
        self,
        topic: str,
        docs_dir: str,
        embeddings_factory: EmbeddingsFactory,
        vector_store_factory: VectorStoreFactory,
        docs_exclude: Optional[List[str]] = None,
    ):
        self.docs_dir = docs_dir
        self.topic = topic
        self.embeddings_factory = embeddings_factory
        self.vector_store_factory = vector_store_factory
        # None means "use the defaults"; an explicit [] disables exclusion.
        self.docs_exclude = (
            list(DEFAULT_DOCS_EXCLUDE) if docs_exclude is None else list(docs_exclude)
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )
        # Set only by a scan that completes, together with the vectorstore it
        # describes, so the two never disagree. A failed scan leaves both alone.
        self.snapshot: Optional[IndexSnapshot] = None
        self._freshness: Optional[IndexFreshness] = None
        # Rescan is open to everyone, so two can arrive at once. They would each
        # embed every document and the slower one would win; serialize instead.
        self._scan_lock = asyncio.Lock()

    def _is_excluded(self, file_path: str) -> bool:
        """Whether a scanned file matches an exclusion pattern.

        Each pattern is matched against both the file's basename and its path
        relative to ``docs_dir``, so ``CLAUDE.md`` excludes that file at any
        depth while ``archive/*`` excludes a subdirectory.
        """
        if not self.docs_exclude:
            return False
        basename = os.path.basename(file_path)
        try:
            relative = os.path.relpath(file_path, self.docs_dir)
        except ValueError:  # different drive on Windows
            relative = basename
        return any(
            fnmatch.fnmatch(basename, pattern) or fnmatch.fnmatch(relative, pattern)
            for pattern in self.docs_exclude
        )

    def _create_empty_store(self):
        """Handle the case where no texts are found to vectorize"""
        collection_name = self._get_collection_name()
        return self.vector_store_factory.create_empty_store(
            collection_name=collection_name,
            embeddings=self.embeddings_factory.create_embeddings(),
        )

    def _get_collection_name(self) -> str:
        """Create a unique collection name using topic and timestamp"""
        # Clean topic name to be filesystem safe
        safe_topic = "".join(c if c.isalnum() else "_" for c in self.topic)
        timestamp = int(time.time() * 1000)  # Milliseconds since epoch
        return f"{safe_topic}_{timestamp}"

    def _discover_files(self):
        """The candidate files under ``docs_dir``, split into (kept, excluded)."""
        found = []
        for ext in ["*.pdf", "*.docx", "*.txt", "*.md"]:
            found.extend(
                glob.glob(os.path.join(self.docs_dir, "**", ext), recursive=True)
            )
        files = [f for f in found if not self._is_excluded(f)]
        excluded = [f for f in found if self._is_excluded(f)]
        return files, excluded

    async def scan_and_vectorize(self) -> str:
        """Scan all documents in the specified directory and create vector embeddings"""
        async with self._scan_lock:
            return await self._scan_and_vectorize()

    async def _scan_and_vectorize(self) -> str:
        started_at = time.time()
        started = time.monotonic()
        document_texts = []

        # Get all files with common document extensions
        files, excluded = self._discover_files()
        found_count = len(files) + len(excluded)

        logger.info(
            f"For {self.topic}: Found {found_count}, excluded {len(excluded)}, "
            f"processing {len(files)} under {self.docs_dir}..."
        )
        # Log exclusions explicitly: a file silently missing from the knowledge
        # base is much harder to diagnose than one reported as skipped.
        for file_path in excluded:
            logger.info(f"  - skipped (excluded): {os.path.basename(file_path)}")
        # Process each file based on its type
        count = 0
        failed: List[str] = []
        stamps: Dict[str, FileStamp] = {}
        for file_path in files:
            logger.info(f"  - {file_path}")
            # Stamped before reading, so an edit that lands mid-scan compares as
            # changed afterwards instead of hiding behind a newer stamp.
            stamp = FileStamp.of(file_path)
            if stamp is not None:
                stamps[file_path] = stamp
            text = await self._extract_text(file_path)
            if text is None:
                # _extract_text logs the cause and returns None.
                logger.error(f"    Text extraction failed for {file_path}")
                failed.append(file_path)
            elif not text.strip():
                # Readable but empty, which is not a failure: an empty file has
                # nothing to contribute and should not hold up the rest.
                logger.warning(f"    No text in {file_path}")
            else:
                document_texts.append({"text": text, "source": file_path})
                count += 1
        logger.info(f"Done. Extracted text from {count} documents")
        extract_seconds = time.monotonic() - started
        index_started = time.monotonic()

        if failed and not count:
            # Every readable candidate failed — a permissions change, a corrupt
            # file, an unreadable encoding. Raising *before* self.vectorstore is
            # reassigned is what keeps the previous index intact, which matters
            # now that a rescan can run on a live bot: replacing a working store
            # with an empty one would make the bot answer "not in my documents"
            # for everything it knew a moment ago. A partial failure still goes
            # through, and is reported in the returned message.
            raise RuntimeError(
                f"On topic '{self.topic}': found {len(files)} document(s) under {self.docs_dir} "
                f"but could not extract text from any of them"
            )

        # Split texts into chunks
        all_chunks = []
        for doc in document_texts:
            chunks = self.text_splitter.split_text(doc["text"])
            all_chunks.extend(
                [{"text": chunk, "source": doc["source"]} for chunk in chunks]
            )

        # Create vector store
        texts = [chunk["text"] for chunk in all_chunks]

        collection_name = self._get_collection_name()

        response = ""
        if not texts:
            self.vectorstore = self._create_empty_store()
            response = f"On topic '{self.topic}': no documents found to process"
        else:
            metadatas = [{"source": chunk["source"]} for chunk in all_chunks]
            self.vectorstore = self.vector_store_factory.create_from_texts(
                texts,
                self.embeddings_factory.create_embeddings(),
                collection_name=collection_name,
                metadatas=metadatas,
            )
            response = f"On topic '{self.topic}': {len(all_chunks)} chunks created from {count} out of {len(files)} references"
        self.snapshot = IndexSnapshot(
            started_at=started_at,
            finished_at=time.time(),
            extract_seconds=extract_seconds,
            index_seconds=time.monotonic() - index_started,
            files=stamps,
            failed=failed,
            indexed_count=count,
            chunk_count=len(all_chunks),
        )
        self._freshness = None  # computed against the previous snapshot
        if excluded:
            # Count only, never names: the channel-facing message is visible to
            # everyone, and a file is often excluded precisely because those
            # readers should not know about it. The names are in the logs, which
            # is where whoever configured the bot will look.
            plural = "s" if len(excluded) != 1 else ""
            response += f" ({len(excluded)} file{plural} excluded; see logs)"
        return response

    def check_freshness(self, force: bool = False) -> Optional[IndexFreshness]:
        """Compare the directory with the last scan, by ``stat`` alone.

        None until a scan has completed. A recent result is reused unless
        ``force`` is set (the ``status`` command wants the truth, not a
        half-minute-old answer). Blocking, but it reads no file contents; async
        callers should run it in a thread.
        """
        snapshot = self.snapshot
        if snapshot is None:
            return None
        cached = self._freshness
        if (
            not force
            and cached is not None
            and time.time() - cached.checked_at < self.FRESHNESS_CACHE_SECONDS
        ):
            return cached

        current, _ = self._discover_files()
        freshness = IndexFreshness(checked_at=time.time())
        seen = set()
        for path in current:
            seen.add(path)
            stamp = FileStamp.of(path)
            if stamp is None:
                continue
            recorded = snapshot.files.get(path)
            if recorded is None:
                freshness.added.append(path)
            elif recorded != stamp:
                freshness.modified.append(path)
        freshness.removed = [p for p in snapshot.files if p not in seen]
        self._freshness = freshness
        return freshness

    async def _extract_text(self, file_path):
        """Extract text from a document file based on its extension"""
        _, ext = os.path.splitext(file_path)

        try:
            if ext.lower() == ".pdf":
                return await self._extract_from_pdf(file_path)
            elif ext.lower() == ".docx":
                return await self._extract_from_docx(file_path)
            elif ext.lower() == ".txt" or ext.lower() == ".md":
                return await self._extract_from_txt(file_path)
            else:
                logger.warning(f"Unsupported file format: {file_path}")
                return None
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {str(e)}")
            return None

    async def _extract_from_pdf(self, file_path):
        """Extract text from a PDF file"""
        text = ""
        with open(file_path, "rb") as file:
            reader = pypdf.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                # "or \"\"" because a page with no extractable text is normal (an
                # image-only scan). pypdf types this as str, but concatenating a
                # None here would raise, and a raise now counts as an extraction
                # failure rather than an empty file.
                text += (page.extract_text() or "") + "\n"
        return text

    async def _extract_from_docx(self, file_path):
        """Extract text from a DOCX file"""
        doc = docx.Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text

    async def _extract_from_txt(self, file_path):
        """Extract text from a TXT file"""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
            text = file.read()
        return text

    async def search_documents(self, query, top_k=5, score_threshold=None) -> List:
        """Search the vectorstore for relevant document chunks.

        Args:
            query: The search text.
            top_k: Maximum number of chunks to return.
            score_threshold: Optional relevance floor between 0 and 1. When set,
                chunks scoring below it are dropped, so a query with only a
                couple of genuinely relevant chunks returns only those instead
                of padding the context out to ``top_k``.
        """
        if not self.vectorstore:
            return []

        if score_threshold is None:
            return self.vectorstore.similarity_search(query, k=top_k)

        try:
            scored = self.vectorstore.similarity_search_with_relevance_scores(
                query, k=top_k
            )
        except Exception as e:
            # Relevance scoring depends on the store's distance metric; fall
            # back to an unfiltered search rather than answering nothing.
            logger.warning(f"Relevance scoring unavailable, ignoring threshold: {e}")
            return self.vectorstore.similarity_search(query, k=top_k)

        kept = [doc for doc, score in scored if score >= score_threshold]
        logger.debug(
            f"Retrieved {len(scored)} chunks, kept {len(kept)} "
            f"at threshold {score_threshold}"
        )
        return kept
