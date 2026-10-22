"""HTTP API and static page."""

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from chessllm.api.errors import register_error_handlers
from chessllm.api.routes import games, leaderboard, models as model_routes, pages
from chessllm.api.state import Engines, GameStore
from chessllm.core.config import DIST_DIR, GAMES_DIR, SAMPLING_FILE, VALIDATION_FILE, AppConfig
from chessllm.core.types import Color, Sampling
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.game.session import Settings
from chessllm.llm.models import LLM_MODELS, LlmModel
from chessllm.llm.players import LlmPlayer


def create_app(
    player_for: Callable[[Settings, Color], LlmPlayer],
    games_dir: Path = GAMES_DIR,
    models: list[LlmModel] = LLM_MODELS,
    sampling_defaults: Callable[[str], Sampling] = lambda model: {},
    sampling_file: Path = SAMPLING_FILE,
    dist_dir: Path = DIST_DIR,
    move_model: MoveModel | None = None,
    move_quality_validation: Path = VALIDATION_FILE,
    evaluator: Evaluator | None = None,
) -> FastAPI:
    """The app with its AppConfig and Engines built from the arguments, and no game yet (see Engines for what
    each engine is for). With a move_model or an evaluator, each game is analysed when it ends, after the response
    is sent."""
    config = AppConfig(
        games_dir=games_dir,
        sampling_file=sampling_file,
        dist_dir=dist_dir,
        move_quality_validation=move_quality_validation,
    )
    app = FastAPI(title="ChessLLM")
    app.state.config = config
    app.state.engines = Engines(player_for, models, sampling_defaults, move_model, evaluator)
    app.state.games = GameStore()
    app.mount("/static", StaticFiles(directory=config.static_dir), name="static")
    register_error_handlers(app)
    for router in [pages.router, model_routes.router, games.router, leaderboard.router]:
        app.include_router(router)
    return app
