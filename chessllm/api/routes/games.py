"""The current game: starting one, its state, a human's move and an LLM turn."""

import logging

from fastapi import APIRouter, BackgroundTasks

from chessllm.analytics.analysis import analyse_game
from chessllm.api.deps import ConfigDep, CurrentGame, EnginesDep, GameStoreDep
from chessllm.api.errors import error_responses
from chessllm.api.schemas.games import HumanMove, NewGame
from chessllm.api.state import Engines
from chessllm.exceptions import (
    InvalidSamplingConfig,
    InvalidSettings,
    NoGameStarted,
    RefusedLlmTurn,
    RejectedHumanMove,
)
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
    config: ConfigDep, engines: EnginesDep, games: GameStoreDep, new_game: NewGame | None = None
) -> GameState:
    new_game = new_game or NewGame()
    for color, side in (("white", new_game.white), ("black", new_game.black)):
        # Hidden from the schema until the Prompt library (#113) lets a new game choose one by its ID.
        if isinstance(side, LlmSide) and side.prompt_template is not None:
            refused = f"A new game takes no Prompt template yet: the LLM side ({color}) plays its default one"
            raise InvalidSettings(refused, code="prompt_template_not_accepted")
        # Hidden from the schema until the page shows a conversation's whole Prompt (#108): it would show only what
        # each attempt added (ADR 0009).
        if isinstance(side, LlmSide) and side.turn_memory != "fresh":
            refused = (
                f"A new game takes no Turn memory but fresh yet: the LLM side ({color}) can't play "
                f"{side.turn_memory} from the app, only from the batch commands"
            )
            raise InvalidSettings(refused, code="turn_memory_not_accepted")
    settings = Settings(
        new_game.mode,
        new_game.white,
        new_game.black,
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


@router.get("/api/games/current", responses=error_responses(NoGameStarted))
def get_game(session: CurrentGame) -> GameState:
    return session.state()


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
