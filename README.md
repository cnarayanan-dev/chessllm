# ChessLLM

Play chess against a small local LLM in the browser. See `CONTEXT.md` for the domain language and `docs/adr/` for decisions.

- Run the app: build the page first (needs Node and pnpm): `pnpm install && pnpm build` in `frontend/`. Then `uv run python -m chessllm`, and open http://127.0.0.1:8000. The opponent is qwen3.5:9b, so Ollama must be running with that model installed. The page is the React app in `frontend/`; its build goes to `chessllm/static/dist/`, which is git-ignored, and isn't rebuilt on its own: build again after changing `frontend/`
- See the leaderboard: the Analytics link in the top bar, or http://127.0.0.1:8000/analytics. It ranks every Player configuration by Rating, from the finished games in `games/`; the "All columns" switch adds the Rating's interval, the Move-quality estimate and the legal-move metrics
- Work on the React page: run `uv run python -m chessllm` in one terminal and `pnpm dev` in `frontend/` in another, then open the address Vite prints. It reloads as you edit and forwards `/api` and `/static` to the app
- Run the frontend tests: `pnpm test` in `frontend/`. Typecheck it: `pnpm typecheck`
- Run the Playwright journeys (a game to checkmate, an illegal LLM try, a forfeit, a promotion, a faceoff, the leaderboard): `pnpm e2e` in `frontend/`, after `pnpm build`. The first time, install the browser: `pnpm exec playwright install chromium`. They play the built page against the app with scripted LLM players (`tests/e2e_server.py`, started on a free port), and the leaderboard against synthetic game logs (`tests/e2e_leaderboard.py`), so Ollama isn't needed
- Edit the LLM's system prompt: `chessllm/prompts/system.txt`. It is a template: `$color` and `$opponent` are filled in with the colours the LLM and the human play, and the `$example_...` placeholders with a worked first move for that colour
- Every game is saved in `games/`: a JSON Lines log of every move and LLM attempt, and a PGN file when the game ends
- Play an Anchor match (an LLM against Komodo Dragon 1, unattended): `uv run python -m chessllm.anchor_match --model llama3:8b --skill 1 --color white --dragon PATH`; `--help` lists the LLM's settings. Dragon isn't bundled: download `dragon.zip` from komodochess.com and pass the executable with `--dragon` or set `CHESSLLM_DRAGON`. Its macOS build is x86_64 only and runs under Rosetta 2 on Apple silicon
- Rate a Player configuration with a batch of Anchor matches: `uv run python -m chessllm.anchor_batch --model llama3:8b --games 30 --dragon PATH` (the LLM's settings as for one Anchor match). Colours alternate, and Dragon's Skill is judged after each pair of games at it (one as White, one as Black): over 50% steps up a level, under 50% steps down, within Skill 1-7. It prints each game's result and a summary. Running it again for the same configuration goes on where its earlier games left the ladder; `--skill N` starts at Skill N instead. Each game is analysed as it ends, with Maia-2 and Stockfish (`--no-analysis` to skip); an engine that can't start is left out with a warning, and `uv run python -m chessllm.analysis` can catch up later. Ctrl-C stops it, leaving every finished game's log complete
- Run the tests: `uv run pytest`. The live tests are left out: `uv run pytest -m ollama` (Ollama with llama3:8b) and `uv run pytest -m dragon` (needs `CHESSLLM_DRAGON`)
- Typecheck: `uv run mypy`
- Rebuild the merida piece sprite: `uv run python scripts/build_merida_sprite.py`

Pieces: Merida by Armando Hernandez Marroquin, GPLv2+.
