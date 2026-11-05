import os

import numpy as np
import pytest
from langchain_core.embeddings import Embeddings

from innieme.document_processor import DocumentProcessor
from innieme.embeddings_factory import ExistingEmbeddingsFactory
from innieme.vector_store_factory import ChromaVectorStoreFactory

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
        ChromaVectorStoreFactory(),
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
async def test_independent_vectorstores_different_topics(
    test_docs_dir, test_docs_2_dir
):
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
        ChromaVectorStoreFactory(),
    )
    plants_processor = DocumentProcessor(
        "plants",
        str(test_docs_2_dir),
        ExistingEmbeddingsFactory(fake_embeddings2),
        ChromaVectorStoreFactory(),
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
    assert (
        plant_results[0].page_content == "This is a document about plants and gardens"
    )
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
        (strong, 0.82),
        (weak, 0.11),
    ]
    results = await document_processor.search_documents(
        "q", top_k=10, score_threshold=0.3
    )
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
    document_processor.vectorstore.similarity_search_with_relevance_scores.side_effect = ValueError(
        "no relevance fn for this metric"
    )
    document_processor.vectorstore.similarity_search.return_value = [doc]
    results = await document_processor.search_documents(
        "q", top_k=5, score_threshold=0.5
    )
    assert results == [doc]


class TestDocsExclude:
    """Scanning skips files that are instructions rather than content."""

    def _processor(self, tmp_path, exclude=None):
        from langchain_community.embeddings import FakeEmbeddings

        from innieme.document_processor import DocumentProcessor
        from innieme.embeddings_factory import ExistingEmbeddingsFactory
        from innieme.vector_store_factory import ChromaVectorStoreFactory

        return DocumentProcessor(
            "t",
            str(tmp_path),
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
        (tmp_path / "Northwind.md").write_text(
            "Northwind is at stage 3 of the pipeline."
        )
        (tmp_path / "CLAUDE.md").write_text(
            "Always invent a next action as a best guess."
        )
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
async def test_total_extraction_failure_keeps_the_previous_store(
    document_processor, test_docs_dir
):
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

    with patch.object(
        document_processor, "_extract_text", AsyncMock(return_value=None)
    ):
        with pytest.raises(RuntimeError, match="could not extract text"):
            await document_processor.scan_and_vectorize()

    assert document_processor.vectorstore is healthy_store


@pytest.mark.asyncio
async def test_partial_extraction_failure_still_rebuilds(
    document_processor, test_docs_dir
):
    """One bad file must not block the rest; the count is reported"""
    from unittest.mock import patch

    (test_docs_dir / "good.md").write_text("Vectorizable content about widgets.")
    (test_docs_dir / "bad.md").write_text("also content")

    real_extract = document_processor._extract_text

    async def fail_one(file_path):
        if file_path.endswith("bad.md"):
            return None
        return await real_extract(file_path)

    with patch.object(document_processor, "_extract_text", side_effect=fail_one):
        result = await document_processor.scan_and_vectorize()

    assert "1 out of 2 references" in result


@pytest.mark.asyncio
async def test_empty_files_are_not_treated_as_failures(
    document_processor, test_docs_dir
):
    """An empty file contributes nothing, but must not fail the whole scan"""
    (test_docs_dir / "empty.md").write_text("")
    (test_docs_dir / "blank.md").write_text("   \n\n")

    result = await document_processor.scan_and_vectorize()

    assert "no documents found to process" in result
    assert document_processor.vectorstore is not None


# --- Index snapshot, staleness, scan serialization ----------------------------

import asyncio
import threading
from unittest.mock import Mock

from innieme.index_status import FreshnessUnavailable


def _bump(path, seconds=10):
    """Move a file's mtime forward without depending on clock resolution."""
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 10**9))


async def _check(processor):
    """An explicit (uncached) check of the current snapshot."""
    return await processor.explicit_freshness()


