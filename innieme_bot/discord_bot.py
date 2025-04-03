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
        self.intents = discord.Intents.all()  # Use all intents for maximum compatibility
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
    
    async def is_following_thread(self, thread):
        """Check if this is a thread we should be following"""
        print(f"Checking thread with name: {thread.name}")
        # First check the cache
        if self.conversation_engine.is_following_thread(thread):
            return True
        
        print(f"Checking if thread {thread.id} should be followed")
        try:
            # If not in cache, check the first message
            # Get the thread's starter message (the message that created the thread)
            print("checking first 10 messages")
            async for message in thread.history(oldest_first=True, limit=10):
                print(f"[{message.author}]: '{message.content[:50]}...'")
                
                # Check multiple conditions
                is_mentioned = self.bot.user.mentioned_in(message)
                has_mention_string = f'<@{self.bot.user.id}>' in message.content
                is_bot_name_in_message = self.bot.user.name.lower() in message.content.lower()
                
                print(f"Mentioned: {is_mentioned}, Mention string: {has_mention_string}, " 
                    f"Name in message: {is_bot_name_in_message}")
                
                # Follow thread if any condition is true
                should_follow = is_mentioned or has_mention_string or is_bot_name_in_message
                print(f"Thread {thread.id} {'should' if should_follow else 'should not'} be followed")
                return should_follow

            # If we get here, there are no messages in the thread (unlikely)
            print(f"Thread {thread.id} has no messages, checking thread name")
            return self.bot.user.name.lower() in thread.name.lower()
        except (discord.NotFound, AttributeError) as e:
            print(f"Thread {thread.id} not found or error: {str(e)}")
            # Fallback: Check if the thread name contains the bot's name
            return self.bot.user.name.lower() in thread.name.lower()
    
    async def get_thread_context(self, thread, limit=10):
        """Get recent messages from the thread for context"""
        messages = []
        async for message in thread.history(limit=limit):
            messages.append({
                "role": "assistant" if message.author == self.bot.user else "user",
                "content": message.content,
                "timestamp": message.created_at.isoformat()
            })
        return list(reversed(messages))  # Return in chronological order
    
    async def process_and_respond(self, channel, query, thread_id, context_channel):
        """Process a query and respond in the channel"""
        context_messages = await self.get_thread_context(context_channel) if context_channel else [{
            "role": "user",
            "content": query,
            "timestamp": datetime.now().isoformat()
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
        if guild:
            print(f"Connected to server: {guild.name}")
        else:
            print(f"Could not connect to server with ID: {self.guild_id}")
            print("Please make sure the bot has been invited to this server.")
            print("Invite URL: https://discord.com/api/oauth2/authorize?client_id=1356846600692957315&permissions=377957124096&scope=bot")
            # Continue anyway as the bot might still be useful in other servers
        
        # Rest of the function remains the same
        if guild:
            # Get channel within the guild
            channel = guild.get_channel(self.channel_id)
            if channel:
                print(f"Found channel: {channel.name}")
            else:
                print(f"Could not find channel with ID: {self.channel_id} in server {guild.name}")
            
            # Notify admin user (try to find them in the guild first)
            admin_member = guild.get_member(self.admin_id)
            if admin_member:
                try:
                    await admin_member.send(f"Bot {self.bot.user} is now online!")
                    print(f"Notified admin user: {admin_member.display_name}")
                except discord.Forbidden:
                    print("Could not DM admin user - they may have DMs disabled")
            else:
                print(f"Could not find admin user with ID: {self.admin_id} in server {guild.name}")
                
            # Vectorize documents on startup
            await self.document_processor.scan_and_vectorize()
            print("Document vectorization complete")
            
            # Optional: Send a startup message to the channel
            if channel:
                await channel.send("Online and ready to assist!")
    
    async def on_message(self, message):
        """Event handler for when a message is received"""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return
        
        # Check if message is in a thread
        if message.channel.type == discord.ChannelType.public_thread:
            # Check if this is a thread we should be following
            print("picked up a message in a thread")
            if await self.is_following_thread(message.channel):
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