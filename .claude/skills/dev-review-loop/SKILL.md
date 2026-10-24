---
name: dev-review-loop
description: Take my uncommitted changes through Codex review, a validation gate, commit and PR, and /code-review, fixing by judgment each round until a code review leads to no fix (8-round cap), then list what wasn't fixed
disable-model-invocation: true
---

Run this project's PR review cycle on my changes, round after round, until a `/code-review` pass leads to no fix. Make every judgment call on findings yourself; stop for me only when you can't proceed on your own (the pauses are listed in each step). At the end, give me one list of everything you chose not to fix.

**Invoking this skill is my request to commit, push, and open or update the PR** for the changes under review, every round. You don't need a separate approval for those. You still never push to `main`, merge, archive an OpenSpec change, or sync specs.

**Argument:** `[<change>]`, an optional OpenSpec change name. Without it, the change is resolved in Start step 2.

**Messages:** keep each round's message to three lines or fewer: round number, Codex result, gate result, commit and PR link, fixed / not-fixed counts. Ask me questions one at a time, each with your recommended answer.

## Start

1. **Scope.** Run `git status --porcelain --untracked-files=all`, so new directories list their individual files.
   - **Uncommitted changes** (tracked or untracked) are the scope. If any are untracked, list the untracked files and ask me once which are in scope. When resuming (this branch's ledger from step 5 exists and its branch matches), skip files already in its scope list, such as a test the loop wrote last round; ask only about the rest. A stray text file wouldn't trip the binary check below and could slip past the personal-data scan. In the same message, say that any file I leave out has to be moved out of the repo or gitignored before we go on, because the Codex review reads every untracked file. Wait until it is.
   - **Nothing uncommitted** but the branch has commits against `main`: ask me to confirm the branch's commits as the scope. On yes, the first Codex run uses `--branch`, and the first commit step commits only whatever that round's fixes left uncommitted (often nothing) before pushing.
   - **Nothing at all:** stop and say there's nothing to review.

   Keep the scope's file list (tracked edits plus the untracked files I confirmed, or the branch's changed files). Later, add only the files you or the Codex procedure write. It's recorded in the ledger in step 5.
2. **OpenSpec change.** Use the argument if given. Otherwise, when resuming (this branch's ledger from step 5 already exists and its branch matches), keep the change it records, since a round's uncommitted code fixes needn't touch `openspec/changes/`. Otherwise use the single live change under `openspec/changes/` (not `archive/`) that the scope touches. If it touches none, skip every OpenSpec step and say so once. If it touches several, ask me which.
3. **Off `main`.** If `main` is checked out:
   - `git fetch origin main`. If local `main` has commits that aren't on `origin/main` (`git log origin/main..main`), stop and ask me. Starting from `origin/main` would leave them out of the review and still sitting on `main`.
   - Choose the branch name: the OpenSpec change from step 2 when there is one, else a short kebab-case name from the diff. If it exists locally or on origin (`git ls-remote --heads origin <name>`), append `-2`, `-3`, … until it's free.
   - `git switch -c <name> origin/main`. It carries the uncommitted changes over when they don't collide with what's new on `origin/main`. If it refuses, stop and ask me. Never use `git stash`: the stash stack is shared with other worktrees and sessions.
4. **Never on `main` after this point.** Every later push goes to this branch.
5. **Ledger.** The ledger is `.review-loop/<branch>/ledger.md`, with `/` in the branch name replaced by `-`. It's gitignored local state. If it exists, check that its header's branch is the current branch exactly: the `/`→`-` mapping lets `feature/foo` and `feature-foo` share a path, so on a mismatch, stop and ask me rather than inherit another branch's judgments. If it matches, resume: continue the round numbering and keep every earlier judgment. Otherwise create it. Its header holds the full branch name, the change name, the scope's file list, the PR URL once known, the last round, and the current cap (8 rounds past the round this invocation started at). It has one table row per finding:

   | id | round | source | location | summary | fixed | reason |
   |---|---|---|---|---|---|---|

   `source` is one of:
   - `claude`: from `/code-review`.
   - `codex`: blocking, fixed by the Codex procedure.
   - `codex-disagree`: blocking, rejected by the procedure as a false positive, so not fixed.
   - `codex-nb`: non-blocking Codex finding.
   - `gate`: a pre-commit gate failure.

   **Dedupe:** a new finding repeats a row when it concerns the same location (same file, or a line that moved) and makes the same claim. That's your judgment, not string matching. A repeat of a not-fixed row keeps that row's judgment and outcome and cites its id. A repeat of a fixed row is a regression: judge it anew.

## Judgment rule (both reviewers)

- **Fix** a finding you've verified is real and in scope: a bug against the spec, wording drift, a missing test for a specified scenario, duplication, a stale cross-reference. When a fix has several reasonable forms, pick the one closest to the delta specs, the design, and earlier ledger judgments, and note the choice in the ledger.
- **Don't fix, and record the reason**, when the finding is:
  - a false positive (verified wrong);
  - a style preference the project doesn't follow;
  - a repeat of a finding already judged not worth fixing;
  - one whose fix would change the change's scope (covering a case the proposal leaves out, or changing a requirement's intent). Record that one as "scope: for the user"; never fix it yourself.

## Round R

Each round runs these steps in order.

### 1. Codex

