import os
import glob
import asyncio
import pypdf
import docx
import numpy as np
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import FakeEmbeddings  # Simple in-memory embedding
from langchain_core.embeddings import Embeddings  # Base class for embeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

class DocumentProcessor:
    def __init__(self, docs_dir, embedding_type="fake", embedding_config=None):
        """
        Initialize document processor with configurable embeddings
        
        Args:
            docs_dir (str): Directory containing documents to process
            embedding_type (str): Type of embedding to use ('fake', 'openai', etc.)
            embedding_config (dict, optional): Configuration for the embedding
        """
        self.docs_dir = docs_dir
        self.embedding_type = embedding_type
        self.embedding_config = embedding_config or {}
        self.embeddings = self._get_embeddings()
        self.vectorstore = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
    
    def _get_embeddings(self):
        """
        Factory method to get embeddings based on configuration
        
        Returns:
            Embeddings: An instance of embeddings
        """
        if self.embedding_type == "openai":
            # Only import if needed
            from langchain_openai import OpenAIEmbeddings
            api_key = self.embedding_config.get("api_key", os.getenv("OPENAI_API_KEY"))
            return OpenAIEmbeddings(openai_api_key=api_key)
        elif self.embedding_type == "fake":
            # Simple embedding for testing
            return FakeEmbeddings(size=1536)  # OpenAI compatible dimension
        else:
            raise ValueError(f"Unsupported embedding type: {self.embedding_type}")
        
    async def scan_and_vectorize(self):
        """Scan all documents in the specified directory and create vector embeddings"""
        document_texts = []
        
        # Get all files with common document extensions
        files = []
        for ext in ['*.pdf', '*.docx', '*.txt', '*.md']:
            files.extend(glob.glob(os.path.join(self.docs_dir, '**', ext), recursive=True))
        
        print(f"Found {len(files)} documents to process")
        # Process each file based on its type
        for file_path in files:
            print(f"Processing {file_path}")
            text = await self._extract_text(file_path)
            if text:
                document_texts.append({"text": text, "source": file_path})
            else:
                print(f"Text extraction failed for {file_path}")
        
        # Split texts into chunks
        all_chunks = []
        for doc in document_texts:
            chunks = self.text_splitter.split_text(doc["text"])
            all_chunks.extend([{"text": chunk, "source": doc["source"]} for chunk in chunks])
        
        # Create vector store
        texts = [chunk["text"] for chunk in all_chunks]
        
        if not texts:
            # Handle empty directory case by creating an empty FAISS index
            print("No texts found to vectorize, creating empty index")
            import faiss
            dimension = 1536  # Same as OpenAI embeddings dimension
            index = faiss.IndexFlatL2(dimension)
            
            # Create empty FAISS instance
            from langchain_community.vectorstores.faiss import FAISS as LangchainFAISS
            self.vectorstore = LangchainFAISS(
                embedding_function=self.embeddings,
                index=index,
                docstore={},
                index_to_docstore_id={}
            )
        else:
            metadatas = [{"source": chunk["source"]} for chunk in all_chunks]
            self.vectorstore = FAISS.from_texts(texts, self.embeddings, metadatas=metadatas)
        
        return True
    
    async def _extract_text(self, file_path):
        """Extract text from a document file based on its extension"""
        _, ext = os.path.splitext(file_path)
        
        try:
            if ext.lower() == '.pdf':
                return await self._extract_from_pdf(file_path)
            elif ext.lower() == '.docx':
                return await self._extract_from_docx(file_path)
            elif ext.lower() == '.txt' or ext.lower() == '.md':
                return await self._extract_from_txt(file_path)
            else:
                print(f"Unsupported file format: {file_path}")
                return None
        except Exception as e:
            print(f"Error extracting text from {file_path}: {str(e)}")
            return None
    
    async def _extract_from_pdf(self, file_path):
        """Extract text from a PDF file"""
        text = ""
        with open(file_path, 'rb') as file:
            reader = pypdf.PdfReader(file)
            for page_num in range(len(reader.pages)):
                page = reader.pages[page_num]
                text += page.extract_text() + "\n"
        return text
    
    async def _extract_from_docx(self, file_path):
        """Extract text from a DOCX file"""
        doc = docx.Document(file_path)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    
    async def _extract_from_txt(self, file_path):
        """Extract text from a TXT file"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            text = file.read()
        return text
    
    async def search_documents(self, query, top_k=5):
        """Search the vectorstore for relevant document chunks"""
        if not self.vectorstore:
            return []
        
        results = self.vectorstore.similarity_search(query, k=top_k)
        return results