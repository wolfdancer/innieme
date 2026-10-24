#!/usr/bin/env bash
#
# review.sh — run a SCOPED Codex review of innieme.
#
# The whole point vs. the old skill: you choose the scope, and the default is
# the SMALLEST useful thing (your uncommitted changes), not the whole branch.
# Small, targeted scope = fast reviews that don't time out.
#
# Usage:
#   .claude/skills/dev-codex-review/review.sh                    # uncommitted working changes, tracked + untracked (DEFAULT)
#   .claude/skills/dev-codex-review/review.sh <path> [path...]   # review current content of file(s)/dir(s)
#   .claude/skills/dev-codex-review/review.sh --staged           # only staged changes (pre-commit)
#   .claude/skills/dev-codex-review/review.sh --branch           # whole branch vs main (the old behavior)
#   .claude/skills/dev-codex-review/review.sh --range A..B       # an arbitrary commit range
#   .claude/skills/dev-codex-review/review.sh --commit <sha>     # a single commit
#   .claude/skills/dev-codex-review/review.sh --help
#
# Env overrides:
#   CODEX_MODEL           model passed to codex (e.g. o4-mini) — optional
#   INNIEME_REVIEW_TIMEOUT   hard cap in seconds (default 900) — kills runaways
#   INNIEME_BASE_BRANCH      base for --branch (default main)
#   REVIEW_LABEL          output filename label (default: round, or the inst name)
#   INNIEME_REVIEW_DIR       where reviews are written (default .codex-review/, gitignored)

set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

TIMEOUT="${INNIEME_REVIEW_TIMEOUT:-900}"
BASE_BRANCH="${INNIEME_BASE_BRANCH:-main}"
LABEL="${REVIEW_LABEL:-}"
REVIEW_DIR="${INNIEME_REVIEW_DIR:-.codex-review}"

mode="working"; paths=(); range=""; commit=""; UNTRACKED=""

if [[ $# -gt 0 ]]; then
  case "$1" in
    --staged)  mode="staged" ;;
    --branch)  mode="branch" ;;
    --range)   mode="range";  range="${2:?--range needs A..B}" ;;
    --commit)  mode="commit"; commit="${2:?--commit needs a sha}" ;;
    -h|--help) sed -n '2,23p' "$0" | sed 's/^#\{0,1\} \{0,1\}//'; exit 0 ;;
    -*)        echo "unknown flag: $1" >&2; exit 2 ;;
    *)         mode="paths"; paths=("$@") ;;
  esac
fi

# --- Resolve scope -> a human description, the review target, and file list ---
case "$mode" in
  working)
    TRACKED="$(git diff --name-only HEAD)"
    UNTRACKED="$(git ls-files --others --exclude-standard)"
    FILES="$(printf '%s\n%s\n' "$TRACKED" "$UNTRACKED" | sed '/^$/d' | sort -u)"
    if [[ -n "$UNTRACKED" ]]; then
      SCOPE_DESC="uncommitted working-tree changes: tracked edits (git diff HEAD) + new untracked files"
    else
      SCOPE_DESC="uncommitted working-tree changes (git diff HEAD)"
    fi
    TARGET_KIND="diff"
    ;;
  staged)
    SCOPE_DESC="staged changes (git diff --cached)"
    TARGET_KIND="diff"
    FILES="$(git diff --cached --name-only)"
    ;;
  branch)
    MB="$(git merge-base "$BASE_BRANCH" HEAD)"
    SCOPE_DESC="branch changes vs $BASE_BRANCH (merge-base ${MB:0:9}...HEAD)"
    TARGET_KIND="diff"
    FILES="$(git diff --name-only "$MB"...HEAD)"
    ;;
  range)
    SCOPE_DESC="commit range $range"
    TARGET_KIND="diff"
    FILES="$(git diff --name-only $range)"
    ;;
  commit)
    SCOPE_DESC="commit $commit"
    TARGET_KIND="diff"
    FILES="$(git show --name-only --format= "$commit")"
    ;;
  paths)
    SCOPE_DESC="current content of: ${paths[*]}"
    TARGET_KIND="content"
    FILES="$(git ls-files -- "${paths[@]}")"
    ;;
esac

FILES="$(printf '%s\n' "$FILES" | sed '/^$/d')"
if [[ -z "$FILES" ]]; then
  echo "Nothing in scope for: $SCOPE_DESC" >&2
  exit 1
fi

