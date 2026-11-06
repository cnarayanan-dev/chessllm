"""Play a game unattended, to its end, through the same game session as the app's Modes: what the command-line
batches and the sample logs play their games with."""

import time
from collections.abc import Callable

from chessllm.engines.anchors import Anchor
from chessllm.core.types import Color
from chessllm.game.records import GameState
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog
from chessllm.system1.port import DecisionModel


def play_anchor_match(
    settings: Settings,
    players: dict[Color, LlmPlayer],
    anchors: dict[Color, Anchor],
    log: GameLog,
    clock: Callable[[], float] = time.monotonic,
    decision_models: dict[Color, DecisionModel] | None = None,
    seed: int | None = None,
) -> GameState:
    """Play the game to its end, each turn by the side to move: the Anchor's, a System 1 model's (from its entry in
    decision_models) or else the LLM's, timed by clock. seed seeds the random source of the System 1 sides, a fresh
    one if none is given. Returns its last state."""
    game = GameSession(players, settings, log, anchors, clock, decision_models=decision_models, seed=seed)
    system1_sides = settings.system1_sides()
    while (state := game.state()).status == "playing":
        if state.turn in anchors:
            game.play_anchor_turn()
        elif state.turn in system1_sides:
            game.play_system1_turn()
        else:
            game.play_llm_turn()
    return state
