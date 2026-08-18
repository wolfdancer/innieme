from .slack_bot_config import SlackBotConfig
from .innie import Innie, Topic

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

import logging
import asyncio
import re
from collections import defaultdict
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Placeholders used while converting markdown; chosen so they cannot appear in
# model output.
_CODE_PLACEHOLDER = "\x00CODE{}\x00"
_BOLD_OPEN = "\x01"
_BOLD_CLOSE = "\x02"

_CODE_SPAN_RE = re.compile(r"```.*?```|`[^`\n]+`", re.DOTALL)
# Space/tab only, never \n: a \s* here would swallow the blank line that
# follows a heading and collapse the paragraph break.
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^(\s*)[-*+][ \t]+", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", re.DOTALL)
_STRIKE_RE = re.compile(r"~~(.+?)~~", re.DOTALL)


# Emoji shown on the message being worked on. No colons — the API wants the bare name.
WORKING_REACTION = "thinking_face"

# Slack recommends keeping a message under 4,000 characters and truncates at
# 40,000. Sit a little under the recommendation for headroom.
SLACK_MESSAGE_LIMIT = 3900


def split_for_slack(text: str, limit: int = SLACK_MESSAGE_LIMIT) -> List[str]:
    """Split a long response into messages Slack will render well.

    Prefers paragraph breaks, then line breaks, then a hard cut, so parts stay
    readable. A message longer than the limit still posts (Slack only truncates
    at 40,000) but reads poorly, and splitting beats uploading a file the reader
    would have to download.
    """
    if not text:
        return [text] if text == "" else []
    if len(text) <= limit:
        return [text]

    fence = "```"
    parts: List[str] = []
    remaining = text
    # Whether the next part begins inside an open code fence. A code block
    # longer than the limit cannot be kept in one message, so the fence is
    # closed at the end of a part and reopened at the start of the next —
    # otherwise the trailing part renders as plain text.
    inside_fence = False

    while remaining:
        prefix = f"{fence}\n" if inside_fence else ""
        # Reserve room for the prefix and a possible closing fence.
        budget = max(limit - len(prefix) - len(fence) - 1, 1)

        if len(remaining) <= budget:
            content, remaining = remaining, ""
        else:
            window = remaining[:budget]
            cut = window.rfind("\n\n")
            if cut <= 0:
                cut = window.rfind("\n")
            if cut <= 0:
                cut = window.rfind(" ")
            if cut <= 0:
                cut = len(window)
            content = remaining[:cut]
            remaining = remaining[cut:].lstrip("\n")

        content = content.rstrip()
        # An odd number of fences in this part flips the open/closed state.
        ends_inside = inside_fence != (content.count(fence) % 2 == 1)
        suffix = f"\n{fence}" if ends_inside else ""
        parts.append(prefix + content + suffix)
        inside_fence = ends_inside

    return parts


def markdown_to_mrkdwn(text: str) -> str:
    """Translate standard markdown into Slack's mrkdwn dialect.

    Slack does not render standard markdown. It uses ``*single asterisks*`` for
    bold and ``_underscores_`` for italic (the opposite emphasis convention from
    markdown), has no heading syntax, and has no list syntax -- bullets must be
    literal characters. Posting raw markdown therefore shows the punctuation
    verbatim, and ``*italic*`` comes out bold, which inverts the author's intent.

    The LLM emits ordinary markdown so the same response can serve Discord,
    which does read ``**bold**``; each platform adapter translates for itself.
    Content inside code spans and fenced blocks is left untouched.
    """
    if not text:
        return text

    # Pull code out first so its contents are never rewritten.
    code_spans: List[str] = []

    def _stash(match: "re.Match[str]") -> str:
        code_spans.append(match.group(0))
        return _CODE_PLACEHOLDER.format(len(code_spans) - 1)

    text = _CODE_SPAN_RE.sub(_stash, text)

    # Headings have no equivalent; bold is the closest visual stand-in.
    text = _HEADING_RE.sub(lambda m: f"{_BOLD_OPEN}{m.group(1)}{_BOLD_CLOSE}", text)
    # Bullets before emphasis, so a leading "* " is not mistaken for italic.
    text = _BULLET_RE.sub(r"\1• ", text)
    text = _LINK_RE.sub(r"<\2|\1>", text)
    text = _STRIKE_RE.sub(r"~\1~", text)
    # Bold goes to sentinels so the italic pass below cannot re-match it.
    text = _BOLD_RE.sub(
        lambda m: f"{_BOLD_OPEN}{m.group(1) or m.group(2)}{_BOLD_CLOSE}", text
    )
    text = _ITALIC_RE.sub(r"_\1_", text)
    text = text.replace(_BOLD_OPEN, "*").replace(_BOLD_CLOSE, "*")

    for index, span in enumerate(code_spans):
        text = text.replace(_CODE_PLACEHOLDER.format(index), span)
    return text


