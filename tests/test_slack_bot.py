from innieme.slack_bot import SlackBot, parse_bot_command
from innieme.slack_bot_config import SlackBotConfig, OutieConfig, TopicConfig, ChannelConfig

import pytest
from unittest.mock import AsyncMock, Mock, patch
import asyncio
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
    
    # Verify initialization. The socket-mode handler is deliberately NOT built
    # here -- it opens an aiohttp session and needs a running event loop, so it
    # is created in start() instead.
    assert bot.app == mock_app_instance
    assert bot.handler is None
    mock_handler.assert_not_called()
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
def test_resolve_cache_dir_uses_configured_value(mock_config):
    """A bot-level cache_dir wins and has ~ expanded"""
    from innieme.innie import Topic
    mock_config.cache_dir = "~/.config/innieme/cache"
    outie = mock_config.outies[0]
    resolved = Topic._resolve_cache_dir(outie, outie.topics[0])
    assert resolved == os.path.expanduser("~/.config/innieme/cache")
    assert "~" not in resolved

def test_resolve_cache_dir_falls_back_to_docs_dir(mock_config):
    """Without cache_dir, the legacy docs_dir location is used"""
    from innieme.innie import Topic
    mock_config.cache_dir = None
    outie = mock_config.outies[0]
    topic_config = outie.topics[0]
    resolved = Topic._resolve_cache_dir(outie, topic_config)
    assert resolved == os.path.join(topic_config.docs_dir, ".cache", "langchain")

@pytest.mark.asyncio
@patch('innieme.slack_bot.AsyncApp')
@patch('innieme.slack_bot.AsyncSocketModeHandler')
async def test_start_builds_handler_inside_event_loop(mock_handler, mock_app, mock_config):
    """The handler is constructed in start(), where a loop is running.

    Building it in __init__ raises "no running event loop" because
    AsyncSocketModeHandler opens an aiohttp.ClientSession.
    """
    mock_app.return_value = Mock(client=Mock())
    handler_instance = Mock()
    handler_instance.close_async = AsyncMock()
    mock_handler.return_value = handler_instance

    bot = SlackBot(mock_config)
    assert bot.handler is None

    # Stop as soon as the connection is up, so start() does not wait forever.
    handler_instance.connect_async = AsyncMock(side_effect=lambda: bot._shutdown.set())

    bot.innies = []  # skip document scanning / channel connection
    await bot.start()

    mock_handler.assert_called_once_with(bot.app, "xapp-test-token")
    assert bot.handler is handler_instance
    handler_instance.connect_async.assert_awaited_once()

@pytest.mark.asyncio
@patch('innieme.slack_bot.AsyncApp')
@patch('innieme.slack_bot.AsyncSocketModeHandler')
async def test_stop_lets_start_return_so_the_process_exits(mock_handler, mock_app, mock_config):
    """stop() must end start(), not just disconnect.

    start_async() ends in an infinite sleep, so closing the socket-mode client
    left the process running after a quit -- disconnected from Slack but alive,
    and only killable by hand.
    """
    mock_app.return_value = Mock(client=Mock())
    handler_instance = Mock()
    handler_instance.connect_async = AsyncMock()
    handler_instance.close_async = AsyncMock()
    # start_async is what must NOT be used: it never returns.
    handler_instance.start_async = AsyncMock(side_effect=AssertionError("start_async blocks forever"))
    mock_handler.return_value = handler_instance

    bot = SlackBot(mock_config)
    bot.innies = []

    async def quit_after_connect():
        while bot._shutdown is None:
            await asyncio.sleep(0)
        await bot.stop()

    # A timeout here means the shutdown path is broken, which is exactly the bug.
    await asyncio.wait_for(asyncio.gather(bot.start(), quit_after_connect()), timeout=5)

    handler_instance.close_async.assert_awaited_once()

@pytest.mark.asyncio
async def test_stop_before_start_does_not_raise(mock_config):
    """Stopping a bot that was never started is a no-op, not an AttributeError"""
    with patch('innieme.slack_bot.AsyncApp') as mock_app:
        mock_app.return_value = Mock(client=Mock())
        bot = SlackBot(mock_config)
        await bot.stop()  # handler is None; must not raise


