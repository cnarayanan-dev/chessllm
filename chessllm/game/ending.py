"""How a game ends by the position: the ends python-chess knows, the draws counted as soon as they arise, and the Move
cap. The game's Rules can add ends of their own (Rules.end), which come first; a Forfeit ends the game in its turn."""

from dataclasses import dataclass
from typing import cast

import chess

from chessllm.core.types import GameResult
from chessllm.game.records import EndReason

MOVE_CAP = 150  # moves per side, so 300 plies


@dataclass(frozen=True)
class GameEnd:
    result: GameResult
    reason: EndReason


def check_end(board: chess.Board, positions: list[str], unattended: bool) -> GameEnd | None:
    """The end of the game if the position is over, counting claimable draws (threefold repetition, fifty moves), or
    an unattended game (its Mode's) at the Move cap, which gives way to an end by the rules on the same move.

    A draw counts once the position has happened, not when the side to move could claim it with its next move (as
    outcome(claim_draw=True) would), so the LLM is never denied a move it could still play.

    positions holds every position of the game, the start position first, each as position_key gives it: repetition
    counts them all, as a chaos move clears python-chess's move stack. So does the Move cap."""
    outcome = board.outcome()
    plies = len(positions) - 1
    if outcome is not None:
        # The termination names double as end reasons, e.g. STALEMATE -> "stalemate".
        return GameEnd(cast(GameResult, outcome.result()), cast(EndReason, outcome.termination.name.lower()))
    if positions.count(positions[-1]) >= 3:
        return GameEnd("1/2-1/2", "threefold_repetition")
    if board.halfmove_clock >= 100:
        return GameEnd("1/2-1/2", "fifty_moves")
    if unattended and plies >= 2 * MOVE_CAP:
        return GameEnd("1/2-1/2", "move_cap")
    return None


def position_key(board: chess.Board) -> str:
    """What makes two positions the same for repetition: the placement, the side to move, the castling rights
    and an en passant square only if a capture there is legal (the first four fields of the FEN)."""
    return " ".join(board.fen().split()[:4])
