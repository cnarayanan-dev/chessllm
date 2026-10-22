"""HTTP API and static page."""

import functools
import hashlib
import json
import logging
import threading
import weakref
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from chessllm.analytics.analysis import analyse_game
from chessllm.engines.evaluator import Evaluator
from chessllm.game.session import (
    AnchorSide,
    Color,
    GameSession,
    HumanSide,
    LlmSide,
    MAX_ATTEMPTS_RANGE,
    Mode,
    Rules,
    RefusedLlmTurn,
    RejectedHumanMove,
    Settings,
)
from chessllm.logs.game_log import GAMES_DIR, GameLog
from chessllm.analytics.leaderboard import Leaderboard, leaderboard
from chessllm.analytics.move_quality import VALIDATION_FILE
from chessllm.engines.move_model import MoveModel
from chessllm.llm.models import LLM_MODELS, SAMPLING_FILE, LlmModel, load_sampling
from chessllm.llm.players import LlmPlayer

STATIC_DIR = Path(__file__).parent.parent / "static"
# The React app's build (frontend/, `pnpm build`), git-ignored. Its files are served under /static/dist/.
DIST_DIR = STATIC_DIR / "dist"
# The fingerprint of the API description the build's types (frontend/src/api/schema.ts) were made from.
BUILD_FINGERPRINT_FILE = "api-fingerprint.txt"


