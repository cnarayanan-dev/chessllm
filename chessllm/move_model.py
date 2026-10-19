"""The MoveModel port: how likely a player of a given rating is to play a move in a position."""

from collections.abc import Sequence
from typing import Protocol


class MoveModel(Protocol):
    """Probability of this move in this position for a player rated r, for every r the model tells apart.

    The real adapter is Maia-2 (chessllm.maia2_model); tests use a fake."""

    @property
    def version(self) -> str:
        """What the analysis file records as the model used, e.g. "maia2 0.11.0, rapid model"."""
        ...

    @property
    def ratings(self) -> Sequence[int]:
        """The ratings the model is asked about, ascending, on its own scale (Lichess Rapid for Maia-2)."""
        ...

    def probabilities(self, fen: str, move: str) -> list[float]:
        """The probability that a player rated r plays move (UCI, legal in fen) in fen, for each r in ratings."""
        ...
