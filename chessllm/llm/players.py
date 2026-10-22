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
    """The model's answer and Thinking, with what the call used. A count is None when the model reported none."""

    raw: str
    thinking: str | None
    latency_s: float
    thinking_tokens: int | None = None
    answer_tokens: int | None = None
    prompt_tokens: int | None = None
    # Why generation stopped, as Ollama says: "stop", "length", ... For a forced answer, why the forced call stopped.
    stop_reason: str | None = None
    token_split_estimated: bool = False  # thinking and answer were counted together and split by characters
    # The Thinking budget ran out, so the answer was taken in a second, forced call (ADR 0007).
    forced: bool = False


class MoveAnswer(BaseModel):
    """The answer schema with thinking on. The move is a free string, unless Enforced decoding limits it to the
    legal moves."""

    move: str


class ReasonedMoveAnswer(BaseModel):
    """The answer schema with thinking off: the reasoning comes first, so the model reasons before it moves."""

    reasoning: str
    move: str


class LlmPlayer(Protocol):
    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        """Ask the model for its answer. Raises LlmTimeout if it takes longer than the time limit.

        Under Enforced decoding allowed_moves are the legal moves in standard SAN, and the move must be one of
        them; None leaves the move free."""
        ...

