#!/usr/bin/env bash
# Implement every ticket on the frontier (open, ready-for-agent, all blockers closed), one feature
# branch + worktree + headless Claude Code session per ticket, in parallel. Then push each branch
# and open a PR that closes its issue. Merging the PRs is left to you; it unblocks the next wave.
#
# Usage:  scripts/run-frontier.sh            run the frontier
#         scripts/run-frontier.sh --dry-run  only list what would run
#         scripts/run-frontier.sh 3 4        run specific issues (must still be unblocked)
set -euo pipefail

REPO="cnarayanan-dev/chessllm"
BASE="main"
ROOT="$(git rev-parse --show-toplevel)"
TREES="$(dirname "$ROOT")/chessllm-worktrees"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && { DRY_RUN=1; shift; }

# The PR base on GitHub must contain everything the branch is built on.
git -C "$ROOT" fetch -q origin "$BASE"
if [[ -n "$(git -C "$ROOT" rev-list "origin/$BASE..$BASE")" ]]; then
  echo "Local $BASE is ahead of origin/$BASE. Push it first: git push origin $BASE" >&2
  exit 1
fi

slug() { echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-|-$//g' | cut -c1-50 | sed -E 's/-$//'; }

# Tickets only: specs carry the same label but have no "## Parent" section.
frontier() {
  local open_heads
  open_heads=$(gh pr list -R "$REPO" --state open --limit 100 --json headRefName --jq '.[].headRefName')
  gh issue list -R "$REPO" --label ready-for-agent --state open --limit 100 --json number,body \
      --jq '.[] | select(.body | test("(?m)^## Parent")) | .number' |
    while read -r n; do
      blocked=$(gh api "repos/$REPO/issues/$n" --jq '.issue_dependencies_summary.blocked_by // 0')
      if [[ "$blocked" == "0" ]] && ! grep -q "^feature/$n-" <<<"$open_heads"; then echo "$n"; fi
    done | sort -n
}

ISSUES=("$@")
[[ ${#ISSUES[@]} -eq 0 ]] && ISSUES=($(frontier))
[[ ${#ISSUES[@]} -eq 0 ]] && { echo "Frontier is empty: nothing unblocked without an open PR."; exit 0; }

echo "Frontier: ${ISSUES[*]}"
for n in "${ISSUES[@]}"; do echo "  #$n $(gh issue view "$n" -R "$REPO" --json title --jq .title)"; done
[[ $DRY_RUN -eq 1 ]] && exit 0

mkdir -p "$TREES/logs"
PIDS=(); BRANCHES=(); TITLES=()  # indexed by position in ISSUES (bash 3.2 has no maps)

for i in "${!ISSUES[@]}"; do
  n="${ISSUES[$i]}"
  title=$(gh issue view "$n" -R "$REPO" --json title --jq .title)
  branch="feature/$n-$(slug "$title")"
  dir="$TREES/$n"
  if [[ ! -d "$dir" ]]; then
    git -C "$ROOT" worktree add -q -b "$branch" "$dir" "$BASE"
  fi
  TITLES[$i]="$title"; BRANCHES[$i]="$branch"

  prompt="/implement GitHub issue #$n in $REPO.
Read it with \`gh issue view $n --comments\` and its parent spec (linked under Parent) the same way.
Follow CLAUDE.md, CONTEXT.md and docs/adr. Implement only this ticket, test-first at the agreed seam
(the HTTP API with a scripted fake LLM player), run the full test suite, then /code-review.
Commit to the current branch ($branch). Do not push, open PRs or touch other branches.
If something blocks you, commit what works and end your reply with a line starting BLOCKED:."

  echo "▶ #$n on $branch (log: $TREES/logs/$n.log)"
  ( cd "$dir" && claude -p "$prompt" --permission-mode dontAsk >"$TREES/logs/$n.log" 2>&1 ) &
  PIDS[$i]=$!
done

for i in "${!ISSUES[@]}"; do
  n="${ISSUES[$i]}"
  if ! wait "${PIDS[$i]}"; then echo "✗ #$n: Claude exited with an error, see $TREES/logs/$n.log"; continue; fi
  dir="$TREES/$n"; branch="${BRANCHES[$i]}"
  if [[ -z "$(git -C "$dir" rev-list "$BASE..HEAD")" ]]; then
    echo "✗ #$n: no commits, see $TREES/logs/$n.log"; continue
  fi
  git -C "$dir" push -q -u origin "$branch"
  body="Closes #$n

Implemented headlessly by \`scripts/run-frontier.sh\` (\`/implement\` → \`/tdd\` → \`/code-review\`).
$(grep -m1 '^BLOCKED:' "$TREES/logs/$n.log" || true)

<details><summary>Session summary</summary>

$(tail -c 6000 "$TREES/logs/$n.log")
</details>

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
  url=$(gh pr create -R "$REPO" --base "$BASE" --head "$branch" --title "${TITLES[$i]} (#$n)" --body "$body")
  echo "✓ #$n → $url"
done

echo
echo "Next: review and merge the PRs (rebase any that conflict), then run this script again for the next wave."
echo "Clean up merged worktrees with: git worktree remove $TREES/<n>"
