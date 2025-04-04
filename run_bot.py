import os
from dotenv import load_dotenv
from innieme_bot.discord_bot import DiscordBot

# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(env_path)
TOKEN = os.getenv('DISCORD_TOKEN')
OUTIE_ID = int(os.getenv('OUTIE_USER_ID', 0))
DOCS_DIR = os.path.join(current_dir, os.getenv('DOCUMENTS_DIRECTORY', 'documents'))
GUILD_ID = int(os.getenv('GUILD_ID', 0))
CHANNEL_ID = int(os.getenv('CHANNEL_ID', 0))

def main():
    # Create and run the bot
    bot = DiscordBot(
        token=TOKEN,
        outie_id=OUTIE_ID,
        guild_id=GUILD_ID,
        channel_id=CHANNEL_ID,
        docs_dir=DOCS_DIR
    )
    bot.run()

if __name__ == "__main__":
    main()