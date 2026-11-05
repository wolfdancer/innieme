import asyncio
import fnmatch
import logging
import os
import time
from typing import Dict, List, Optional, Tuple, Union

import docx
import pypdf
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import SecretStr

from .embeddings_factory import EmbeddingsFactory
from .index_status import (
    FileStamp,
    FreshnessUnavailable,
    IndexFreshness,
    IndexSnapshot,
    PublishedIndex,
    ScanResult,
    compare,
)
from .vector_store_factory import VectorStoreFactory

logger = logging.getLogger(__name__)

# CLAUDE.md is agent instructions by convention, not subject-matter content.
# Ingesting instructions into the knowledge base means the model can retrieve
# directives meant for a different task and follow them as if they applied to
# answering the question.
DEFAULT_DOCS_EXCLUDE = ["CLAUDE.md"]

# File types the scanner reads. Matched case-sensitively, as the per-extension
# globs this replaced were.
DOC_EXTENSIONS = (".pdf", ".docx", ".txt", ".md")


class DocumentProcessor:
    # How long a routine (answer-time) freshness result is reused. 0 disables.
    FRESHNESS_CACHE_SECONDS = 30
    # How long an answer waits for a freshness check before going on without.
    ROUTINE_CHECK_TIMEOUT = 5.0
    # Total time an explicit check (``status``) may take, including waiting for
    # a routine check already in flight.
    EXPLICIT_CHECK_TIMEOUT = 10.0

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
        # The store and the snapshot describing it, published together by a
        # scan that succeeds so no reader sees one without the other. A failed
        # scan leaves the previous pair in place.
        self._index: Optional[PublishedIndex] = None
        # Rescan is open to everyone, so two can arrive at once; each would
        # embed every document and the slower would win. Serialize them.
        self._scan_lock = asyncio.Lock()
        # Last routine freshness result, valid only for its own snapshot.
        self._freshness_cache: Optional[IndexFreshness] = None
        # The one routine check allowed in flight, and the snapshot it is for.
        self._inflight: Optional[Tuple[IndexSnapshot, "asyncio.Future"]] = None

    @property
    def vectorstore(self):
        return self._index.store if self._index else None

    @vectorstore.setter
    def vectorstore(self, store):
        # Kept for callers and tests that set the store directly: it keeps the
        # current snapshot, so the pair stays a pair.
        self._index = PublishedIndex(store=store, snapshot=self.snapshot)

    @property
    def snapshot(self) -> Optional[IndexSnapshot]:
        return self._index.snapshot if self._index else None

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

    def _discover_files(self, strict: bool = False) -> Tuple[List[str], List[str]]:
        """Candidate files under ``docs_dir``, split into (kept, excluded).

        One walk, shared by the scan and the staleness check so both see the
        same candidates: supported extensions only, hidden files and
        directories skipped, directory symlinks followed except one pointing
        back up the tree (which would recurse forever).

        ``strict`` raises on a directory that cannot be listed. The scan skips
        one, as the glob it replaced did; the staleness check must not, because
        a directory it cannot read would otherwise make its new files invisible
        and its indexed files look deleted.
        """

        top = self.docs_dir
        real_top = os.path.realpath(top)
        found = list(self._walk(top, real_top, strict, (real_top,)))
        files = [f for f in found if not self._is_excluded(f)]
        excluded = [f for f in found if self._is_excluded(f)]
        return files, excluded

    def _wholly_excluded(self, directory: str) -> bool:
        """Whether every file under ``directory`` is provably excluded.

        Only a pattern that is a literal prefix followed by a final ``*``
        (``archive/*``, or ``*`` alone) proves it: ``*`` matches any rest of
        the path, ``/`` included. Anything cleverer (``archive/[!_]*``) could
        still let a file through, so it is not taken as proof and the strict
        walk keeps reporting the directory as unreadable.
        """
        try:
            relative = os.path.relpath(directory, self.docs_dir)
        except ValueError:  # different drive on Windows
            return False
        # What every file path under the directory starts with, relative to
        # docs_dir: nothing for docs_dir itself (relpath gives "."), else the
        # directory's own path and a separator.
        descendants = "" if relative == os.curdir else relative + os.sep
        for pattern in self.docs_exclude:
            if not pattern.endswith("*"):
                continue
            prefix = pattern[:-1]
            if any(c in prefix for c in "*?["):
                continue
            if descendants.startswith(prefix):
                return True
        return False

    def _walk(self, top: str, real_top: str, strict: bool, ancestors: Tuple[str, ...]):
        """Yield candidate document paths under ``top``.

        Written out rather than ``os.walk``, which swallows a failure to tell
        whether an entry is a directory and silently treats it as a file:
        strict mode has to hear about every directory it could not examine.

        A directory the strict walk cannot examine is still skipped quietly
        when everything under it is excluded: the topic ignores those files, so
        they must not make every freshness check fail.

        ``ancestors`` holds the real paths of the directories on the way down
        to ``top`` (``real_top`` is its own). A directory whose real path is already among them would
        recurse forever -- a symlink to an ancestor, or a cycle through
        siblings (``a/to_b -> b``, ``b/to_a -> a``) -- so it is pruned. Any
        other alias is walked, as the glob did, so an excluded alias can never
        hide its allowed target.
        """
        try:
            with os.scandir(top) as it:
                entries = list(it)
        except OSError as err:
            if strict and not self._wholly_excluded(top):
                raise
            logger.warning(f"Skipping unreadable directory: {err.filename}")
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                is_dir = entry.is_dir()  # follows symlinks
            except OSError:
                if strict and not self._wholly_excluded(entry.path):
                    raise
                is_dir = False  # as os.walk and glob treat it
            if is_dir:
                # Only a symlink can move the real path; anything else is its
                # parent's real path plus its name, with no extra syscalls.
                if entry.is_symlink():
                    real = os.path.realpath(entry.path)
                else:
                    real = os.path.join(real_top, entry.name)
                if real in ancestors:
                    continue
                yield from self._walk(entry.path, real, strict, ancestors + (real,))
            elif entry.name.endswith(DOC_EXTENSIONS):
                yield entry.path

    async def scan_and_vectorize(self) -> str:
        """Scan and vectorize, returning only the channel message.

        Kept for the startup callers; ``scan()`` also returns the snapshot.
        """
        return (await self.scan()).message

    async def scan(self) -> ScanResult:
        """Scan all documents in the directory and create vector embeddings.

        Returns this scan's own message and snapshot, so a caller that queued
        behind another scan reports its own figures, not its neighbour's.
        """
        async with self._scan_lock:
            return await self._scan()

    async def _scan(self) -> ScanResult:
        started_at = time.time()
        started = time.monotonic()
        document_texts = []

        files, excluded = self._discover_files()

        logger.info(
            f"For {self.topic}: Found {len(files) + len(excluded)}, excluded {len(excluded)}, "
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
            if stamp is None:
                # Vanished or unreadable between discovery and now: a failure,
                # recorded without a stamp.
                logger.error(f"    Could not stat {file_path}")
                failed.append(file_path)
                continue
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
            # file, an unreadable encoding. Raising *before* the new index is
            # published is what keeps the previous index intact, which matters
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
            store = self._create_empty_store()
            response = f"On topic '{self.topic}': no documents found to process"
        else:
            metadatas = [{"source": chunk["source"]} for chunk in all_chunks]
            store = self.vector_store_factory.create_from_texts(
                texts,
                self.embeddings_factory.create_embeddings(),
                collection_name=collection_name,
                metadatas=metadatas,
            )
            response = f"On topic '{self.topic}': {len(all_chunks)} chunks created from {count} out of {len(files)} references"

        snapshot = IndexSnapshot(
            started_at=started_at,
            finished_at=time.time(),
            extract_seconds=extract_seconds,
            index_seconds=time.monotonic() - index_started,
            files=stamps,
            failed=failed,
            indexed_count=count,
            chunk_count=len(all_chunks),
        )
        # Published together, in one assignment: see PublishedIndex.
        self._index = PublishedIndex(store=store, snapshot=snapshot)
        if excluded:
            # Count only, never names: the channel-facing message is visible to
            # everyone, and a file is often excluded precisely because those
            # readers should not know about it. The names are in the logs, which
            # is where whoever configured the bot will look.
            plural = "s" if len(excluded) != 1 else ""
            response += f" ({len(excluded)} file{plural} excluded; see logs)"
        return ScanResult(message=response, snapshot=snapshot)

    # --- Freshness ----------------------------------------------------------

    def _compute_freshness(self, snapshot: IndexSnapshot) -> IndexFreshness:
        """Compare the directory with ``snapshot``. Blocking; stat only."""
        current, _ = self._discover_files(strict=True)
        return compare(snapshot, current)

    def _remember(self, freshness: IndexFreshness) -> None:
        """Cache a result, but only for the snapshot currently published.

        A late result for an older snapshot is never useful and must not push
        out a newer one.
        """
        if freshness.snapshot is not None and freshness.snapshot is self.snapshot:
            self._freshness_cache = freshness

    def _start_check(self, snapshot: IndexSnapshot) -> "asyncio.Future":
        """Start a check of ``snapshot`` in a worker thread, in the one slot.

        Routine and explicit checks share the slot, so a hung notes mount holds
        at most one worker thread however many questions or ``status``
        requests arrive. The thread cannot be cancelled: a caller that gives up
        leaves it running, and it keeps the slot until it ends, when a late
        result still fills the reuse window.
        """
        future = asyncio.ensure_future(
            asyncio.to_thread(self._compute_freshness, snapshot)
        )
        self._inflight = (snapshot, future)

        def _done(fut):
            if self._inflight is not None and self._inflight[1] is fut:
                self._inflight = None
            if not fut.cancelled() and fut.exception() is None:
                self._remember(fut.result())

        future.add_done_callback(_done)
        return future

    async def routine_freshness(
        self, snapshot: Optional[IndexSnapshot]
    ) -> Optional[IndexFreshness]:
        """Freshness for an answer whose excerpts came from ``snapshot``.

        Never raises and never waits longer than ROUTINE_CHECK_TIMEOUT: it only
        informs an answer, so on any problem the answer goes ahead without it
        (None). A caller arriving while a check is in flight shares it only if
        it is for the same snapshot, and never starts a second one.
        """
        if snapshot is None:
            return None
        cached = self._freshness_cache
        if (
            cached is not None
            and cached.snapshot is snapshot
            and time.time() - cached.checked_at < self.FRESHNESS_CACHE_SECONDS
        ):
            return cached

        if self._inflight is None:
            future = self._start_check(snapshot)
        else:
            inflight_snapshot, future = self._inflight
            if inflight_snapshot is not snapshot:
                return None

        try:
            return await asyncio.wait_for(
                asyncio.shield(future), self.ROUTINE_CHECK_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Freshness check for {self.topic} timed out; answering without it"
            )
        except Exception:
            logger.exception(
                f"Freshness check for {self.topic} failed; answering without it"
            )
        return None

    async def explicit_freshness(self) -> Optional[IndexFreshness]:
        """A fresh check of the current snapshot, for someone who asked.

        Waits for whatever check is in flight (it may have looked at a file
        before the edit being asked about, or be another ``status``), then
        runs its own in the shared slot, all within EXPLICIT_CHECK_TIMEOUT.
        None before the first scan; raises FreshnessUnavailable if the check
        errors or runs out of time.
        """
        snapshot = self.snapshot
        if snapshot is None:
            return None
        deadline = time.monotonic() + self.EXPLICIT_CHECK_TIMEOUT

        async def finished(future) -> bool:
            # asyncio.wait reports the deadline as "not done" instead of
            # raising, so a TimeoutError the worker itself raised (a slow
            # network mount, say) is never mistaken for our deadline. It also
            # never cancels or wraps the worker, so a caller that gives up
            # leaves nothing attached to it.
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return future.done()
            done, _ = await asyncio.wait({future}, timeout=remaining)
            return bool(done)

        while self._inflight is not None:
            running = self._inflight[1]
            if not await finished(running):
                raise FreshnessUnavailable("freshness check timed out")
            # Whatever it raised is its own; ours runs next regardless.
            if self._inflight is not None and self._inflight[1] is running:
                self._inflight = None  # finished; its callback just hasn't run
        if deadline - time.monotonic() <= 0:
            raise FreshnessUnavailable("freshness check timed out")
        future = self._start_check(snapshot)
        if not await finished(future):
            raise FreshnessUnavailable("freshness check timed out")
        try:
            return future.result()
        except Exception as e:
            raise FreshnessUnavailable(str(e)) from e

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
        docs, _ = await self.search_with_snapshot(query, top_k, score_threshold)
        return docs

    async def search_with_snapshot(
        self, query, top_k=5, score_threshold=None
    ) -> Tuple[List, Optional[IndexSnapshot]]:
        """``search_documents``, plus the snapshot of the store it searched.

        The published pair is read once, so the snapshot always describes the
        index the excerpts came from, even if a rescan lands straight after.
        """
        index = self._index
        if index is None or not index.store:
            return [], None
        return self._search(index.store, query, top_k, score_threshold), index.snapshot

    def _search(self, store, query, top_k, score_threshold) -> List:
        if score_threshold is None:
            return store.similarity_search(query, k=top_k)

        try:
            scored = store.similarity_search_with_relevance_scores(query, k=top_k)
        except Exception as e:
            # Relevance scoring depends on the store's distance metric; fall
            # back to an unfiltered search rather than answering nothing.
            logger.warning(f"Relevance scoring unavailable, ignoring threshold: {e}")
            return store.similarity_search(query, k=top_k)

        kept = [doc for doc, score in scored if score >= score_threshold]
        logger.debug(
            f"Retrieved {len(scored)} chunks, kept {len(kept)} "
            f"at threshold {score_threshold}"
        )
        return kept
