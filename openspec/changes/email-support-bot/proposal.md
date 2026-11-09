# Proposal

## Why

Scouts need a way to ask the troop's knowledge base questions without joining a Slack workspace or Discord server; email is what they already have. Youth-protection practice ("two-deep leadership") requires an adult to see every exchange, so an email bot must only answer when the outie and one of the scout's own guardians are copied.

## What Changes

- Add email as a third platform: `innieme email` runs a bot that polls one mailbox per topic over **POP3** (every 5 minutes by default) and replies over **SMTP**. POP3 because the first mailbox (Dynadot) offers no IMAP on its plan.
- Classify every incoming message by sender and recipients:
  - auto-generated mail (out-of-office, lists, bounces) and unknown senders: deleted, logged;
  - the outie: no reply (they are answering the scout and copying the bot);
  - a guardian: a setup note (not repeated in reply to one) explaining the bot is for scouts who copy the outie and a guardian;
  - a scout who copied the outie and at least one of **their own** guardians: answered from the topic's documents;
  - a scout who did not: a rule reminder naming their guardians (not repeated in reply to one).
- Answers go to the scout, Cc the outie and the guardians who were on the scout's email, threaded with `In-Reply-To`/`References`, marked `Auto-Submitted: auto-replied`, as plain text plus HTML.
- Read email the way a model can use it: HTML converted to markdown, the new text taken as the question and the quoted history as thread context, signatures stripped, attachments ignored (and the reply says so).
- No persistent store: every message is deleted from the server once handled; a message whose handling fails stays and is retried next poll (a reply the mail server permanently refuses is not retried until restart); anything still on the server after `retention_days` (default 30) is deleted. A reply goes to all its recipients or none. Whether a reply chain already has a setup note or reminder is read from the Message-IDs of the bot's own replies in its headers.
- New config file `email_config.yaml`: bot → outies (`outie_email`) → topics, each with a `mailbox` (POP3/SMTP host, port, address, password) and `scouts`, each with their own `guardians`.
- No admin commands over email in this change.

## Capabilities

### New Capabilities
- `email-bot`: the email platform — mailbox polling and deletion, sender/recipient classification and the responses for each class, reading questions and context out of a message, reply addressing and threading, and its configuration.

### Modified Capabilities
- `answer-freshness-awareness`: the "applies on every platform" requirement names Discord and Slack; it extends to email answers, which share the same answering path.

## Impact

- New: `src/innieme/email_bot.py`, `src/innieme/email_bot_config.py`, `src/innieme/cli/run_email_bot.py`, `email_config.example.yaml`, tests.
- Changed: `cli/run_unified_bot.py` (`email` platform), `pyproject.toml` (`innieme_email_bot` entry point; `markdownify`, `markdown-it-py` and a quote-splitting dependency via `uv add`), `.gitignore` (`/email_config.yaml`), `CLAUDE.md`.
- Reused: `Topic`, `ConversationEngine`, `DocumentProcessor`. One opt-in addition: `process_query` can re-raise model errors instead of returning an apology, so a failed answer leaves the email for retry; Discord and Slack behavior is unchanged. `Topic` reads `outie_config.bot.*` fields, so the email config must expose the same bot-level model/key fields.
- Operational: messages are deleted permanently from the mailbox; the bot's logs are the only record of what arrived. Uses stdlib `poplib`/`smtplib` via `asyncio.to_thread`.
