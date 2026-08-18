from innieme.discord_bot_config import (
    OutieConfig, DiscordBotConfig, TopicConfig, ChannelConfig,
)
from pydantic import ValidationError

import pytest

import os

def test_valid_outie_id():
    """Test that a positive outie_id is accepted"""
    bot = DiscordBotConfig(discord_token="test_token", embeddings_api_key="key", llm_api_key="key", embedding_model="huggingface", outies=[])
    outie = OutieConfig(outie_id=1, topics=[], bot=bot)
    assert outie.outie_id == 1

@pytest.mark.parametrize("invalid_id,expected_message", [
    (0, "ID value must be positive, got: 0"),
    (-1, "ID value must be positive, got: -1"),
    (-100, "ID value must be positive, got: -100")
])

def test_invalid_outie_id(invalid_id, expected_message):
    """Test that non-positive outie_ids raise ValueError with correct message"""
    with pytest.raises(ValueError) as exc_info:
        OutieConfig(outie_id=invalid_id, topics=[])

    assert expected_message in str(exc_info.value)

def test_invalid_discord_token():
    with pytest.raises(ValueError) as exc_info:
        DiscordBotConfig(
            embeddings_api_key="test_key",
            llm_api_key="test_key",
            embedding_model="huggingface",
            outies=[OutieConfig(outie_id=1, topics=[])]
        )
    assert "discord_token" in str(exc_info.value)

def test_config_from_yaml():
    math_docs_dir = 'data/math'
    scouting_docs_dir = 'data/scouting'
    innieme_docs_dir = 'data/innieme'
    for dir in [math_docs_dir, scouting_docs_dir, innieme_docs_dir]:
        os.makedirs(dir, exist_ok=True)

    """Test creating config from multi-line YAML content"""
    yaml_content = f"""
    discord_token: "test_discord_token"
    embeddings_api_key: "test_embeddings_key"
    llm_api_key: "test_llm_key"
    embedding_model: "openai"
    outies:
      - outie_id: 1
        topics:
          - name: "math"
            role: "Math Teacher"
            docs_dir: "{math_docs_dir}"
            channels:
            - guild_id: "11111111"
              channel_id: "22222222"
          - name: "scouting"
            role: "ASM"
            docs_dir: "{scouting_docs_dir}"
            channels:
            - guild_id: "33333333"
              channel_id: "44444444"
      - outie_id: 2
        topics:
          - name: "innieme"
            role: "Support"
            docs_dir: "{innieme_docs_dir}"
            channels:
            - guild_id: "55555555"
              channel_id: "66666666"
    """

    config = DiscordBotConfig.from_yaml(yaml_content)

    assert config.discord_token == "test_discord_token"
    assert config.embeddings_api_key == "test_embeddings_key"
    assert config.llm_api_key == "test_llm_key"
    assert len(config.outies) == 2

    # Verify first outie
    assert config.outies[0].outie_id == 1
    assert config.outies[0].topics[0].name == "math"

    # Verify second outie
    assert config.outies[1].outie_id == 2
    assert config.outies[1].topics[0].name == "innieme"


class TestDiscordRetrievalAndExclusionConfig:
    """Mirrors the Slack config tests so the two platforms cannot drift."""

    def _base(self, **overrides):
        base = dict(
            discord_token="t",
            embeddings_api_key="k",
            llm_api_key="k",
            embedding_model="fake",
            outies=[],
        )
        base.update(overrides)
        return base

    def test_defaults(self):
        c = DiscordBotConfig(**self._base())
        assert c.retrieval_top_k == 5
        assert c.retrieval_score_threshold is None
        assert c.embeddings_model_name is None
        assert c.cache_dir is None

    def test_retrieval_top_k_must_be_positive(self):
        for bad in (0, -1):
            with pytest.raises(ValidationError):
                DiscordBotConfig(**self._base(retrieval_top_k=bad))

    def test_retrieval_score_threshold_must_be_a_fraction(self):
        for bad in (1.5, -0.1, float("nan")):
            with pytest.raises(ValidationError):
                DiscordBotConfig(**self._base(retrieval_score_threshold=bad))

    def test_valid_retrieval_bounds_are_accepted(self):
        for good in (0.0, 0.5, 1.0):
            c = DiscordBotConfig(**self._base(retrieval_score_threshold=good))
            assert c.retrieval_score_threshold == good

    def test_bot_level_docs_exclude_raises_rather_than_being_ignored(self):
        """Misplacing it must fail loudly, not parse and silently do nothing"""
        with pytest.raises(ValidationError) as exc_info:
            DiscordBotConfig(**self._base(docs_exclude=["CLAUDE.md"]))
        assert "per-topic setting" in str(exc_info.value)

    def test_docs_exclude_is_per_topic(self, tmp_path):
        docs = tmp_path / "docs"
        docs.mkdir()
        topic = TopicConfig(
            name="t", role="r", docs_dir=str(docs),
            docs_exclude=["CLAUDE.md"],
            channels=[ChannelConfig(guild_id=1, channel_id=2)],
        )
        assert topic.docs_exclude == ["CLAUDE.md"]
        assert TopicConfig(
            name="t2", role="r", docs_dir=str(docs),
            channels=[ChannelConfig(guild_id=1, channel_id=3)],
        ).docs_exclude is None
