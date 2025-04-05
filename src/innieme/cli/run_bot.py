import os, yaml
from dotenv import load_dotenv
from innieme.discord_bot import DiscordBot
from innieme.discord_bot_config import DiscordBotConfig

def load_config_from_yaml(file_path: str) -> DiscordBotConfig:
    with open(file_path, "r") as yaml_file:
        yaml_data = yaml.safe_load(yaml_file)
    return DiscordBotConfig(**yaml_data)

# Load environment variables
current_dir = os.getcwd()
yaml_path = os.path.join(current_dir, 'config.yaml')
config = load_config_from_yaml(yaml_path)
print(f"Loaded config: {config}")

def main():
    # Create and run the bot
    bot = DiscordBot(config)
    bot.run()

if __name__ == "__main__":
    main()