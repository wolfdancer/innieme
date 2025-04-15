from .embeddings_factory import EmbeddingsFactory, OpenAIEmbeddingsFactory, HuggingFaceEmbeddingsFactory, ExistingEmbeddingsFactory
from .vector_store_factory import ChromaVectorStoreFactory, FAISSVectorStoreFactory
from .document_processor import DocumentProcessor
from .knowledge_manager import KnowledgeManager
from .conversation_engine import ConversationEngine
from .discord_bot_config import OutieConfig, TopicConfig

from langchain_community.embeddings import FakeEmbeddings

import os

from dataclasses import dataclass
from typing import Dict
from functools import wraps

class Topic:
    def __init__(self, outie_config:OutieConfig, api_key:str, config: TopicConfig):
        self.config = config
        self.outie_config = outie_config
        # Initialize components
        self.document_processor = DocumentProcessor(
            self.config.name,
            config.docs_dir, 
            self._create_embeddings_from_config(
                {
                    "type":outie_config.bot.embedding_model, 
                    "api_key": outie_config.bot.openai_api_key,
                    "cache_dir": os.path.join(config.docs_dir, ".cache", "langchain")
                }
            ),
            ChromaVectorStoreFactory()
#            FAISSVectorStoreFactory()
        )
        self.knowledge_manager = KnowledgeManager()
        self.active_threads = set()
        self.conversation_engine = ConversationEngine(
            api_key,
            config,
            self.document_processor, 
            self.knowledge_manager
        )

    def _create_embeddings_from_config(self, config: Dict[str, str]) -> EmbeddingsFactory:
        embedding_type = config.get("type", "<empty>")
        if embedding_type == "openai":
            api_key = config['api_key']
            return OpenAIEmbeddingsFactory(api_key)
        elif embedding_type == "huggingface":
            return HuggingFaceEmbeddingsFactory(
                cache_dir=config['cache_dir'],
                model_name=config.get("model_name", "all-MiniLM-L6-v2")
            )
        elif embedding_type == "fake":
            return ExistingEmbeddingsFactory(FakeEmbeddings(size=1536))
        else:
            raise ValueError(f"Unsupported embedding type: {embedding_type}")

    def is_following_thread(self, thread_id:int) -> bool:
        return thread_id in self.active_threads
    
    async def process_query(self, thread_id: int, query: str, context_messages: list[dict[str, str]]) -> str:
        self.active_threads.add(thread_id)
        return await self.conversation_engine.process_query(query, context_messages)
    
    async def scan_and_vectorize(self) -> str:
        return await self.document_processor.scan_and_vectorize()
    
    async def generate_summary(self, thread_id) -> str:
        return await self.knowledge_manager.generate_summary(thread_id)
    
    async def store_summary(self, thread_id) -> bool:
        return await self.knowledge_manager.store_summary(thread_id)

class Innie:
    def __init__(self, api_key:str, outie_config: OutieConfig):
        """Initialize an Innie instance with configuration"""
        self.outie_config = outie_config
        self.topics = [Topic(outie_config, api_key, topic_config) for topic_config in outie_config.topics]
