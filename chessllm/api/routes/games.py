"""The current game: starting one, its state, a human's move, an LLM turn and the whole Prompt of an attempt."""

import logging
from dataclasses import replace

from fastapi import APIRouter, BackgroundTasks

from chessllm.analytics.analysis import analyse_game
from chessllm.api.deps import ConfigDep, CurrentGame, EnginesDep, GameStoreDep, PromptLibraryDep
from chessllm.api.errors import error_responses
from chessllm.api.schemas.games import HumanMove, NewGame, SideIn
from chessllm.api.state import Engines
from chessllm.core.types import Color
from chessllm.exceptions import (
    InvalidSamplingConfig,
    InvalidSettings,
    NoGameStarted,
    NoLlmAttempt,
    RefusedLlmTurn,
    RejectedHumanMove,
)
from chessllm.game.llm_turn.conversation import TurnPrompt, turn_prompt
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.records import GameState
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.models import load_sampling
from chessllm.logs.game_log import GameLog

router = APIRouter()


@router.get("/api/games/defaults")
def new_game_defaults() -> NewGame:
    """The settings a new game is started with when none are given. The New game sheet starts from them when
    there is no game to copy."""
    return NewGame()


@router.post("/api/games", responses=error_responses(InvalidSettings, InvalidSamplingConfig))
def start_game(
    config: ConfigDep,
    engines: EnginesDep,
    games: GameStoreDep,
    library: PromptLibraryDep,
    new_game: NewGame | None = None,
) -> GameState:
    new_game = new_game or NewGame()
    settings = Settings(
        new_game.mode,
        with_template(new_game.white, "white", library),
        with_template(new_game.black, "black", library),
        sampling=load_sampling(config.sampling_file),
        rules=new_game.rules,
        max_attempts=new_game.max_attempts,
        legal_counterpart=new_game.legal_counterpart,
    )
    settings.check(engines.models)
    players = {color: engines.player_for(settings, color) for color in settings.llm_sides()}
    log = GameLog(config.games_dir, *settings.side_names())
    session = GameSession(players, settings, log, clock=engines.clock, evaluator=engines.evaluator)
    games.start(session)
    return session.state()


def with_template(side: SideIn, color: Color, library: PromptLibrary) -> SideIn:
    """An LLM side with the Prompt template its ID names in the library, or with none for the Default of its LLM
    constraints. Raises InvalidSettings if the library has no such template, or if the side gives one's text: the
    API takes a template by its ID only, so a game always plays one from the library."""
    if not isinstance(side, LlmSide):
        return side
    if side.prompt_template is not None:
        refused = (
            "A new game takes a Prompt template by its ID in the Prompt library (prompt_template_id), not its text: "
            f"the LLM side ({color})"
        )
        raise InvalidSettings(refused, code="prompt_template_not_accepted")
    if side.prompt_template_id is None:
        return side
    return replace(side, prompt_template=library.resolve(side.prompt_template_id, color))


@router.get("/api/games/current", responses=error_responses(NoGameStarted))
def get_game(session: CurrentGame) -> GameState:
    return session.state()


@router.get(
    "/api/games/current/llm-turns/{ply}/attempts/{attempt}/prompt",
    responses=error_responses(NoGameStarted, NoLlmAttempt),
)
def get_attempt_prompt(ply: int, attempt: int, session: CurrentGame) -> TurnPrompt:
    """The whole Prompt of an attempt (numbered from 1) of the LLM turn at ply, by turn, as the LLM received it. In a
    conversation kept by Turn memory the state records only what each attempt added (ADR 0009), so the Turn panel
    asks for it here, rebuilt from the records, with how many of the side's earliest turns were trimmed from it."""
    return turn_prompt(session.state().llm_turns, ply, attempt)


@router.post("/api/games/current/moves", responses=error_responses(RejectedHumanMove, NoGameStarted))
def play_move(move: HumanMove, session: CurrentGame, engines: EnginesDep, background: BackgroundTasks) -> GameState:
    session.play_human_move(move.uci)
    return respond(session, engines, background)


@router.post("/api/games/current/llm-turn", responses=error_responses(NoGameStarted, RefusedLlmTurn))
def play_llm_turn(session: CurrentGame, engines: EnginesDep, background: BackgroundTasks) -> GameState:
    """The only way an LLM turn starts. The page asks for one whenever a state says it is an LLM's turn, which
    in an LLM faceoff is every turn until the game ends.

    The state returned is that of the game the turn was played in, even if a new game has started since."""
    session.play_llm_turn()
    return respond(session, engines, background)


def respond(session: GameSession, engines: Engines, background: BackgroundTasks) -> GameState:
    """The game's state, and its analysis started, after the response is sent, if this request ended it."""
    state = session.state()
    if state.status == "over" and engines.analyses_games():
        background.add_task(analyse, session, engines)
    return state


def analyse(session: GameSession, engines: Engines) -> None:
    try:
        analyse_game(session.log_path, engines.move_model, engines.evaluator)
    except Exception:  # the game is over and logged either way; `analyse-games` can redo it
        logging.getLogger(__name__).exception("could not analyse %s", session.log_path)
