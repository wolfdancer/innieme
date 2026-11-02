# Review profile

## Review

InnieMe is a Discord/Slack Q&A bot (Python 3.13, uv, PydanticAI, Chroma, LangChain 1.x). `CLAUDE.md` describes the architecture, config hierarchy and platform differences; read it first, since Codex gets no `AGENTS.md` here.

- Source is under `src/innieme/`; tests under `tests/`. Discord and Slack adapters (`discord_bot.py`, `slack_bot.py`) mirror each other; a change to one usually needs the other checked.
- OpenSpec lives under `openspec/`. When a change's files are in scope, review against its proposal, design and delta specs (`openspec/changes/<name>/`); otherwise against `CLAUDE.md` and the surrounding code.
- Treat as BLOCKING, beyond bugs and spec violations: dropping Chroma's cosine `COLLECTION_METADATA` without revisiting `retrieval_score_threshold`; reading new optional config fields without `getattr(..., None)`; instruction files (e.g. `CLAUDE.md`) leaking into the document corpus; dependency changes not reflected in `uv.lock`; real credentials or IDs in committed files.

## Validate

- `uv run pytest`
- `uv run flake8 . --select=E9,F63,F7,F82 --show-source --statistics` (the hard-fail pass CI runs)
- `uv run black --check` and `uv run isort --check` on the changed Python files, when there are any
- `openspec validate <change> --strict`, when an OpenSpec change is in play

## Sensitive data

This repo is public-facing: real configs live outside it, and `docs_dir` contents are confidential.

- Real data looks like: bot/app/LLM/embedding API tokens (`xoxb-`, `xapp-`, `sk-` prefixes), real Slack/Discord workspace, channel, guild or user IDs, real people's or companies' names, and text copied from private documents.
- Not a hit: the synthetic sample company Northwind and names already used in committed fixtures.
- Placeholders: Northwind names, IDs like `C0000000000`, `xxxxxxxxxx` for secrets. Never borrow names from private docs for fixtures.
- Treat as binaries (stop and ask before committing): PDFs, images, spreadsheets, `.env`-style files, `*_config.yaml` (non-example) files.
