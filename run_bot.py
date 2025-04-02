import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from innieme_bot.document_processor import DocumentProcessor
from innieme_bot.conversation_engine import ConversationEngine
from innieme_bot.knowledge_manager import KnowledgeManager

# Load environment variables
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(env_path)
TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_USER_ID'))
DOCS_DIR = os.getenv('DOCUMENTS_DIRECTORY')
GUILD_ID = int(os.getenv('GUILD_ID'))
CHANNEL_ID = int(os.getenv('CHANNEL_ID'))

# Bot setup with required intents
intents = discord.Intents.all()  # Use all intents for maximum compatibility
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
            await channel.send("Bot is online and ready to assist!")

# Rest of the code remains the same...

def main():
    bot.run(TOKEN)

if __name__ == "__main__":
    main()