class SlackBot:
    def __init__(self, config: SlackBotConfig):
        # Bot setup
        self.app = AsyncApp(token=config.slack_bot_token)
        self.client = self.app.client
        # AsyncSocketModeHandler builds an aiohttp.ClientSession, which requires a
        # *running* event loop. __init__ is called synchronously before
        # asyncio.run(), so the handler is created in start() instead.
        self._app_token = config.slack_app_token
        self.handler: Optional[AsyncSocketModeHandler] = None

        # Innies setup        
        self.innies = [Innie(outie_config) for outie_config in config.outies]
        # Channel->Topic mapping
        self.channels: defaultdict[str, List[Topic]] = defaultdict(list)
        for innie in self.innies:
            for topic in innie.topics:
                for channel_config in topic.config.channels:
                    self.channels[channel_config.channel_id].append(topic)
        
        # Register event handlers and commands
        self._register_events()
        self._register_commands()

    def _register_events(self):
        """Register all event handlers"""
        @self.app.event("app_mention")
        async def handle_app_mention(event, say, client):
            await self.handle_mention(event, say, client)
        
        @self.app.event("message")
        async def handle_message(event, say, client):
            # Only handle direct messages and thread replies where the bot was previously mentioned
            if event.get("channel_type") == "im" or self._should_respond_to_thread(event):
                await self.handle_message(event, say, client)

    def _register_commands(self):
        """Register all slash commands"""
        @self.app.command("/approve")
        async def approve_command(ack, command, client):
            await ack()
            await self.approve_summary(command, client)
                    
        @self.app.command("/quit")
        async def quit_command(ack, command, client):
            await ack()
            topic = self._identify_topic(command["channel_id"])
            if not topic:
                await client.chat_postMessage(
                    channel=command["channel_id"],
                    text="'quit' command ignored as there is no topic in this channel to support."
                )
                return
            
            topic_outie = topic.outie_config.outie_id
            if command["user_id"] != topic_outie:
                await client.chat_postMessage(
                    channel=command["channel_id"],
                    text=f"This command is only available to the outie (<@{topic_outie}>)."
                )
                return
            
            await client.chat_postMessage(
                channel=command["channel_id"],
                text="Goodbye! Bot shutting down..."
            )
            await self.stop()

        @self.app.command("/hello")
        async def hello_command(ack, command, client):
            await ack()
            # Create a rich message block
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "InnieMe: Your Knowledge Speaks for Itself"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Democratizes access to AI-powered Q&A capabilities\n\n*Pricing:* Free during early access\n*Key Feature:* Ask and you shall receive\n*Deployment:* Channel specific"
                    },
                    "accessory": {
                        "type": "image",
                        "image_url": "https://repository-images.githubusercontent.com/956066438/8dce1cee-0386-423d-817c-283e3dfb7288",
                        "alt_text": "InnieMe logo"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "*InnieMe © 2025* | <https://github.com/wolfdancer/innieme|GitHub>"
                        }
                    ]
                }
            ]
            
            await client.chat_postMessage(
                channel=command["channel_id"],
                blocks=blocks
            )

    def _identify_topic(self, channel_id: str) -> Optional[Topic]:
        topics = self.channels.get(channel_id, [])
        return topics[0] if topics else None

    def _should_respond_to_thread(self, event: Dict[str, Any]) -> bool:
        """Check if bot should respond to a thread message"""
        # Only respond in threads where bot was mentioned or is actively participating
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return False
        
        # Check if this thread involves the bot
        topic = self._identify_topic(event["channel"])
        if topic:
            return topic.is_following_thread(thread_ts)
        
        return False

    async def get_thread_context(self, channel_id: str, thread_ts: str, limit: int = 10) -> List[Dict[str, str]]:
        """Get recent messages from the thread for context"""
        messages = []
        try:
            # Get thread messages
            result = await self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=limit
            )
            
            bot_user_id = (await self.client.auth_test())["user_id"]
            
            for message in result["messages"]:
                if "text" in message:
                    role = "assistant" if message["user"] == bot_user_id else "user"
                    messages.append({
                        "role": role,
                        "content": message["text"]
                    })
            
            return messages
        except Exception as e:
            logger.error(f"Error fetching thread context: {e}")
            return []

    async def respond(self, channel_id: str, text: str, thread_ts: str = None):
        """Send a response to a channel or thread"""
        try:
            await self.client.chat_postMessage(
                channel=channel_id,
                text=text,
                thread_ts=thread_ts
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def _set_working(self, channel_id: str, timestamp: str, working: bool):
        """Show or clear the "working on it" reaction on a message.

        Preferred over posting a "Thinking..." message, which stays in the thread
        forever and gets tiresome. Reacting to the thread's parent also means the
        signal is visible in the channel without opening the thread.

        Needs the ``reactions:write`` scope. A bot missing it should still answer,
        so failures here are logged and swallowed.
        """
        if not timestamp:
            return
        action = self.client.reactions_add if working else self.client.reactions_remove
        try:
            await action(
                channel=channel_id, name=WORKING_REACTION, timestamp=timestamp
            )
        except Exception as e:
            # already_reacted / no_reaction are normal races, not problems.
            logger.debug(f"Could not {'add' if working else 'remove'} reaction: {e}")

    async def _post_response(self, channel_id: str, response: str, thread_ts: str = None):
        """Post a response, split across messages when it is too long for one.

        Slack recommends keeping a message under 4,000 characters (it truncates
        at 40,000). Splitting keeps a long summary readable in the thread —
        better than uploading it as a file the reader has to download to see.
        """
        for part in split_for_slack(markdown_to_mrkdwn(response)):
            await self.client.chat_postMessage(
                channel=channel_id,
                text=part,
                thread_ts=thread_ts
            )

    async def process_and_respond(self, topic: Topic, channel_id: str, query: str, thread_id: str, thread_ts: str = None):
        """Process a query and respond in the channel"""
        context_messages = []
        if thread_ts:
            context_messages = await self.get_thread_context(channel_id, thread_ts)
        else:
            context_messages = [{"role": "user", "content": query}]

        try:
            await self._set_working(channel_id, thread_ts, True)

            response = await topic.process_query(thread_id, query, context_messages=context_messages)

            await self._post_response(channel_id, response, thread_ts)

        except Exception as e:
            error_message = f"Sorry, I encountered an error while processing your request: {str(e)}"
            await self.client.chat_postMessage(
                channel=channel_id,
                text=error_message,
                thread_ts=thread_ts
            )
            raise  # Re-raise the exception for logging/debugging
        finally:
            # Clear the indicator whether the answer succeeded or failed, so a
            # failure never leaves the thread looking like it is still working.
            await self._set_working(channel_id, thread_ts, False)

    async def handle_mention(self, event: Dict[str, Any], say, client: AsyncWebClient):
        """Handle app mentions"""
        channel_id = event["channel"]
        user_id = event["user"]
        text = event["text"]
        ts = event["ts"]
        
        topic = self._identify_topic(channel_id)
        if not topic:
            await say(text="Sorry I am not set up to support a topic in this channel.")
            return

        logger.debug(f"Handling mention in topic: {topic.config.name}")
        
        # Clean the mention from the text
        bot_user_id = (await client.auth_test())["user_id"]
        clean_text = text.replace(f'<@{bot_user_id}>', '').strip()
        
        # Start a thread and process the query
        await self.process_and_respond(
            topic,
            channel_id,
            clean_text,
            ts,  # Use timestamp as thread_id
            ts   # Use timestamp as thread_ts for threading
        )

    async def handle_message(self, event: Dict[str, Any], say, client: AsyncWebClient):
        """Handle direct messages and thread replies"""
        channel_id = event["channel"]
        user_id = event["user"]
        text = event["text"]
        ts = event["ts"]
        thread_ts = event.get("thread_ts")
        
        # Skip bot's own messages
        bot_user_id = (await client.auth_test())["user_id"]
        if user_id == bot_user_id:
            return
            
        topic = self._identify_topic(channel_id)
        if not topic:
            return

        outie_id = topic.outie_config.outie_id

        # Handle outie commands
        if user_id == outie_id and "summary and file" in text.lower():
            if thread_ts:
                summary = await topic.generate_summary(thread_ts)
                await client.chat_postMessage(
                    channel=channel_id,
                    text=(
                        f"Summary generated:\n\n{markdown_to_mrkdwn(summary)}\n\n"
                        "Approve to add to knowledge base? (use `/approve`)"
                    ),
                    thread_ts=thread_ts
                )
            return
        
        # Handle consultation requests
        if "please consult outie" in text.lower():
            if thread_ts:
                await client.chat_postMessage(
                    channel=channel_id,
                    text=f"<@{outie_id}> Your consultation has been requested in this thread.",
                    thread_ts=thread_ts
                )
            return
        
        # Handle thread responses
        if thread_ts and topic.is_following_thread(thread_ts):
            await self.process_and_respond(
                topic,
                channel_id,
                text,
                thread_ts,
                thread_ts
            )

    async def connect_and_prepare(self, topic: Topic):
        """Connect to channels and prepare documents"""
        outie_id = topic.outie_config.outie_id
        channels = []
        
        for channel_config in topic.config.channels:
            channel_id = channel_config.channel_id
            try:
                # Test if we can access the channel
                await self.client.conversations_info(channel=channel_id)
                channels.append(channel_id)
                await self.client.chat_postMessage(
                    channel=channel_id,
                    text=f"Bot is connected, preparing documents for {topic.config.name}..."
                )
            except Exception as e:
                logger.error(f"Could not connect to channel {channel_id}: {e}")
                # Try to notify the outie via DM
                try:
                    await self.client.chat_postMessage(
                        channel=outie_id,
                        text=f"Bot is now online but could not access channel <#{channel_id}>. Please make sure the bot is invited to the channel."
                    )
                except Exception as dm_e:
                    logger.error(f"Could not send DM to outie {outie_id}: {dm_e}")
        
        # Scan and vectorize documents
        scanning_result = await topic.scan_and_vectorize()
        
        # Notify channels of completion
        for channel_id in channels:
            mention = f"(fyi <@{outie_id}>)"
            await self.client.chat_postMessage(
                channel=channel_id,
                text=f"{scanning_result} {mention}"
            )

    async def approve_summary(self, command: Dict[str, Any], client: AsyncWebClient):
        """Handle summary approval"""
        channel_id = command["channel_id"]
        user_id = command["user_id"]
        
        topic = self._identify_topic(channel_id)
        if not topic:
            return
        
        outie_id = topic.outie_config.outie_id
        if user_id == outie_id:
            # This would need thread_ts to identify which summary to approve
            # For now, we'll use a simple implementation
            await client.chat_postMessage(
                channel=channel_id,
                text="Summary approved and added to knowledge base."
            )
            # TODO: Implement actual summary storage with thread tracking

    async def start(self):
        """Start the bot"""
        logger.info("Starting Slack bot...")

        # Created here, not in __init__: the handler opens an aiohttp session
        # and so needs the event loop to already be running.
        if self.handler is None:
            self.handler = AsyncSocketModeHandler(self.app, self._app_token)

        # Prepare all topics
        for innie in self.innies:
            for topic in innie.topics:
                await self.connect_and_prepare(topic)

        # Start the socket mode handler
        await self.handler.start_async()

    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping Slack bot...")
        if self.handler is not None:
            await self.handler.close_async()

    def run(self):
        """Run the bot (blocking)"""
        asyncio.run(self.start())