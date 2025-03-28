import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from .document_processor import DocumentProcessor
from .conversation_engine import ConversationEngine
from .knowledge_manager import KnowledgeManager

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_USER_ID'))
DOCS_DIR = os.getenv('DOCUMENTS_DIRECTORY')
GUILD_ID = int(os.getenv('GUILD_ID'))
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

# Bot setup with required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Initialize components
document_processor = DocumentProcessor(DOCS_DIR, embedding_type="fake")
''' for OpenAI embeddings
document_processor = DocumentProcessor(
    DOCS_DIR, 
    embedding_type="openai",
    embedding_config={"api_key": os.getenv("OPENAI_API_KEY")}
)
'''
knowledge_manager = KnowledgeManager()
conversation_engine = ConversationEngine(document_processor, knowledge_manager, ADMIN_ID)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    # Vectorize documents on startup
    await document_processor.scan_and_vectorize()
    print("Document vectorization complete")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Check if bot is mentioned
    if bot.user.mentioned_in(message):
        # If message is in a thread, use that thread
        # Otherwise create a new thread
        if message.channel.type == discord.ChannelType.public_thread:
            thread = message.channel
        else:
            thread = await message.create_thread(name=f"Chat with {message.author.display_name}")
        
        # Process the query and respond
        query = message.content.replace(f'<@{bot.user.id}>', '').strip()
        response = await conversation_engine.process_query(query, message.author.id, thread.id)
        await thread.send(response)
    
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