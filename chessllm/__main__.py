"""Start the app locally: uv run python -m chessllm"""

import shutil

import uvicorn

from chessllm.app import create_app
from chessllm.game import Color, LlmSide, Settings
from chessllm.maia2_model import Maia2MoveModel
from chessllm.ollama_models import sampling_defaults
from chessllm.ollama_player import OllamaPlayer
from chessllm.stockfish_evaluator import StockfishEvaluator


def player_for(settings: Settings, color: Color) -> OllamaPlayer:
    """The LLM player of one LLM side of a game, built when the game starts."""
    side = settings.side(color)
    assert isinstance(side, LlmSide)
    return OllamaPlayer(side.model, side.think(), sampling=settings.sampling)


def main() -> None:
    # Each game is analysed with Maia-2 when it ends; the worker starts at the first game's end (chessllm.maia2_model).
    # Stockfish adds centipawn loss and accuracy when it's installed; without it, they are left out.
    evaluator = StockfishEvaluator() if shutil.which("stockfish") else None
    if evaluator is None:
        print("Stockfish isn't installed (`brew install stockfish`), so games get no centipawn loss or accuracy")
    app = create_app(player_for, sampling_defaults=sampling_defaults, move_model=Maia2MoveModel(), evaluator=evaluator)
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
