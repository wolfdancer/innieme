# Tasks

## 1. Dependencies

- [ ] 1.1 Compare reply-parsing libraries (`mail-parser-reply`, `email-reply-parser`) on sample Gmail, Outlook and Apple Mail replies, plain and HTML-converted; record the pick and its license in design.md
- [ ] 1.2 `uv add markdownify markdown-it-py <reply parser>` and verify `uv sync --locked` succeeds and the three import under `uv run python -c`

## 2. Configuration

- [ ] 2.1 Add `email_bot_config.py` (`EmailBotConfig` → `OutieConfig` with `outie_email` and `outie_id` property → `TopicConfig` with `mailbox` and `scouts[{email, guardians}]`), bot-level fields matching `SlackBotConfig` plus `poll_interval_seconds=300`, `retention_days=30`, back-references, case-insensitive addresses; verify with tests that a valid config loads and `Topic`/`ConversationEngine` can be built from it with `embedding_model: fake`
- [ ] 2.2 Add load-time validation (scout without guardians, scout also a guardian, mailbox address equal to outie/scout/guardian, misplaced `docs_exclude`, missing `docs_dir`); verify each case fails in a test whose error names the address
- [ ] 2.3 Add `email_config.example.yaml` with comments (Dynadot POP3/SMTP example, scouts with guardians) and `/email_config.yaml` to `.gitignore`; verify the example loads in a test

## 3. Model failures

- [ ] 3.1 Add opt-in `raise_errors=False` to `ConversationEngine.process_query` and `Topic.process_query`; verify with a test where the real agent's model raises (PydanticAI `FunctionModel`) that `raise_errors=True` propagates the exception and the default still returns the apology, and that existing Slack/Discord tests pass unchanged

## 4. Reading messages

- [ ] 4.1 Implement body extraction (plain part, else HTML → markdown via markdownify, images dropped) and attachment detection; verify with tests on plain, HTML-only and multipart-with-PDF fixtures
- [ ] 4.2 Implement question / quoted-history split, signature removal and history → `context_messages` (oldest first, mailbox address → `assistant`, current question appended as the final `user` entry), with whole-body fallback; verify with Gmail, Outlook, Apple Mail and no-quote fixtures
- [ ] 4.3 Implement the size cap (newest kept, oldest history dropped first); verify with a long-chain fixture

## 5. Classification

- [ ] 5.1 Implement auto-generated detection (all headers in the spec, empty return path, delivery reports) and bounce recipient extraction; verify each signal with a fixture test
- [ ] 5.2 Implement sender classification (unknown / outie / guardian / scout) and the copy rule (outie + one of the scout's own guardians in To/Cc); verify with tests including another scout's guardian not counting
- [ ] 5.3 Implement bot Message-IDs `<innieme.{kind}.{uuid}@domain>` and prior-reply detection from `References`/`In-Reply-To`; verify in tests that a reply to a reminder gets no second reminder, two sibling replies to the same original each get one, and reminder → corrected question → answer → rule-breaking reply gets no reminder
- [ ] 5.4 Implement retention by `Date`, falling back to `Received`, undatable never expiring; verify with tests at 29/31 days and with no date

## 6. Replying

- [ ] 6.1 Compose replies: recipients from config only (answer: To scout, Cc outie + guardians present on the original), `Re:` without stacking, `In-Reply-To`/`References` (falling back to incoming `In-Reply-To` when `References` is absent), `Auto-Submitted: auto-replied`, plain + HTML parts; verify with tests asserting headers, the `References` fallback, and that an extra Cc'd friend is excluded
- [ ] 6.2 Implement all-or-nothing SMTP sending (`MAIL FROM`, `RCPT TO` per recipient, `RSET` and fail on any refusal, `DATA` only when all accepted); verify with a fake SMTP server test where one of three recipients is refused and no message data is sent
- [ ] 6.3 Add setup-note and rule-reminder templates (placeholder wording; reminder names the scout's guardians), attachment notice, and the `outie please` reply; verify rendered text in tests

## 7. Mailbox and poll loop

- [ ] 7.1 Implement the POP3 client over `asyncio.to_thread`: read session (UIDL + RETR + QUIT) and delete session (UIDL lookup + DELE + QUIT); verify with tests against a fake `poplib.POP3_SSL`, including a UID missing at delete time
- [ ] 7.2 Implement `EmailBot`: scan topics at start, one poll loop per topic at `poll_interval_seconds`, handle each message per the classification order, delete only after SMTP success, keep failed messages, skip UIDs in flight, log every message's classification and action, isolate one mailbox's errors from the others; verify with tests using fake POP3/SMTP and `FakeEmbeddings`, covering answer, reminder, setup note, outie, unknown, auto-generated, SMTP failure and partial recipient refusal (message kept, nothing sent) and model failure via `raise_errors=True` (message kept, nothing sent)
- [ ] 7.3 Verify answers go through `Topic.process_query` with the parsed history, so freshness labels reach the model as on Slack (test with a real `ConversationEngine` and a recording model asserting the agent receives the question and a history containing a single quoted answer)

## 8. CLI and docs

- [ ] 8.1 Add `cli/run_email_bot.py`, the `email` platform in `run_unified_bot.py` (default `email_config.yaml`), and the `innieme_email_bot` script in `pyproject.toml`; verify `uv run innieme email -c missing.yaml` exits with the config-not-found error and `uv run innieme --help` lists `email`
- [ ] 8.2 Update `CLAUDE.md` (platforms, commands, email config fields, POP3 / delete-after-handling behavior, roles and copy rule); verify the documented commands match the CLI

## 9. Integration

- [ ] 9.1 Run `uv run pytest` and the hard-fail flake8 pass; both clean
- [ ] 9.2 Manual check against the Dynadot mailbox with a test config: a scout email copying outie + guardian is answered in-thread with correct Cc; one missing the outie gets a single reminder; an unknown sender's mail disappears; logs show each action

## Workflow follow-up

- Finalize the setup-note and reminder wording with the user.
- Archive the change after review and merge.
