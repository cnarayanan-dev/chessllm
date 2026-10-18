# ChessLLM

Play chess against a small local LLM in the browser. See `CONTEXT.md` for the domain language and `docs/adr/` for decisions.

- Run the app: `uv run python -m chessllm`, then open http://127.0.0.1:8000
- Run the tests: `uv run pytest`
- Typecheck: `uv run mypy`
- Rebuild the merida piece sprite: `uv run python scripts/build_merida_sprite.py`

Pieces: Merida by Armando Hernandez Marroquin, GPLv2+.
