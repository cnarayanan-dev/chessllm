"""HTTP API and static page."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from chessllm.game import (
    Color,
    GameSession,
    HumanSide,
    LlmSide,
    Mode,
    Rules,
    RefusedLlmTurn,
    RejectedHumanMove,
    Settings,
)
from chessllm.game_log import GAMES_DIR, GameLog
from chessllm.leaderboard import Leaderboard, leaderboard
from chessllm.models import LLM_MODELS, SAMPLING_FILE, LlmModel, load_sampling
from chessllm.players import LlmPlayer

STATIC_DIR = Path(__file__).parent / "static"
# The React app's build (frontend/, `pnpm build`), git-ignored. Its files are served under /static/dist/.
DIST_DIR = STATIC_DIR / "dist"


class HumanMove(BaseModel):
    uci: str


SideIn = Annotated[HumanSide | LlmSide, Field(discriminator="player")]


class NewGame(BaseModel):
    """The settings chosen in the settings modal: the Mode and who plays each side, with the settings of each LLM
    side, and the rules for every LLM in the game. Sampling isn't one of them: it comes from the config file."""

    model_config = ConfigDict(extra="forbid")

    mode: Mode = Settings.mode
    white: SideIn = Settings.white
    black: SideIn = Settings.black
    rules: Rules = Settings.rules  # refused unless every LLM side is under Free or Listed


# Sampling options keep the type they were given in: an int stays an int in the JSON (top_k 40, not 40.0).
Sampling = dict[str, int | float]


class ModelInfo(BaseModel):
    """A model the game can be played against, with the sampling it would play at."""

    name: str
    thinking: bool
    sampling: Sampling | None  # None when Ollama can't show the model


def is_none(value: object) -> bool:
    return value is None


class Resolution(BaseModel):
    """How the resolver read an LLM's move under Chaos rules (ADR 0006), so a replay never resolves it again."""

    kind: Literal["legal", "chaos", "spawn", "invalid"]
    from_square: str | None = Field(alias="from")  # None for a spawn
    to: str | None
    piece: str | None  # the symbol of the piece that ends up on to, e.g. "q" for a black queen
    rook: list[str] | None  # a castling rook's from and to
    reason: str


class Attempt(BaseModel):
    """One try of an LLM turn, as the game log has it. Most fields are None until the LLM has answered."""

    move: str | None  # the move as written, or the raw reply if it isn't the move schema
    san: str | None  # the move's standard SAN, when it is legal
    notation_slip: bool
    result: Literal["legal", "invalid", "illegal", "ambiguous", "timeout", "error"] | None
    feedback_sent: str | None  # the retry feedback this try answers, None on the first
    raw_reply: str | None
    thinking: str | None
    error: str | None  # why the call failed or timed out
    latency_s: float | None
    # Only under Chaos rules, and only when there was a move to resolve; a chaos move or spawn was played.
    resolution: Resolution | None = Field(None, exclude_if=is_none)


class LlmTurn(BaseModel):
    ply: int
    color: Color
    attempts: list[Attempt]
    thinking: str | None  # the thinking of the last try that answered


class IllegalMoves(BaseModel):
    invalid: int
    illegal: int
    ambiguous: int


class LlmSideStats(BaseModel):
    """The totals of one LLM side. Under Enforced decoding the illegal-move metrics are None (ADR 0003)."""

    legal_move_streak: int | None
    illegal_moves: IllegalMoves | None
    recovered_turns: int | None
    notation_slips: int
    # Only under Chaos rules: the chaos moves played, spawns included, and the spawns among them.
    chaos_moves: int | None = Field(None, exclude_if=is_none)
    spawns: int | None = Field(None, exclude_if=is_none)


class Stats(BaseModel):
    """The totals of each side; a human's side has none (ADR 0004)."""

    white: LlmSideStats | None
    black: LlmSideStats | None


class GameSettings(BaseModel):
    mode: Mode
    white: SideIn
    black: SideIn
    sampling: Sampling  # from the config file; empty means the models' defaults
    # Left out under Standard rules, so a Standard rules game reads as it did before Chaos rules existed.
    rules: Rules | None = Field(None, exclude_if=lambda rules: rules in (None, "standard"))


