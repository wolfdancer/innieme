# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InnieMe is a multi-platform Q&A bot (Discord and Slack) backed by document knowledge bases.
It scans and vectorizes documents from configured directories and responds to user mentions
with context-aware answers, using a configurable LLM provider (OpenAI, Anthropic, …) via
[PydanticAI](https://ai.pydantic.dev/).

Requires Python >= 3.13 (see `pyproject.toml`).

## Development Commands

```bash
# Install (runtime + dev)
pip install -e .
pip install -r requirements.txt -r requirements-dev.txt

# Run a bot via the unified CLI (-c overrides the default config path)
innieme discord                       # default: discord_config.yaml
innieme discord -c custom_config.yaml
innieme slack                         # default: slack_config.yaml

# Legacy / dedicated entry points
innieme_bot          # Discord (== innieme.cli.run_bot:main)
innieme_slack_bot    # Slack   (== innieme.cli.run_slack_bot:main)

# Tests
pytest                                         # all
pytest tests/test_slack_bot.py                 # one file
pytest tests/test_slack_bot.py::test_name      # one test
pytest --cov=src/innieme                       # with coverage

# Code quality (CI runs flake8 against the whole repo — see below)
black src/ tests/
isort src/ tests/
flake8 . --select=E9,F63,F7,F82 --show-source --statistics            # hard-fail pass
flake8 . --exit-zero --max-complexity=10 --max-line-length=127 --statistics   # advisory
```

Dependency sources: `requirements.in` / `requirements-dev.in` are the pinned inputs;
`requirements.txt` / `requirements-dev.txt` are the compiled lockfiles that CI installs.

### Continuous Integration
`.github/workflows/python-app.yml` runs on push/PR to `main`: installs `requirements.txt`
+ `requirements-dev.txt` + `pip install -e .`, runs the two flake8 passes above (only the
first can fail the build), then `pytest`.

## Architecture

### Data flow

1. On startup, each `Topic` runs `scan_and_vectorize()` — documents in `docs_dir` are chunked
   (1000 chars, 200 overlap) and stored in an **in-memory** Chroma collection using **cosine**
   distance. Each chunk carries a `source` metadata field holding its file path. A new collection
   is created every startup; there is no persistence.
2. On mention/message, the bot identifies the `Topic` for that channel, gets the `thread_id`,
   and calls `Topic.process_query()`.
3. `ConversationEngine` runs a similarity search (`retrieval_top_k` chunks, default 5) and invokes
   a PydanticAI `Agent` whose system prompt is built from `ConversationDependencies` (topic `role`
   + matched doc chunks + thread conversation history). Chunks are rendered by
   `conversation_engine._format_chunk()`, which prefixes each with `[source: <basename>]` so the
   model can attribute an answer to a file. When `retrieval_score_threshold` is set,
   `search_documents()` scores results and drops those below the floor, falling back to an
   unfiltered search if the store cannot produce relevance scores.
4. The LLM is configurable via `llm_model` (default `openai:gpt-5.6-terra`); the provider/model
   string and `llm_api_key` are resolved in `conversation_engine._build_model()`.

### Core components

- **DiscordBot** (`src/innieme/discord_bot.py`) / **SlackBot** (`src/innieme/slack_bot.py`):
  platform adapters that handle events, commands, and message routing.
- **Innie** / **Topic** (`src/innieme/innie.py`): `Innie` holds an outie's topics; `Topic` owns
  one topic's document store, channels, and conversation engine.
- **ConversationEngine** (`src/innieme/conversation_engine.py`): query → response via a
  PydanticAI `Agent`. Imports `TopicConfig` from `discord_bot_config` — shared by both platforms
  since the config shapes are identical.
- **DocumentProcessor** (`src/innieme/document_processor.py`): scanning, vectorization,
  similarity search.
- **KnowledgeManager** (`src/innieme/knowledge_manager.py`): conversation summarization via a
  PydanticAI `Agent` with structured `SummaryOutput`, plus knowledge-base storage.
- **EmbeddingsFactory** (`embeddings_factory.py`) / **VectorStoreFactory**
  (`vector_store_factory.py`): pluggable embeddings (OpenAI/HuggingFace/Fake) and vector stores
  (Chroma/FAISS).

### Config → runtime object hierarchy

Both `DiscordBotConfig` (`discord_bot_config.py`) and `SlackBotConfig` (`slack_bot_config.py`)
share the same nested YAML shape:

```
BotConfig                                # top-level: tokens, model/key fields
  └── outies: List[OutieConfig]          # admins
        └── topics: List[TopicConfig]    # knowledge domains (role, docs_dir)
              └── channels: List[ChannelConfig]   # where the bot listens
```

`TopicConfig` also carries `docs_exclude`: filename patterns skipped when scanning that topic's
`docs_dir`, matched against both the basename and the `docs_dir`-relative path. It is **per topic,
not bot-level** — each document set has its own non-content files. Unset uses
`DEFAULT_DOCS_EXCLUDE` (`["CLAUDE.md"]`) in `document_processor.py`; an explicit `[]` scans
everything. Instruction files must stay out of the corpus: a retrieved chunk of directives is read
as instructions to follow and can override the answering prompt's own rules.

Pydantic models wire **back-references** via `model_validator(mode='after')`: `OutieConfig.bot`,
`TopicConfig.outie`, `ChannelConfig.topic`. This lets any nested object reach its parent config
(e.g. `Topic.__init__` reads `outie_config.bot.llm_model`) without threading arguments around.

Both bot configs expose the same model/key fields, read by `Innie`/`Topic`:
- `embedding_model`: `"openai"`, `"huggingface"`, or `"fake"`
- `embeddings_model_name`: optional embedding model name. Unset means the backend's own default —
  `text-embedding-3-small` (OpenAI) or `all-MiniLM-L6-v2` (HuggingFace), each declared as
  `DEFAULT_MODEL` on its factory in `embeddings_factory.py`
- `embeddings_api_key`: API key for the embedding model (required when `embedding_model` is `"openai"`)
- `llm_model`: PydanticAI model string, e.g. `"openai:gpt-5.6-terra"` or `"anthropic:claude-sonnet-5"`
- `llm_api_key`: API key for the LLM provider
- `cache_dir`: optional embedding-model cache location (`huggingface` backend only; supports `~`).
  Falls back to `<docs_dir>/.cache/langchain` — see `Topic._resolve_cache_dir()`
- `retrieval_top_k`: max chunks sent as context per query (default 5)
- `retrieval_score_threshold`: optional relevance floor (0–1). Unset means no filtering

The optional fields are read with `getattr(..., None)` so a config predating them still works.

Platform differences:
- Discord: `discord_token`; `outie_id`/`guild_id`/`channel_id` are **integers**; thread IDs are
  Discord integer IDs.
- Slack: `slack_bot_token` + `slack_app_token` (Socket Mode); `outie_id` (`U…`) and `channel_id`
  (`C…`) are **strings**; thread IDs are Slack message timestamps (strings).

### Channel → Topic routing

Both bots build a `defaultdict[channel_id, List[Topic]]` at init. `_identify_topic(channel_id)`
returns the first topic for a channel. A channel can map to multiple topics, but only the first
is used.

### Thread tracking

`Topic.active_threads` is the set of thread IDs the bot is actively following. A mention adds the
thread ID; subsequent messages in that thread are answered automatically without another mention.

### Bot behavior & admin workflow

- Responds when mentioned; creates/follows a thread per interaction.
- Users can ask to "please consult outie" to bring in an admin.
- Admins can summarize a thread ("summary and file" on Discord, `/approve` etc. on Slack) and
  approve the summary to be stored into the knowledge base (`./data/summaries/`).
- Slack admin (outie) commands are **mentions**, not slash commands — `@bot rescan` re-vectorizes
  the topic's documents without a restart, `@bot quit` shuts the bot down. A slash command has to
  be declared in the Slack app config as well as in code, so it cannot ship in the repo alone;
  `parse_bot_command()` requires the whole message to be the command, so questions that merely
  contain the word still go to the model. Slack delivers both `app_mention` and `message` for the
  same text, so `handle_message` deliberately ignores commands that `handle_mention` already ran.

### Embedding & vector store selection

`embedding_model` selects the embeddings backend (use `fake` in tests to avoid real API calls);
`embeddings_model_name` selects the model within that backend. The vector store backend is
**hardcoded to Chroma** in `innie.py` (`FAISSVectorStoreFactory` is present but commented out).

`ChromaVectorStoreFactory` sets `hnsw:space: cosine` on every collection. This is deliberate:
cosine is the right metric for text embeddings, and Chroma's default squared-L2 produces
normalized relevance scores that can go negative, which makes `retrieval_score_threshold`
meaningless. Do not drop `COLLECTION_METADATA` without also revisiting the threshold logic.

Note `huggingface` needs `sentence-transformers`, which is **not** in `requirements.txt` — that
backend raises an `ImportError` until it is installed separately.

### Response length limits

- Discord: 2000 chars — overflow sent as a `response.txt` file attachment.
- Slack: `SLACK_MESSAGE_LIMIT` (3900 chars) — overflow is split across sequential thread
  messages by `slack_bot.split_for_slack()`, which prefers paragraph then line boundaries and
  closes/reopens a code fence that spans parts. Slack itself recommends staying under 4,000
  chars and truncates at 40,000. The old `files_upload` path is gone: that endpoint was retired
  in March 2025, and a downloadable file reads worse than messages for a summary.

## Configuration

Copy the example file(s) for the platform(s) you run and fill in credentials:

```bash
cp discord_config.example.yaml discord_config.yaml  # Discord
cp slack_config.example.yaml slack_config.yaml      # Slack
```

The `role` field in each topic is the LLM system prompt. Each topic has its own `docs_dir` and
set of channels. The CLI loads the config from the current working directory by default, so run
from the project root (or pass `-c`).

## Environment Variables

- `LOG_LEVEL`: root logger level (default `INFO`)
- `INNIEME_LOG_LEVEL`: `innieme` package logger level (default `INFO`)
