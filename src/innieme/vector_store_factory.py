from langchain.vectorstores.base import VectorStore
from langchain.embeddings.base import Embeddings
from langchain_chroma.vectorstores import Chroma
from langchain_community.vectorstores import FAISS

from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class VectorStoreFactory(ABC):
    """Abstract factory interface for creating vector stores"""
    @abstractmethod
    def create_empty_store(self, collection_name: str, embeddings: Embeddings) -> VectorStore:
        """Create an empty vector store"""
        pass

    @abstractmethod
    def create_from_texts(self, texts: List[str], embeddings: Embeddings, collection_name: str, metadatas: Optional[List[Dict]] = None) -> VectorStore:
        """Create a vector store from texts"""
        pass

class ChromaVectorStoreFactory(VectorStoreFactory):
    # Cosine is the right metric for text embeddings (OpenAI's are normalised),
    # and it is what keeps relevance scores in a usable 0..1 range. Chroma
    # defaults to squared L2, whose normalised scores can go negative and make
    # a score threshold meaningless.
    COLLECTION_METADATA = {"hnsw:space": "cosine"}

    def create_empty_store(self, collection_name: str, embeddings: Embeddings) -> VectorStore:
        return Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            collection_metadata=self.COLLECTION_METADATA,
        )

    def create_from_texts(self, texts: List[str], embeddings: Embeddings, collection_name: str, metadatas: Optional[List[Dict]] = None) -> VectorStore:
        return Chroma.from_texts(
            texts,
            embeddings,
            collection_name=collection_name,
            metadatas=metadatas,
            collection_metadata=self.COLLECTION_METADATA,
        )

class FAISSVectorStoreFactory(VectorStoreFactory):
    def create_empty_store(self, collection_name: str, embeddings: Embeddings) -> VectorStore:
        return FAISS.from_texts([], embeddings)

    def create_from_texts(self, texts: List[str], embeddings: Embeddings, collection_name: str, metadatas: Optional[List[Dict]] = None) -> VectorStore:
        return FAISS.from_texts(texts, embeddings, metadatas=metadatas)