@pytest.mark.asyncio
async def test_no_snapshot_before_first_scan(document_processor):
    assert document_processor.snapshot is None
    assert await document_processor.explicit_freshness() is None
    assert await document_processor.routine_freshness(None) is None


@pytest.mark.asyncio
async def test_scan_records_snapshot(document_processor, sample_txt_file):
    result = await document_processor.scan()
    snap = result.snapshot
    assert snap is document_processor.snapshot
    assert "chunks created" in result.message
    assert snap.indexed_count == 1 and snap.chunk_count >= 1
    assert str(sample_txt_file) in snap.files
    assert snap.failed == []
    assert snap.finished_at >= snap.started_at
    assert snap.extract_seconds >= 0 and snap.index_seconds >= 0


@pytest.mark.asyncio
async def test_scan_and_vectorize_still_returns_the_message(
    document_processor, sample_txt_file
):
    message = await document_processor.scan_and_vectorize()
    assert isinstance(message, str) and "chunks created" in message


@pytest.mark.asyncio
async def test_discovery_matches_extension_filter(document_processor, test_docs_dir):
    """One walk finds exactly the supported types, hidden entries skipped"""
    for name in ["a.md", "b.txt", "c.pdf", "d.docx", "e.csv", "F.MD", ".hidden.md"]:
        (test_docs_dir / name).write_text("x")
    (test_docs_dir / ".cache").mkdir()
    (test_docs_dir / ".cache" / "in_hidden_dir.md").write_text("x")
    (test_docs_dir / "sub").mkdir()
    (test_docs_dir / "sub" / "deep.md").write_text("x")
    files, _ = document_processor._discover_files()
    names = sorted(os.path.relpath(f, test_docs_dir) for f in files)
    assert names == ["a.md", "b.txt", "c.pdf", "d.docx", os.path.join("sub", "deep.md")]


@pytest.mark.asyncio
async def test_unstattable_file_is_recorded_as_failed(
    document_processor, test_docs_dir, sample_txt_file, monkeypatch
):
    from innieme import document_processor as dp_module

    bad = str(test_docs_dir / "flaky.txt")
    (test_docs_dir / "flaky.txt").write_text("x")
    real_of = dp_module.FileStamp.of
    monkeypatch.setattr(
        dp_module.FileStamp,
        "of",
        classmethod(lambda cls, p: None if p == bad else real_of(p)),
    )
    snap = (await document_processor.scan()).snapshot
    assert bad in snap.failed and bad not in snap.files


@pytest.mark.asyncio
async def test_freshness_detects_modified_added_removed(
    document_processor, test_docs_dir, sample_txt_file
):
    gone = test_docs_dir / "gone.txt"
    gone.write_text("soon deleted")
    await document_processor.scan()
    assert (await _check(document_processor)).is_current

    sample_txt_file.write_text("This is a changed test document, longer than before.")
    added = test_docs_dir / "new.md"
    added.write_text("brand new")
    gone.unlink()

    fresh = await _check(document_processor)
    assert fresh.modified == [str(sample_txt_file)]
    assert fresh.added == [str(added)]
    assert fresh.removed == [str(gone)]


@pytest.mark.asyncio
async def test_mtime_change_alone_is_detected(document_processor, sample_txt_file):
    await document_processor.scan()
    _bump(sample_txt_file)
    assert (await _check(document_processor)).modified == [str(sample_txt_file)]


@pytest.mark.asyncio
async def test_excluded_files_never_count(
    document_processor, test_docs_dir, sample_txt_file
):
    await document_processor.scan()
    (test_docs_dir / "CLAUDE.md").write_text("instructions")
    assert (await _check(document_processor)).is_current


