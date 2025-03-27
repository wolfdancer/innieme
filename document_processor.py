import os
import glob
import asyncio
import PyPDF2
import docx
import numpy as np
from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

class DocumentProcessor:
    def __init__(self, docs_dir):
        self.docs_dir = docs_dir
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        
    async def scan_and_vectorize(self):
        """Scan all documents in the specified directory and create vector embeddings"""
        document_texts = []
        
        # Get all files with common document extensions
        files = []
        for ext in ['*.pdf', '*.docx', '*.txt']:
            files.extend(glob.glob(os.path.join(self.docs_dir, '**', ext), recursive=True))
        
        # Process each file based on its type
        for file_path in files:
            text = await self._extract_text(file_path)
            if text:
                document_texts.append({"text": text, "source": file_path})
        
        # Split texts into chunks
        all_chunks = []
        for doc in document_texts:
            chunks = self.text_splitter.split_text(doc["text"])
            all_chunks.extend([{"text": chunk, "source": doc["source"]} for chunk in chunks])
        
        # Create vector store
        texts = [chunk["text"] for chunk in all_chunks]
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
            elif ext.lower() == '.txt':
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
            reader = PyPDF2.PdfReader(file)
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