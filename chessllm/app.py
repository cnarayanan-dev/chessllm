"""HTTP API and static page."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from chessllm.game import (
    Color,
    GameSession,
    HumanSide,
    LlmSide,
    Mode,
    RefusedLlmTurn,
    RejectedHumanMove,
    Settings,
)
from chessllm.game_log import GAMES_DIR, GameLog
from chessllm.models import LLM_MODELS, SAMPLING_FILE, LlmModel, load_sampling
from chessllm.players import LlmPlayer

STATIC_DIR = Path(__file__).parent / "static"


class HumanMove(BaseModel):
    uci: str


SideIn = Annotated[HumanSide | LlmSide, Field(discriminator="player")]


class NewGame(BaseModel):
    """The settings chosen in the settings modal: the Mode and who plays each side, with the settings of each LLM
    side. Sampling isn't one of them: it comes from the config file."""

    model_config = ConfigDict(extra="forbid")

    mode: Mode = Settings.mode
    white: SideIn = Settings.white
    black: SideIn = Settings.black


def create_app(
    player_for: Callable[[Settings, Color], LlmPlayer],
    games_dir: Path = GAMES_DIR,
    models: list[LlmModel] = LLM_MODELS,
    sampling_defaults: Callable[[str], dict[str, float]] = lambda model: {},
    sampling_file: Path = SAMPLING_FILE,
) -> FastAPI:
    """player_for builds the LLM player of each LLM side of a game, from that game's settings and the side's colour.

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
        new_game = new_game or NewGame()
        settings = Settings(new_game.mode, new_game.white, new_game.black, sampling=sampling_config())
        problem = settings.problem(models)
        if problem is not None:
            raise HTTPException(400, problem)
        players = {color: player_for(settings, color) for color in settings.llm_sides()}
        game = GameSession(players, settings, GameLog(games_dir, *settings.side_names()))
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

    @app.post("/api/games/current/llm-turn")
    def play_llm_turn() -> dict[str, Any]:
        """The only way an LLM turn starts. The page asks for one whenever a state says it is an LLM's turn, which
        in an LLM faceoff is every turn until the game ends.

        The state returned is that of the game the turn was played in, even if a new game has started since."""
        session = current_game()
        try:
            session.play_llm_turn()
        except RefusedLlmTurn as error:
            raise HTTPException(409, str(error)) from None
        return session.state()

    return app