@pytest.mark.asyncio
async def test_unchanged_failed_file_is_not_stale_but_repaired_one_is(
    document_processor, test_docs_dir, sample_txt_file
):
    bad = test_docs_dir / "bad.txt"
    bad.write_text("x")
    original = document_processor._extract_text

    async def selective(path):
        return None if path == str(bad) else await original(path)

    document_processor._extract_text = selective
    await document_processor.scan()
    assert document_processor.snapshot.failed == [str(bad)]
    assert (await _check(document_processor)).is_current  # rescanning would not help
    bad.write_text("repaired and longer")
    assert (await _check(document_processor)).modified == [str(bad)]


@pytest.mark.asyncio
async def test_empty_file_gaining_text_is_modified(
    document_processor, test_docs_dir, sample_txt_file
):
    empty = test_docs_dir / "empty.md"
    empty.write_text("")
    await document_processor.scan()
    empty.write_text("now it has content")
    assert (await _check(document_processor)).modified == [str(empty)]


@pytest.mark.asyncio
async def test_mid_scan_edit_reads_as_stale(document_processor, sample_txt_file):
    """The stamp is taken before the read, so an edit during the scan shows"""
    original = document_processor._extract_text

    async def edit_then_extract(path):
        text = await original(path)
        _bump(sample_txt_file)
        return text

    document_processor._extract_text = edit_then_extract
    await document_processor.scan()
    assert (await _check(document_processor)).modified == [str(sample_txt_file)]


