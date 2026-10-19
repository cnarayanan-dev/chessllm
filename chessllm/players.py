"""The LLM player port: the one place the game talks to a language model."""

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LlmReply:
    raw: str
    thinking: str | None
    latency_s: float


class MoveAnswer(BaseModel):
    """The answer schema with thinking on. The move is a free string, unless Enforced decoding limits it to the
    legal moves."""

    move: str


class ReasonedMoveAnswer(BaseModel):
    """The answer schema with thinking off: the reasoning comes first, so the model reasons before it moves."""

    reasoning: str
    move: str


class LlmTimeout(Exception):
    """The model gave no answer within the time limit, so the call was cancelled."""

    def __init__(self, timeout_s: float) -> None:
        super().__init__(f"no answer within {timeout_s:g}s")
        self.timeout_s = timeout_s


class LlmPlayer(Protocol):
    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        """Ask the model for its answer. Raises LlmTimeout if it takes longer than the time limit.

        Under Enforced decoding allowed_moves are the legal moves in standard SAN, and the move must be one of
        them; None leaves the move free."""
        ...

