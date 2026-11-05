# Proposal

## Why

The document index is a snapshot, but nothing records when it was taken or what it was taken from. In a Slack thread the bot could not say when the last scan ran or whether a note had been edited since, and could only tell people to ask the outie for a `rescan`. Neither the bot nor its users can tell a current answer from one built on a stale note, and a rescan gives no indication of what it cost.

## What Changes

- Each completed scan records an **index snapshot**: start and end time, read time vs. index time, chunk count, files that could not be read, and an mtime + size stamp for every candidate file.
- A **staleness check** compares the snapshot with the directory using `stat` only (no re-reading, no embedding) and reports files modified, new, or removed since the scan.
- The **answering model is told about freshness**: a retrieved chunk whose source changed since indexing is labelled as such, and the system prompt carries a count-only note with the index build time.
- New Slack mention command **`@bot status`** reports last scan time, duration, file and chunk counts, and freshness. The channel reply shows counts only; file names go to the outie in a private (ephemeral) message.
- **`@bot rescan` is open to everyone** (previously outie-only) and its reply states how long the scan took. `quit` remains outie-only.
- Concurrent scans of one topic are **serialized**, since rescan is now open to everyone.

Not changing: scanning, chunking, the vector store, or retrieval. Discord gets no new commands (it has no rescan today), but because Discord and Slack share one answering path, Discord answers receive the same chunk labels and freshness note.

## Capabilities

### New Capabilities
- `index-freshness`: what a scan records about itself, and how the index is compared with its source files to determine what is stale.
- `answer-freshness-awareness`: how freshness is conveyed to the answering model so answers can flag possibly out-of-date material.
- `slack-bot-commands`: the mention commands (`status`, `rescan`, `quit`, `hello`), who may run them, and what they report. Only the behavior touched by this change is specified; `hello` is out of scope.

### Modified Capabilities
<!-- None: openspec/specs/ is empty, so there is nothing to modify. -->

## Impact

- Code: `document_processor.py` (snapshot, staleness check, scan lock), `conversation_engine.py` (chunk labels, prompt note), `slack_bot.py` (new command, access change, rescan timing), `innie.py` (accessors), plus a new module for snapshot types and report formatting.
- Behavior: every answer's system prompt gains a short index-freshness paragraph; `rescan` becomes available to any channel member.
- Cost/risk: one directory walk per 30s of query activity per topic; any channel member can trigger embedding calls via `rescan`.
- Dependencies: none added.
- Reference only: a working prototype exists on branch `shane/innieme-index-freshness-b802b6` (closed PR wolfdancer/innieme#73). It is input for the apply step, not a decision this proposal depends on.

## Non-goals

- Automatically rescanning when files are stale.
- Re-indexing individual files; a rescan still rebuilds the whole index.
- Persisting the snapshot across restarts (the index is rebuilt at startup).
- Content hashing; mtime + size is deliberately sufficient.
- `status` or `rescan` commands on Discord (freshness awareness in Discord *answers* is in scope).
