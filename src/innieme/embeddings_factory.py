from abc import ABC, abstractmethod
from pydantic import SecretStr
from langchain.embeddings.base import Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings

class EmbeddingsFactory(ABC):
    """Abstract factory interface for creating embeddings"""
    @abstractmethod
    def create_embeddings(self) -> Embeddings:
        """Create and return an embeddings instance"""
        pass

class OpenAIEmbeddingsFactory(EmbeddingsFactory):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def create_embeddings(self) -> Embeddings:
        return OpenAIEmbeddings(api_key=SecretStr(self.api_key))

class HuggingFaceEmbeddingsFactory(EmbeddingsFactory):
    def __init__(self, cache_dir: str, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.cache_dir = cache_dir

    def create_embeddings(self) -> Embeddings:
        return HuggingFaceEmbeddings(
            model_name=self.model_name,
            cache_folder=self.cache_dir
        )

class ExistingEmbeddingsFactory(EmbeddingsFactory):
    def __init__(self, embeddings: Embeddings):
        self.embeddings = embeddings

    def create_embeddings(self) -> Embeddings:
        return self.embeddings