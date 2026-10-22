"""Start the app locally: uv run python -m chessllm"""

import shutil

import uvicorn

from chessllm.api.app import create_app
from chessllm.game.session import BenchmarkLlmSide, Color, LlmSide, Settings
from chessllm.engines.maia2_model import Maia2MoveModel
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.ollama_models import sampling_defaults
from chessllm.llm.ollama_player import OllamaPlayer, time_limit_s
from chessllm.engines.stockfish_evaluator import StockfishEvaluator


def player_for(settings: Settings, color: Color) -> OllamaPlayer:
    """The LLM player of one LLM side of a game, built when the game starts. A benchmark side's Thinking budget
    sets its time limit, from its model's speed (ADR 0007)."""
    side = settings.side(color)
    assert isinstance(side, LlmSide)
    budget = side.thinking_budget if isinstance(side, BenchmarkLlmSide) else None
    speed = next((model.tokens_per_s for model in LLM_MODELS if model.name == side.model), None)
    timeout_s = time_limit_s(budget, speed)
    return OllamaPlayer(side.model, side.think(), timeout_s=timeout_s, sampling=settings.sampling, budget=budget)


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
