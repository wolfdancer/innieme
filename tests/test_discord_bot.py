from innieme.discord_bot_config import DiscordBotConfig, OutieConfig, TopicConfig, ChannelConfig
from innieme.discord_bot import DiscordBot

import os

os.environ['OPENAI_API_KEY'] = 'test_openai_key'

# Create test documents directory if it doesn't exist
test_docs_dir = 'data/test-documents'
os.makedirs(test_docs_dir, exist_ok=True)

bot_config = DiscordBotConfig(
    discord_token="test_token",
    openai_api_key="test_key",
    outies=[]
)
outie_config = OutieConfig(
    outie_id=123,
    topics=[],
    bot=bot_config
)
bot_config.outies.append(outie_config)
topic_config = TopicConfig(
    name="test_topic",
    role="test_role",
    docs_dir=test_docs_dir,
    channels=[],
    outie=outie_config
)
outie_config.topics.append(topic_config)
channel_config = ChannelConfig(guild_id=123456789, channel_id=987654321, topic=topic_config)
topic_config.channels.append(channel_config)

bot = DiscordBot(config=bot_config)

def test_bot_initialization():
    """Test that the bot and its components are initialized correctly"""
    # Check if bot is created with correct prefix
    assert bot.bot.command_prefix == '!'
    
    # Check if document processor is initialized
    assert bot._identify_topic(987654321) is not None


def test_bot_intents():
    """Test that the bot has the required intents"""
    assert bot.bot.intents.message_content is True
    assert bot.bot.intents.members is True