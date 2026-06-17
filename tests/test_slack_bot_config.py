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