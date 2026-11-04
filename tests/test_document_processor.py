import os
import pytest
from innieme.document_processor import DocumentProcessor
from innieme.vector_store_factory import ChromaVectorStoreFactory
from innieme.embeddings_factory import ExistingEmbeddingsFactory
from langchain_core.embeddings import Embeddings
import numpy as np

# Test data directory
TEST_DOCS_DIR = "test_documents"
TEST_DOCS_2_DIR = "test_documents_2"

class FakeEmbeddings(Embeddings):
    """Fake embeddings for testing"""
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Return consistent fake embeddings based on text content
        return [self._get_fake_embedding(text) for text in texts]
    
    def embed_query(self, text: str) -> list[float]:
        return self._get_fake_embedding(text)
    
    def _get_fake_embedding(self, text: str) -> list[float]:
        # Generate deterministic fake embeddings
        if "cars" in text.lower():
            return [1.0, 0.0, 0.0]
        elif "plants" in text.lower():
            return [0.0, 1.0, 0.0]
        else:
            return [0.0, 0.0, 1.0]

@pytest.fixture
def test_docs_dir(tmp_path):
    """Create a temporary directory for test documents"""
    docs_dir = tmp_path / TEST_DOCS_DIR
    docs_dir.mkdir()
    return docs_dir

@pytest.fixture
def test_docs_2_dir(tmp_path):
    """Create a second temporary directory for test documents"""
    docs_2_dir = tmp_path / TEST_DOCS_2_DIR
    docs_2_dir.mkdir()
    return docs_2_dir

@pytest.fixture
def sample_txt_file(test_docs_dir):
    """Create a sample text file for testing"""
    file_path = test_docs_dir / "test.txt"
    file_path.write_text("This is a test document.\nIt has multiple lines.")
    return file_path

@pytest.fixture
def document_processor(test_docs_dir) -> DocumentProcessor:
    """Create a DocumentProcessor instance for testing"""
    return DocumentProcessor(
        "testing", 
        str(test_docs_dir), 
        ExistingEmbeddingsFactory(FakeEmbeddings()),
        ChromaVectorStoreFactory()
    )

@pytest.mark.asyncio
async def test_extract_from_txt(document_processor, sample_txt_file):
    """Test text extraction from a TXT file"""
    text = await document_processor._extract_from_txt(str(sample_txt_file))
    assert text is not None
    assert "This is a test document" in text
    assert "It has multiple lines" in text

@pytest.mark.asyncio
async def test_scan_and_vectorize_empty_dir(document_processor):
    """Test scanning an empty directory"""
    result = await document_processor.scan_and_vectorize()
    assert result == "On topic 'testing': no documents found to process"
    assert document_processor.vectorstore is not None
    results = await document_processor.search_documents("test query")
    assert results == []

@pytest.mark.asyncio
async def test_search_documents_with_data(document_processor, sample_txt_file):
    """Test searching after processing documents"""
    # First scan and vectorize
    await document_processor.scan_and_vectorize()
    
    # Then search
    results = await document_processor.search_documents("test document")
    assert len(results) > 0
    assert "test document" in results[0].page_content.lower()

@pytest.mark.asyncio
async def test_independent_vectorstores_different_topics(test_docs_dir, test_docs_2_dir):
    """Test that document processors with different topics maintain separate vectorstores"""
    # Create test files for different topics
    topic1_file = test_docs_dir / "cars.txt"
    topic2_file = test_docs_2_dir / "plants.txt"
    topic1_file.write_text("This is a document about cars and vehicles")
    topic2_file.write_text("This is a document about plants and gardens")
    
    fake_embeddings1 = FakeEmbeddings()
    fake_embeddings2 = FakeEmbeddings()
    
    # Create processors for different topics with fake embeddings
    cars_processor = DocumentProcessor(
        "cars", 
        str(test_docs_dir), 
        ExistingEmbeddingsFactory(fake_embeddings1),
        ChromaVectorStoreFactory()
    )
    plants_processor = DocumentProcessor(
        "plants", 
        str(test_docs_2_dir), 
        ExistingEmbeddingsFactory(fake_embeddings2),
        ChromaVectorStoreFactory()
    )
    
    # Process documents under different topics
    await cars_processor.scan_and_vectorize()
    await plants_processor.scan_and_vectorize()
    
    # Search for cars in cars processor - should find just one result
    car_results = await cars_processor.search_documents("cars")
    assert len(car_results) == 1
    assert car_results[0].page_content == "This is a document about cars and vehicles"
    assert car_results[0].metadata["source"].endswith("cars.txt")
    
    # Search for plants in cars processor - should find at most 1 result
    plant_results_in_cars = await cars_processor.search_documents("plants")
    assert len(plant_results_in_cars) < 2
    
    # Search for plants in plants processor - should find just one result
    plant_results = await plants_processor.search_documents("plants")
    assert len(plant_results) == 1
    assert plant_results[0].page_content == "This is a document about plants and gardens"
    assert plant_results[0].metadata["source"].endswith("plants.txt")
    
    # Search for cars in plants processor - should find at most 1 result
    car_results_in_plants = await plants_processor.search_documents("cars")
    assert len(car_results_in_plants) < 2
