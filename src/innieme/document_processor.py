import os
import glob
from typing import List
import pypdf
import docx
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores.faiss import FAISS as LangchainFAISS
from langchain_community.embeddings import FakeEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
import faiss


class DocumentProcessor:
    def __init__(self, docs_dir, embedding_config={}):
        self.docs_dir = docs_dir
        self.embedding_config = embedding_config
        self.embeddings = self._get_embeddings()
        self.vectorstore = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
    
    def _get_embeddings(self):
        embedding_type = self.embedding_config.get("type", "fake")
        if embedding_type == "openai":
            # Only import if needed
            from langchain_openai import OpenAIEmbeddings
            api_key = self.embedding_config["api_key"]
            return OpenAIEmbeddings(api_key=api_key)
        elif embedding_type == "huggingface":
            # Only import if needed
            from langchain_huggingface import HuggingFaceEmbeddings
            model_name = self.embedding_config.get("model_name", "all-MiniLM-L6-v2")
            return HuggingFaceEmbeddings(
                model_name=model_name,
                cache_folder=os.path.join(self.docs_dir, ".cache", "langchain"),
            )
        elif embedding_type == "fake":
            # Simple embedding for testing
            return FakeEmbeddings(size=1536)  # OpenAI compatible dimension
        else:
            raise ValueError(f"Unsupported embedding type: {embedding_type}")

    def _create_empty_store(self):
        """Handle the case where no texts are found to vectorize by creating an empty FAISS index"""
        dimension = 1536  # Same as OpenAI embeddings dimension
        # Create empty FAISS instance
        return LangchainFAISS(
            embedding_function=self.embeddings,
            index=faiss.IndexFlatL2(dimension),
            docstore=InMemoryDocstore({}),
            index_to_docstore_id={}
        )

    async def scan_and_vectorize(self, topic_name:str) -> str:
        """Scan all documents in the specified directory and create vector embeddings"""
        document_texts = []
        
        # Get all files with common document extensions
        files = []
        for ext in ['*.pdf', '*.docx', '*.txt', '*.md']:
            files.extend(glob.glob(os.path.join(self.docs_dir, '**', ext), recursive=True))
        
        print(f"For {topic_name}: Found {len(files)} documents to process under {self.docs_dir}...")
        # Process each file based on its type
        count = 0
        for file_path in files:
            print(f"  - {file_path}")
            text = await self._extract_text(file_path)
            if text:
                document_texts.append({"text": text, "source": file_path})
                count += 1
            else:
                print(f"    Text extraction failed for {file_path}")
        print(f"Done. Extracted text from {count} documents")

        # Split texts into chunks
        all_chunks = []
        for doc in document_texts:
            chunks = self.text_splitter.split_text(doc["text"])
            all_chunks.extend([{"text": chunk, "source": doc["source"]} for chunk in chunks])
        
        # Create vector store
        texts = [chunk["text"] for chunk in all_chunks]
        
        response = ""
        if not texts:
            self.vectorstore = self._create_empty_store()
            response = f"On topic '{topic_name}': no documents found to process"
        else:
            metadatas = [{"source": chunk["source"]} for chunk in all_chunks]
            self.vectorstore = FAISS.from_texts(texts, self.embeddings, metadatas=metadatas)
            response = f"On topic '{topic_name}': {len(all_chunks)} chunks created from {count} out of {len(files)} references"
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
    
    async def search_documents(self, query, top_k=5) -> List:
        """Search the vectorstore for relevant document chunks"""
        if not self.vectorstore:
            return []
        
        results = self.vectorstore.similarity_search(query, k=top_k)
        return results