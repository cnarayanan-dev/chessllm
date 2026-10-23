"""The Chaos gain of a chaos move (CONTEXT.md): the Evaluation after it minus the Evaluation of each Gain baseline, the
Legal counterpart and Stockfish's best move, in pawns from the mover's point of view.

A position that ends the game has no Evaluation, so it counts by the game's result: +10 for the mover's win (a King
capture), -10 for its loss (a King left in check) and 0 for a draw. With every value capped at ±10, a gain is capped
at ±20."""

from dataclasses import dataclass

from chessllm.core.types import Color, GameResult
from chessllm.game.evaluation import PAWN_CAP
from chessllm.game.records import ChaosGain, Evaluation

WINS: dict[Color, GameResult] = {"white": "1-0", "black": "0-1"}


def for_mover(evaluation: Evaluation | None, mover: Color) -> float | None:
    """The Evaluation in pawns from the mover's point of view, or None if the position wasn't judged."""
    if evaluation is None or evaluation.pawns is None:
        return None
    return evaluation.pawns if mover == "white" else -evaluation.pawns


def result_for_mover(result: GameResult, mover: Color) -> float:
    """What a position that ends the game is worth to the mover, by the result: the cap for a win, minus it for a
    loss, 0 for a draw."""
    if result == "1/2-1/2":
        return 0.0
    return PAWN_CAP if result == WINS[mover] else -PAWN_CAP


@dataclass(frozen=True)
class GainBaselines:
    """What a chaos move's gains are measured against, judged before its move lands: the Evaluation of the position
    before it, and the value to the mover of the position its Legal counterpart would have left: None when none was
    asked for, it failed, or its position wasn't judged."""

    mover: Color
    best_evaluation: Evaluation
    counterpart: float | None

    def gain(self, after: float | None) -> ChaosGain:
        """The gains of the chaos move, given the value to the mover of the position it left (None: not judged)."""
        best = for_mover(self.best_evaluation, self.mover)
        return ChaosGain(
            best_evaluation=self.best_evaluation,
            vs_counterpart=difference(after, self.counterpart),
            vs_best=difference(after, best),
        )


def difference(after: float | None, baseline: float | None) -> float | None:
    if after is None or baseline is None:
        return None
    return round(after - baseline, 2)