@pytest.mark.asyncio
async def test_search_documents_applies_score_threshold(document_processor):
    """Chunks scoring below the threshold are dropped"""
    from unittest.mock import Mock
    strong, weak = Mock(page_content="strong"), Mock(page_content="weak")
    document_processor.vectorstore = Mock()
    document_processor.vectorstore.similarity_search_with_relevance_scores.return_value = [
        (strong, 0.82), (weak, 0.11),
    ]
    results = await document_processor.search_documents("q", top_k=10, score_threshold=0.3)
    assert results == [strong]

@pytest.mark.asyncio
async def test_search_documents_without_threshold_skips_scoring(document_processor):
    """No threshold means the plain similarity search is used"""
    from unittest.mock import Mock
    doc = Mock(page_content="text")
    document_processor.vectorstore = Mock()
    document_processor.vectorstore.similarity_search.return_value = [doc]
    results = await document_processor.search_documents("q", top_k=3)
    assert results == [doc]
    document_processor.vectorstore.similarity_search.assert_called_once_with("q", k=3)
    document_processor.vectorstore.similarity_search_with_relevance_scores.assert_not_called()

@pytest.mark.asyncio
async def test_search_documents_falls_back_when_scoring_unavailable(document_processor):
    """A store that can't produce relevance scores still returns results"""
    from unittest.mock import Mock
    doc = Mock(page_content="text")
    document_processor.vectorstore = Mock()
    document_processor.vectorstore.similarity_search_with_relevance_scores.side_effect = (
        ValueError("no relevance fn for this metric")
    )
    document_processor.vectorstore.similarity_search.return_value = [doc]
    results = await document_processor.search_documents("q", top_k=5, score_threshold=0.5)
    assert results == [doc]

class TestDocsExclude:
    """Scanning skips files that are instructions rather than content."""

    def _processor(self, tmp_path, exclude=None):
        from innieme.document_processor import DocumentProcessor
        from innieme.embeddings_factory import ExistingEmbeddingsFactory
        from innieme.vector_store_factory import ChromaVectorStoreFactory
        from langchain_community.embeddings import FakeEmbeddings
        return DocumentProcessor(
            "t", str(tmp_path),
            ExistingEmbeddingsFactory(FakeEmbeddings(size=1536)),
            ChromaVectorStoreFactory(),
            docs_exclude=exclude,
        )

    def test_claude_md_excluded_by_default(self, tmp_path):
        p = self._processor(tmp_path)
        assert p._is_excluded(str(tmp_path / "CLAUDE.md"))
        assert not p._is_excluded(str(tmp_path / "Northwind.md"))

    def test_excluded_at_any_depth(self, tmp_path):
        p = self._processor(tmp_path)
        assert p._is_excluded(str(tmp_path / "sub" / "dir" / "CLAUDE.md"))

    def test_empty_list_disables_exclusion(self, tmp_path):
        p = self._processor(tmp_path, exclude=[])
        assert not p._is_excluded(str(tmp_path / "CLAUDE.md"))

    def test_directory_pattern_matches_relative_path(self, tmp_path):
        p = self._processor(tmp_path, exclude=["archive/*"])
        assert p._is_excluded(str(tmp_path / "archive" / "old.md"))
        assert not p._is_excluded(str(tmp_path / "current" / "new.md"))

    def test_glob_pattern_on_basename(self, tmp_path):
        p = self._processor(tmp_path, exclude=["*-draft.md"])
        assert p._is_excluded(str(tmp_path / "Northwind-draft.md"))
        assert not p._is_excluded(str(tmp_path / "Northwind.md"))

    @pytest.mark.asyncio
    async def test_excluded_file_is_not_vectorized_and_is_reported(self, tmp_path):
        (tmp_path / "Northwind.md").write_text("Northwind is at stage 3 of the pipeline.")
        (tmp_path / "CLAUDE.md").write_text("Always invent a next action as a best guess.")
        p = self._processor(tmp_path)
        response = await p.scan_and_vectorize()

        assert "1 out of 1 references" in response
        # Count only -- the channel-facing message must not name excluded files,
        # since a file is often excluded precisely to keep it from those readers.
        assert "1 file excluded" in response
        assert "CLAUDE.md" not in response

        results = await p.search_documents("next action", top_k=10)
        sources = {os.path.basename(d.metadata["source"]) for d in results}
        assert sources == {"Northwind.md"}

    @pytest.mark.asyncio
    async def test_nothing_reported_when_no_exclusions_match(self, tmp_path):
        (tmp_path / "Northwind.md").write_text("Northwind notes.")
        p = self._processor(tmp_path)
        response = await p.scan_and_vectorize()
        assert "excluded" not in response


