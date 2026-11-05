import os

import pytest
import pytest_asyncio
from langchain_core.embeddings import Embeddings
from pydantic_ai.models.test import TestModel

from innieme.conversation_engine import ConversationEngine
from innieme.discord_bot_config import (
    ChannelConfig,
    DiscordBotConfig,
    OutieConfig,
    TopicConfig,
)
from innieme.document_processor import DocumentProcessor
from innieme.embeddings_factory import ExistingEmbeddingsFactory
from innieme.knowledge_manager import KnowledgeManager
from innieme.vector_store_factory import ChromaVectorStoreFactory

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
            context_messages=[
                {"role": "user", "content": "What is the refund policy?"}
            ],
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
    from unittest.mock import Mock

    from innieme.conversation_engine import _format_chunk

    doc = Mock(
        page_content="Northwind is at stage 3.",
        metadata={"source": "/Users/x/notes/Northwind.md"},
    )
    out = _format_chunk(doc)
    assert "[source: Northwind.md]" in out
    assert "Northwind is at stage 3." in out
    assert "/Users/x/notes" not in out  # full path is not leaked to the model


def test_format_chunk_without_metadata_falls_back_to_content():
    """A chunk with no source metadata still renders its text"""
    from unittest.mock import Mock

    from innieme.conversation_engine import _format_chunk

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

    assert OpenAIEmbeddingsFactory(
        "k", model_name="text-embedding-3-large"
    ).model_name == ("text-embedding-3-large")


@pytest.mark.asyncio
async def test_engine_passes_retrieval_settings_through():
    """Configured retrieval settings must actually reach retrieval"""
    from unittest.mock import AsyncMock, Mock, patch

    from innieme.conversation_engine import ConversationEngine

    topic = Mock()
    topic.outie.outie_id = "U1"
    topic.outie.bot.retrieval_top_k = 12
    topic.outie.bot.retrieval_score_threshold = 0.42
    topic.role = "r"

    processor = Mock()
    processor.search_with_snapshot = AsyncMock(return_value=([], None))
    processor.routine_freshness = AsyncMock(return_value=None)

    with patch("innieme.conversation_engine.Agent"):
        engine = ConversationEngine(topic, processor, Mock())
    engine._generate_response = AsyncMock(return_value="ok")

    await engine.process_query("q", context_messages=[{"role": "user", "content": "q"}])

    processor.search_with_snapshot.assert_awaited_once_with(
        "q", top_k=12, score_threshold=0.42
    )


@pytest.mark.asyncio
async def test_engine_falls_back_to_defaults_for_older_configs():
    """A config predating these fields still works"""
    from unittest.mock import AsyncMock, Mock, patch

    from innieme.conversation_engine import ConversationEngine

    class Bare:
        pass

    topic = Mock()
    topic.outie.outie_id = "U1"
    topic.outie.bot = Bare()  # no retrieval attributes at all
    topic.role = "r"

    processor = Mock()
    processor.search_with_snapshot = AsyncMock(return_value=([], None))
    processor.routine_freshness = AsyncMock(return_value=None)

    with patch("innieme.conversation_engine.Agent"):
        engine = ConversationEngine(topic, processor, Mock())
    engine._generate_response = AsyncMock(return_value="ok")

    await engine.process_query("q", context_messages=[{"role": "user", "content": "q"}])

    processor.search_with_snapshot.assert_awaited_once_with(
        "q", top_k=5, score_threshold=None
    )


# --- Index freshness in the model's context ----------------------------------

from unittest.mock import Mock

from pydantic_ai import capture_run_messages

from innieme.conversation_engine import (
    ConversationDependencies,
    _build_system_prompt,
    _format_chunk,
)
from innieme.index_status import IndexFreshness, IndexSnapshot


def _snap():
    return IndexSnapshot(
        started_at=0,
        finished_at=0,
        extract_seconds=1,
        index_seconds=1,
        files={},
        failed=[],
        indexed_count=1,
        chunk_count=1,
    )


def test_format_chunk_labels_modified_and_deleted_sources():
    snap = _snap()
    fresh = IndexFreshness(0, snap, modified=["/n/Northwind.md"], removed=["/n/Old.md"])
    modified = Mock(page_content="Stage 3.", metadata={"source": "/n/Northwind.md"})
    deleted = Mock(page_content="Stage 1.", metadata={"source": "/n/Old.md"})
    unchanged = Mock(page_content="Stage 2.", metadata={"source": "/n/Other.md"})
    bare = Mock(page_content="No source.", metadata=None)
    assert "[source: Northwind.md, changed since it was indexed]" in _format_chunk(
        modified, fresh
    )
    assert "[source: Old.md, no longer exists]" in _format_chunk(deleted, fresh)
    assert "[source: Other.md]" in _format_chunk(unchanged, fresh)
    assert _format_chunk(bare, fresh) == "No source."
    # Without freshness information the label is the plain one.
    assert "[source: Northwind.md]" in _format_chunk(modified)


