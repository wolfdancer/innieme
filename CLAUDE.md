# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

InnieMe is a Discord bot that provides AI-powered Q&A capabilities using document knowledge bases. The bot scans and vectorizes documents from specified directories, connects to Discord channels, and responds to user mentions with context-aware responses using configurable LLM providers via PydanticAI.

## Common Development Commands

### Installation and Setup
```bash
# Install dependencies
pip install -e .
pip install -r requirements-dev.txt

# Create configuration from example
cp config.example.yaml config.yaml
# Edit config.yaml with your Discord token, API keys, LLM model, and channel settings
```

### Running the Bot
```bash
# Run the bot (main entry point)
innieme_bot

# Or run directly with Python
python src/innieme/cli/run_bot.py
```

### Testing
```bash
# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/innieme

# Run async tests specifically
pytest -k "async" --asyncio-mode=strict
```

### Code Quality
```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint code
flake8 src/ tests/
```

## Architecture Overview

The application follows a modular architecture with clear separation of concerns:

### Core Components

1. **DiscordBot** (`src/innieme/discord_bot.py`): Main bot interface that handles Discord events, commands, and message routing
2. **Innie** (`src/innieme/innie.py`): Container class that manages multiple topics and their configurations
3. **Topic** (`src/innieme/innie.py`): Represents a single topic with its own document store, channels, and conversation engine
4. **ConversationEngine** (`src/innieme/conversation_engine.py`): Handles query processing and response generation using a PydanticAI `Agent`
5. **DocumentProcessor** (`src/innieme/document_processor.py`): Manages document scanning, vectorization, and similarity search
6. **KnowledgeManager** (`src/innieme/knowledge_manager.py`): Handles conversation summarization (via a PydanticAI `Agent` with structured `SummaryOutput`) and knowledge base storage

### Factory Pattern Components

- **EmbeddingsFactory** (`src/innieme/embeddings_factory.py`): Creates embedding instances (OpenAI, HuggingFace, or Fake)
- **VectorStoreFactory** (`src/innieme/vector_store_factory.py`): Creates vector store instances (Chroma, FAISS)

### Configuration System

The bot uses YAML configuration (`config.yaml`) with the following structure:
- Multiple "outies" (administrators) can be defined
- Each outie can have multiple topics
- Each topic has its own role/system prompt, document directory, and Discord channels
- Configuration is loaded via `DiscordBotConfig` class

Key top-level config fields:
- `embedding_model`: `"openai"`, `"huggingface"`, or `"fake"`
- `embeddings_api_key`: API key for the embedding model (required when `embedding_model` is `"openai"`)
- `llm_model`: PydanticAI model string, e.g. `"openai:gpt-4o"` or `"anthropic:claude-sonnet-4-6"`
- `llm_api_key`: API key for the LLM provider

### Bot Behavior

- Bot responds when mentioned in Discord channels
- Creates threaded conversations for each interaction
- Follows threads where it was mentioned or initially responded
- Supports admin commands like "summary and file" and "please consult outie"
- Admin can approve summaries to add to the knowledge base

## Key Implementation Details

### Thread Management
- New mentions create threads automatically
- Bot tracks active threads in `Topic.active_threads` set
- Thread context is preserved for conversation continuity

### Document Processing
- Documents are vectorized using configurable embedding models
- Vector stores support both Chroma and FAISS backends
- Document search provides context for LLM responses

### Response Generation
- Uses PydanticAI `Agent` with a configurable LLM (default: `openai:gpt-3.5-turbo`)
- LLM provider and model are set via `llm_model` in `config.yaml` (e.g. `"openai:gpt-4o"`, `"anthropic:claude-sonnet-4-6"`)
- Combines document context with conversation history via `ConversationDependencies`
- Handles responses longer than Discord's 2000 character limit by sending as files

### Error Handling
- Comprehensive logging with configurable levels (LOG_LEVEL, INNIEME_LOG_LEVEL environment variables)
- Graceful error messages sent to Discord users
- Exception re-raising for debugging purposes

## Testing Configuration

Tests are configured for async support with `pytest.ini` settings:
- `asyncio_mode = strict`
- Various warning filters for dependencies (faiss, pydantic, numpy, etc.)

## Environment Variables

- `LOG_LEVEL`: Global logging level (default: INFO)
- `INNIEME_LOG_LEVEL`: Package-specific logging level (default: INFO)