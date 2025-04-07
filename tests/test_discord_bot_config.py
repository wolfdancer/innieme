from innieme.discord_bot_config import OutieConfig, DiscordBotConfig

import pytest

import os

def test_valid_outie_id():
    """Test that a positive outie_id is accepted"""
    # Create a bot config first
    bot = DiscordBotConfig(discord_token="test_token", openai_api_key="key", embedding_model="huggingface", outies=[])  # Add minimal bot config
    outie = OutieConfig(outie_id=1, topics=[], bot=bot)  # Add bot reference
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
            openai_api_key="test_openai_key",
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
    openai_api_key: "test_openai_key"
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
    assert config.openai_api_key == "test_openai_key"
    assert len(config.outies) == 2
    
    # Verify first outie
    assert config.outies[0].outie_id == 1
    assert config.outies[0].topics[0].name == "math"
    
    # Verify second outie
    assert config.outies[1].outie_id == 2
    assert config.outies[1].topics[0].name == "innieme"