def test_system_prompt_carries_index_note_only_when_set():
    with_note = ConversationDependencies("ctx", [], "role", index_note="Index built X.")
    assert "Index built X." in _build_system_prompt(Mock(deps=with_note))
    without = ConversationDependencies("ctx", [], "role")
    assert "Index built" not in _build_system_prompt(Mock(deps=without))


def _instructions(messages):
    return "\n".join(getattr(m, "instructions", None) or "" for m in messages)


async def _ask(engine, query="Tell me about the refund policy."):
    with capture_run_messages() as messages:
        with engine.agent.override(model=TestModel()):
            await engine.process_query(query, [{"role": "user", "content": query}])
    return _instructions(messages)


@pytest.mark.asyncio
async def test_answer_context_includes_note_and_labels_after_an_edit(
    topic_config, tmp_path
):
    """A Discord-configured topic (the fixture's config) gets the shared behavior"""
    docs = tmp_path / "docs"
    docs.mkdir()
    note = docs / "refunds.md"
    note.write_text("The refund policy allows returns within 30 days.")
    processor = DocumentProcessor(
        "t",
        str(docs),
        ExistingEmbeddingsFactory(FakeEmbeddings()),
        ChromaVectorStoreFactory(),
    )
    await processor.scan()
    engine = ConversationEngine(
        topic_config, processor, KnowledgeManager(summaries_path=str(tmp_path / "s"))
    )

    context = await _ask(engine)
    assert "No source file has changed" in context
    assert "[source: refunds.md]" in context

    st = os.stat(note)
    os.utime(note, ns=(st.st_atime_ns, st.st_mtime_ns + 10 * 10**9))
    processor.FRESHNESS_CACHE_SECONDS = 0
    context = await _ask(engine)
    assert "1 file changed since" in context
    assert "[source: refunds.md, changed since it was indexed]" in context


@pytest.mark.asyncio
async def test_freshness_check_failure_still_answers(conversation_engine):
    def boom(snapshot):
        raise OSError("notes volume unmounted")

    conversation_engine.document_processor._compute_freshness = boom
    conversation_engine.document_processor.FRESHNESS_CACHE_SECONDS = 0
    context = await _ask(conversation_engine)
    assert "last built" not in context  # no note, but an answer


@pytest.mark.asyncio
async def test_freshness_check_that_never_completes_still_answers(conversation_engine):
    import asyncio
    import threading

    gate = threading.Event()
    processor = conversation_engine.document_processor

    def hang(snapshot):
        gate.wait(5)
        raise OSError("gave up")

    processor._compute_freshness = hang
    processor.FRESHNESS_CACHE_SECONDS = 0
    processor.ROUTINE_CHECK_TIMEOUT = 0.05
    try:
        # Bounded well below the worker's 5 s hang: only the 0.05 s timeout
        # lets the answer finish in time.
        context = await asyncio.wait_for(_ask(conversation_engine), 2)
        assert "last built" not in context
        assert not gate.is_set()  # answered while the check was still stuck
    finally:
        gate.set()


@pytest.mark.asyncio
async def test_rescan_between_retrieval_and_freshness_uses_retrieved_snapshot(
    topic_config, tmp_path
):
    docs = tmp_path / "docs"
    docs.mkdir()
    note = docs / "refunds.md"
    note.write_text("The refund policy allows returns within 30 days.")
    processor = DocumentProcessor(
        "t",
        str(docs),
        ExistingEmbeddingsFactory(FakeEmbeddings()),
        ChromaVectorStoreFactory(),
    )
    await processor.scan()
    processor.FRESHNESS_CACHE_SECONDS = 0
    engine = ConversationEngine(
        topic_config, processor, KnowledgeManager(summaries_path=str(tmp_path / "s"))
    )

    real_search = processor.search_with_snapshot

    async def search_then_rescan(*args, **kwargs):
        result = await real_search(*args, **kwargs)  # excerpts from index A
        st = os.stat(note)
        os.utime(note, ns=(st.st_atime_ns, st.st_mtime_ns + 10 * 10**9))
        await processor.scan()  # index B records the edit
        return result

    processor.search_with_snapshot = search_then_rescan
    context = await _ask(engine)
    # Judged against A, the excerpt's own index: the edit still shows.
    assert "[source: refunds.md, changed since it was indexed]" in context
