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