class TestMarkdownToMrkdwn:
    """Slack's mrkdwn dialect differs from markdown; see markdown_to_mrkdwn."""

    def test_bold_double_becomes_single_asterisk(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("**Stage:** drafted") == "*Stage:* drafted"
        assert markdown_to_mrkdwn("__Stage:__ drafted") == "*Stage:* drafted"

    def test_italic_becomes_underscores_not_bold(self):
        """The inversion that matters: *x* means bold in Slack, italic in markdown"""
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("*Sources: a.md*") == "_Sources: a.md_"

    def test_bold_is_not_downgraded_to_italic(self):
        """Bold must not be re-matched by the italic pass"""
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("**bold** and *italic*") == "*bold* and _italic_"

    def test_headings_become_bold(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("## Key contacts") == "*Key contacts*"
        assert markdown_to_mrkdwn("# Top\n\ntext") == "*Top*\n\ntext"

    def test_bullets_become_literal_bullet_chars_preserving_indent(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        out = markdown_to_mrkdwn("- one\n- two\n  - nested")
        assert out == "• one\n• two\n  • nested"

    def test_asterisk_bullets_are_not_read_as_italic(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("* one\n* two") == "• one\n• two"

    def test_links_use_slack_angle_syntax(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("[docs](https://x.com/a)") == "<https://x.com/a|docs>"
        assert markdown_to_mrkdwn("[mail](mailto:a@b.co)") == "<mailto:a@b.co|mail>"

    def test_control_syntax_targets_are_not_converted(self):
        """Slack's link brackets are also its control syntax.

        Link targets reach this function from document text by way of the model,
        so they are untrusted. Converting [all](!here) would emit <!here>, an
        actual channel-wide ping; (@U123) and (#C123) become real user and
        channel references. Unsafe targets stay literal markdown, which Slack
        renders harmlessly.
        """
        from innieme.slack_bot import markdown_to_mrkdwn
        for src in ("[all](!here)", "[everyone](!channel)",
                    "[someone](@U012ABC)", "[somewhere](#C012ABC)",
                    "[js](javascript:alert(1))", "[rel](/etc/passwd)"):
            out = markdown_to_mrkdwn(src)
            assert out == src, f"{src!r} was converted to {out!r}"
            assert not out.startswith("<"), f"{src!r} produced control syntax"

    def test_link_label_cannot_break_out_of_the_brackets(self):
        """A label must not be able to close the link's angle brackets.

        `>` survives as the escaped `&gt;` (Slack displays it as `>`), while `|`
        is dropped because it separates target from label and is not escaped.
        """
        from innieme.slack_bot import markdown_to_mrkdwn
        out = markdown_to_mrkdwn("[a>b|c](https://x.co)")
        assert out == "<https://x.co|a&gt;bc>"

    def test_raw_control_syntax_in_text_is_neutralised(self):
        """Slack reads <!here> as a live ping wherever it appears.

        The text comes from documents by way of the model, so a note containing
        <!channel> must not make the bot ping everyone.
        """
        from innieme.slack_bot import markdown_to_mrkdwn
        for raw, dead in [
            ("<!here>", "&lt;!here&gt;"),
            ("<!channel>", "&lt;!channel&gt;"),
            ("<@U012ABC>", "&lt;@U012ABC&gt;"),
            ("<#C012ABC>", "&lt;#C012ABC&gt;"),
        ]:
            out = markdown_to_mrkdwn(f"see {raw} now")
            assert out == f"see {dead} now"
            assert raw not in out

    def test_bracketed_control_target_cannot_survive_a_rejected_link(self):
        """A rejected link is returned literally, so its text must be inert too"""
        from innieme.slack_bot import markdown_to_mrkdwn
        out = markdown_to_mrkdwn("[all](<!here>)")
        assert "<!here>" not in out
        assert "&lt;!here&gt;" in out

    def test_control_syntax_inside_code_is_also_neutralised(self):
        """Slack interprets mentions inside code spans too"""
        from innieme.slack_bot import markdown_to_mrkdwn
        out = markdown_to_mrkdwn("run `echo <!here>`")
        assert "<!here>" not in out
        assert "&lt;!here&gt;" in out

    def test_ampersand_escaped_once(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("a & b") == "a &amp; b"

    def test_url_containing_delimiters_is_left_literal(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        src = "[x](https://x.co/a|b)"
        assert markdown_to_mrkdwn(src) == src

    def test_strikethrough_single_tilde(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("~~gone~~") == "~gone~"

    def test_inline_code_is_left_alone(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("run `a - b` now") == "run `a - b` now"

    def test_fenced_block_contents_untouched(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        src = "text\n```\n- **not** a bullet\n## not a heading\n```\n- real"
        out = markdown_to_mrkdwn(src)
        assert "```\n- **not** a bullet\n## not a heading\n```" in out
        assert out.endswith("• real")

    def test_empty_and_none_safe(self):
        from innieme.slack_bot import markdown_to_mrkdwn
        assert markdown_to_mrkdwn("") == ""
        assert markdown_to_mrkdwn(None) is None

    def test_real_bot_response_regression(self):
        """Mirrors the shape of a real answer that surfaced this bug.

        Covers, in one string, every construct that was rendering wrong: a bold
        heading line, bold labels inside bullets, bold mid-sentence, a nested
        bullet, inline code, and an italic trailer.
        """
        from innieme.slack_bot import markdown_to_mrkdwn
        src = (
            "**Northwind Energy — Customer**\n"
            "- **Stage:** proposal drafted for the pilot engagement\n"
            "- **Close outlook:** roughly **$10–20K/year**\n"
            "  - Mar 12: drafted `NORTHWIND_Pilot_Proposal`\n"
            "\n*Sources: `Northwind-Energy.md`*"
        )
        out = markdown_to_mrkdwn(src)
        assert "**" not in out
        assert out.startswith("*Northwind Energy — Customer*")
        assert "• *Stage:*" in out
        assert "  • Mar 12: drafted `NORTHWIND_Pilot_Proposal`" in out
        assert "_Sources: `Northwind-Energy.md`_" in out


class TestSplitForSlack:
    """Long responses are split across messages, not uploaded as files."""

    def test_short_text_is_one_part(self):
        from innieme.slack_bot import split_for_slack
        assert split_for_slack("short") == ["short"]

    def test_splits_on_paragraph_boundary(self):
        from innieme.slack_bot import split_for_slack
        text = ("a" * 50 + "\n\n") * 10
        parts = split_for_slack(text, limit=120)
        assert len(parts) > 1
        assert all(len(p) <= 120 for p in parts)
        # No paragraph was cut mid-word
        assert all(set(p) <= set("a\n") for p in parts)

    def test_falls_back_to_line_then_space(self):
        from innieme.slack_bot import split_for_slack
        parts = split_for_slack("word " * 100, limit=60)
        assert all(len(p) <= 60 for p in parts)
        assert "".join(parts).replace("\n", " ").split() == ["word"] * 100

    def test_never_splits_inside_code_fence(self):
        from innieme.slack_bot import split_for_slack
        text = "intro\n\n```\n" + ("x" * 200) + "\n```\n\noutro"
        parts = split_for_slack(text, limit=100)
        for part in parts:
            assert part.count("```") % 2 == 0, f"unbalanced fence in: {part[:40]!r}"

    def test_rejoined_content_is_preserved(self):
        """No words are dropped. Parts are separate messages, so the join
        separator is implicit -- rejoin with a newline, not edge-to-edge."""
        from innieme.slack_bot import split_for_slack
        text = "\n\n".join(f"Paragraph {i} " + "y" * 80 for i in range(12))
        parts = split_for_slack(text, limit=200)
        assert "\n".join(parts).split() == text.split()

    def test_empty_string(self):
        from innieme.slack_bot import split_for_slack
        assert split_for_slack("") == [""]

    def test_oversized_code_block_reopens_fence_each_part(self):
        """A code block bigger than one message stays code in every part"""
        from innieme.slack_bot import split_for_slack
        text = "intro\n\n```\n" + "\n".join(f"line {i}" for i in range(60)) + "\n```\n\noutro"
        parts = split_for_slack(text, limit=120)
        assert len(parts) > 2
        for part in parts:
            assert part.count("```") % 2 == 0, f"unbalanced: {part[:40]!r}"
        # every line of the code block survives somewhere
        for i in range(60):
            assert any(f"line {i}\n" in p or p.endswith(f"line {i}") or f"line {i}\n```" in p
                       for p in parts), f"lost line {i}"


@pytest.mark.asyncio
async def test_working_reaction_added_then_removed(mock_config):
    """The indicator is a reaction on the parent, cleared when the answer posts"""
    with patch('innieme.slack_bot.AsyncApp') as mock_app:
        client = Mock()
        client.reactions_add = AsyncMock()
        client.reactions_remove = AsyncMock()
        client.chat_postMessage = AsyncMock()
        mock_app.return_value = Mock(client=client)
        bot = SlackBot(mock_config)

        topic = Mock()
        topic.process_query = AsyncMock(return_value="**Answer**")
        await bot.process_and_respond(topic, "C1234567890", "q", "111.1", "111.1")

        client.reactions_add.assert_awaited_once_with(
            channel="C1234567890", name="thinking_face", timestamp="111.1")
        client.reactions_remove.assert_awaited_once_with(
            channel="C1234567890", name="thinking_face", timestamp="111.1")
        # No "Thinking..." message is posted any more
        posted = [c.kwargs["text"] for c in client.chat_postMessage.await_args_list]
        assert posted == ["*Answer*"]

@pytest.mark.asyncio
async def test_working_reaction_cleared_on_error(mock_config):
    """A failed answer must not leave the thread looking like it's still working"""
    with patch('innieme.slack_bot.AsyncApp') as mock_app:
        client = Mock()
        client.reactions_add = AsyncMock()
        client.reactions_remove = AsyncMock()
        client.chat_postMessage = AsyncMock()
        mock_app.return_value = Mock(client=client)
        bot = SlackBot(mock_config)

        topic = Mock()
        topic.process_query = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(RuntimeError):
            await bot.process_and_respond(topic, "C1234567890", "q", "111.1", "111.1")

        client.reactions_remove.assert_awaited_once()

@pytest.mark.asyncio
async def test_missing_reactions_scope_does_not_block_answering(mock_config):
    """Without reactions:write the bot still answers"""
    from slack_sdk.errors import SlackApiError
    with patch('innieme.slack_bot.AsyncApp') as mock_app:
        client = Mock()
        client.reactions_add = AsyncMock(
            side_effect=SlackApiError("missing_scope", {"error": "missing_scope"}))
        client.reactions_remove = AsyncMock(
            side_effect=SlackApiError("missing_scope", {"error": "missing_scope"}))
        client.chat_postMessage = AsyncMock()
        mock_app.return_value = Mock(client=client)
        bot = SlackBot(mock_config)

        topic = Mock()
        topic.process_query = AsyncMock(return_value="Answer")
        await bot.process_and_respond(topic, "C1234567890", "q", "111.1", "111.1")

        client.chat_postMessage.assert_awaited_once()

@pytest.mark.asyncio
async def test_long_response_posts_multiple_messages_not_a_file(mock_config):
    """Long summaries are split into thread messages; files_upload is not used"""
    with patch('innieme.slack_bot.AsyncApp') as mock_app:
        client = Mock()
        client.reactions_add = AsyncMock()
        client.reactions_remove = AsyncMock()
        client.chat_postMessage = AsyncMock()
        client.files_upload = AsyncMock()
        mock_app.return_value = Mock(client=client)
        bot = SlackBot(mock_config)

        topic = Mock()
        topic.process_query = AsyncMock(
            return_value="\n\n".join(f"Para {i} " + "z" * 500 for i in range(20)))
        await bot.process_and_respond(topic, "C1234567890", "q", "111.1", "111.1")

        assert client.chat_postMessage.await_count > 1
        client.files_upload.assert_not_called()
        for call in client.chat_postMessage.await_args_list:
            assert len(call.kwargs["text"]) <= 3900


class TestParseBotCommand:
    """Commands arrive as mentions, so the parser is what separates them from questions."""

    BOT = "U0BOT"

    def test_bare_command_after_mention(self):
        assert parse_bot_command(f"<@{self.BOT}> rescan", self.BOT) == "rescan"
        assert parse_bot_command(f"<@{self.BOT}> quit", self.BOT) == "quit"

    def test_case_and_surrounding_whitespace_ignored(self):
        assert parse_bot_command(f"  <@{self.BOT}>   ReScan  ", self.BOT) == "rescan"

    def test_trailing_punctuation_ignored(self):
        assert parse_bot_command(f"<@{self.BOT}> quit!", self.BOT) == "quit"

    def test_command_before_the_mention(self):
        assert parse_bot_command(f"rescan <@{self.BOT}>", self.BOT) == "rescan"

    def test_a_question_that_merely_contains_the_word_is_not_a_command(self):
        """The whole message has to be the command, or "should we quit?" shuts the bot down."""
        for text in [
            f"<@{self.BOT}> should we rescan the notes?",
            f"<@{self.BOT}> did the rescan pick up Northwind.md",
            f"<@{self.BOT}> what happens when you quit",
            f"<@{self.BOT}> quit rescan",
        ]:
            assert parse_bot_command(text, self.BOT) is None, text

    def test_unmentioned_message_is_never_a_command(self):
        assert parse_bot_command("rescan", self.BOT) is None
        assert parse_bot_command("<@U0SOMEONEELSE> rescan", self.BOT) is None

    def test_empty_text_safe(self):
        assert parse_bot_command("", self.BOT) is None
        assert parse_bot_command(None, self.BOT) is None


def _command_bot(mock_config, client):
    with patch('innieme.slack_bot.AsyncApp') as mock_app:
        mock_app.return_value = Mock(client=client)
        return SlackBot(mock_config)


def _topic(outie_id="U1234567890", name="math"):
    topic = Mock()
    topic.config = Mock(name=name)
    topic.config.name = name
    topic.outie_config = Mock(outie_id=outie_id)
    return topic


@pytest.mark.asyncio
async def test_rescan_command_rebuilds_the_index(mock_config):
    """"@bot rescan" re-vectorizes without a restart and reports the result"""
    client = Mock()
    client.chat_postMessage = AsyncMock()
    client.reactions_add = AsyncMock()
    client.reactions_remove = AsyncMock()
    bot = _command_bot(mock_config, client)

    topic = _topic()
    topic.scan_and_vectorize = AsyncMock(return_value="On topic 'math': 12 chunks created")
    event = {"channel": "C1234567890", "user": "U1234567890", "ts": "111.1"}

    await bot.run_bot_command("rescan", topic, event, client)

    topic.scan_and_vectorize.assert_awaited_once()
    posted = client.chat_postMessage.await_args_list[-1].kwargs
    assert "12 chunks created" in posted["text"]
    assert posted["thread_ts"] == "111.1"
    # The working indicator goes on the mention itself and is cleared after.
    client.reactions_add.assert_awaited_once()
    client.reactions_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_rescan_says_the_old_index_is_still_serving(mock_config):
    """A failure leaves the previous store in place; the outie needs to know that"""
    client = Mock()
    client.chat_postMessage = AsyncMock()
    client.reactions_add = AsyncMock()
    client.reactions_remove = AsyncMock()
    bot = _command_bot(mock_config, client)

    topic = _topic()
    topic.scan_and_vectorize = AsyncMock(side_effect=RuntimeError("embeddings down"))
    event = {"channel": "C1234567890", "user": "U1234567890", "ts": "111.1"}

    await bot.run_bot_command("rescan", topic, event, client)

    text = client.chat_postMessage.await_args_list[-1].kwargs["text"]
    assert "embeddings down" in text
    assert "previously loaded" in text
    client.reactions_remove.assert_awaited_once()


@pytest.mark.asyncio
async def test_commands_are_outie_only(mock_config):
    """Anyone in the channel can mention the bot, so commands must be gated"""
    client = Mock()
    client.chat_postMessage = AsyncMock()
    bot = _command_bot(mock_config, client)

    topic = _topic(outie_id="U1234567890")
    topic.scan_and_vectorize = AsyncMock()
    bot.stop = AsyncMock()
    event = {"channel": "C1234567890", "user": "U0INTRUDER", "ts": "111.1"}

    await bot.run_bot_command("rescan", topic, event, client)
    await bot.run_bot_command("quit", topic, event, client)

    topic.scan_and_vectorize.assert_not_awaited()
    bot.stop.assert_not_awaited()
    for call in client.chat_postMessage.await_args_list:
        assert "only available to the outie" in call.kwargs["text"]


@pytest.mark.asyncio
async def test_quit_command_stops_the_bot(mock_config):
    client = Mock()
    client.chat_postMessage = AsyncMock()
    bot = _command_bot(mock_config, client)
    bot.stop = AsyncMock()

    topic = _topic()
    event = {"channel": "C1234567890", "user": "U1234567890", "ts": "111.1"}

    await bot.run_bot_command("quit", topic, event, client)

    bot.stop.assert_awaited_once()
    assert "shutting down" in client.chat_postMessage.await_args_list[0].kwargs["text"]


@pytest.mark.asyncio
async def test_mention_routes_a_command_instead_of_querying_the_model(mock_config):
    client = Mock()
    client.auth_test = AsyncMock(return_value={"user_id": "U0BOT"})
    client.chat_postMessage = AsyncMock()
    bot = _command_bot(mock_config, client)

    topic = _topic()
    bot._identify_topic = Mock(return_value=topic)
    bot.run_bot_command = AsyncMock()
    bot.process_and_respond = AsyncMock()

    event = {"channel": "C1234567890", "user": "U1234567890",
             "text": "<@U0BOT> rescan", "ts": "111.1"}
    await bot.handle_mention(event, AsyncMock(), client)

    bot.run_bot_command.assert_awaited_once()
    assert bot.run_bot_command.await_args.args[0] == "rescan"
    bot.process_and_respond.assert_not_awaited()


@pytest.mark.asyncio
async def test_command_in_a_followed_thread_is_not_also_answered_as_a_question(mock_config):
    """Slack sends app_mention *and* message for the same text.

    handle_mention runs the command; if handle_message also treated it as a
    query the thread would get a stray answer next to the command's reply.
    """
    client = Mock()
    client.auth_test = AsyncMock(return_value={"user_id": "U0BOT"})
    client.chat_postMessage = AsyncMock()
    bot = _command_bot(mock_config, client)

    topic = _topic()
    topic.is_following_thread = Mock(return_value=True)
    bot._identify_topic = Mock(return_value=topic)
    bot.process_and_respond = AsyncMock()

    event = {"channel": "C1234567890", "user": "U1234567890", "text": "<@U0BOT> rescan",
             "ts": "222.2", "thread_ts": "111.1"}
    await bot.handle_message(event, AsyncMock(), client)

    bot.process_and_respond.assert_not_awaited()


@pytest.mark.asyncio
async def test_ordinary_mention_still_reaches_the_model(mock_config):
    """The command path must not swallow real questions"""
    client = Mock()
    client.auth_test = AsyncMock(return_value={"user_id": "U0BOT"})
    bot = _command_bot(mock_config, client)

    topic = _topic()
    bot._identify_topic = Mock(return_value=topic)
    bot.run_bot_command = AsyncMock()
    bot.process_and_respond = AsyncMock()

    event = {"channel": "C1234567890", "user": "U1234567890",
             "text": "<@U0BOT> should we rescan the Northwind notes?", "ts": "111.1"}
    await bot.handle_mention(event, AsyncMock(), client)

    bot.run_bot_command.assert_not_awaited()
    bot.process_and_respond.assert_awaited_once()
    assert bot.process_and_respond.await_args.args[2] == "should we rescan the Northwind notes?"