@pytest.mark.asyncio
async def test_total_extraction_failure_keeps_the_previous_store(document_processor, test_docs_dir):
    """A rescan must not replace a working index with an empty one.

    scan_and_vectorize() can now run on a live bot, so an unreadable documents
    directory would otherwise swap in an empty store and leave the bot answering
    "not in my documents" for everything it knew a moment ago.
    """
    from unittest.mock import AsyncMock, patch

    (test_docs_dir / "broken.md").write_text("content")
    await document_processor.scan_and_vectorize()
    healthy_store = document_processor.vectorstore
    assert healthy_store is not None

    with patch.object(document_processor, '_extract_text', AsyncMock(return_value=None)):
        with pytest.raises(RuntimeError, match="could not extract text"):
            await document_processor.scan_and_vectorize()

    assert document_processor.vectorstore is healthy_store


@pytest.mark.asyncio
async def test_partial_extraction_failure_still_rebuilds(document_processor, test_docs_dir):
    """One bad file must not block the rest; the count is reported"""
    from unittest.mock import patch

    (test_docs_dir / "good.md").write_text("Vectorizable content about widgets.")
    (test_docs_dir / "bad.md").write_text("also content")

    real_extract = document_processor._extract_text

    async def fail_one(file_path):
        if file_path.endswith("bad.md"):
            return None
        return await real_extract(file_path)

    with patch.object(document_processor, '_extract_text', side_effect=fail_one):
        result = await document_processor.scan_and_vectorize()

    assert "1 out of 2 references" in result


@pytest.mark.asyncio
async def test_empty_files_are_not_treated_as_failures(document_processor, test_docs_dir):
    """An empty file contributes nothing, but must not fail the whole scan"""
    (test_docs_dir / "empty.md").write_text("")
    (test_docs_dir / "blank.md").write_text("   \n\n")

    result = await document_processor.scan_and_vectorize()

    assert "no documents found to process" in result
    assert document_processor.vectorstore is not None


# --- Index snapshot and freshness -------------------------------------------

import asyncio

from innieme.index_status import (
    describe_for_channel,
    describe_for_model,
    format_age,
)


def _bump(path, seconds=10):
    """Move a file's mtime forward without relying on clock resolution."""
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 10**9))


@pytest.mark.asyncio
async def test_no_snapshot_before_first_scan(document_processor):
    assert document_processor.snapshot is None
    assert document_processor.check_freshness() is None


@pytest.mark.asyncio
async def test_scan_records_snapshot_with_timings(document_processor, sample_txt_file):
    await document_processor.scan_and_vectorize()
    snap = document_processor.snapshot
    assert snap.indexed_count == 1
    assert snap.chunk_count >= 1
    assert str(sample_txt_file) in snap.files
    assert snap.failed == []
    assert snap.finished_at >= snap.started_at
    assert snap.extract_seconds >= 0 and snap.index_seconds >= 0
    assert snap.duration == snap.extract_seconds + snap.index_seconds


@pytest.mark.asyncio
async def test_freshness_detects_modified_added_removed(
    document_processor, test_docs_dir, sample_txt_file
):
    gone = test_docs_dir / "gone.txt"
    gone.write_text("soon deleted")
    await document_processor.scan_and_vectorize()
    assert document_processor.check_freshness(force=True).is_current

    sample_txt_file.write_text("This is a changed test document, longer than before.")
    added = test_docs_dir / "new.md"
    added.write_text("brand new")
    gone.unlink()

    fresh = document_processor.check_freshness(force=True)
    assert fresh.modified == [str(sample_txt_file)]
    assert fresh.added == [str(added)]
    assert fresh.removed == [str(gone)]
    assert fresh.changed_sources == {str(sample_txt_file), str(gone)}


@pytest.mark.asyncio
async def test_mtime_change_alone_is_detected(document_processor, sample_txt_file):
    await document_processor.scan_and_vectorize()
    _bump(sample_txt_file)
    assert document_processor.check_freshness(force=True).modified == [str(sample_txt_file)]


