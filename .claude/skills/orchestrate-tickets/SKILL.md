---
name: orchestrate-tickets
description: Work through every open ready-for-agent ticket in dependency order, one background subagent per ticket in its own worktree, at most 5 at a time, with a code review and all checks before each merge into local main, and one push at the end. Use when the user has several tickets ready and wants them implemented, says "run the tickets", "do all ready-for-agent tickets", or /orchestrate-tickets.
user-invocable: true
argument-hint: "[issue numbers | label] (default: every open ready-for-agent ticket)"
---

You are the orchestrator. Subagents write the code; you plan, dispatch, review, merge and report. Don't implement tickets yourself, except for small merge fixes.

Read first: `CLAUDE.md`, `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `docs/agents/domain.md`.

## Fixed policy

- **At most 5 subagents running at once.** Queue the rest; dispatch as slots free up.
- **Every ticket gets a `code-review` before it merges** (see Merge).
- **Push once, at the end**, after the user approves the push. Never push in between.
- **Specs are never implemented directly.** A spec with no work tickets: propose a breakdown (title, one-line scope, blockers per ticket) and ask before creating any issue.
- **Local `main` only moves by fast-forward**, after a rebase and green checks. No merge commits.

## 1. Plan

1. List the tickets: the ones named in the arguments, otherwise every open issue labelled `ready-for-agent`. Leave out specs (title starts with "Spec:" or the issue has sub-issues) and issues without the label (mention them, e.g. "#9 needs triage").
2. For each ticket read its body and "Blocked by". A blocker counts as done if the issue is closed **or** its `Closes #n` commit is already on local `main` (`git log main --grep "Closes #n"`).
3. Check each ticket against the specs and ADRs it touches. Flag conflicts, e.g. a UI ticket aimed at a page a spec is replacing, two tickets building the same thing, a ticket depending on a tool that isn't installed.
4. Show the plan once: a table of chains, what runs in parallel now, what waits on what, and the conflicts. Ask only about decisions that change scope (re-scoping a ticket, editing an issue body, creating issues). Then run without further questions.

## 2. Dispatch

For each unblocked ticket, while fewer than 5 agents are running:

- Launch an `Agent` with `subagent_type: general-purpose`, `isolation: worktree`, `run_in_background: true`.
- Build the prompt from `agent-prompt.md` in this folder. Fill in:
  - the ticket number and what's on `main` that it should see after rebasing (the last commit's subject);
  - **what exists**: the interfaces, fields and file locations that earlier agents reported and this ticket builds on;
  - **parallel work**: which tickets are running now and which files to stay out of;
  - ticket-specific traps you know of (generated files, response models, tools not installed).
- Keep a running ledger in your head (or a scratch list): ticket → agent id → branch → status.

## 3. Merge (each time an agent finishes)

1. **Rebase** in the agent's worktree: `git -C <worktree> rebase main`.
   - Generated files in conflict (e.g. `frontend/src/api/schema.ts`): take main's copy with `git show main:<path> > <path>`, regenerate (`uv run python -m scripts.generate_api_types`), `git add`, `GIT_EDITOR=true git rebase --continue`.
   - A one-line conflict (two imports): resolve it yourself.
   - Anything bigger: send it back to the agent with `SendMessage`, saying what moved on `main` and what to keep from both sides. Wait for its notification.
   - Never use `git checkout main` (blocked in this repo); use `git show main:<path>`.
2. **Checks** in the worktree, all must pass:
   - `uv run pytest -q` and `uv run mypy`
   - if `frontend/` exists: `pnpm install --frozen-lockfile`, `pnpm typecheck`, `pnpm test`, `pnpm build`, and `pnpm e2e` when the ticket touched the frontend or routes.
3. **Code review**: invoke the `code-review` skill on the agent's branch since `main` (the merge-base), against its issue. Then:
   - Real defects or spec gaps: send them to the agent with `SendMessage`, have it amend its commit, and go back to step 1.
   - Nitpicks and style-only notes: don't block; list them in your report.
4. **Fast-forward**: `git -C <repo> merge --ff-only <branch>`.
5. **Notify** agents still running that `main` moved when the change touches files they work in (what changed, rebase before committing).
6. **Dispatch** whatever just became unblocked (step 2).

## 4. Report after each merge

Short, to the user:
- what merged, with the test counts;
- the decisions the agent made that the issue left open (they're the user's to overrule);
- what needs the user (tools to install, policy calls, a failed validation);
- what's running and what's next.

## 5. Finish

When every ticket is merged:
1. Run the full checks once more on `main` itself.
2. Show the commits to push (`git log --oneline origin/main..main`) and the issues they close, and ask to push.
3. After approval: `git push origin main`. Then check that GitHub closed every issue with a `Closes #n` (it can take a minute; poll `gh issue list`).
4. List what's still open: specs whose work tickets are all done (offer to close them), unlabelled issues, follow-ups the agents raised.
5. Offer to remove the finished worktrees under `.claude/worktrees/` (ask; don't delete them unasked).

## Lessons that apply to every ticket

- Worktrees can start from a stale base. Every agent rebases onto `main` first, and you rebase again before merging.
- The API returns Pydantic models built from `GameSession.state()`. A field added to the state but not to the model is dropped without an error. Tell every backend agent.
- Tests must not depend on Ollama, Maia-2, Dragon or Stockfish being installed. Live tests get a pytest marker that's excluded by default.
- Two agents in parallel on the same file is fine, but tell each to keep its changes there focused, and expect to rebase.
- Stage only the agent's own files: the user edits the main checkout in parallel and has untracked files there.
- Ticket-completing commits end with `Closes #n`; partial work uses `Refs #n`.
