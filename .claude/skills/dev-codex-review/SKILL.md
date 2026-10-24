---
name: dev-codex-review
description: Run a scoped Codex review of the current changes (or a path), auto-fix BLOCKING findings across up to 3 review/fix rounds, then show me the diff and anything left to decide
disable-model-invocation: true
---

Run the scoped Codex reviewer (it needs the `codex` CLI on PATH, plus GNU `timeout` (macOS: `brew install coreutils`); neither ships with this repo) and automatically resolve BLOCKING findings yourself, looping review→fix with Codex until clean or a 3-round cap — then show me exactly what changed and anything left for me to decide. You have the project context (CLAUDE.md, and any OpenSpec change in play); push back on (don't apply) a finding you disagree with, but don't ask before applying one you've confirmed — that per-finding confirmation step is gone by design.

**Scope comes from `$ARGUMENTS`** (pass them straight through to the script, and reused unchanged on every round):

- (no args) — review my uncommitted working changes, tracked edits and new untracked files alike. This is the fast default.
- `<path> [path...]` — review the current content of those files/dirs against their specs (or CLAUDE.md when no spec covers them).
- `--staged` — only staged changes (pre-commit check).
- `--branch` — the whole branch vs `main` (slow; only when I ask for a full pre-PR pass).
- `--range A..B` / `--commit <sha>` — a commit range or single commit.

## Before the loop

Record `BASELINE="$(git rev-parse HEAD)"`. All diffing below is against this fixed commit, not against the index — that's deliberate: it keeps the diff correct regardless of what gets staged/unstaged mid-loop (see the `--staged` note below), and it isolates our diff to the files actually in scope so it can't pick up unrelated pre-existing changes elsewhere in the tree.

Also note whether `$ARGUMENTS` is (or includes) `--staged` — that scope needs an extra step each round (below), because it reviews `git diff --cached`, i.e. the index. If your fixes aren't re-staged, the next round's review sees the pre-fix snapshot again, not your fix — this bit us once already.

## Loop (up to 3 rounds)

For round N = 1, 2, 3:

1. Run: `bash .claude/skills/dev-codex-review/review.sh $ARGUMENTS`
   - It writes the review to a new file under the review dir (default `.codex-review/`, gitignored) and prints that path on the last `out :` line.
   - Its prompt to Codex always echoes a "Files in scope:" list — capture that list once (round 1) and reuse it for every diff/restore command below, so scope stays exactly what the script reviewed.
   - If it prints a timeout, a "changed files other than" warning, or a write-verification failure (exited 0 but never wrote the file), tell me and stop the loop immediately — don't keep iterating on a broken run.
2. Read that review file. If `VERDICT: APPROVED`, stop the loop — nothing left to fix.
3. Otherwise, evaluate every BLOCKING finding: CONFIRMED (real, matches CLAUDE.md and any OpenSpec spec) or DISAGREE (false positive) — record which and why for the final summary.
4. Apply fixes for every CONFIRMED finding immediately, without asking me first. Never apply a DISAGREE finding or any NON-BLOCKING finding — collect NON-BLOCKING findings into a running list across rounds instead, for me to decide on at the end.
5. **If scope is `--staged`**: re-stage the fix, `git add -- <scope files>`, before moving on — otherwise the next round's review won't see it (see above).
6. Save the cumulative diff to `.codex-review/round-N.diff` via `git diff "$BASELINE" -- <scope files>` — this shows everything changed since the loop started regardless of staged/unstaged state, so it stays correct across rounds even for `--staged` scope. Plain `git diff` never shows untracked files, even when named explicitly: for any scope file still untracked, append its full content with `git diff --no-index -- /dev/null <file>` (a clean unified diff for a new file) instead, so round-N.diff doesn't silently omit new files the loop reviewed and fixed.
7. If this was round 3, stop the loop regardless of remaining findings.

## After the loop

- **If scope was `--staged` and step 5 ever ran**: run `git restore --staged -- <scope files>` now, so the final index state matches every other scope — nothing left staged just because the loop needed to stage it internally.
- Report, without staging or committing anything further (leave it all in the working tree for me to review and stage myself):
  - How many rounds ran and how it ended: converged to `VERDICT: APPROVED`, or hit the 3-round cap still at `CHANGES_REQUESTED` (say this explicitly — don't imply it converged if it didn't).
  - Every BLOCKING finding across all rounds: CONFIRMED-and-fixed, or DISAGREE-and-why.
  - Every NON-BLOCKING finding collected across all rounds, for me to decide on manually.
  - Point me at the latest `.codex-review/round-N.diff` as the full cumulative diff of what the loop changed.