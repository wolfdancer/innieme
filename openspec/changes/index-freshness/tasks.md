# Tasks

The branch `shane/innieme-index-freshness-b802b6` (closed PR wolfdancer/innieme#73) holds a prototype that can be consulted, but each task is to be implemented and verified against the specs, not copied.

## 1. Snapshot and staleness check

- [ ] 1.1 Add snapshot and freshness types and age/duration/timestamp formatting (new module); verify with unit tests for formatting edge cases (seconds, minutes, hours, days, negative)
- [ ] 1.2 Record a snapshot on each completed scan, stamping files before reading and keeping the previous snapshot when a scan fails; verify with tests for: stat failure recorded as failed, fields populated, no-scan-yet, mid-scan edit reads as stale, failed scan keeps old snapshot, unreadable file recorded as failed, all-empty corpus (no errors) still succeeds, all-error corpus fails, mixed empty-and-error corpus fails and preserves the old index, partial failure with some text succeeds
- [ ] 1.3 Implement the stat-only staleness check with the 30 s reuse window and an explicit force option; verify with tests for modified (size and mtime-only), new, removed, excluded files, unchanged failed file, repaired failed file, empty file gaining text, no snapshot, cache vs. forced, cache not reused across snapshots
- [ ] 1.4 Serialize scans per topic with a lock; verify with a test that two concurrent scans never overlap
- [ ] 1.5 Publish the store and snapshot as one object, and expose the snapshot and an off-thread forced check on the topic (the check takes the snapshot as an argument, runs one at a time per topic, uses a single directory walk); verify a test that a stuck routine check is not duplicated, that an explicit check waits and then re-runs, and `uv run pytest` passes and the hard-fail flake8 pass is clean

## 2. Model awareness

- [ ] 2.1 Label chunks from modified and from deleted sources in the model's context; verify tests cover modified, deleted, unchanged, other-file, and missing-metadata chunks
- [ ] 2.2 Add the count-only freshness note to the system prompt (absent before first scan, "no change" when current, hedging direction when stale, no file names); verify with prompt-building tests
- [ ] 2.3 Capture the snapshot at retrieval time, judge freshness against it, run the check off the event loop with a 5 s bound, and treat failure or timeout as non-fatal; verify with tests where the check raises, where it never completes, and where a rescan lands between retrieval and the freshness result
- [ ] 2.4 Confirm the shared answering path applies to Discord; verify with a test that a Discord-configured topic's model context carries the labels and note

## 3. Slack commands

- [ ] 3.1 Add `status` to the mention commands and make `rescan` open to everyone while `quit` stays outie-only; verify parse tests (`status` is a command, "what is the status?" is not) and access tests for each command and requester
- [ ] 3.2 Implement the `status` reply (counts-only channel reply; names to the outie in an ephemeral message, escaped, never in channel or model history; no-scan and failure replies without paths; channel reply survives a failed private send); verify with tests including a hostile file name and that thread context excludes the private message
- [ ] 3.3 Report the scan's own duration (from its result, excluding queue wait) in the `rescan` reply without turning a successful scan into a reported failure; verify with a test for the success text and the existing failed-rescan tests
- [ ] 3.4 Update CLAUDE.md for the new commands, access change and freshness behavior; verify the documented commands match `BOT_COMMANDS` and the access rules

## 4. Integration

- [ ] 4.1 Run the full suite and both flake8 passes; verify all pass
- [ ] 4.2 Against a real Slack workspace, edit a note then run `@bot status` and `@bot rescan` as both an outie and another member; verify counts, names and timing match the specs and a question about the edited note is hedged

## 5. Review fixes

- [x] 5.1 Review loop 1: Codex findings (private status names, snapshot-recorded files, failure rule, snapshot binding, check bound, Discord scope) and `/code-review` findings (single-flight check, atomic store+snapshot, name disclosure wording, deleted-file label, per-scan duration, stat failure, single walk, merged cache requirement)

## Workflow follow-up

- Archive the change after review and merge.
