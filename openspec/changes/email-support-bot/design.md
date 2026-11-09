# Design

## Context

Discord and Slack are push platforms: an event arrives, the adapter routes it by channel to a `Topic`, fetches thread history from the platform API, and calls `Topic.process_query()`. Email has no push here and no history API: the first mailbox (Dynadot, `webhost.dynadot.com`) offers **POP3 + SMTP only** on its current plan, confirmed by logging in — IMAP rejects the same credentials. POP3 has no folders, flags or Sent, so nothing can be marked or moved on the server; the only server-side operations are list, read and delete.

Two constraints from the existing code:
- `Topic` and `ConversationEngine` read bot-level fields through back-references (`outie_config.bot.llm_model`, `topic.outie.bot.retrieval_top_k`, …) and `topic.outie.outie_id`. The email config must expose the same names.
- InnieMe keeps no state across restarts; the user chose to keep it that way for email (see proposal).

## Goals / Non-Goals

**Goals:**
- Reuse `Topic` / `ConversationEngine` / `DocumentProcessor`, with one opt-in change (see *Model failures*) and no behavior change for Discord or Slack.
- Correct behavior across restarts with no local storage.
- A message is never silently lost because of a transient failure (model, SMTP, network).

**Non-Goals:**
- IMAP, OAuth (Gmail API / Microsoft Graph), IMAP IDLE push.
- Admin commands over email (`status`, `rescan`, `quit`).
- Verifying the sender (DKIM/DMARC via `Authentication-Results`). A forged `From` of a scout still needs the outie and a real guardian copied, who then see the answer.
- Reading attachments.
- Final wording of the setup note and rule reminder (placeholders until decided).

## Decisions

### Platform adapter shaped like the other two
New `email_bot.py` (`EmailBot`), `email_bot_config.py` (`EmailBotConfig`), `cli/run_email_bot.py`, an `email` choice in `run_unified_bot.py` (default `email_config.yaml`), and an `innieme_email_bot` script. `EmailBot.run()` builds an `Innie` per outie, scans each topic once (`scan_and_vectorize()`, as Slack's `connect_and_prepare` does), then runs one asyncio poll loop per topic.

### Config shape
```
EmailBotConfig        tokens-style secrets inline; llm/embedding/retrieval fields
                      identical to SlackBotConfig; poll_interval_seconds=300;
                      retention_days=30
  └── outies[]: OutieConfig        outie_email (+ property outie_id -> outie_email)
        └── topics[]: TopicConfig  name, role, docs_dir, docs_exclude,
                                   mailbox: {address, username=address,
                                             password, pop_host, pop_port=995,
                                             smtp_host, smtp_port=587}
                                   scouts[]: {email, guardians[]}
```
`outie_id` as a property lets `ConversationEngine` read the outie without changes to how it does so. Addresses are compared case-insensitively and normalized at load. Validation per the spec (scout without guardians, scout/guardian overlap, mailbox address colliding with a person). `docs_dir` existence and misplaced-`docs_exclude` checks are copied from the Slack config. Alternative considered: extracting a shared base config for all three platforms — worthwhile, but a refactor of two working platforms; out of scope here.

### POP3 sessions: short, keyed by UIDL
POP3 only commits `DELE` on a clean `QUIT`, and servers drop idle sessions; holding one open while the model answers (seconds to a minute per message) risks rolling back every delete in that session and re-answering. So each poll:

1. **Read session**: connect, `UIDL`, fetch every message (`RETR`), `QUIT`.
2. Handle each message in memory (classify → maybe reply).
3. **Delete session**: right after each message is handled, connect, `UIDL`, `DELE` the matching number, `QUIT`. One short session per message, not one batch at the end of the poll, so a crash mid-poll can duplicate at most the one reply in flight. A message is deleted only after its reply was accepted by SMTP.

UIDL identifies a message across sessions; message numbers do not. A message that failed stays, is fetched again next poll. Each topic's loop awaits its whole poll before sleeping, so polls of one mailbox never overlap and no in-flight bookkeeping is needed. `poplib`/`smtplib` are blocking stdlib modules, called through `asyncio.to_thread` — no new network dependency. Alternative: `aioimaplib`-style async libraries — none needed for POP3 at this volume.

### Classification order
```
auto-generated? ─yes─▶ delete (warn if bounce)
      │no
unknown sender? ─yes─▶ delete, log sender
      │no
outie? ──────────yes─▶ delete
      │no
guardian? ───────yes─▶ setup note unless one is in its chain ─▶ delete
      │no (scout)
outie + own guardian in To/Cc? ─no─▶ reminder unless one is in its chain ─▶ delete
      │yes
answer ─▶ delete
```
Auto-generated is checked first so a scout's out-of-office never earns a reminder. Retention (older than `retention_days` by the newest `Received` header, which the receiving server stamps, falling back to `Date`, which the sender's clock sets; undatable messages never expire) is checked before all of it.

