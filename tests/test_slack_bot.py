from innieme.slack_bot import SlackBot
from innieme.slack_bot_config import SlackBotConfig, OutieConfig, TopicConfig, ChannelConfig

import pytest
from unittest.mock import AsyncMock, Mock, patch
import os

@pytest.fixture
def mock_config():
    """Create a mock SlackBotConfig for testing"""
    # Create test directories
    math_docs_dir = 'data/math'
    os.makedirs(math_docs_dir, exist_ok=True)
    
    # Create channel config
    channel_config = ChannelConfig(channel_id="C1234567890")
    
    # Create topic config
    topic_config = TopicConfig(
        name="math",
        role="Math Teacher",
        docs_dir=math_docs_dir,
        channels=[channel_config]
    )
    
    # Create outie config
    outie_config = OutieConfig(
        outie_id="U1234567890",
        topics=[topic_config]
    )
    
    # Create bot config
    config = SlackBotConfig(
        slack_bot_token="xoxb-test-token",
        slack_app_token="xapp-test-token",
        embeddings_api_key="test_embeddings_key",
        llm_api_key="test_llm_key",
        embedding_model="fake",  # Use fake for testing
        outies=[outie_config]
    )
    
    return config

@patch('innieme.slack_bot.AsyncApp')
@patch('innieme.slack_bot.AsyncSocketModeHandler')
def test_slack_bot_initialization(mock_handler, mock_app, mock_config):
    """Test SlackBot initialization"""
    # Mock the AsyncApp and handler
    mock_app_instance = Mock()
    mock_app.return_value = mock_app_instance
    mock_app_instance.client = Mock()
    
    mock_handler_instance = Mock()
    mock_handler.return_value = mock_handler_instance
    
    # Create SlackBot instance
    bot = SlackBot(mock_config)
    
    # Verify initialization
    assert bot.app == mock_app_instance
    assert bot.handler == mock_handler_instance
    assert bot.client == mock_app_instance.client
    assert len(bot.innies) == 1
    assert len(bot.channels) == 1
    assert "C1234567890" in bot.channels

def test_identify_topic(mock_config):
    """Test topic identification by channel ID"""
    with patch('innieme.slack_bot.AsyncApp'), \
         patch('innieme.slack_bot.AsyncSocketModeHandler'):
        bot = SlackBot(mock_config)
        
        # Test existing channel
        topic = bot._identify_topic("C1234567890")
        assert topic is not None
        assert topic.config.name == "math"
        
        # Test non-existing channel
        topic = bot._identify_topic("C0000000000")
        assert topic is None

@pytest.mark.asyncio
async def test_get_thread_context(mock_config):
    """Test getting thread context from Slack"""
    with patch('innieme.slack_bot.AsyncApp'), \
         patch('innieme.slack_bot.AsyncSocketModeHandler'):
        bot = SlackBot(mock_config)
        
        # Mock the Slack client
        bot.client = AsyncMock()
        bot.client.conversations_replies.return_value = {
            "messages": [
                {"user": "U1234567890", "text": "Hello"},
                {"user": "UBOT123456", "text": "Hi there!"},
                {"user": "U1234567890", "text": "How are you?"}
            ]
        }
        bot.client.auth_test.return_value = {"user_id": "UBOT123456"}
        
        # Get thread context
        context = await bot.get_thread_context("C1234567890", "1234567890.123456")
        
        # Verify context
        assert len(context) == 3
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "Hello"
        assert context[1]["role"] == "assistant"
        assert context[1]["content"] == "Hi there!"
        assert context[2]["role"] == "user"
        assert context[2]["content"] == "How are you?"

def test_should_respond_to_thread(mock_config):
    """Test thread response logic"""
    with patch('innieme.slack_bot.AsyncApp'), \
         patch('innieme.slack_bot.AsyncSocketModeHandler'):
        bot = SlackBot(mock_config)
        
        # Test message without thread_ts
        event = {"channel": "C1234567890"}
        assert not bot._should_respond_to_thread(event)
        
        # Test message with thread_ts but no following thread
        event = {"channel": "C1234567890", "thread_ts": "1234567890.123456"}
        assert not bot._should_respond_to_thread(event)
        
        # Test message with thread_ts in non-existing channel
        event = {"channel": "C0000000000", "thread_ts": "1234567890.123456"}
        assert not bot._should_respond_to_thread(event)