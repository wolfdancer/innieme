# Tasks

The branch `shane/innieme-index-freshness-b802b6` (closed PR wolfdancer/innieme#73) holds a prototype that can be consulted, but each task is to be implemented and verified against the specs, not copied.

## 1. Snapshot and staleness check

- [ ] 1.1 Add snapshot and freshness types and age/duration/timestamp formatting (new module); verify with unit tests for formatting edge cases (seconds, minutes, hours, days, negative)
- [ ] 1.2 Record a snapshot on each completed scan, stamping files before reading and keeping the previous snapshot when a scan fails; verify with tests for: fields populated, no-scan-yet, mid-scan edit reads as stale, failed scan keeps old snapshot, unreadable file recorded as failed
- [ ] 1.3 Implement the stat-only staleness check with the 30 s reuse window and an explicit force option; verify with tests for modified (size and mtime-only), new, removed, excluded files, unchanged failed file, no snapshot, cache vs. forced
- [ ] 1.4 Serialize scans per topic with a lock; verify with a test that two concurrent scans never overlap
- [ ] 1.5 Expose snapshot and an off-thread forced check on the topic; verify `uv run pytest` passes and the hard-fail flake8 pass is clean

## 2. Model awareness

- [ ] 2.1 Label chunks from changed sources in the model's context; verify tests cover changed, unchanged, other-file, and missing-metadata chunks
- [ ] 2.2 Add the count-only freshness note to the system prompt (absent before first scan, "no change" when current, hedging direction when stale, no file names); verify with prompt-building tests
- [ ] 2.3 Run the freshness check off the event loop during answering and treat failure as non-fatal; verify with a test where the check raises and the question is still answered

## 3. Slack commands

- [ ] 3.1 Add `status` to the mention commands and make `rescan` open to everyone while `quit` stays outie-only; verify parse tests (`status` is a command, "what is the status?" is not) and access tests for each command and requester
- [ ] 3.2 Implement the `status` reply (counts for all, names for the outie only, escaped names, no-scan and failure replies without paths); verify with tests including a hostile file name
- [ ] 3.3 Report scan duration in the `rescan` reply without turning a successful scan into a reported failure; verify with a test for the success text and the existing failed-rescan tests
- [ ] 3.4 Update CLAUDE.md for the new commands, access change and freshness behavior; verify the documented commands match `BOT_COMMANDS` and the access rules

## 4. Integration

- [ ] 4.1 Run the full suite and both flake8 passes; verify all pass
- [ ] 4.2 Against a real Slack workspace, edit a note then run `@bot status` and `@bot rescan` as both an outie and another member; verify counts, names and timing match the specs and a question about the edited note is hedged

## Workflow follow-up

- Archive the change after review and merge.
