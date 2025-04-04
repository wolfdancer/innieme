import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from .document_processor import DocumentProcessor
from .conversation_engine import ConversationEngine
from .knowledge_manager import KnowledgeManager
import importlib
import sys
from datetime import datetime
class DiscordBot:
    def __init__(self, token, admin_id, guild_id, channel_id, docs_dir):
        """Initialize the Discord bot with the necessary components"""
        self.token = token
        self.admin_id = admin_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.docs_dir = docs_dir
        
        # Bot setup with required intents
        self.intents = discord.Intents.default()
        self.intents.message_content = True
        self.intents.members = True
        self.intents.guilds = True
        self.bot = commands.Bot(command_prefix='!', intents=self.intents)
        
        # Initialize components
        self.document_processor = DocumentProcessor(
            self.docs_dir, 
            embedding_type="openai",
            embedding_config={"api_key": os.getenv("OPENAI_API_KEY")}
        )
        
        self.knowledge_manager = KnowledgeManager()
        self.conversation_engine = ConversationEngine(
            self.document_processor, 
            self.knowledge_manager, 
            self.admin_id
        )
        
        # Store original modules for reloading
        self.original_modules = {}
        
        # Register event handlers and commands
        self._register_events()
        self._register_commands()
    
    def _register_events(self):
        """Register all event handlers"""
        self.bot.event(self.on_ready)
        self.bot.event(self.on_message)
    
    def _register_commands(self):
        """Register all commands"""
        @self.bot.command(name='approve')
        async def approve(ctx):
            await self.approve_summary(ctx)
            
        @self.bot.command(name='reload')
        async def reload(ctx):
            await self.reload_modules(ctx)

    async def _should_follow_thread(self, thread, user):
        """Check if this is a thread we should be following"""
        print(f"Checking thread with name: {thread.name}")
        # First check the cache
        if self.conversation_engine.is_following_thread(thread):
            return True
        
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
    
    async def process_and_respond(self, channel, query, thread_id, context_channel):
        """Process a query and respond in the channel"""
        context_messages = await self.get_thread_context(context_channel) if context_channel else [{
            "role": "user",
            "content": query,
        }]
        
        # Add typing indicator while processing
        async with channel.typing():
            response = await self.conversation_engine.process_query(
                query, 
                thread_id,
                context_messages=context_messages
            )
        
        await channel.send(response)
    
    async def on_ready(self):
        """Event handler for when the bot is ready"""
        print(f'{self.bot.user} has connected to Discord!')
        
        # Print all available guilds
        print(f"Available guilds:")
        for guild in self.bot.guilds:
            print(f"- {guild.name} (ID: {guild.id})")
        
        # Connect to specific guild/server
        guild = self.bot.get_guild(self.guild_id)
        if not guild:
            print(f"Could not connect to server with ID: {self.guild_id}")
            print("Please make sure the bot has been invited to this server.")
            print("Invite URL: https://discord.com/api/oauth2/authorize?client_id=1356846600692957315&permissions=377957210176&scope=bot")
            return
        # Get channel within the guild
        channel = guild.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            print(f"Channel with ID: {self.channel_id} is not a text channel.")
            channel = None
        admin_member = guild.get_member(self.admin_id)
        if not channel:
            if admin_member:
                await admin_member.send(f"Bot {self.bot.user} is now online but could not find text channel with ID: {self.channel_id}")
            else:
                print(f"Could not find channel with ID: {self.channel_id} in server {guild.name} or admin user {self.admin_id}.")
            return
        await channel.send(f"Bot {self.bot.user} is connected, preparing documents...")
        scanning_result = await self.document_processor.scan_and_vectorize()
        mention = f"(fyi <@{self.admin_id}>)" if self.admin_id else f"(no admin user {self.admin_id})"
        await channel.send(f"{scanning_result} (fyi {mention})")
    
    async def on_message(self, message):
        """Event handler for when a message is received"""
        # Ignore messages from the bot itself
        if not self.bot.user or message.author == self.bot.user:
            return
        
        # Check if message is in a thread
        if message.channel.type == discord.ChannelType.public_thread:
            # Check if this is a thread we should be following
            starter_message = await message.channel.parent.fetch_message(message.channel.id)
            print(f"Starter message: [{starter_message.author}]: '{starter_message.content[:50]}...'")
            if await self._should_follow_thread(message.channel, self.bot.user):
                # Get recent context from the thread
                await self.process_and_respond(
                    message.channel,
                    message.content,
                    message.channel.id,
                    message.channel
                )
                return
        
        # Check if bot is mentioned (for starting new threads)
        if self.bot.user.mentioned_in(message):
            # Create a new thread
            thread = await message.create_thread(name=f"Chat with {message.author.display_name}")        
            # Process the query and respond
            await self.process_and_respond(
                thread,
                message.content.replace(f'<@{self.bot.user.id}>', '').strip(),
                thread.id,
                None
            )
            return
        
        # Check for admin commands
        elif message.author.id == self.admin_id and "summary and file" in message.content.lower():
            # This command should be used in a thread
            if message.channel.type == discord.ChannelType.public_thread:
                summary = await self.knowledge_manager.generate_summary(message.channel.id)
                await message.channel.send(f"Summary generated:\n\n{summary}\n\nApprove to add to knowledge base? (yes/no)")
        
        # Check for consultation requests
        elif "please consult outie" in message.content.lower():
            if message.channel.type == discord.ChannelType.public_thread:
                admin_user = self.bot.get_user(self.admin_id)
                await message.channel.send(f"<@{self.admin_id}> Your consultation has been requested in this thread.")
        
        await self.bot.process_commands(message)
    
    async def approve_summary(self, ctx):
        """Command to approve a summary and add it to the knowledge base"""
        if ctx.author.id == self.admin_id and ctx.channel.type == discord.ChannelType.public_thread:
            await self.knowledge_manager.store_summary(ctx.channel.id)
            await ctx.send("Summary approved and added to knowledge base.")
    
    async def reload_modules(self, ctx):
        """Reload bot modules without restarting the bot (admin only)"""
        if ctx.author.id != self.admin_id:
            await ctx.send("This command is only available to the admin.")
            return
        
        try:
            # Store original modules if not already stored
            if not self.original_modules:
                for module_name in sys.modules:
                    if module_name.startswith('innieme_bot'):
                        self.original_modules[module_name] = sys.modules[module_name]
            
            # Reload the modules
            for module_name in self.original_modules:
                if module_name in sys.modules:
                    print(f"Reloading module: {module_name}")
                    importlib.reload(sys.modules[module_name])
            
            # Update the conversation engine with the new modules
            self.document_processor = DocumentProcessor(
                self.docs_dir, 
                embedding_type="openai",
                embedding_config={"api_key": os.getenv("OPENAI_API_KEY")}
            )
            
            self.knowledge_manager = KnowledgeManager()
            self.conversation_engine = ConversationEngine(
                self.document_processor, 
                self.knowledge_manager, 
                self.admin_id
            )
            await ctx.send("✅ Bot modules reloaded successfully!")
            print("Bot modules reloaded successfully")
        except Exception as e:
            await ctx.send(f"❌ Error reloading modules: {str(e)}")
            print(f"Error reloading modules: {str(e)}")
    
    def run(self):
        """Run the bot"""
        self.bot.run(self.token)