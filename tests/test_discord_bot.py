import pytest
import os
import sys

from innieme.discord_bot_config import DiscordBotConfig
from innieme.discord_bot import DiscordBot

os.environ['OPENAI_API_KEY'] = 'test_openai_key'

# Create test documents directory if it doesn't exist
test_docs_dir = 'data/test-documents'
os.makedirs(test_docs_dir, exist_ok=True)

config = DiscordBotConfig(
    discord_token='test_token',
    outie_id=123456789,
    guild_id=987654321,
    channel_id=456789123,
    docs_dir=test_docs_dir
)

bot = DiscordBot(config=config)

def test_bot_initialization():
    """Test that the bot and its components are initialized correctly"""
    # Check if bot is created with correct prefix
    assert bot.bot.command_prefix == '!'
    
    # Check if document processor is initialized
    assert bot.document_processor is not None
    assert bot.document_processor.docs_dir.endswith(test_docs_dir)
    
    # Check if knowledge manager is initialized
    assert bot.knowledge_manager is not None
    
    # Check if conversation engine is initialized
    assert bot.conversation_engine is not None
    assert bot.conversation_engine.admin_id == 123456789

def test_bot_intents():
    """Test that the bot has the required intents"""
    assert bot.intents.message_content is True
    assert bot.intents.members is True