@pytest.mark.asyncio
async def test_failed_scan_keeps_previous_snapshot_and_store(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    before_snapshot = document_processor.snapshot
    before_store = document_processor.vectorstore

    async def boom(path):
        return None

    document_processor._extract_text = boom
    with pytest.raises(RuntimeError):
        await document_processor.scan()
    assert document_processor.snapshot is before_snapshot
    assert document_processor.vectorstore is before_store


@pytest.mark.asyncio
async def test_all_empty_corpus_succeeds(document_processor, test_docs_dir):
    (test_docs_dir / "a.md").write_text("")
    (test_docs_dir / "b.md").write_text("   ")
    result = await document_processor.scan()
    assert result.snapshot.chunk_count == 0 and result.snapshot.failed == []


@pytest.mark.asyncio
async def test_mixed_empty_and_failed_corpus_fails_and_keeps_old_index(
    document_processor, test_docs_dir, sample_txt_file
):
    await document_processor.scan()
    before = document_processor.snapshot
    sample_txt_file.unlink()
    (test_docs_dir / "empty.md").write_text("")
    (test_docs_dir / "broken.txt").write_text("x")
    original = document_processor._extract_text

    async def selective(path):
        return None if path.endswith("broken.txt") else await original(path)

    document_processor._extract_text = selective
    with pytest.raises(RuntimeError):
        await document_processor.scan()
    assert document_processor.snapshot is before


@pytest.mark.asyncio
async def test_partial_failure_with_some_text_succeeds(
    document_processor, test_docs_dir, sample_txt_file
):
    (test_docs_dir / "broken.txt").write_text("x")
    original = document_processor._extract_text

    async def selective(path):
        return None if path.endswith("broken.txt") else await original(path)

    document_processor._extract_text = selective
    snap = (await document_processor.scan()).snapshot
    assert snap.failed == [str(test_docs_dir / "broken.txt")]
    assert snap.indexed_count == 1


@pytest.mark.asyncio
async def test_routine_check_is_cached_per_snapshot(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    snap = document_processor.snapshot
    assert (await document_processor.routine_freshness(snap)).is_current
    _bump(sample_txt_file)
    assert (await document_processor.routine_freshness(snap)).is_current  # cached
    document_processor.FRESHNESS_CACHE_SECONDS = 0
    assert not (await document_processor.routine_freshness(snap)).is_current


@pytest.mark.asyncio
async def test_explicit_check_ignores_cache(document_processor, sample_txt_file):
    await document_processor.scan()
    snap = document_processor.snapshot
    assert (await document_processor.routine_freshness(snap)).is_current
    _bump(sample_txt_file)
    assert not (await _check(document_processor)).is_current


@pytest.mark.asyncio
async def test_cache_never_crosses_snapshots(document_processor, sample_txt_file):
    await document_processor.scan()
    old = document_processor.snapshot
    await document_processor.routine_freshness(old)
    _bump(sample_txt_file)
    await document_processor.scan()  # new snapshot records the bumped stamp
    new = document_processor.snapshot
    assert (await document_processor.routine_freshness(new)).is_current
    # An answer still holding the old snapshot is judged against it, not the cache.
    document_processor.FRESHNESS_CACHE_SECONDS = 0
    stale = await document_processor.routine_freshness(old)
    assert stale.modified == [str(sample_txt_file)]
    assert stale.snapshot is old


def _blocking_compute(processor):
    """Make _compute_freshness block on a gate; returns (gate, calls)."""
    gate = threading.Event()
    calls = []
    real = processor._compute_freshness

    def blocked(snapshot):
        calls.append(snapshot)
        gate.wait(5)
        return real(snapshot)

    processor._compute_freshness = blocked
    return gate, calls


@pytest.mark.asyncio
async def test_stuck_routine_check_is_not_duplicated(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    snap = document_processor.snapshot
    document_processor.ROUTINE_CHECK_TIMEOUT = 0.05
    gate, calls = _blocking_compute(document_processor)
    try:
        assert await document_processor.routine_freshness(snap) is None  # timed out
        assert (
            await document_processor.routine_freshness(snap) is None
        )  # shares, no new thread
        assert len(calls) == 1
    finally:
        gate.set()
    await asyncio.sleep(0.2)
    # The late result filled the reuse window.
    document_processor.ROUTINE_CHECK_TIMEOUT = 5
    assert (await document_processor.routine_freshness(snap)).is_current
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_inflight_result_for_older_snapshot_is_not_taken(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    old = document_processor.snapshot
    document_processor.ROUTINE_CHECK_TIMEOUT = 0.05
    gate, calls = _blocking_compute(document_processor)
    try:
        assert await document_processor.routine_freshness(old) is None
        await document_processor.scan()
        new = document_processor.snapshot
        assert await document_processor.routine_freshness(new) is None
        assert calls == [old]  # the new caller neither shared nor piled on
    finally:
        gate.set()


@pytest.mark.asyncio
async def test_explicit_check_waits_for_inflight_then_reruns(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    snap = document_processor.snapshot
    document_processor.ROUTINE_CHECK_TIMEOUT = 0.05
    gate, calls = _blocking_compute(document_processor)
    assert (
        await document_processor.routine_freshness(snap) is None
    )  # in flight, pre-edit
    _bump(sample_txt_file)
    explicit = asyncio.ensure_future(document_processor.explicit_freshness())
    await asyncio.sleep(0.05)
    assert not explicit.done()  # waiting on the routine check
    gate.set()
    fresh = await explicit
    assert fresh.modified == [str(sample_txt_file)]
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_explicit_check_is_bounded_when_mount_hangs(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    document_processor.EXPLICIT_CHECK_TIMEOUT = 0.1
    gate, _ = _blocking_compute(document_processor)
    try:
        with pytest.raises(FreshnessUnavailable):
            await document_processor.explicit_freshness()
    finally:
        gate.set()


@pytest.mark.asyncio
async def test_explicit_check_error_is_unavailable(document_processor, sample_txt_file):
    await document_processor.scan()

    def boom(snapshot):
        raise OSError("notes volume unmounted")

    document_processor._compute_freshness = boom
    with pytest.raises(FreshnessUnavailable):
        await document_processor.explicit_freshness()


@pytest.mark.asyncio
async def test_routine_check_error_is_none(document_processor, sample_txt_file):
    await document_processor.scan()

    def boom(snapshot):
        raise OSError("notes volume unmounted")

    document_processor._compute_freshness = boom
    assert (
        await document_processor.routine_freshness(document_processor.snapshot) is None
    )


@pytest.mark.asyncio
async def test_search_with_snapshot_pairs_excerpts_with_their_index(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    docs, snap = await document_processor.search_with_snapshot("test document")
    assert docs and snap is document_processor.snapshot


@pytest.mark.asyncio
async def test_setting_vectorstore_keeps_the_snapshot(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    snap = document_processor.snapshot
    document_processor.vectorstore = Mock()
    assert document_processor.snapshot is snap


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
    a, b = await asyncio.gather(document_processor.scan(), document_processor.scan())
    assert peak == 1
    assert a.snapshot is not b.snapshot  # each reports its own scan


@pytest.mark.asyncio
async def test_overlapping_explicit_checks_share_one_worker_on_a_hung_mount(
    document_processor, sample_txt_file
):
    """Repeated status requests on a hung mount must not pile up threads"""
    await document_processor.scan()
    document_processor.EXPLICIT_CHECK_TIMEOUT = 0.05
    gate, calls = _blocking_compute(document_processor)
    try:
        for _ in range(3):
            with pytest.raises(FreshnessUnavailable):
                await document_processor.explicit_freshness()
        results = await asyncio.gather(
            document_processor.explicit_freshness(),
            document_processor.explicit_freshness(),
            return_exceptions=True,
        )
        assert all(isinstance(r, FreshnessUnavailable) for r in results)
        assert len(calls) == 1  # one stuck worker, however many requests
    finally:
        gate.set()
    await asyncio.sleep(0.2)
    document_processor.EXPLICIT_CHECK_TIMEOUT = 5
    assert (await document_processor.explicit_freshness()).is_current


@pytest.mark.asyncio
async def test_concurrent_explicit_checks_run_one_after_another(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    gate, calls = _blocking_compute(document_processor)
    first = asyncio.ensure_future(document_processor.explicit_freshness())
    second = asyncio.ensure_future(document_processor.explicit_freshness())
    await asyncio.sleep(0.05)
    assert len(calls) == 1  # the second waits for the first's worker
    gate.set()
    a, b = await asyncio.gather(first, second)
    assert a.is_current and b.is_current
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_routine_question_during_explicit_check_shares_it(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    snap = document_processor.snapshot
    gate, calls = _blocking_compute(document_processor)
    explicit = asyncio.ensure_future(document_processor.explicit_freshness())
    await asyncio.sleep(0.05)
    routine = asyncio.ensure_future(document_processor.routine_freshness(snap))
    await asyncio.sleep(0.05)
    gate.set()
    assert (await explicit).is_current and (await routine).is_current
    assert len(calls) == 1


def _restore(path, mode):
    os.chmod(path, mode)


@pytest.mark.asyncio
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
async def test_unreadable_directory_is_unknown_not_deleted(
    document_processor, test_docs_dir
):
    """glob skips a directory it cannot list; its files must not read as removed"""
    sub = test_docs_dir / "private"
    sub.mkdir()
    (sub / "note.md").write_text("indexed note")
    await document_processor.scan()
    os.chmod(sub, 0)
    try:
        assert (
            await document_processor.routine_freshness(document_processor.snapshot)
            is None
        )
        with pytest.raises(FreshnessUnavailable):
            await document_processor.explicit_freshness()
    finally:
        _restore(sub, 0o755)


@pytest.mark.asyncio
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
async def test_unstattable_candidate_is_unknown_not_current(
    document_processor, test_docs_dir
):
    """A listable directory whose entries cannot be stat'ed is not 'unchanged'"""
    sub = test_docs_dir / "locked"
    sub.mkdir()
    (sub / "note.md").write_text("indexed note")
    await document_processor.scan()
    os.chmod(sub, 0o644)  # readable listing, no search permission: stat fails
    try:
        with pytest.raises(FreshnessUnavailable):
            await document_processor.explicit_freshness()
    finally:
        _restore(sub, 0o755)


@pytest.mark.asyncio
async def test_file_deleted_between_walk_and_stat_is_removed(
    document_processor, test_docs_dir, sample_txt_file
):
    await document_processor.scan()
    real = document_processor._discover_files

    def walk_then_delete(*args, **kwargs):
        found = real(*args, **kwargs)
        sample_txt_file.unlink()
        return found

    document_processor._discover_files = walk_then_delete
    fresh = await document_processor.explicit_freshness()
    assert fresh.removed == [str(sample_txt_file)]


@pytest.mark.asyncio
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
async def test_unreadable_directory_of_only_new_files_is_unknown_not_current(
    document_processor, test_docs_dir, sample_txt_file
):
    """A directory the walk cannot list could hold new files: freshness is unknown"""
    await document_processor.scan()
    sub = test_docs_dir / "incoming"
    sub.mkdir()
    for i in range(3):
        (sub / f"new{i}.md").write_text("not yet indexed")
    os.chmod(sub, 0)
    try:
        assert (
            await document_processor.routine_freshness(document_processor.snapshot)
            is None
        )
        assert document_processor._freshness_cache is None  # nothing wrong was cached
        with pytest.raises(FreshnessUnavailable):
            await document_processor.explicit_freshness()
    finally:
        os.chmod(sub, 0o755)


@pytest.mark.asyncio
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
async def test_scan_skips_an_unreadable_directory(
    document_processor, test_docs_dir, sample_txt_file
):
    """The scan keeps the old glob's tolerance: index what can be read"""
    sub = test_docs_dir / "private"
    sub.mkdir()
    (sub / "note.md").write_text("x")
    os.chmod(sub, 0)
    try:
        snap = (await document_processor.scan()).snapshot
        assert snap.indexed_count == 1
    finally:
        os.chmod(sub, 0o755)


@pytest.mark.asyncio
async def test_symlink_loop_is_walked_once(
    document_processor, test_docs_dir, sample_txt_file
):
    (test_docs_dir / "loop").symlink_to(test_docs_dir, target_is_directory=True)
    files, _ = document_processor._discover_files(strict=True)
    assert files == [str(sample_txt_file)]


@pytest.mark.asyncio
async def test_excluded_symlink_alias_does_not_hide_its_target(test_docs_dir):
    """An excluded alias walked first must not stop the allowed target being indexed"""
    current = test_docs_dir / "current"
    current.mkdir()
    (current / "note.md").write_text("current note")
    (test_docs_dir / "archive").symlink_to(current, target_is_directory=True)
    processor = DocumentProcessor(
        "testing",
        str(test_docs_dir),
        ExistingEmbeddingsFactory(FakeEmbeddings()),
        ChromaVectorStoreFactory(),
        docs_exclude=["archive/*"],
    )
    files, excluded = processor._discover_files(strict=True)
    assert files == [str(current / "note.md")]
    assert excluded == [str(test_docs_dir / "archive" / "note.md")]
    snap = (await processor.scan()).snapshot
    assert snap.indexed_count == 1


@pytest.mark.asyncio
@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
async def test_unclassifiable_directory_symlink_is_unknown_not_skipped(
    document_processor, test_docs_dir, sample_txt_file, tmp_path
):
    """A symlink whose type cannot be determined must not be dropped as a file"""
    await document_processor.scan()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "new.md").write_text("not yet indexed")
    gate = test_docs_dir / "gate"
    gate.mkdir()
    (gate / "incoming").symlink_to(elsewhere, target_is_directory=True)
    os.chmod(gate, 0o644)  # listable, not searchable: is_dir() on the link fails
    try:
        with pytest.raises(OSError):
            document_processor._discover_files(strict=True)
        with pytest.raises(FreshnessUnavailable):
            await document_processor.explicit_freshness()
        files, _ = document_processor._discover_files()  # the scan stays lenient
        assert str(sample_txt_file) in files
    finally:
        os.chmod(gate, 0o755)


@pytest.mark.asyncio
async def test_sibling_symlink_cycle_is_pruned(
    document_processor, test_docs_dir, sample_txt_file
):
    a, b = test_docs_dir / "a", test_docs_dir / "b"
    a.mkdir()
    b.mkdir()
    (a / "in_a.md").write_text("a")
    (b / "in_b.md").write_text("b")
    (a / "to_b").symlink_to(b, target_is_directory=True)
    (b / "to_a").symlink_to(a, target_is_directory=True)
    files, _ = document_processor._discover_files(strict=True)  # terminates, no ELOOP
    names = sorted(os.path.relpath(f, test_docs_dir) for f in files)
    # Each alias reached through a different branch is still walked, as glob did.
    assert names == sorted(
        [
            "test.txt",
            os.path.join("a", "in_a.md"),
            os.path.join("a", "to_b", "in_b.md"),
            os.path.join("b", "in_b.md"),
            os.path.join("b", "to_a", "in_a.md"),
        ]
    )
    await document_processor.scan()
    assert (await document_processor.explicit_freshness()).is_current


@pytest.mark.asyncio
async def test_worker_timeout_error_is_not_mistaken_for_the_deadline(
    document_processor, sample_txt_file
):
    """A TimeoutError raised by a routine worker must not cancel status's own check"""
    await document_processor.scan()
    snap = document_processor.snapshot
    gate = threading.Event()
    calls = []
    real = document_processor._compute_freshness

    def first_times_out_then_works(snapshot):
        calls.append(snapshot)
        if len(calls) == 1:
            gate.wait(5)
            raise TimeoutError("NFS server not responding")
        return real(snapshot)

    document_processor._compute_freshness = first_times_out_then_works
    document_processor.ROUTINE_CHECK_TIMEOUT = 0.05
    assert await document_processor.routine_freshness(snap) is None  # in flight
    explicit = asyncio.ensure_future(document_processor.explicit_freshness())
    await asyncio.sleep(0.05)
    gate.set()
    fresh = await explicit
    assert fresh.is_current
    assert len(calls) == 2  # status ran its own check after the failed one


@pytest.mark.asyncio
async def test_repeated_status_timeouts_attach_nothing_to_the_stuck_worker(
    document_processor, sample_txt_file
):
    await document_processor.scan()
    document_processor.EXPLICIT_CHECK_TIMEOUT = 0.02
    gate, calls = _blocking_compute(document_processor)
    try:
        with pytest.raises(FreshnessUnavailable):
            await document_processor.explicit_freshness()
        worker = document_processor._inflight[1]
        baseline = len(worker._callbacks)
        for _ in range(5):
            with pytest.raises(FreshnessUnavailable):
                await document_processor.explicit_freshness()
        assert len(worker._callbacks) == baseline
        assert len(calls) == 1
    finally:
        gate.set()


@pytest.mark.asyncio
async def test_failed_worker_exceptions_are_always_retrieved(
    document_processor, sample_txt_file
):
    """No 'Future exception was never retrieved' when checks fail"""
    import gc

    await document_processor.scan()
    loop = asyncio.get_running_loop()
    reported = []
    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: reported.append(context))

    def boom(snapshot):
        raise OSError("notes volume unmounted")

    document_processor._compute_freshness = boom
    try:
        for _ in range(3):
            with pytest.raises(FreshnessUnavailable):
                await document_processor.explicit_freshness()
            assert (
                await document_processor.routine_freshness(document_processor.snapshot)
                is None
            )
        await asyncio.sleep(0)
        gc.collect()
        await asyncio.sleep(0)
    finally:
        loop.set_exception_handler(previous)
    assert not [c for c in reported if "never retrieved" in str(c.get("message", ""))]