class GameState(BaseModel):
    """What GameSession.state() returns: the game as the page shows it."""

    game_id: str
    fen: str
    pgn: str
    turn: Color
    human_legal_moves: list[str]
    last_move: str | None  # in UCI
    check: bool
    llm_turn: LlmTurn | None  # the last LLM turn
    llm_turns: list[LlmTurn]
    settings: GameSettings
    status: Literal["playing", "over"]
    result: Literal["1-0", "0-1", "1/2-1/2"] | None
    end_reason: str | None  # "checkmate", "forfeit", "king_capture", ...
    stats: Stats


def create_app(
    player_for: Callable[[Settings, Color], LlmPlayer],
    games_dir: Path = GAMES_DIR,
    models: list[LlmModel] = LLM_MODELS,
    sampling_defaults: Callable[[str], dict[str, float]] = lambda model: {},
    sampling_file: Path = SAMPLING_FILE,
    dist_dir: Path = DIST_DIR,
) -> FastAPI:
    """player_for builds the LLM player of each LLM side of a game, from that game's settings and the side's colour.

    models are the models the game can be played against, and sampling_defaults gives a model's own sampling."""
    app = FastAPI(title="ChessLLM")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    game: GameSession | None = None

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/next", include_in_schema=False, response_model=None)
    def next_page() -> FileResponse | PlainTextResponse:
        """The React app, served here while the old page stays at /."""
        index = dist_dir / "index.html"
        if not index.is_file():
            return PlainTextResponse(
                f"The frontend isn't built: {index} is missing. Run `pnpm install && pnpm build` in frontend/, "
                "then reload this page.",
                status_code=503,
            )
        return FileResponse(index)

    @app.get("/api/models")
    def list_models() -> list[ModelInfo]:
        """Each model with the sampling it would play at: its own defaults, overridden by the config file.

        The sampling is None when Ollama can't show the model, e.g. when it isn't installed."""
        config = sampling_config()

        def sampling(model: LlmModel) -> Sampling | None:
            try:
                return sampling_defaults(model.name) | config
            except Exception:
                return None

        return [ModelInfo(name=model.name, thinking=model.thinking, sampling=sampling(model)) for model in models]

    def sampling_config() -> dict[str, float]:
        try:
            return load_sampling(sampling_file)
        except ValueError as error:
            raise HTTPException(500, str(error)) from None

    @app.post("/api/games")
    def start_game(new_game: NewGame | None = None) -> GameState:
        nonlocal game
        new_game = new_game or NewGame()
        settings = Settings(
            new_game.mode, new_game.white, new_game.black, sampling=sampling_config(), rules=new_game.rules
        )
        problem = settings.problem(models)
        if problem is not None:
            raise HTTPException(400, problem)
        players = {color: player_for(settings, color) for color in settings.llm_sides()}
        game = GameSession(players, settings, GameLog(games_dir, *settings.side_names()))
        return GameState.model_validate(game.state())

    def current_game() -> GameSession:
        if game is None:
            raise HTTPException(404, "no game started")
        return game

    @app.get("/api/games/current")
    def get_game() -> GameState:
        return GameState.model_validate(current_game().state())

    @app.post("/api/games/current/moves")
    def play_move(move: HumanMove) -> GameState:
        session = current_game()
        try:
            session.play_human_move(move.uci)
        except RejectedHumanMove as error:
            raise HTTPException(400, str(error)) from None
        return GameState.model_validate(session.state())

    @app.post("/api/games/current/llm-turn")
    def play_llm_turn() -> GameState:
        """The only way an LLM turn starts. The page asks for one whenever a state says it is an LLM's turn, which
        in an LLM faceoff is every turn until the game ends.

        The state returned is that of the game the turn was played in, even if a new game has started since."""
        session = current_game()
        try:
            session.play_llm_turn()
        except RefusedLlmTurn as error:
            raise HTTPException(409, str(error)) from None
        return GameState.model_validate(session.state())

    @app.get("/api/leaderboard")
    def get_leaderboard() -> Leaderboard:
        """Every finished game's results, grouped by Player configuration, read from the game logs."""
        return leaderboard(games_dir)

    return app
