from pydantic import ValidationError
from innieme.slack_bot_config import OutieConfig, SlackBotConfig

import pytest

import os

def test_valid_outie_id():
    """Test that a valid outie_id is accepted"""
    # Create a bot config first
    bot = SlackBotConfig(
        slack_bot_token="xoxb-test-token",
        slack_app_token="xapp-test-token",
        embeddings_api_key="key",
        llm_api_key="key",
        embedding_model="huggingface",
        outies=[]
    )
    outie = OutieConfig(outie_id="U1234567890", topics=[], bot=bot)
    assert outie.outie_id == "U1234567890"

def test_invalid_outie_id():
    """Test that empty outie_id raises ValueError"""
    with pytest.raises(ValueError) as exc_info:
        OutieConfig(outie_id="", topics=[])
    
    assert "Outie ID cannot be empty" in str(exc_info.value)

def test_invalid_slack_bot_token():
    """Test that empty bot token raises ValueError"""
    with pytest.raises(ValueError) as exc_info:
        SlackBotConfig(
            slack_bot_token="",
            slack_app_token="xapp-test-token",
            embeddings_api_key="test_embeddings_key",
            llm_api_key="test_llm_key",
            embedding_model="huggingface",
            outies=[OutieConfig(outie_id="U1234567890", topics=[])]
        )
    assert "Slack bot token cannot be empty" in str(exc_info.value)

def test_invalid_slack_app_token():
    """Test that empty app token raises ValueError"""
    with pytest.raises(ValueError) as exc_info:
        SlackBotConfig(
            slack_bot_token="xoxb-test-token",
            slack_app_token="",
            embeddings_api_key="test_embeddings_key",
            llm_api_key="test_llm_key",
            embedding_model="huggingface",
            outies=[OutieConfig(outie_id="U1234567890", topics=[])]
        )
    assert "Slack app token cannot be empty" in str(exc_info.value)

def test_config_from_yaml():
    """Test creating config from multi-line YAML content"""
    math_docs_dir = 'data/math'
    scouting_docs_dir = 'data/scouting'
    innieme_docs_dir = 'data/innieme'
    for dir in [math_docs_dir, scouting_docs_dir, innieme_docs_dir]:
        os.makedirs(dir, exist_ok=True)

    yaml_content = f"""
    slack_bot_token: "xoxb-test-discord-token"
    slack_app_token: "xapp-test-app-token"
    embeddings_api_key: "test_embeddings_key"
    llm_api_key: "test_llm_key"
    embedding_model: "openai"
    outies:
      - outie_id: "U1234567890"
        topics:
          - name: "math"
            role: "Math Teacher"
            docs_dir: "{math_docs_dir}"
            channels:
            - channel_id: "C1234567890"
          - name: "scouting"
            role: "ASM"
            docs_dir: "{scouting_docs_dir}"
            channels:
            - channel_id: "C0987654321"
      - outie_id: "U0987654321"
        topics:
          - name: "innieme"
            role: "Support"
            docs_dir: "{innieme_docs_dir}"
            channels:
            - channel_id: "C5555555555"
    """
    
    config = SlackBotConfig.from_yaml(yaml_content)
    
    assert config.slack_bot_token == "xoxb-test-discord-token"
    assert config.slack_app_token == "xapp-test-app-token"
    assert config.embeddings_api_key == "test_embeddings_key"
    assert config.llm_api_key == "test_llm_key"
    assert len(config.outies) == 2
    
    # Verify first outie
    assert config.outies[0].outie_id == "U1234567890"
    assert config.outies[0].topics[0].name == "math"
    assert config.outies[0].topics[0].channels[0].channel_id == "C1234567890"
    
    # Verify second outie
    assert config.outies[1].outie_id == "U0987654321"
    assert config.outies[1].topics[0].name == "innieme"
    assert config.outies[1].topics[0].channels[0].channel_id == "C5555555555"

def test_invalid_embedding_model():
    """Test that unsupported embedding model raises ValueError"""
    with pytest.raises(ValueError) as exc_info:
        SlackBotConfig(
            slack_bot_token="xoxb-test-token",
            slack_app_token="xapp-test-token",
            embeddings_api_key="test_embeddings_key",
            llm_api_key="test_llm_key",
            embedding_model="unsupported_model",
            outies=[]
        )
    assert "Unsupported embedding model: unsupported_model" in str(exc_info.value)
def test_cache_dir_defaults_to_none():
    """cache_dir is optional so existing configs keep working"""
    config = SlackBotConfig(
        slack_bot_token="xoxb-test-token",
        slack_app_token="xapp-test-token",
        embeddings_api_key="test_embeddings_key",
        llm_api_key="test_llm_key",
        embedding_model="fake",
        outies=[]
    )
    assert config.cache_dir is None

def test_cache_dir_read_from_yaml():
    """cache_dir is parsed when present"""
    yaml_content = """
slack_bot_token: "xoxb-test-token"
slack_app_token: "xapp-test-token"
embeddings_api_key: "test_embeddings_key"
llm_api_key: "test_llm_key"
embedding_model: "fake"
cache_dir: "~/.config/innieme/cache"
outies: []
"""
    config = SlackBotConfig.from_yaml(yaml_content)
    assert config.cache_dir == "~/.config/innieme/cache"