# --- Find the specs that are the source of truth for what changed ----------
# innieme keeps OpenSpec specs under openspec/specs/ (merged) and
# openspec/changes/<name>/ (active, unarchived changes). Include any spec,
# proposal, design or tasks file that is itself in scope, plus every delta spec
# of an active change the scope touches. Empty is fine: most reviews have none.
specs=()
while IFS= read -r f; do
  case "$f" in
    openspec/specs/*/spec.md)
      specs+=("$f")
      ;;
    openspec/changes/archive/*)
      ;;
    openspec/changes/*/*)
      change="$(printf '%s' "$f" | cut -d/ -f3)"
      for sp in openspec/changes/"$change"/proposal.md openspec/changes/"$change"/design.md \
                openspec/changes/"$change"/specs/*/spec.md; do
        [[ -f "$sp" ]] && specs+=("$sp")
      done
      ;;
  esac
done <<< "$FILES"
SPECS="$(printf '%s\n' "${specs[@]:-}" | sed '/^$/d' | sort -u)"
[[ -z "$SPECS" ]] && SPECS="(none: review against CLAUDE.md and the surrounding code)"

# --- Derive an output filename: <review-dir>/<label>-<n>.md ----------------
if [[ -z "$LABEL" ]]; then
  LABEL="round"
fi
mkdir -p "$REVIEW_DIR"
n=1; while [[ -e "${REVIEW_DIR}/${LABEL}-${n}.md" ]]; do n=$((n+1)); done
OUT="${REVIEW_DIR}/${LABEL}-${n}.md"

# --- Build the review prompt (small: point Codex at files, don't inline them) ---
if [[ "$TARGET_KIND" == "content" ]]; then
  WHAT="Review the CURRENT CONTENT of the files in scope (not a diff): is each correct, and does it match its spec?"
elif [[ -n "$UNTRACKED" ]]; then
  WHAT="Review the DIFF for the scope below. For files already tracked by git, get the diff yourself with the appropriate git command (e.g. \`git diff HEAD -- <file>\`). The files listed below are NEW and not yet tracked by git — plain \`git diff\` never shows untracked files, even when named explicitly — so for these, read the full current file content directly instead and review it as newly-added code:
$UNTRACKED"
else
  WHAT="Review the DIFF for the scope below. Get the diff yourself with the appropriate git command."
fi

PROMPT="You are the reviewer for the 'innieme' repository (a Discord/Slack Q&A bot backed by document knowledge bases; see CLAUDE.md). Format your review EXACTLY like this: a '## BLOCKING' section (bugs, spec or CLAUDE.md violations, missing tests for specified behavior, anything that should stop a merge) and a '## NON-BLOCKING' section (style, nits, optional improvements); a path:line citation and a 'Suggested fix:' for every finding; and a final 'VERDICT: APPROVED' (no BLOCKING findings) or 'VERDICT: CHANGES_REQUESTED' line.

$WHAT

SCOPE (review ONLY this — ignore everything outside it):
$SCOPE_DESC

Files in scope:
$FILES

Specs that are the source of truth for this scope (read the relevant ones; the code must match them):
$SPECS

Read CLAUDE.md first for project conventions and architecture. Keep the review tightly focused on the scope above — do not wander into unrelated files.

Output your review as Markdown directly in your final response message. Do NOT try to write it to a file yourself — the CLI harness captures your final message and saves it on your behalf. Do NOT modify any file in the repository."

# --- Run Codex, bounded so it can never hang the terminal -------------------
# -o/--output-last-message writes the final message from the OUTER harness
# process, not from inside the model's sandboxed shell — this is deliberate:
# Codex's own sandbox refuses to write into any directory literally named
# .codex (even one it otherwise has workspace-write access to), so asking the
# agent to write $OUT itself reliably fails. Letting the harness write it
# instead sidesteps that restriction entirely.
CODEX_ARGS=(exec --sandbox workspace-write -o "$OUT")
[[ -n "${CODEX_MODEL:-}" ]] && CODEX_ARGS+=(-m "$CODEX_MODEL")

echo "▶ innieme review" >&2
echo "  scope : $SCOPE_DESC" >&2
echo "  files : $(printf '%s\n' "$FILES" | wc -l | tr -d ' ')   specs: $(printf '%s\n' "$SPECS" | grep -c . || true)" >&2
echo "  out   : $OUT   (timeout ${TIMEOUT}s)" >&2

before="$(git status --porcelain)"

if timeout "$TIMEOUT" codex "${CODEX_ARGS[@]}" "$PROMPT"; then
  if [[ -f "$OUT" ]]; then
    echo "✓ Review written to $OUT" >&2
  else
    echo "✗ Codex exited 0 but $OUT still doesn't exist — the -o harness write itself failed unexpectedly; check codex's console output above for the review text." >&2
    exit 1
  fi
else
  rc=$?
  if [[ $rc -eq 124 ]]; then
    echo "✗ Codex hit the ${TIMEOUT}s timeout — scope is still too big. Try one file, or --staged." >&2
  else
    echo "✗ Codex exited $rc" >&2
  fi
  exit $rc
fi

# --- Safety net: the reviewer must not have edited code ---------------------
after="$(git status --porcelain | grep -v " ${OUT#./}\$" || true)"
if [[ "$after" != "$before" ]]; then
  echo "⚠  Codex changed files other than $OUT — review these before trusting the run:" >&2
  diff <(printf '%s\n' "$before") <(printf '%s\n' "$after") | grep '^>' >&2 || true
fi