1. **Out-of-scope guard.** Run `git ls-files --others --exclude-standard`. If any untracked file isn't in the scope's file list (for example, a statement dropped into the repo mid-loop), stop and ask me before running Codex. The review would send that file to an external service.
2. **Run the procedure.** Read [`../dev-codex-review/SKILL.md`](../dev-codex-review/SKILL.md) and follow its procedure. Use no arguments (uncommitted changes), except `--branch` on a first round whose scope is confirmed branch commits. With these differences:
   - **Retry once per round.** If the procedure ends at its 3-round cap without `VERDICT: APPROVED`, or the script times out, run the procedure once more. That's the round's one retry. A gate restart (step 2) that sends the round back here doesn't grant another. If the retry also fails to approve or times out, or the script prints a warning the procedure says to stop on, stop and ask me, showing the open blocking findings.
   - **Non-blocking findings:** the procedure leaves these for me. Instead, judge each one by the judgment rule: fix the worthwhile ones now (they skip a Codex re-run, because this round's `/code-review` covers them) and record the rest as `codex-nb` with a reason.
   - **Ledger, not me:** record each review-file path the script prints, plus a row for every blocking finding (`codex` or `codex-disagree`, with the procedure's reason). The procedure's After-loop report goes into the ledger, not to me. Your round message summarizes it in a few words.

### 2. Pre-commit gate

Run all of these. Commit nothing while any fails.

- **Validate:** `openspec validate <change> --strict` (when a change is in sync), `uv run --extra dev pytest`, `uv run --extra dev flake8 . --select=E9,F63,F7,F82 --show-source --statistics` (the hard-fail pass CI runs), and `uv run --extra dev black --check` and `uv run --extra dev isort --check` on the changed Python files (when there are any).
- **Confidential-data scan** over everything the next push would publish. It looks for credentials (bot, app, LLM or embedding API tokens, `xoxb-`/`xapp-`/`sk-` prefixes), real workspace, channel, guild or user IDs, real people's or companies' names, and text copied from private documents. This repo is public-facing: configs live outside it, and fixtures use the synthetic sample company Northwind.
  - *What it reads:* the diff to be committed (tracked files, and untracked scope files in full), plus each unpushed commit on its own: `git fetch origin`, then `git log -p --cc HEAD --not --remotes=origin`. Measuring against remote history catches commits a branch inherited from unpushed local `main` and a confirmed branch scope never pushed. Per-commit reading catches data one commit adds and a later one removes. `--cc` shows what a merge's conflict resolution introduced.
  - *Handling:* a hit in the diff to be committed is replaced with a synthetic equivalent (Northwind names, placeholder IDs such as `C0000000000`, `xxxxxxxxxx` for secrets), so it never reaches history. A hit in an unpushed commit stops the loop and asks me: cleaning it needs a history rewrite, which is my call.
- **Binary files** (PDFs, images, spreadsheets, `.env`-style files) can't be scanned. If one is about to be committed, or is in an unpushed commit, stop and ask me, naming the file.

**Gate failures:**
- A failure with one obvious fix (an over-long requirement, a stale test expectation, a real-looking ID) is fixed, recorded as a `gate` row, and the round restarts at step 1 so Codex sees the final tree.
- A round restarts this way at most twice. A third gate failure means fixes are fighting each other: stop and ask me.
- A failure without an obvious fix also stops and asks me.

### 3. Commit and PR

1. Stage only the scope's file list: `git add -- <files>`, never `git add -A`. An untracked file not on the list stays out and goes in the final report.
2. Commit with a message summarizing the round (round 1: what the change does; later rounds: the fixes), ending with this session's attribution line.
3. `git push -u origin <branch>`.
4. If `gh pr view` finds no PR, open one with `gh pr create --base main`.
   - **With an OpenSpec change:** the title is a one-line summary of the proposal's What Changes, and the body is its Why and What Changes.
   - **Without one:** both summarize the branch's commits (`git log main..HEAD`).
   - The body ends with this session's PR attribution line.
5. If a PR exists, rewrite its body the same way when this round changed the proposal's What Changes. With no OpenSpec change, rewrite it every round so it covers the later commits.

### 4. Code review

Invoke the `code-review` skill with `high`. It reviews the branch against `main`. Judge every finding by the judgment rule and record it as a `claude` row.

**If no finding leads to a fix, the loop is finished.** Re-report this round's findings with their outcomes (step 5, item 4), then go to Stop and report.

### 5. Fix

1. Make the fixes. Leave them uncommitted.
2. **OpenSpec sync** (when a change is in sync): when a fix changes behavior a delta spec describes, update the delta specs, then the design, then the proposal, so each follows from the one before. In `tasks.md`, create a `## N. Review fixes` section on the first fix round. Each fix round appends `- [x] N.k Review round R: <fixes, one clause each>`.
3. **Drift check:** for each rule, term or behavior this round changed, grep the branch's changed files and the OpenSpec change for other statements of it. Make each one agree with the source of truth (delta specs, then design, then proposal). Where a skill restates something a shared doc owns, replace the restatement with a link. Keep the check to what this round changed; the next `/code-review` catches older drift.
4. **Re-report** this round's `/code-review` findings with `ReportFindings`, each with an outcome from the ledger:
   - fixed → `fixed`
   - a false positive → `no_change_needed`
   - any other not-fixed finding (style, scope) → `skipped`
   - a repeat → the outcome of the row it repeats
5. If R has reached the current cap, stop and ask me whether to continue. Continuing allows 8 more rounds: the next round starts at Codex on these uncommitted fixes, and you ask again after 8 more. Otherwise start round R+1.

## Stop and report

Every stop, whether finished, capped, or stopped to ask, ends with a short report:

- how it ended: "the review loop is finished", the round cap, or why you stopped;
- the rounds run, and the PR link;
- every finding from either reviewer that wasn't fixed, with its reason, "scope: for the user" items first;
- any untracked files left out of the commits.

Never imply convergence at the cap. Say that it's capped and that the last round's fixes are uncommitted.
