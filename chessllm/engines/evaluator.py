"""The Evaluator port: an engine's evaluation of a position, for centipawn loss and accuracy."""

from typing import Protocol

from chess.engine import Score


class Evaluator(Protocol):
    """How good a position is for the side to move, by a fixed search.

    The real adapter is Stockfish (chessllm.engines.stockfish_evaluator); tests use a fake."""

    @property
    def version(self) -> str:
        """What the analysis file records as the engine used, e.g. "Stockfish 19"."""
        ...

    @property
    def search(self) -> dict[str, int]:
        """The search settings every position is evaluated with, as recorded in the analysis file."""
        ...

    def evaluate(self, fen: str) -> Score:
        """The evaluation of fen, a valid position that isn't over, relative to the side to move."""
        ...
