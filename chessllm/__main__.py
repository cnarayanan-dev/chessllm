"""Start the app locally: uv run python -m chessllm"""

import shutil

import uvicorn

from chessllm.api.app import create_app
from chessllm.cli.common import player_for
from chessllm.engines.maia2_model import Maia2MoveModel
from chessllm.llm.ollama_models import sampling_defaults
from chessllm.engines.stockfish_evaluator import StockfishEvaluator


def main() -> None:
    # Each game is analysed with Maia-2 when it ends; the worker starts at the first game's end (chessllm.engines.maia2_model).
    # Stockfish adds centipawn loss and accuracy when it's installed; without it, they are left out.
    evaluator = StockfishEvaluator() if shutil.which("stockfish") else None
    if evaluator is None:
        print("Stockfish isn't installed (`brew install stockfish`), so games get no centipawn loss or accuracy")
    app = create_app(player_for, sampling_defaults=sampling_defaults, move_model=Maia2MoveModel(), evaluator=evaluator)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
