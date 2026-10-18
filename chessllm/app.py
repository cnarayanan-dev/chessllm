"""HTTP API and static page."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chessllm.game import GameSession, RejectedHumanMove, Settings
from chessllm.game_log import GAMES_DIR, GameLog
from chessllm.models import SAMPLING_FILE, InstalledModel, load_sampling
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


def create_app(
    player_for: Callable[[Settings], LlmPlayer],
    games_dir: Path = GAMES_DIR,
    installed_models: Callable[[], list[InstalledModel]] = list,
    sampling_file: Path = SAMPLING_FILE,
) -> FastAPI:
    """player_for builds the LLM player of each game from that game's settings.

    installed_models lists the models the game can be played against."""
    app = FastAPI(title="ChessLLM")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    game: GameSession | None = None

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/models")
    def models() -> list[dict[str, Any]]:
        """Each model with the sampling it would play at: its own defaults, overridden by the config file."""
        sampling = sampling_config()
        try:
            installed = installed_models()
        except Exception as error:  # e.g. Ollama isn't running
            raise HTTPException(503, str(error)) from None
        return [{"name": model.name, "sampling": model.sampling | sampling} for model in installed]

    def sampling_config() -> dict[str, float]:
        try:
            return load_sampling(sampling_file)
        except ValueError as error:
            raise HTTPException(500, str(error)) from None

    @app.post("/api/games")
    def start_game(new_game: NewGame | None = None) -> dict[str, Any]:
        nonlocal game
        settings = Settings(**(new_game or NewGame()).model_dump(), sampling=sampling_config())
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
