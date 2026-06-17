# InnieMe

InnieMe is a chat bot that answers questions from your own documents. Point it at a directory
of files, connect it to a chat channel, and it responds to mentions with context-aware answers
backed by a vector search over your knowledge base — using the LLM provider of your choice
(OpenAI, Anthropic, …) via [PydanticAI](https://ai.pydantic.dev/).

It currently supports **Discord** and **Slack**. It's built for teams that keep answering the
same questions: instead of repeating yourself (DRY), let InnieMe field the routine ones from
your docs and keep each interaction in its own thread.

## Features

- **Multi-platform** — run the same knowledge bot on Discord or Slack from one codebase and CLI.
- **Document-grounded answers** — scans and vectorizes a documents directory and uses similarity
  search to ground every response.
- **Pluggable models** — choose your embedding backend (`openai`, `huggingface`, or `fake` for
  testing) and any PydanticAI LLM (e.g. `openai:gpt-4o`, `anthropic:claude-sonnet-4-6`).
- **Threaded conversations** — each mention spins up a thread and the bot follows it for context.
- **Multi-topic** — define multiple topics, each with its own system prompt, documents, and
  channels, owned by one or more admins who own the documents.

## How it works

1. On startup the bot reads its config, vectorizes the documents for each configured topic, and
   connects to the chat platform.
2. When mentioned in a watched channel, it retrieves relevant document context, builds a prompt
   (topic role + context + conversation history), and replies in a thread.

## Prerequisites

- Python **3.13+**
- A bot for your platform (Discord bot token, or Slack bot + app tokens) and the IDs of the
  server/channel(s) it should watch
- An API key for your chosen LLM provider (and for embeddings, if using OpenAI embeddings)

`discord_config.example.yaml` (Discord) and `slack_config.example.yaml` (Slack) include
step-by-step instructions for obtaining each token/ID.

## Installation

```bash
git clone https://github.com/wolfdancer/innieme.git
cd innieme

# (recommended) create a virtual environment
python -m venv .venv && source .venv/bin/activate

# install the package and its dependencies
pip install -e .
```

## Configuration

Copy the example config for your platform and fill in your values:

```bash
cp discord_config.example.yaml discord_config.yaml  # Discord
cp slack_config.example.yaml slack_config.yaml      # Slack
```

Common fields (both platforms):

| Field | Description |
| --- | --- |
| `embedding_model` | `"openai"`, `"huggingface"`, or `"fake"` |
| `embeddings_api_key` | API key for the embedding model (required for `openai`) |
| `llm_model` | PydanticAI model string, e.g. `"openai:gpt-4o"` or `"anthropic:claude-sonnet-4-6"` |
| `llm_api_key` | API key for the LLM provider |
| `outies` | List of admins, each with one or more `topics` (role/system prompt, `docs_dir`, and channels) |

Platform-specific fields:

- **Discord**: `discord_token`; `outie_id`/`guild_id`/`channel_id` are numeric IDs.
- **Slack**: `slack_bot_token` + `slack_app_token` (Socket Mode); `outie_id` (`U…`) and
  `channel_id` (`C…`) are strings.

Place the documents you want the bot to learn from in the `docs_dir` configured for each topic.

## Running

Use the unified CLI and pick a platform. It loads the config from the current working directory
by default (run from the project root), or pass `-c` to point elsewhere:

```bash
innieme discord                       # uses ./discord_config.yaml
innieme slack                         # uses ./slack_config.yaml
innieme discord -c custom_config.yaml
```

Logging is controlled by environment variables: `LOG_LEVEL` (global, default `INFO`) and
`INNIEME_LOG_LEVEL` (this package, default `INFO`).

### Docker

```bash
docker build -t innieme .

# Discord (default command)
docker run -v "$(pwd)/discord_config.yaml:/app/discord_config.yaml" -v "$(pwd)/data:/app/data" innieme

# Slack — pass the platform as the command
docker run -v "$(pwd)/slack_config.yaml:/app/slack_config.yaml" -v "$(pwd)/data:/app/data" innieme slack
```

## Development

```bash
# install dev dependencies
pip install -e . && pip install -r requirements-dev.txt

# run the test suite
pytest

# format, sort imports, and lint
black src/ tests/
isort src/ tests/
flake8 .
```

## License

See [LICENSE](LICENSE).
