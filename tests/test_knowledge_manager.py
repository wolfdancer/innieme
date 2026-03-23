import pytest
import os

from pydantic_ai.models.test import TestModel

from innieme.knowledge_manager import KnowledgeManager, SummaryOutput

os.environ.setdefault("OPENAI_API_KEY", "test_key")


@pytest.fixture
def knowledge_manager(tmp_path):
    return KnowledgeManager(summaries_path=str(tmp_path / "summaries"))


@pytest.mark.asyncio
async def test_generate_summary_returns_summary_output(knowledge_manager):
    with knowledge_manager.summary_agent.override(model=TestModel()):
        result = await knowledge_manager.generate_summary(
            thread_id=42,
            conversation_text="user: What is the return policy?\nassistant: Returns are accepted within 30 days.",
        )
    assert isinstance(result, SummaryOutput)
    assert isinstance(result.summary, str)
    assert isinstance(result.key_points, list)
    assert isinstance(result.suggested_title, str)


@pytest.mark.asyncio
async def test_generate_summary_stores_pending(knowledge_manager):
    with knowledge_manager.summary_agent.override(model=TestModel()):
        await knowledge_manager.generate_summary(
            thread_id=99,
            conversation_text="user: Hello\nassistant: Hi!",
        )
    assert 99 in knowledge_manager.pending_summaries
    assert "summary" in knowledge_manager.pending_summaries[99]
    assert "timestamp" in knowledge_manager.pending_summaries[99]


@pytest.mark.asyncio
async def test_store_summary_persists_to_disk(knowledge_manager, tmp_path):
    with knowledge_manager.summary_agent.override(model=TestModel()):
        await knowledge_manager.generate_summary(
            thread_id=7,
            conversation_text="user: Test\nassistant: OK",
        )
    result = await knowledge_manager.store_summary(7)
    assert result is True
    assert 7 not in knowledge_manager.pending_summaries
    json_files = list((tmp_path / "summaries").glob("*.json"))
    assert len(json_files) == 1


@pytest.mark.asyncio
async def test_store_summary_returns_false_for_missing_thread(knowledge_manager):
    result = await knowledge_manager.store_summary(thread_id=9999)
    assert result is False


@pytest.mark.asyncio
async def test_load_summaries(knowledge_manager, tmp_path):
    with knowledge_manager.summary_agent.override(model=TestModel()):
        await knowledge_manager.generate_summary(
            thread_id=1,
            conversation_text="Conversation one",
        )
        await knowledge_manager.generate_summary(
            thread_id=2,
            conversation_text="Conversation two",
        )
    await knowledge_manager.store_summary(1)
    await knowledge_manager.store_summary(2)

    summaries = await knowledge_manager.load_summaries()
    assert len(summaries) == 2
    for s in summaries:
        assert "summary" in s
        assert "timestamp" in s
