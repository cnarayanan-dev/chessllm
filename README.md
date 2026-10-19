# ChessLLM

Play chess against a small local LLM in the browser. See `CONTEXT.md` for the domain language and `docs/adr/` for decisions.

- Run the app: `uv run python -m chessllm`, then open http://127.0.0.1:8000. The opponent is qwen3.5:9b, so Ollama must be running with that model installed.
- Edit the LLM's system prompt: `chessllm/prompts/system.txt`. It is a template: `$color` and `$opponent` are filled in with the colours the LLM and the human play, and the `$example_...` placeholders with a worked first move for that colour
- Every game is saved in `games/`: a JSON Lines log of every move and LLM attempt, and a PGN file when the game ends
- Run the tests: `uv run pytest`
- Typecheck: `uv run mypy`
- Rebuild the merida piece sprite: `uv run python scripts/build_merida_sprite.py`

Pieces: Merida by Armando Hernandez Marroquin, GPLv2+.
