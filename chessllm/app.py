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
from chessllm.players import LlmPlayer

STATIC_DIR = Path(__file__).parent / "static"


class HumanMove(BaseModel):
    uci: str


def create_app(player_for: Callable[[Settings], LlmPlayer], games_dir: Path = GAMES_DIR) -> FastAPI:
    """player_for builds the LLM player of each game from that game's settings."""
    app = FastAPI(title="ChessLLM")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    game: GameSession | None = None

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.post("/api/games")
    def start_game(settings: Settings | None = None) -> dict[str, Any]:
        nonlocal game
        settings = settings or Settings()
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
