from .discord_bot_config import DiscordBotConfig
from .innie import Innie, Topic

import discord
from discord.ext import commands

from collections import defaultdict
from typing import Optional, List
import io

class DiscordBot:    
    def __init__(self, config: DiscordBotConfig):
        # Bot setup with required intents
        self.token = config.discord_token
        self.bot = commands.Bot(command_prefix='!', intents=self._create_intents())

        # Innies setup        
        self.innies = [Innie(config.openai_api_key, outie_config) for outie_config in config.outies]
        # Channel->Topic mapping
        self.channels: defaultdict[int, List[Topic]] = defaultdict(list)
        for innie in self.innies:
            for topic in innie.topics:
                for channel_config in topic.config.channels:
                    self.channels[channel_config.channel_id].append(topic)
        
        # Register event handlers and commands
        self._register_events()
        self._register_commands()

    def _create_intents(self) -> discord.Intents:
        """Set up Discord intents"""
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        return intents

    def _register_events(self):
        """Register all event handlers"""
        self.bot.event(self.on_ready)
        self.bot.event(self.on_message)

    def _register_commands(self):
        """Register all commands"""
        @self.bot.command(name='approve')
        async def approve(ctx):
            await self.approve_summary(ctx)
                    
        @self.bot.command(name='quit')
        async def quit(ctx):
            topic = self._identify_topic(ctx.channel.id)
            if not topic:
                await ctx.send(f"'quit' command ignored as there is no topic in this channel to support.")
                return
            topic_outie = topic.outie_config.outie_id
            if ctx.author.id != topic_outie:
                outie_name = getattr(ctx.guild.get_member(topic_outie), 'display_name', 'unknown')
                await ctx.send(f"This command is only available to the outie ({outie_name}).")
                return            
            await ctx.send("Goodbye! Bot shutting down...")
            await self.bot.close()
        
    def _identify_topic(self, channel_id) -> Optional[Topic]:
        topics = self.channels.get(channel_id, [])
        return topics[0] if topics else None

    def _identify_topic_by_message(self, message) -> Optional[Topic]:
        channel_id = message.channel.parent.id if message.channel.type == discord.ChannelType.public_thread else message.channel.id
        return self._identify_topic(channel_id)

    async def _should_follow_thread(self, thread, user):
        print(f"Checking if thread {thread.id} should be followed")
        try:
            # Get the starter message that created the thread
            starter_message = await thread.parent.fetch_message(thread.id)
            print(f"Starter message: [{starter_message.author}]: '{starter_message.content[:50]}...'")
            
            # Check multiple conditions
            is_mentioned = user.mentioned_in(starter_message)
            has_mention_string = f'<@{user.id}>' in starter_message.content
            is_bot_name_in_message = user.name.lower() in starter_message.content.lower()
            
            print(f"Mentioned: {is_mentioned}, Mention string: {has_mention_string}, " 
                f"Name in message: {is_bot_name_in_message}")
            
            # Follow thread if any condition is true
            should_follow = is_mentioned or has_mention_string or is_bot_name_in_message
            print(f"Thread {thread.id} {'should' if should_follow else 'should not'} be followed")
            return should_follow

        except (discord.NotFound, AttributeError) as e:
            print(f"Error checking starter message: {str(e)}")
            # Fallback: Check if the thread name contains the bot's name
            return user.name.lower() in thread.name.lower()
    
    async def get_thread_context(self, thread, limit=10):
        """Get recent messages from the thread for context"""
        messages = []
        async for message in thread.history(limit=limit):
            messages.append({
                "role": "assistant" if message.author == self.bot.user else "user",
                "content": message.content
            })
        
        # If we have fewer messages than the limit, get the parent message
        if len(messages) < limit:
            try:
                starter_message = await thread.parent.fetch_message(thread.id)
                messages.append({
                    "role": "user",
                    "content": starter_message.content
                })
            except (discord.NotFound, AttributeError) as e:
                print(f"Could not fetch parent message: {str(e)}")
        
        return list(reversed(messages))  # Return in chronological order
    
    async def process_and_respond(self, topic, channel, query, thread_id, context_channel):
        """Process a query and respond in the channel"""
        context_messages = await self.get_thread_context(context_channel) if context_channel else [{
            "role": "user",
            "content": query,
        }]
        # Add typing indicator while processing
        async with channel.typing():
            try:
                response = await topic.process_query(
                    query, 
                    thread_id,
                    context_messages=context_messages
                )
                if len(response) > 2000:
                    # Create a file object with the response
                    file = discord.File(io.BytesIO(response.encode()), filename="response.txt")
                    await channel.send("Response is too long, sending as a file:", file=file)
                else:
                    # Send as normal message if under limit
                    await channel.send(response)                
            except Exception as e:
                error_message = f"Sorry, I encountered an error while processing your request: {str(e)}"
                await channel.send(error_message)
                raise  # Re-raise the exception for logging/debugging
        
    
    async def on_ready(self):
        """Event handler for when the bot is ready"""
        print(f'{self.bot.user} has connected to Discord!')
        
        # Print all available guilds
        print(f"Available guilds:")
        for guild in self.bot.guilds:
            print(f"- {guild.name} (ID: {guild.id})")
        
        if not self.channels:
            print("No channels configured for this bot.")
            return
        innie = self.innies[0]
        outie_id = innie.outie_config.outie_id
        topic = innie.topics[0]
        channel = topic.config.channels[0]
        guild_id = channel.guild_id
        channel_id = channel.channel_id
        # Connect to specific guild/server
        guild = self.bot.get_guild(guild_id)
        if not guild:
            print(f"Could not connect to server with ID: {guild_id}")
            print("Please make sure the bot has been invited to this server.")
            print("Invite URL: https://discord.com/api/oauth2/authorize?client_id=1356846600692957315&permissions=377957210176&scope=bot")
            return
        # Get channel within the guild
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            print(f"Channel with ID: {channel_id} is not a text channel.")
            channel = None
        outie_member = guild.get_member(outie_id)
        if not channel:
            if outie_member:
                await outie_member.send(f"Bot {self.bot.user} is now online but could not find text channel with ID: {channel_id}")
            else:
                print(f"Could not find channel with ID: {channel_id} in server {guild.name} or outie user {outie_id}.")
            return
        await channel.send(f"Bot {self.bot.user} is connected, preparing documents...")
        scanning_result = await topic.scan_and_vectorize()
        mention = f"(fyi <@{outie_id}>)" if outie_member else f"(no outie user {outie_id})"
        await channel.send(f"{scanning_result} {mention}")
    
    async def on_message(self, message):
        """Event handler for when a message is received"""
        # Ignore messages from the bot itself
        if not self.bot.user or message.author == self.bot.user:
            return
        
        topic = self._identify_topic_by_message(message)
        if not topic:
            return
        print(f"On message, located topic: {topic.config.name}")
        outie_id = topic.outie_config.outie_id

        # Check if message is in a thread
        if message.channel.type == discord.ChannelType.public_thread:
            # Check if this is a thread we should be following
            starter_message = await message.channel.parent.fetch_message(message.channel.id)
            if (
                self.bot.user.mentioned_in(message) 
                or topic.is_following_thread(message.channel) 
                or await self._should_follow_thread(message.channel, self.bot.user)
            ):
                # Get recent context from the thread
                await self.process_and_respond(
                    topic,
                    message.channel,
                    message.content,
                    message.channel.id,
                    message.channel
                )
                return
            else:
                print(f"Not responding to thread")
                        
        # Check if bot is mentioned (for starting new threads)
        if self.bot.user.mentioned_in(message):
            # Create a new thread
            thread = await message.create_thread(name=f"Chat with {message.author.display_name}")        
            # Process the query and respond
            await self.process_and_respond(
                topic,
                thread,
                message.content.replace(f'<@{self.bot.user.id}>', '').strip(),
                thread.id,
                None
            )
            return
        
        # Check for outie commands
        elif message.author.id == outie_id and "summary and file" in message.content.lower():
            # This command should be used in a thread
            if message.channel.type == discord.ChannelType.public_thread:
                summary = await topic.generate_summary(message.channel.id)
                await message.channel.send(f"Summary generated:\n\n{summary}\n\nApprove to add to knowledge base? (yes/no)")
        
        # Check for consultation requests
        elif "please consult outie" in message.content.lower():
            if message.channel.type == discord.ChannelType.public_thread:
                outie_user = self.bot.get_user(outie_id)
                await message.channel.send(f"<@{outie_id}> Your consultation has been requested in this thread.")
        
        await self.bot.process_commands(message)
    
    async def approve_summary(self, ctx):
        topic = self._identify_topic_by_message(ctx.message)
        if not topic:
            return
        outie_id = topic.outie_config.outie_id
        if ctx.author.id == outie_id and ctx.channel.type == discord.ChannelType.public_thread:
            await topic.store_summary(ctx.channel.id)
            await ctx.send("Summary approved and added to knowledge base.")
    
    def run(self):
        """Run the bot"""
        self.bot.run(self.token)