"""HTTP API and static page."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chessllm.game import Color, GameSession, RejectedHumanMove, Settings
from chessllm.game_log import GAMES_DIR, GameLog
from chessllm.models import LLM_MODELS, SAMPLING_FILE, LlmModel, load_sampling
from chessllm.players import LlmPlayer
from chessllm.prompt import RetryFeedback

STATIC_DIR = Path(__file__).parent / "static"


class HumanMove(BaseModel):
    uci: str


class NewGame(BaseModel):
    """The settings chosen in the settings modal. Sampling isn't one of them: it comes from the config file."""

    model: str = Settings.model
    thinking: bool = Settings.thinking
    retry_feedback: RetryFeedback = Settings.retry_feedback
    human_color: Color = Settings.human_color


def create_app(
    player_for: Callable[[Settings], LlmPlayer],
    games_dir: Path = GAMES_DIR,
    models: list[LlmModel] = LLM_MODELS,
    sampling_defaults: Callable[[str], dict[str, float]] = lambda model: {},
    sampling_file: Path = SAMPLING_FILE,
) -> FastAPI:
    """player_for builds the LLM player of each game from that game's settings.

    models are the models the game can be played against, and sampling_defaults gives a model's own sampling."""
    app = FastAPI(title="ChessLLM")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    game: GameSession | None = None

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/models")
    def list_models() -> list[dict[str, Any]]:
        """Each model with the sampling it would play at: its own defaults, overridden by the config file.

        The sampling is None when Ollama can't show the model, e.g. when it isn't installed."""
        config = sampling_config()

        def sampling(model: LlmModel) -> dict[str, float] | None:
            try:
                return sampling_defaults(model.name) | config
            except Exception:
                return None

        return [{"name": model.name, "thinking": model.thinking, "sampling": sampling(model)} for model in models]

    def sampling_config() -> dict[str, float]:
        try:
            return load_sampling(sampling_file)
        except ValueError as error:
            raise HTTPException(500, str(error)) from None

    @app.post("/api/games")
    def start_game(new_game: NewGame | None = None) -> dict[str, Any]:
        nonlocal game
        settings = Settings(**(new_game or NewGame()).model_dump(), sampling=sampling_config())
        model = next((model for model in models if model.name == settings.model), None)
        if model is None:
            raise HTTPException(400, f"{settings.model} is not in the model list")
        if settings.thinking and not model.thinking:
            raise HTTPException(400, f"{settings.model} cannot think, so thinking must be off")
        game = GameSession(player_for(settings), settings, GameLog(games_dir, settings.model))
        return game.state()

    def current_game() -> GameSession:
        if game is None:
            raise HTTPException(404, "no game started")
        return game

    @app.get("/api/games/current")
    def get_game() -> dict[str, Any]:
        return current_game().state()

    @app.post("/api/games/current/moves")
    def play_move(move: HumanMove) -> dict[str, Any]:
        session = current_game()
        try:
            session.play_human_move(move.uci)
        except RejectedHumanMove as error:
            raise HTTPException(400, str(error)) from None
        return session.state()

    return app
