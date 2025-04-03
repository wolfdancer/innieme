import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from innieme_bot.document_processor import DocumentProcessor
from innieme_bot.conversation_engine import ConversationEngine
from innieme_bot.knowledge_manager import KnowledgeManager

# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)
TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_USER_ID'))
DOCS_DIR = os.path.join(current_dir, os.getenv('DOCUMENTS_DIRECTORY'))
GUILD_ID = int(os.getenv('GUILD_ID'))
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

# Bot setup with required intents
intents = discord.Intents.all()  # Use all intents for maximum compatibility
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize components
# document_processor = DocumentProcessor(DOCS_DIR, embedding_type="fake")
# for OpenAI embeddings
document_processor = DocumentProcessor(
    DOCS_DIR, 
    embedding_type="openai",
    embedding_config={"api_key": os.getenv("OPENAI_API_KEY")}
)

knowledge_manager = KnowledgeManager()
conversation_engine = ConversationEngine(document_processor, knowledge_manager, ADMIN_ID)

async def is_following_thread(thread):
    """Check if this is a thread we should be following"""
    # First check the cache
    if conversation_engine.is_following_thread(thread):
        return True
    
    try:
        # If not in cache, check the first message
        first_message = await thread.fetch_message(thread.id)
        is_bot_thread = bot.user.mentioned_in(first_message)
        return is_bot_thread
    except discord.NotFound:
        return False

async def get_thread_context(thread, limit=10):
    """Get recent messages from the thread for context"""
    messages = []
    async for message in thread.history(limit=limit):
        messages.append({
            "role": "assistant" if message.author == bot.user else "user",
            "content": message.content,
            "timestamp": message.created_at.isoformat()
        })
    return list(reversed(messages))  # Return in chronological order

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    
    # Print all available guilds
    print(f"Available guilds:")
    for guild in bot.guilds:
        print(f"- {guild.name} (ID: {guild.id})")
    
    # Connect to specific guild/server
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f"Connected to server: {guild.name}")
    else:
        print(f"Could not connect to server with ID: {GUILD_ID}")
        print("Please make sure the bot has been invited to this server.")
        print("Invite URL: https://discord.com/api/oauth2/authorize?client_id=1356846600692957315&permissions=377957124096&scope=bot")
        # Continue anyway as the bot might still be useful in other servers
    
    # Rest of the function remains the same
    if guild:
        # Get channel within the guild
        channel = guild.get_channel(CHANNEL_ID)
        if channel:
            print(f"Found channel: {channel.name}")
        else:
            print(f"Could not find channel with ID: {CHANNEL_ID} in server {guild.name}")
        
        # Notify admin user (try to find them in the guild first)
        admin_member = guild.get_member(ADMIN_ID)
        if admin_member:
            try:
                await admin_member.send(f"Bot {bot.user} is now online!")
                print(f"Notified admin user: {admin_member.display_name}")
            except discord.Forbidden:
                print("Could not DM admin user - they may have DMs disabled")
        else:
            print(f"Could not find admin user with ID: {ADMIN_ID} in server {guild.name}")
            
        # Vectorize documents on startup
        await document_processor.scan_and_vectorize()
        print("Document vectorization complete")
        
        # Optional: Send a startup message to the channel
        if channel:
            await channel.send("Online and ready to assist!")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Check if message is in a thread
    if message.channel.type == discord.ChannelType.public_thread:
        # Check if this is a thread we should be following
        if await is_following_thread(message.channel):
            # Get recent context from the thread
            context_messages = await get_thread_context(message.channel)
            # Process the query with context and respond
            response = await conversation_engine.process_query(
                message.content, 
                message.channel.id,
                context_messages=context_messages
            )
            await message.channel.send(response)
            return
    
    # Check if bot is mentioned (for starting new threads)
    if bot.user.mentioned_in(message):
        # Create a new thread
        thread = await message.create_thread(name=f"Chat with {message.author.display_name}")        
        # Process the query and respond
        query = message.content.replace(f'<@{bot.user.id}>', '').strip()
        response = await conversation_engine.process_query(query, thread.id)
        await thread.send(response)
        return
    
    # Check for admin commands
    elif message.author.id == ADMIN_ID and "summary and file" in message.content.lower():
        # This command should be used in a thread
        if message.channel.type == discord.ChannelType.public_thread:
            summary = await knowledge_manager.generate_summary(message.channel.id)
            await message.channel.send(f"Summary generated:\n\n{summary}\n\nApprove to add to knowledge base? (yes/no)")
    
    # Check for consultation requests
    elif "please consult outie" in message.content.lower():
        if message.channel.type == discord.ChannelType.public_thread:
            admin_user = bot.get_user(ADMIN_ID)
            await message.channel.send(f"<@{ADMIN_ID}> Your consultation has been requested in this thread.")
    
    await bot.process_commands(message)

@bot.command(name='approve')
async def approve_summary(ctx):
    if ctx.author.id == ADMIN_ID and ctx.channel.type == discord.ChannelType.public_thread:
        await knowledge_manager.store_summary(ctx.channel.id)
        await ctx.send("Summary approved and added to knowledge base.")

def main():
    bot.run(TOKEN)

if __name__ == "__main__":
    main()