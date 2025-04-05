import os
from innieme.discord_bot import DiscordBot
from innieme.discord_bot_config import DiscordBotConfig

# Load environment variables
current_dir = os.getcwd()
yaml_path = os.path.join(current_dir, 'config.yaml')
with open(yaml_path, "r") as yaml_file:
    yaml_content = yaml_file.read()
config = DiscordBotConfig.from_yaml(yaml_content)
print(f"Loaded config from {yaml_path}")

def main():
    # Create and run the bot
    bot = DiscordBot(config)
    bot.run()

if __name__ == "__main__":
    main()