from innieme.discord_bot import DiscordBot
from innieme.discord_bot_config import DiscordBotConfig
from innieme.cli.run_unified_bot import resolve_discord_config_path

import logging
import os

# Configure root logger with LOG_LEVEL
log_level_name = os.environ.get("LOG_LEVEL", "INFO")
log_level = getattr(logging, log_level_name.upper(), logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s %(levelname)-8s %(name)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Configure innieme package logger with INNIEME_LOG_LEVEL
innieme_log_level_name = os.environ.get("INNIEME_LOG_LEVEL", "INFO")
innieme_log_level = getattr(logging, innieme_log_level_name.upper(), logging.INFO)
innieme_logger = logging.getLogger("innieme")
innieme_logger.setLevel(innieme_log_level)

# Load configuration (prefers discord_config.yaml, falls back to config.yaml)
yaml_path = resolve_discord_config_path()
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