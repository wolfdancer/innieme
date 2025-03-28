import pytest
import os
import sys

# Set up environment variables before importing the bot
os.environ['DISCORD_TOKEN'] = 'test_token'
os.environ['ADMIN_USER_ID'] = '123456789'
os.environ['DOCUMENTS_DIRECTORY'] = './test_documents'
os.environ['GUILD_ID'] = '987654321'
os.environ['CHANNEL_ID'] = '456789123'
os.environ['OPENAI_API_KEY'] = 'test_openai_key'

# Now import the bot
from innieme_bot.innieme_bot import bot, document_processor, knowledge_manager, conversation_engine

def test_bot_initialization():
    """Test that the bot and its components are initialized correctly"""
    # Check if bot is created with correct prefix
    assert bot.command_prefix == '!'
    
    # Check if document processor is initialized
    assert document_processor is not None
    assert document_processor.docs_dir == './test_documents'
    
    # Check if knowledge manager is initialized
    assert knowledge_manager is not None
    
    # Check if conversation engine is initialized
    assert conversation_engine is not None
    assert conversation_engine.admin_id == 123456789

def test_bot_intents():
    """Test that the bot has the required intents"""
    assert bot.intents.message_content is True
    assert bot.intents.members is True 