def api_fingerprint(description: dict[str, Any]) -> str:
    """The sha256 of an OpenAPI description, written canonically, so that the same API always gives the same one."""
    canonical = json.dumps(description, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class HumanMove(BaseModel):
    uci: str


# The app starts Play LLM games and LLM faceoffs; an Anchor match is started from the command line
# (anchor-match), so no Anchor side is taken here.
AppMode = Literal["play_llm", "llm_faceoff"]
SideIn = Annotated[HumanSide | LlmSide, Field(discriminator="player")]
SideOut = Annotated[HumanSide | LlmSide | AnchorSide, Field(discriminator="player")]


class NewGame(BaseModel):
    """The settings chosen in the New game sheet: the Mode and who plays each side, with the settings of each LLM
    side, and the rules for every LLM in the game. Sampling isn't one of them: it comes from the config file."""

    model_config = ConfigDict(extra="forbid")

    mode: AppMode = "play_llm"
    white: SideIn = HumanSide()
    black: SideIn = LlmSide()
    rules: Rules = Settings.rules  # refused unless every LLM side is under Free or Listed
    # Illegal moves per turn before an LLM forfeits, the same for every LLM in the game.
    max_attempts: int = Field(default=Settings.max_attempts, ge=MAX_ATTEMPTS_RANGE[0], le=MAX_ATTEMPTS_RANGE[-1])


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


class PromptMessage(BaseModel):
    """One message of the Prompt, as sent to the LLM."""

    role: Literal["system", "user", "assistant"]
    content: str


class Attempt(BaseModel):
    """One try of an LLM turn, as the game log has it. Most fields are None until the LLM has answered."""

    move: str | None  # the move as written, or the raw reply if it isn't the move schema
    san: str | None  # the move's standard SAN, when it is legal
    notation_slip: bool
    result: Literal["legal", "invalid", "illegal", "ambiguous", "timeout", "error"] | None
    feedback_sent: str | None  # the retry feedback this try answers, None on the first
    raw_reply: str | None
    thinking: str | None  # the Thinking, with thinking on
    reasoning: str | None  # the Reasoning in the answer, with thinking off
    error: str | None  # why the call failed or timed out
    latency_s: float | None
    prompt: list[PromptMessage] | None = None  # the messages sent for this try; None in games from before it was kept
    # Only under Chaos rules, and only when there was a move to resolve; a chaos move or spawn was played.
    resolution: Resolution | None = Field(None, exclude_if=is_none)


class LlmTurn(BaseModel):
    ply: int
    color: Color
    attempts: list[Attempt]
    thinking: str | None  # the thinking of the last try that answered
    reasoning: str | None  # the Reasoning of the last try: the one played, or the last before a Forfeit


class Ply(BaseModel):
    """One ply of the game as played, for the page's move history: it shows any ply's position and animates into
    it without chess logic of its own (ADR 0001). The LLM turn that played it, if any, has the same ply number."""

    ply: int  # 1 for White's first move
    color: Color  # the side that moved
    move: str  # in UCI, with any promotion (e7e8q); a Spawn as a drop (Q@d5)
    written: str  # as in the Move record: standard SAN, or a chaos move in the LLM's own spelling
    fen_before: str
    fen_after: str
    check: bool  # whether the side to move after the ply is in check
    # Only for a chaos move or spawn: its resolution, as its attempt has it, so a replay never resolves it again.
    resolution: Resolution | None = Field(None, exclude_if=is_none)


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
    white: SideOut
    black: SideOut
    sampling: Sampling  # from the config file; empty means the models' defaults
    # Left out under Standard rules, so a Standard rules game reads as it did before Chaos rules existed.
    rules: Rules | None = Field(None, exclude_if=lambda rules: rules in (None, "standard"))
    max_attempts: int


class GameState(BaseModel):
    """What GameSession.state() returns: the game as the page shows it."""

    game_id: str
    fen: str
    pgn: str
    turn: Color
    human_legal_moves: list[str]
    last_move: str | None  # in UCI
    plies: list[Ply]  # every ply played, in order
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
    move_model: MoveModel | None = None,
    move_quality_validation: Path = VALIDATION_FILE,
    evaluator: Evaluator | None = None,
) -> FastAPI:
    """player_for builds the LLM player of each LLM side of a game, from that game's settings and the side's colour.

    models are the models the game can be played against, and sampling_defaults gives a model's own sampling.
    With a move_model or an evaluator, each game is analysed into its analysis file when it ends, after the response
    is sent: its Move-quality estimate with the move_model, and its centipawn loss and accuracy with the evaluator."""
    app = FastAPI(title="ChessLLM")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    game: GameSession | None = None
    game_swap = threading.Lock()  # so each new game abandons the one it replaces, even if two start at once
    game_logs: weakref.WeakKeyDictionary[GameSession, Path] = weakref.WeakKeyDictionary()

    def analyse(log: Path) -> None:
        try:
            analyse_game(log, move_model, evaluator)
        except Exception:  # the game is over and logged either way; `analyse-games` can redo it
            logging.getLogger(__name__).exception("could not analyse %s", log)

    def respond(session: GameSession, background: BackgroundTasks) -> GameState:
        """The game's state, and its analysis started if this request ended it."""
        state = GameState.model_validate(session.state())
        if state.status == "over" and (move_model is not None or evaluator is not None):
            background.add_task(analyse, game_logs[session])
        return state

    @app.get("/", include_in_schema=False, response_model=None)
    @app.get("/analytics", include_in_schema=False, response_model=None)
    def page() -> FileResponse | PlainTextResponse:
        """The React app, from its build: the game at /, the analytics page at /analytics.

        A build made for a different API is refused rather than left to break in the browser."""
        index = dist_dir / "index.html"
        if not index.is_file():
            return PlainTextResponse(
                f"The frontend isn't built: {index} is missing. Run `pnpm install && pnpm build` in frontend/, "
                "then reload this page.",
                status_code=503,
            )
        built_for = build_fingerprint()
        running = running_fingerprint()
        if built_for != running:
            return PlainTextResponse(
                f"The frontend build in {dist_dir} was made for a different API (fingerprint {built_for or 'missing'}) "
                f"than the one running (fingerprint {running}). Run `pnpm install && pnpm build` in frontend/, "
                "then reload this page. If the API itself changed, run `uv run python -m scripts.generate_api_types` "
                "first.",
                status_code=503,
            )
        return FileResponse(index)

    @functools.cache
    def running_fingerprint() -> str:
        """Taken on the first page load rather than here, once every route is in the description."""
        return api_fingerprint(app.openapi())

    def build_fingerprint() -> str | None:
        try:
            return (dist_dir / BUILD_FINGERPRINT_FILE).read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None

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

        # The models are asked at once, so a stalled Ollama holds the list up for one timeout, not one per model.
        with ThreadPoolExecutor() as pool:
            samplings = list(pool.map(sampling, models))
        return [
            ModelInfo(name=model.name, thinking=model.thinking, sampling=model_sampling)
            for model, model_sampling in zip(models, samplings)
        ]

    def sampling_config() -> dict[str, float]:
        try:
            return load_sampling(sampling_file)
        except ValueError as error:
            raise HTTPException(500, str(error)) from None

    @app.get("/api/games/defaults")
    def new_game_defaults() -> NewGame:
        """The settings a new game is started with when none are given. The New game sheet starts from them when
        there is no game to copy."""
        return NewGame()

    @app.post("/api/games")
    def start_game(new_game: NewGame | None = None) -> GameState:
        nonlocal game
        new_game = new_game or NewGame()
        settings = Settings(
            new_game.mode,
            new_game.white,
            new_game.black,
            sampling=sampling_config(),
            rules=new_game.rules,
            max_attempts=new_game.max_attempts,
        )
        problem = settings.problem(models)
        if problem is not None:
            raise HTTPException(400, problem)
        players = {color: player_for(settings, color) for color in settings.llm_sides()}
        log = GameLog(games_dir, *settings.side_names())
        session = GameSession(players, settings, log)
        game_logs[session] = log.path
        with game_swap:
            previous, game = game, session
        if previous is not None:
            previous.abandon()
        return GameState.model_validate(session.state())

    def current_game() -> GameSession:
        if game is None:
            raise HTTPException(404, "no game started")
        return game

    @app.get("/api/games/current")
    def get_game() -> GameState:
        return GameState.model_validate(current_game().state())

    @app.post("/api/games/current/moves")
    def play_move(move: HumanMove, background: BackgroundTasks) -> GameState:
        session = current_game()
        try:
            session.play_human_move(move.uci)
        except RejectedHumanMove as error:
            raise HTTPException(400, str(error)) from None
        return respond(session, background)

    @app.post("/api/games/current/llm-turn")
    def play_llm_turn(background: BackgroundTasks) -> GameState:
        """The only way an LLM turn starts. The page asks for one whenever a state says it is an LLM's turn, which
        in an LLM faceoff is every turn until the game ends.

        The state returned is that of the game the turn was played in, even if a new game has started since."""
        session = current_game()
        try:
            session.play_llm_turn()
        except RefusedLlmTurn as error:
            raise HTTPException(409, str(error)) from None
        return respond(session, background)

    @app.get("/api/leaderboard")
    def get_leaderboard() -> Leaderboard:
        """Every finished game's results, grouped by Player configuration, read from the game logs."""
        return leaderboard(games_dir, move_quality_validation)

    return app
