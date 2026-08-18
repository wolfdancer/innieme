import pytest
import pytest_asyncio
import os

from pydantic_ai.models.test import TestModel

from innieme.conversation_engine import ConversationEngine
from innieme.discord_bot_config import DiscordBotConfig, OutieConfig, TopicConfig, ChannelConfig
from innieme.embeddings_factory import ExistingEmbeddingsFactory
from innieme.vector_store_factory import ChromaVectorStoreFactory
from innieme.document_processor import DocumentProcessor
from innieme.knowledge_manager import KnowledgeManager
from langchain_core.embeddings import Embeddings

os.environ.setdefault("OPENAI_API_KEY", "test_key")

TEST_DOCS_DIR = "data/test-documents"
os.makedirs(TEST_DOCS_DIR, exist_ok=True)


class FakeEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[0.0] * 3 for _ in texts]

    def embed_query(self, text):
        return [0.0] * 3


@pytest.fixture
def topic_config():
    bot_config = DiscordBotConfig(
        discord_token="test_token",
        embeddings_api_key="test_key",
        llm_api_key="test_key",
        embedding_model="fake",
        outies=[],
    )
    outie_config = OutieConfig(outie_id=123, topics=[], bot=bot_config)
    bot_config.outies.append(outie_config)
    config = TopicConfig(
        name="test_topic",
        role="You are a helpful assistant.",
        docs_dir=TEST_DOCS_DIR,
        channels=[],
        outie=outie_config,
    )
    outie_config.topics.append(config)
    return config


@pytest_asyncio.fixture
async def conversation_engine(topic_config, tmp_path):
    doc_processor = DocumentProcessor(
        "test_topic",
        TEST_DOCS_DIR,
        ExistingEmbeddingsFactory(FakeEmbeddings()),
        ChromaVectorStoreFactory(),
    )
    await doc_processor.scan_and_vectorize()
    km = KnowledgeManager(summaries_path=str(tmp_path / "summaries"))
    return ConversationEngine(
        topic=topic_config,
        document_processor=doc_processor,
        knowledge_manager=km,
    )


@pytest.mark.asyncio
async def test_generate_response_returns_string(conversation_engine):
    with conversation_engine.agent.override(model=TestModel()):
        response = await conversation_engine.process_query(
            query="What is the refund policy?",
            context_messages=[{"role": "user", "content": "What is the refund policy?"}],
        )
    assert isinstance(response, str)
    assert len(response) > 0


@pytest.mark.asyncio
async def test_outie_please_command(conversation_engine):
    response = await conversation_engine.process_query(
        query="outie please",
        context_messages=[{"role": "user", "content": "outie please"}],
    )
    assert "<@123>" in response
    assert "consultation" in response.lower()


@pytest.mark.asyncio
async def test_generate_response_with_history(conversation_engine):
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "Tell me more."},
    ]
    with conversation_engine.agent.override(model=TestModel()):
        response = await conversation_engine.process_query(
            query="Tell me more.",
            context_messages=history,
        )
    assert isinstance(response, str)


@pytest.mark.asyncio
async def test_context_messages_cannot_be_none(conversation_engine):
    with pytest.raises(AssertionError):
        await conversation_engine.process_query(query="hello", context_messages=None)

def test_format_chunk_includes_source_basename():
    """Retrieved chunks are labelled with the file they came from"""
    from innieme.conversation_engine import _format_chunk
    from unittest.mock import Mock
    doc = Mock(page_content="Northwind is at stage 3.",
               metadata={"source": "/Users/x/notes/Northwind.md"})
    out = _format_chunk(doc)
    assert "[source: Northwind.md]" in out
    assert "Northwind is at stage 3." in out
    assert "/Users/x/notes" not in out  # full path is not leaked to the model

def test_format_chunk_without_metadata_falls_back_to_content():
    """A chunk with no source metadata still renders its text"""
    from innieme.conversation_engine import _format_chunk
    from unittest.mock import Mock
    doc = Mock(page_content="Some text.", metadata=None)
    assert _format_chunk(doc) == "Some text."

def test_openai_embeddings_factory_defaults_to_3_small():
    """The OpenAI backend defaults to text-embedding-3-small, not ada-002"""
    from innieme.embeddings_factory import OpenAIEmbeddingsFactory
    assert OpenAIEmbeddingsFactory.DEFAULT_MODEL == "text-embedding-3-small"
    assert OpenAIEmbeddingsFactory("k").model_name == "text-embedding-3-small"

def test_openai_embeddings_factory_honours_override():
    """A configured model name wins over the default"""
    from innieme.embeddings_factory import OpenAIEmbeddingsFactory
    assert OpenAIEmbeddingsFactory("k", model_name="text-embedding-3-large").model_name == (
        "text-embedding-3-large"
    )