@pytest.mark.asyncio
async def test_rescan_resets_freshness(document_processor, sample_txt_file):
    await document_processor.scan_and_vectorize()
    _bump(sample_txt_file)
    assert not document_processor.check_freshness(force=True).is_current
    await document_processor.scan_and_vectorize()
    assert document_processor.check_freshness(force=True).is_current


@pytest.mark.asyncio
async def test_excluded_files_never_count_as_new(document_processor, test_docs_dir, sample_txt_file):
    await document_processor.scan_and_vectorize()
    (test_docs_dir / "CLAUDE.md").write_text("instructions")
    assert document_processor.check_freshness(force=True).is_current


@pytest.mark.asyncio
async def test_freshness_is_cached_unless_forced(document_processor, sample_txt_file):
    await document_processor.scan_and_vectorize()
    assert document_processor.check_freshness().is_current
    _bump(sample_txt_file)
    assert document_processor.check_freshness().is_current  # cached
    assert not document_processor.check_freshness(force=True).is_current
    document_processor.FRESHNESS_CACHE_SECONDS = 0
    assert not document_processor.check_freshness().is_current


@pytest.mark.asyncio
async def test_file_edited_during_scan_reads_as_stale(document_processor, sample_txt_file):
    """The stamp is taken before the read, so a mid-scan edit is not hidden"""
    original = document_processor._extract_text

    async def edit_then_extract(path):
        text = await original(path)
        _bump(sample_txt_file)
        return text

    document_processor._extract_text = edit_then_extract
    await document_processor.scan_and_vectorize()
    assert document_processor.check_freshness(force=True).modified == [str(sample_txt_file)]


@pytest.mark.asyncio
async def test_failed_scan_keeps_previous_snapshot(document_processor, test_docs_dir, sample_txt_file):
    await document_processor.scan_and_vectorize()
    before = document_processor.snapshot

    async def boom(path):
        return None

    document_processor._extract_text = boom
    with pytest.raises(RuntimeError):
        await document_processor.scan_and_vectorize()
    assert document_processor.snapshot is before


@pytest.mark.asyncio
async def test_unreadable_file_is_recorded_as_failed(document_processor, test_docs_dir, sample_txt_file):
    bad = test_docs_dir / "bad.txt"
    bad.write_text("x")
    original = document_processor._extract_text

    async def selective(path):
        return None if path == str(bad) else await original(path)

    document_processor._extract_text = selective
    await document_processor.scan_and_vectorize()
    assert document_processor.snapshot.failed == [str(bad)]
    # Unchanged since the scan: rescanning would not help, so it is not "stale".
    assert document_processor.check_freshness(force=True).is_current


@pytest.mark.asyncio
async def test_concurrent_scans_are_serialized(document_processor, sample_txt_file):
    running = 0
    peak = 0
    original = document_processor._extract_text

    async def tracked(path):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        try:
            return await original(path)
        finally:
            running -= 1

    document_processor._extract_text = tracked
    await asyncio.gather(
        document_processor.scan_and_vectorize(), document_processor.scan_and_vectorize()
    )
    assert peak == 1


def test_format_age():
    assert format_age(5) == "5s"
    assert format_age(125) == "2m"
    assert format_age(3 * 3600 + 5 * 60) == "3h 5m"
    assert format_age(2 * 86400 + 4 * 3600) == "2d 4h"
    assert format_age(-3) == "0s"


@pytest.mark.asyncio
async def test_model_note_covers_unscanned_current_and_stale(document_processor, sample_txt_file):
    assert describe_for_model(None, None) == ""
    await document_processor.scan_and_vectorize()
    snap = document_processor.snapshot
    assert "No source file has changed" in describe_for_model(
        snap, document_processor.check_freshness(force=True))
    _bump(sample_txt_file)
    note = describe_for_model(snap, document_processor.check_freshness(force=True))
    assert "1 changed since" in note and "rescan" in note
    # Counts only: no file names go into the prompt note.
    assert "test.txt" not in note


@pytest.mark.asyncio
async def test_channel_report_hides_names_unless_asked(
    document_processor, test_docs_dir, sample_txt_file
):
    await document_processor.scan_and_vectorize()
    _bump(sample_txt_file)
    fresh = document_processor.check_freshness(force=True)
    snap = document_processor.snapshot
    args = (document_processor.topic, snap, fresh, str(test_docs_dir))
    assert "test.txt" not in describe_for_channel(*args, show_names=False)
    named = describe_for_channel(*args, show_names=True)
    assert "`test.txt`" in named and "Modified" in named
    assert "No scan has completed" in describe_for_channel(
        "t", None, None, str(test_docs_dir), show_names=True)
