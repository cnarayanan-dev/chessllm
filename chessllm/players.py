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
    """The answer schema with thinking on. The move is a free string, never limited to the legal moves."""

    move: str


class LlmPlayer(Protocol):
    def reply(self, messages: list[Message]) -> LlmReply: ...