def test_retrieval_top_k_defaults_to_five():
    """Existing configs keep the previous retrieval behaviour"""
    config = SlackBotConfig(
        slack_bot_token="xoxb-test-token",
        slack_app_token="xapp-test-token",
        embeddings_api_key="test_embeddings_key",
        llm_api_key="test_llm_key",
        embedding_model="fake",
        outies=[]
    )
    assert config.retrieval_top_k == 5

def test_retrieval_top_k_read_from_yaml():
    """retrieval_top_k is parsed when present"""
    yaml_content = """
slack_bot_token: "xoxb-test-token"
slack_app_token: "xapp-test-token"
embeddings_api_key: "test_embeddings_key"
llm_api_key: "test_llm_key"
embedding_model: "fake"
retrieval_top_k: 10
outies: []
"""
    config = SlackBotConfig.from_yaml(yaml_content)
    assert config.retrieval_top_k == 10

def test_docs_exclude_is_per_topic(tmp_path):
    """Each topic carries its own exclusions -- that's the point of per-topic"""
    leads = tmp_path / "leads"
    faq = tmp_path / "faq"
    leads.mkdir()
    faq.mkdir()
    yaml_content = f"""
slack_bot_token: "xoxb-test-token"
slack_app_token: "xapp-test-token"
embeddings_api_key: "k"
llm_api_key: "k"
embedding_model: "fake"
outies:
  - outie_id: "U1"
    topics:
      - name: "leads"
        role: "r"
        docs_dir: "{leads}"
        docs_exclude:
          - "CLAUDE.md"
        channels:
          - channel_id: "C1"
      - name: "faq"
        role: "r"
        docs_dir: "{faq}"
        docs_exclude: []
        channels:
          - channel_id: "C2"
"""
    config = SlackBotConfig.from_yaml(yaml_content)
    topics = config.outies[0].topics
    assert topics[0].docs_exclude == ["CLAUDE.md"]
    assert topics[1].docs_exclude == []   # explicitly scans everything

def test_docs_exclude_defaults_to_none_on_topic(tmp_path):
    """Unset means 'use DEFAULT_DOCS_EXCLUDE', which DocumentProcessor applies"""
    docs = tmp_path / "docs"
    docs.mkdir()
    yaml_content = f"""
slack_bot_token: "xoxb-test-token"
slack_app_token: "xapp-test-token"
embeddings_api_key: "k"
llm_api_key: "k"
embedding_model: "fake"
outies:
  - outie_id: "U1"
    topics:
      - name: "t"
        role: "r"
        docs_dir: "{docs}"
        channels:
          - channel_id: "C1"
"""
    config = SlackBotConfig.from_yaml(yaml_content)
    assert config.outies[0].topics[0].docs_exclude is None

def test_bot_level_docs_exclude_raises_rather_than_being_ignored(tmp_path):
    """A misplaced docs_exclude must fail loudly.

    Pydantic ignores unknown top-level keys by default, so without an explicit
    guard this config would load fine and silently ingest the file it names.
    """
    docs = tmp_path / "docs"
    docs.mkdir()
    yaml_content = f"""
slack_bot_token: "xoxb-test-token"
slack_app_token: "xapp-test-token"
embeddings_api_key: "k"
llm_api_key: "k"
embedding_model: "fake"
docs_exclude:
  - "CLAUDE.md"
outies:
  - outie_id: "U1"
    topics:
      - name: "t"
        role: "r"
        docs_dir: "{docs}"
        channels:
          - channel_id: "C1"
"""
    with pytest.raises(ValidationError) as exc_info:
        SlackBotConfig.from_yaml(yaml_content)
    assert "per-topic setting" in str(exc_info.value)

def test_retrieval_top_k_must_be_positive():
    """k <= 0 reaches the vector store and fails at query time, not startup"""
    for bad in (0, -1):
        with pytest.raises(ValidationError):
            SlackBotConfig(
                slack_bot_token="xoxb-t", slack_app_token="xapp-t",
                embeddings_api_key="k", llm_api_key="k",
                embedding_model="fake", retrieval_top_k=bad, outies=[])

def test_retrieval_score_threshold_must_be_a_fraction():
    """Out of range or NaN silently drops every chunk"""
    for bad in (1.5, -0.1, float("nan")):
        with pytest.raises(ValidationError):
            SlackBotConfig(
                slack_bot_token="xoxb-t", slack_app_token="xapp-t",
                embeddings_api_key="k", llm_api_key="k",
                embedding_model="fake", retrieval_score_threshold=bad, outies=[])

def test_valid_retrieval_bounds_are_accepted():
    """The edges of the documented range stay legal"""
    for good in (0.0, 0.5, 1.0):
        c = SlackBotConfig(
            slack_bot_token="xoxb-t", slack_app_token="xapp-t",
            embeddings_api_key="k", llm_api_key="k",
            embedding_model="fake", retrieval_score_threshold=good, outies=[])
        assert c.retrieval_score_threshold == good
