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
  testing) and any PydanticAI LLM (e.g. `openai:gpt-5.6-terra`, `anthropic:claude-sonnet-5`).
- **Threaded conversations** — each mention spins up a thread and the bot follows it for context.
- **Multi-topic** — define multiple topics, each with its own system prompt, documents, and
  channels, owned by one or more admins who own the documents.

## How it works

1. On startup the bot reads its config, vectorizes the documents for each configured topic, and
   connects to the chat platform.
2. When mentioned in a watched channel, it retrieves the most relevant document chunks, builds a
   prompt (topic role + context + conversation history), and replies in a thread. Each chunk is
   labelled with the file it came from, so the model can attribute an answer to a source document.

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

| Field | Default | Description |
| --- | --- | --- |
| `embedding_model` | — | `"openai"`, `"huggingface"`, or `"fake"` (use `fake` in tests to avoid API calls) |
| `embeddings_model_name` | per backend | Embedding model name. Unset means the backend's default: `text-embedding-3-small` (OpenAI) or `all-MiniLM-L6-v2` (HuggingFace) |
| `embeddings_api_key` | — | API key for the embedding model (required for `openai`) |
| `llm_model` | `openai:gpt-5.6-terra` | PydanticAI model string, e.g. `"openai:gpt-5.6-terra"` or `"anthropic:claude-sonnet-5"` |
| `llm_api_key` | — | API key for the LLM provider |
| `cache_dir` | `<docs_dir>/.cache/langchain` | Where downloaded embedding models are cached. Only used by the `huggingface` backend; supports `~` |
| `retrieval_top_k` | `5` | Maximum document chunks sent to the model as context per query |
| `retrieval_score_threshold` | unset | Optional relevance floor (0–1). Drops weak matches instead of padding context out to `retrieval_top_k` |
| `outies` | — | List of admins, each with one or more `topics` |

Per-topic fields, inside each entry of a topic list:

| Field | Default | Description |
| --- | --- | --- |
| `name` | — | Topic name |
| `role` | — | The topic's system prompt |
| `docs_dir` | — | Directory of documents to ingest for this topic |
| `docs_exclude` | `["CLAUDE.md"]` | Filename patterns to skip when scanning this topic's `docs_dir`. Set to `[]` to scan everything |
| `channels` | — | Channels where this topic answers |

### Tuning retrieval

`retrieval_top_k` caps how much document context each answer is built from. Raising it improves
recall on questions that span several documents, at the cost of more input tokens — and of more
irrelevant context, which degrades answer quality more often than it helps.

`retrieval_score_threshold` makes the count adaptive: chunks are still capped at
`retrieval_top_k`, but any scoring below the floor are dropped, so a narrow question returns only
the two or three chunks that actually matter. It is unset by default, which is the safe choice —
setting it too high makes the bot report that something is absent when it is present. Pick a
value by measuring rather than guessing: compare the scores for questions you know your documents
answer against questions you know they do not, and choose a value between the two ranges. If the
ranges overlap, no threshold will separate them and it should stay off.

Chroma collections use cosine distance, which is the appropriate metric for text embeddings and
keeps relevance scores in a usable 0–1 range.

### Excluding files from the knowledge base

`docs_exclude` is set **per topic**, next to that topic's `docs_dir` — different document sets
have different non-content files, so one global list would be wrong for most of them. Each pattern
is matched against both the filename and the path relative to `docs_dir`, so `CLAUDE.md` skips that
file at any depth while `archive/*` skips a subdirectory.

It defaults to `["CLAUDE.md"]`. Agent instruction files are not subject-matter content, and
ingesting them is actively harmful: a retrieved chunk of instructions reads to the model as
directions to follow, so rules written for one task ("always produce a next action, even if it's a
guess") can override the answering prompt's rules ("never invent a next step"). Set `docs_exclude`
to `[]` to scan everything.

The startup message reports how many files were excluded, and the logs name each one. The count
goes to the channel but the names do not: a file is often excluded precisely because the people
in that channel should not know about it, while whoever configured the bot can read the logs.

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

### Slack commands

Ask a question by mentioning the bot, or by replying in a thread it is already following. The
bot also understands three commands, given the same way:

| Command | Who can use it | What it does |
| --- | --- | --- |
| `@bot hello` | anyone | Posts the introduction card. Works in any channel, even one with no topic configured, so it doubles as an "is this thing running?" check. |
| `@bot rescan` | the topic's outie | Re-reads and re-vectorizes the topic's `docs_dir`. Use it after editing your documents — there is no need to restart. If the scan fails, the previous index keeps serving answers. |
| `@bot quit` | the topic's outie | Shuts the bot down, process included. |

The whole message has to be the command, so `@bot rescan` runs a rescan while `@bot should we
rescan the notes?` is answered as a question.

These are **mentions, not slash commands**, deliberately: a slash command must be declared in
your Slack app's configuration as well as in the code, so it cannot work on a fresh install
without extra setup, whereas a mention works as soon as the bot is running.

`/approve` (approve a generated summary into the knowledge base) is the one remaining slash
command, so it does need declaring under **Features → Slash Commands** in your Slack app to be
reachable.

> **Upgrading:** `/quit` and `/hello` used to be slash commands and are now the mentions above.
> If you declared either in your Slack app configuration, delete it there — otherwise Slack keeps
> offering a command the bot no longer handles.

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