### Earlier bot replies via the bot's own Message-IDs
Outgoing replies get `Message-ID: <innieme.{kind}.{uuid}@{mailbox domain}>` with `kind` ∈ `answer`, `reminder`, `setup`. A reply carries its ancestors' IDs in `References`/`In-Reply-To`, so "this chain already has a reminder" is a regex over two headers. Stateless and restart-proof. Headers record ancestry, not the whole thread: two sibling replies to the same original each look like the first, so each can earn a note. The spec states this limitation. Alternative: an in-memory set — lost on restart, and still per process.

### Model failures
`ConversationEngine._generate_response` catches agent exceptions and returns an apology string, which is right for chat but would make the email bot send the apology and delete the question. Add an opt-in `raise_errors: bool = False` to `ConversationEngine.process_query`; when true the exception propagates. Discord and Slack keep the default. The email bot passes `True`, so a model failure leaves the message for the next poll.

The email bot calls `topic.conversation_engine.process_query` directly, not `Topic.process_query`: the latter adds the thread to `active_threads` and `thread_history`, chat bookkeeping for Slack/Discord thread-following and summaries. Email has neither feature and rebuilds history from the quote each time, so going through `Topic` would only grow both collections for the life of the process, on success and failure alike.

### Reading a message
- Body: `text/plain` part if present, else `text/html` converted with **markdownify** (MIT); images dropped, links kept. Converted blockquotes become `>` lines, so one splitter handles both.
- Split new text from quoted history with a reply-parsing library (candidates: `mail-parser-reply`, `email-reply-parser`; pick by license and Gmail/Outlook/Apple coverage), falling back to "whole body is the question".
- Quoted history becomes `context_messages`, oldest first: split at attribution lines ("On … wrote:") where found; a quoted message from the mailbox address gets role `assistant`, others `user`; if it cannot be split, one `user` message holding the whole quote. The **current question is appended as the final `user` entry**, matching what Slack and Discord pass: `_generate_response` drops the last entry as the current query, so omitting it would silently lose the newest quoted message.
- Cap: total text to the model limited (e.g. 12k characters), trimming oldest history first.
- The engine's exact-match `outie please` shortcut returns a Slack-style `<@id>` mention; the email adapter answers that phrase itself ("the outie is already copied on this thread") rather than passing it through.

### Composing replies
`EmailMessage` with plain text (model markdown as-is) and HTML (markdown rendered to HTML with `markdown-it-py`, already in the lockfile transitively, added as a direct dependency, with raw HTML disabled — `MarkdownIt("commonmark", {"html": False})` — so HTML the model echoes from a scout's message or a document is escaped, not sent as live markup), `Re:` subject without stacking, `In-Reply-To` = incoming `Message-ID`, `References` = incoming `References` (or, when absent, the single ID in incoming `In-Reply-To`, per RFC 5322 §3.6.4) + incoming `Message-ID`, `Auto-Submitted: auto-replied`. Recipients computed from config, never copied wholesale from the incoming headers.

Sent via SMTP STARTTLS on 587 with the mailbox credentials, all-or-nothing: `smtplib.sendmail` succeeds when only *some* recipients are accepted, which could answer the scout without the adults (or the reverse) and then delete the question. So the bot drives the envelope itself — `MAIL FROM`, then `RCPT TO` for each recipient; if any is refused, `RSET` and treat it as a failure (message kept); only when all are accepted, `DATA`.

## Risks / Trade-offs

- [Permanent delete; logs are the only trace] → log sender, subject, classification and action for every message at INFO; misconfiguration (typo in a scout address) shows up as "unknown sender" lines.
- [Crash after SMTP accepts, before delete] → duplicate answer next poll. Accepted by the user as rare.
- [Quoted history trimmed by clients or top/bottom-posting variety] → partial context; the answer still uses the documents. Fallback keeps the question intact.
- [Sibling replies, or clients that truncate `References`] → a second note or reminder in the same conversation. Low cost; acceptable for a stateless design.
- [A recipient permanently refused, e.g. a mistyped guardian address] → nothing is answered and the message stays until `retention_days` deletes it. To avoid re-running the model every poll for a reply that cannot be delivered, a permanent (5xx) `RCPT` refusal adds the message's UID to an in-memory skip set for the life of the process (lost on restart, which retries once — consistent with keeping no stored state); transient (4xx) refusals and model failures are retried each poll. Logged as a warning naming the refused address, so the config error is visible.
- [Forged `From` of a scout] → still requires outie + a guardian copied, who see the answer; sender verification is a later change.
- [Prompt injection from scout text] → same exposure as Slack/Discord; the sender set is closed and every answer is copied to adults.
- [Dynadot POP3 maildrop lock / connection limits] → sessions are short and sequential per mailbox.
- [Re-indexing per platform] → running email alongside Slack scans documents twice; acceptable, same as running Slack and Discord today.

## Migration Plan

New platform; no existing behavior changes. Deploy: `cp email_config.example.yaml email_config.yaml`, fill credentials and people, `uv run innieme email`. Rollback: stop the process. `/email_config.yaml` is added to `.gitignore`.

## Open Questions

- Wording of the guardian setup note and the scout rule reminder (placeholders until then).
- Which reply-parsing library, decided by a quick comparison against sample Gmail/Outlook/Apple Mail replies.
