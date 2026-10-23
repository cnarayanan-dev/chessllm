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


def play_anchor_match(
    settings: Settings,
    players: dict[Color, LlmPlayer],
    anchors: dict[Color, Anchor],
    log: GameLog,
    clock: Callable[[], float] = time.monotonic,
) -> GameState:
    """Play the game to its end, each turn by the side to move: the LLM's turn or the Anchor's, timed by clock.
    Returns its last state."""
    game = GameSession(players, settings, log, anchors, clock)
    while (state := game.state()).status == "playing":
        if state.turn in anchors:
            game.play_anchor_turn()
        else:
            game.play_llm_turn()
    return state
