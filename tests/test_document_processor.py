import os
import pytest
import asyncio
from innieme.document_processor import DocumentProcessor

# Test data directory
TEST_DOCS_DIR = "test_documents"

@pytest.fixture
def test_docs_dir(tmp_path):
    """Create a temporary directory for test documents"""
    docs_dir = tmp_path / TEST_DOCS_DIR
    docs_dir.mkdir()
    return docs_dir

@pytest.fixture
def sample_txt_file(test_docs_dir):
    """Create a sample text file for testing"""
    file_path = test_docs_dir / "test.txt"
    file_path.write_text("This is a test document.\nIt has multiple lines.")
    return file_path

@pytest.fixture
def document_processor(test_docs_dir):
    """Create a DocumentProcessor instance for testing"""
    return DocumentProcessor(str(test_docs_dir))

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
    assert result == "no documents found to process"
    assert document_processor.vectorstore is not None

@pytest.mark.asyncio
async def test_search_documents_empty_vectorstore(document_processor):
    """Test searching with empty vectorstore"""
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