# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InnieMe is a multi-platform bot (Discord and Slack) that provides AI-powered Q&A using document knowledge bases. It scans and vectorizes documents from configured directories and responds to user mentions with context-aware answers via OpenAI's GPT models.

## Development Commands

```bash
# Install
pip install -e .
pip install -r requirements-dev.txt

# Run Discord bot (default: config.yaml)
innieme discord
innieme discord -c custom_config.yaml

# Run Slack bot (default: slack_config.yaml)
innieme slack

# Run all tests
pytest

# Run a single test file
pytest tests/test_slack_bot.py

# Run a specific test
pytest tests/test_slack_bot.py::test_identify_topic

# With coverage
pytest --cov=src/innieme

# Format / lint
black src/ tests/
isort src/ tests/
flake8 src/ tests/
```

## Architecture

### Data flow

1. On startup, each `Topic` runs `scan_and_vectorize()` — documents in `docs_dir` are chunked (1000 chars, 200 overlap) and stored in an **in-memory** Chroma collection. A new collection is created every startup; there is no persistence.
2. On mention/message, the bot identifies the `Topic` for that channel, retrieves the `thread_id`, and calls `Topic.process_query()`.
3. `ConversationEngine` does a similarity search (top-5 chunks) and constructs an OpenAI chat completion with: system prompt (`role`) + matched doc chunks + thread conversation history.
4. OpenAI model: `gpt-3.5-turbo`, `temperature=0.1`, `max_tokens=1000`.

### Config → runtime object hierarchy

Both `DiscordBotConfig` and `SlackBotConfig` share the same YAML shape:

```
BotConfig
  └── outies: List[OutieConfig]       # admins
        └── topics: List[TopicConfig]  # knowledge domains
              └── channels: List[ChannelConfig]  # where bot listens
```

Pydantic models wire **back-references** via `model_validator(mode='after')`: `OutieConfig.bot`, `TopicConfig.outie`, `ChannelConfig.topic`. This lets any nested object reach its parent config without extra arguments being passed around.

Key difference between platforms:
- Discord: `outie_id`, `guild_id`, `channel_id` are **integers**; thread IDs are Discord integer IDs.
- Slack: `outie_id` (`U...`), `channel_id` (`C...`) are **strings**; thread IDs are Slack message timestamps (strings).

`ConversationEngine` imports `TopicConfig` from `discord_bot_config` — this is shared by both platforms since the config shapes are identical.

### Channel → Topic routing

Both `DiscordBot` and `SlackBot` build a `defaultdict[channel_id, List[Topic]]` at init time. `_identify_topic(channel_id)` returns the first topic for a channel. A channel can theoretically map to multiple topics but only the first is used.

### Thread tracking

`Topic.active_threads` is a set of thread IDs the bot is actively following. When a user mentions the bot, the thread ID is added to this set. Subsequent messages in that thread are then answered automatically without needing another mention.

### Embedding model selection

Configured via `embedding_model` in the YAML. Options: `openai`, `huggingface`, `fake`. Use `fake` in tests to avoid real API calls. The vector store backend is **hardcoded to Chroma** in `innie.py` (`FAISSVectorStoreFactory` is present but commented out).

### KnowledgeManager (partial implementation)

`KnowledgeManager.generate_summary()` is a placeholder — it returns a static string, not an actual LLM summary. `store_summary()` saves the pending summary to `./data/summaries/` as JSON. The approval workflow (`!approve` / `/approve`) exists but thread tracking for approval is not fully wired in the Slack bot.

### Response length limits

- Discord: 2000 chars — overflow sent as `response.txt` file attachment.
- Slack: 4000 chars — overflow uploaded via `files_upload`.

## Configuration

Copy the example files and fill in credentials:

```bash
cp config.example.yaml config.yaml          # Discord
cp slack_config.example.yaml slack_config.yaml  # Slack
```

The `role` field in each topic is the LLM system prompt. Each topic has its own `docs_dir` and set of channels.

## Environment Variables

- `LOG_LEVEL`: Root logger level (default: `INFO`)
- `INNIEME_LOG_LEVEL`: `innieme` package logger level (default: `INFO`)
