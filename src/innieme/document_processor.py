from .embeddings_factory import EmbeddingsFactory
from .vector_store_factory import VectorStoreFactory

from langchain.text_splitter import RecursiveCharacterTextSplitter

import pypdf
import docx
import glob
from pydantic import SecretStr

from typing import List, Dict, Optional, Union
from langchain.embeddings.base import Embeddings

import logging
import os
import time

logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(self, 
                 topic: str, 
                 docs_dir: str,
                 embeddings_factory: EmbeddingsFactory,
                 vector_store_factory: VectorStoreFactory):
        self.docs_dir = docs_dir
        self.topic = topic
        self.embeddings_factory = embeddings_factory
        self.vector_store_factory = vector_store_factory
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

    def _create_empty_store(self):
        """Handle the case where no texts are found to vectorize"""
        collection_name = self._get_collection_name()
        return self.vector_store_factory.create_empty_store(
            collection_name=collection_name,
            embeddings=self.embeddings_factory.create_embeddings()
        )

    def _get_collection_name(self) -> str:
        """Create a unique collection name using topic and timestamp"""
        # Clean topic name to be filesystem safe
        safe_topic = "".join(c if c.isalnum() else "_" for c in self.topic)
        timestamp = int(time.time() * 1000)  # Milliseconds since epoch
        return f"{safe_topic}_{timestamp}"

    async def scan_and_vectorize(self) -> str:
        """Scan all documents in the specified directory and create vector embeddings"""
        document_texts = []
        
        # Get all files with common document extensions
        files = []
        for ext in ['*.pdf', '*.docx', '*.txt', '*.md']:
            files.extend(glob.glob(os.path.join(self.docs_dir, '**', ext), recursive=True))
        
        logger.info(f"For {self.topic}: Found {len(files)} documents to process under {self.docs_dir}...")
        # Process each file based on its type
        count = 0
        for file_path in files:
            logger.info(f"  - {file_path}")
            text = await self._extract_text(file_path)
            if text:
                document_texts.append({"text": text, "source": file_path})
                count += 1
            else:
                logger.error(f"    Text extraction failed for {file_path}")
        logger.info(f"Done. Extracted text from {count} documents")

        # Split texts into chunks
        all_chunks = []
        for doc in document_texts:
            chunks = self.text_splitter.split_text(doc["text"])
            all_chunks.extend([{"text": chunk, "source": doc["source"]} for chunk in chunks])
        
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
                metadatas=metadatas
            )
            response = f"On topic '{self.topic}': {len(all_chunks)} chunks created from {count} out of {len(files)} references"
        return response
    
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
                logger.warning(f"Unsupported file format: {file_path}")
                return None
        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {str(e)}")
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
    
    async def search_documents(self, query, top_k=5) -> List:
        """Search the vectorstore for relevant document chunks"""
        if not self.vectorstore:
            return []
        
        results = self.vectorstore.similarity_search(query, k=top_k)
        return results