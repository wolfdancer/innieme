# Design

## Context

The index is an in-memory Chroma collection built by `DocumentProcessor.scan_and_vectorize()`, replaced wholesale on each scan (startup, or `rescan` on Slack). It keeps only a human-readable result string. The answering model sees retrieved chunks labelled `[source: <basename>]` and nothing about the index itself. See proposal.md for motivation and specs/ for required behavior.

Constraints: the notes directory is the user's own, possibly large, possibly on a slow mount; channel-visible text must not leak excluded or unindexed file names (existing convention); a failed rescan must keep the previous index serving.

## Goals / Non-Goals

**Goals:**
- Make index age and per-file staleness knowable cheaply, by the bot and by people.
- Keep the freshness check independent of the vector store, so it survives a store change.

**Non-Goals:**
- Anything in the proposal's non-goals (auto-rescan, per-file reindex, persistence, hashing).
- Changing retrieval ranking based on staleness.

## Decisions

**1. A snapshot object owned by the document processor, set together with the store.**
The snapshot is assigned in the same step that replaces the vector store, after a scan succeeds, so the two cannot disagree. A scan that raises never reaches that step.
*Alternative:* store the metadata in Chroma collection metadata. Rejected: couples freshness to one backend (FAISS is already half-present), and the collection is replaced each scan anyway.

**1a. Bind each answer to the index it retrieved from.**
An answer retrieves chunks, then awaits a freshness check. A rescan could publish a new snapshot in between and the old chunks would be judged current against it. The engine therefore captures the snapshot at retrieval time and computes freshness against that snapshot; cached check results are keyed by snapshot identity, so a result for an old snapshot is never reused or written back after a rescan.
*Alternative:* a generation counter on store plus snapshot. Equivalent; the snapshot object already is the generation, so no new counter is needed.

**2. Staleness = mtime_ns + size, stamped before the read.**
The comparison covers every candidate recorded in the snapshot, including empty and failed files, so an empty file gaining text or a failed file being repaired is detected. Chosen for cost (stat only) and because the notes-maintenance process rewrites files, changing at least one. Stamping before reading means a mid-scan edit is flagged rather than masked.
*Alternative:* content hash. Rejected by decision: requires reading every file per check. Known false positives (sync tools touching mtimes) are accepted; the cost is a spurious "rescan?" suggestion, not a wrong answer.

**3. Check by re-walking the directory, with a 30 s reuse window for routine checks.**
Per-query checks run in a worker thread so a slow mount does not stall the event loop, and the answer waits at most 5 seconds for one before proceeding without freshness information (the abandoned thread finishes harmlessly). `status` forces a fresh check; a scan clears the cached result.
*Alternatives:* filesystem watcher (extra dependency, platform quirks, unreliable on network mounts); check only at `status` time (the model would never know).

**4. Two audiences, two levels of detail.**
The model gets chunk-level labels (names it already sees via `[source: ...]`) plus a count-only note; it is never handed the full list of changed files. Channel replies show counts only. Names go to the outie in an ephemeral message, because a threaded channel reply is visible to everyone and is also read back into the model's conversation history (`get_thread_context`); ephemeral messages are neither in channel history nor returned by the thread-replies API. This extends the existing "count, never names" rule for excluded files to unindexed files.
*Alternatives:* names in the channel reply for the outie (rejected: public, and fed back to the model); a DM to the outie (works but moves the conversation out of the thread). Give the model all names so it can answer "what's stale?". Rejected: the model would repeat them to any channel member.

**4a. The model is told to suggest a rescan, not to refuse.**
The note asks the model to flag possible staleness when it affects the answer. It does not suppress answers. Wording is a prompt, so it is not a hard guarantee; the chunk label is the reliable signal.

**5. Rescan opened to everyone, guarded by a per-topic scan lock.**
Opening rescan makes overlapping scans likely. A lock serializes them so the later one does not discard the earlier one's work mid-flight or double the embedding spend at once.
*Alternative:* reject a second request while one runs ("already scanning"). Simpler to reason about for users but needs a reply path; deferred, see Open Questions.

**6. Freshness failures are non-fatal for answers.**
The check only informs a response, so any error during it is logged and the question is answered without freshness information. `status` instead reports a generic failure and logs details.

**7. Timing reported in two parts.**
Reading/parsing vs. chunking/embedding/store-building, since the second is where provider latency and cost live and is the part a user would act on.

## Risks / Trade-offs

- [`rescan` open to all can spend embedding credits] → scans are serialized; no rate limit yet (see Open Questions).
- [mtime churn from sync tools causes false "stale" reports] → accepted trade-off of decision 2; wording asks the model to hedge, not to refuse.
- [Slow or unavailable notes mount during per-query checks] → worker thread, 30 s reuse, failure is non-fatal.
- [Prompt note adds tokens to every answer and may make answers over-cautious] → note is short and omitted before the first scan; revisit if answers become noisy.
- [Slack escaping of hostile file names] → names are shown only to the outie, privately, rendered as escaped inline code.
- [Ephemeral messages can be dismissed or fail to deliver] → the counts-only channel reply never depends on them; a failed private send is logged and the names are simply not shown.
- [Scan success semantics] → a readable empty file is not an extraction failure, so an all-empty corpus still scans successfully as today; a scan aborts only when at least one extraction error occurs and no candidate supplies text, exactly as today, so a mix of empty and failed files cannot replace a working index with an empty one.
- [Rescan still rebuilds everything, so one edited file costs a full re-embed] → accepted; per-file reindexing is a separate change.

## Migration Plan

No data migration: the snapshot is in memory and is built by the next scan, which already happens at startup. Rollback is reverting the change. The Slack app config needs no change (commands are mentions). Anyone relying on `rescan` being outie-only should be told it is now open.

## Open Questions

- Should a rescan requested while another is running reply "already scanning (started Ns ago)" instead of queueing silently?
- Should non-outie `rescan` be rate-limited (for example one per N minutes per topic)?
- Should `status` also show whether the last rescan attempt failed? Today a failed rescan is only visible in its own reply.
