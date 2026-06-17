#!/usr/bin/env python3
"""
Unified CLI for running either Discord or Slack bots
"""

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Discord config was renamed from config.yaml to discord_config.yaml. The old
# name is still accepted as a fallback so existing setups keep working.
DISCORD_CONFIG_NAME = "discord_config.yaml"
LEGACY_DISCORD_CONFIG_NAME = "config.yaml"

def resolve_discord_config_path(cwd: str = None) -> str:
    """Return the default Discord config path.

    Prefers ``discord_config.yaml``. If that file is absent but the legacy
    ``config.yaml`` exists, returns the legacy path with a deprecation warning.
    """
    cwd = cwd or os.getcwd()
    preferred = os.path.join(cwd, DISCORD_CONFIG_NAME)
    legacy = os.path.join(cwd, LEGACY_DISCORD_CONFIG_NAME)
    if not os.path.exists(preferred) and os.path.exists(legacy):
        logger.warning(
            "'%s' is deprecated; please rename it to '%s'.",
            LEGACY_DISCORD_CONFIG_NAME, DISCORD_CONFIG_NAME,
        )
        return legacy
    return preferred

def setup_logging():
    """Set up logging configuration"""
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

def run_discord_bot(config_path: str = None):
    """Run the Discord bot"""
    from innieme.discord_bot import DiscordBot
    from innieme.discord_bot_config import DiscordBotConfig
    
    if not config_path:
        config_path = resolve_discord_config_path()

    try:
        with open(config_path, "r") as yaml_file:
            yaml_content = yaml_file.read()
        config = DiscordBotConfig.from_yaml(yaml_content)
        print(f"Loaded Discord config from {config_path}")
        
        bot = DiscordBot(config)
        bot.run()
    except FileNotFoundError:
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading Discord config: {e}")
        sys.exit(1)

def run_slack_bot(config_path: str = None):
    """Run the Slack bot"""
    from innieme.slack_bot import SlackBot
    from innieme.slack_bot_config import SlackBotConfig
    
    if not config_path:
        config_path = os.path.join(os.getcwd(), 'slack_config.yaml')
    
    try:
        with open(config_path, "r") as yaml_file:
            yaml_content = yaml_file.read()
        config = SlackBotConfig.from_yaml(yaml_content)
        print(f"Loaded Slack config from {config_path}")
        
        bot = SlackBot(config)
        bot.run()
    except FileNotFoundError:
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading Slack config: {e}")
        sys.exit(1)

def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(
        description="InnieMe Bot - Run Discord or Slack bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s discord                    # Run Discord bot with default discord_config.yaml
  %(prog)s slack                      # Run Slack bot with default slack_config.yaml
  %(prog)s discord -c my_config.yaml  # Run Discord bot with custom config
  %(prog)s slack -c my_slack.yaml     # Run Slack bot with custom config
        """
    )
    
    parser.add_argument(
        'platform',
        choices=['discord', 'slack'],
        help='Platform to run the bot on'
    )
    
    parser.add_argument(
        '-c', '--config',
        help='Path to configuration file'
    )
    
    args = parser.parse_args()
    
    if args.platform == 'discord':
        run_discord_bot(args.config)
    elif args.platform == 'slack':
        run_slack_bot(args.config)

if __name__ == "__main__":
    main()