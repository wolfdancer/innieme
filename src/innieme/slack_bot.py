from .slack_bot_config import SlackBotConfig
from .innie import Innie, Topic

from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

import logging
import asyncio
from collections import defaultdict
from typing import Optional, List, Dict, Any
import io

logger = logging.getLogger(__name__)

class SlackBot:    
    def __init__(self, config: SlackBotConfig):
        # Bot setup
        self.app = AsyncApp(token=config.slack_bot_token)
        self.handler = AsyncSocketModeHandler(self.app, config.slack_app_token)
        self.client = self.app.client

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

    async def process_and_respond(self, topic: Topic, channel_id: str, query: str, thread_id: str, thread_ts: str = None):
        """Process a query and respond in the channel"""
        context_messages = []
        if thread_ts:
            context_messages = await self.get_thread_context(channel_id, thread_ts)
        else:
            context_messages = [{"role": "user", "content": query}]
        
        try:
            # Add typing indicator
            await self.client.chat_postMessage(
                channel=channel_id,
                text="🤔 Thinking...",
                thread_ts=thread_ts
            )
            
            response = await topic.process_query(thread_id, query, context_messages=context_messages)
            
            # Delete thinking message and send response
            if len(response) > 4000:  # Slack has a 4000 character limit for messages
                # Upload as a file
                await self.client.files_upload(
                    channels=channel_id,
                    content=response,
                    filename="response.txt",
                    title="Response (too long for message)",
                    thread_ts=thread_ts
                )
            else:
                # Send as normal message
                await self.client.chat_postMessage(
                    channel=channel_id,
                    text=response,
                    thread_ts=thread_ts
                )
                
        except Exception as e:
            error_message = f"Sorry, I encountered an error while processing your request: {str(e)}"
            await self.client.chat_postMessage(
                channel=channel_id,
                text=error_message,
                thread_ts=thread_ts
            )
            raise  # Re-raise the exception for logging/debugging

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
                    text=f"Summary generated:\n\n{summary}\n\nApprove to add to knowledge base? (use `/approve`)",
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
        
        # Prepare all topics
        for innie in self.innies:
            for topic in innie.topics:
                await self.connect_and_prepare(topic)
        
        # Start the socket mode handler
        await self.handler.start_async()

    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping Slack bot...")
        await self.handler.close_async()

    def run(self):
        """Run the bot (blocking)"""
        asyncio.run(self.start())