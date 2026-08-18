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
