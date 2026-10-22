Implement GitHub issue #{N} in the repo cnarayanan-dev/chessllm (you are in a git worktree of it).

FIRST run `git rebase main` so you start from local main; `git log --oneline -1` should show "{LAST_MAIN_COMMIT_SUBJECT}". If `frontend/` exists and you'll touch it: `cd frontend && pnpm install` (and `pnpm exec playwright install chromium` for e2e).

Read: `gh issue view {N} --comments`, its parent spec `gh issue view {PARENT}`, CLAUDE.md, CONTEXT.md (use its terms in code and UI copy), the ADRs in docs/adr/ that the issue touches, and docs/research/ where relevant.

What exists that you build on:
{WHAT_EXISTS}

Running in parallel (stay out of their files, keep shared-file changes focused):
{PARALLEL_WORK}

Traps:
- The API's response models in chessllm/api/app.py are built from GameSession.state(); a field not in the models is silently dropped. After API changes regenerate `frontend/src/api/schema.ts` with `uv run python -m scripts.generate_api_types` (a test checks it).
- Tests must not need Ollama, Maia-2, Dragon or Stockfish; a live test gets a pytest marker excluded by default in pyproject.toml.
- Don't use port 8000 for servers you start; stop them afterwards.
{TICKET_TRAPS}

Work test-first (invoke the `tdd` skill). Match the surrounding code's style, naming and comment density.

Done means all of these pass: `uv run pytest`, `uv run mypy`, and if you touched the frontend `pnpm typecheck`, `pnpm test`, `pnpm build`, `pnpm e2e`. Check visible behaviour in the built app when the issue has a manual check.

Commit on your branch in the repo's message style (`git log -5`), ending with:

Closes #{N}

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

(Use `Refs #{N}` instead if an acceptance criterion couldn't be met, and say which.)

Do NOT push, open PRs, or touch main. Only stage your own files.

Report: branch, commit hash, summary, the interfaces/fields/files later tickets build on, check results, and the decisions the issue left open.
