"""The decision model port: the one place the game talks to a System 1 model (ADR 0012)."""

from collections.abc import Sequence
from typing import Protocol


class DecisionModel(Protocol):
    def decide(self, state: str, question: str, options: Sequence[str]) -> list[float]:
        """The probability of each option, in the order given and summing to 1, that the model gives as the answer to
        the question about the state: one forward pass, no text. Raises DecisionModelFailed if it can't."""
        ...
