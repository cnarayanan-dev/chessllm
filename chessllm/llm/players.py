"""The LLM player port: the one place the game talks to a language model."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel


# Who a message of the Prompt is from: a tool message is a Tool's answer to a call (ADR 0011).
MessageRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str
    # With Tools only: an assistant message's tool calls, by the name called, in order, and a tool message's tool.
    tool_calls: tuple[str, ...] = ()
    tool_name: str | None = None


@dataclass(frozen=True)
class Tools:
    """The Tools an LLM may call during an attempt (ADR 0011): each a function named as its tool, taking no input
    and answering about the position to move in, its docstring telling the LLM what it gives; and the Tool-call cap
    on them."""

    functions: tuple[Callable[[], str], ...]
    cap: int


@dataclass(frozen=True)
class ToolCall:
    """One tool call of an attempt, as made and answered. The thinking and latency are those of the reply that made
    it, given with the first of its calls only (None with the others), so adding them up counts each reply once."""

    tool: str  # the name called, which may be no tool the side has
    arguments: dict[str, Any]  # as the LLM gave them: no tool takes any, so they are never used
    result: str
    thinking: str | None
    latency_s: float | None


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
    # With Tools (ADR 0011): every tool call of the attempt in order; the messages its tool phase added to the Prompt
    # before the move was asked for, as sent; and whether that phase ended in a tool call written as text instead
    # of made. The latency and counts above add up all the attempt's calls.
    tool_calls: tuple[ToolCall, ...] = ()
    tool_messages: tuple[Message, ...] = ()
    tool_call_as_text: bool = False


class FailedAfterToolCalls(Exception):
    """A call of an attempt with Tools failed or timed out after the attempt had made tool calls, or written one as
    text (ADR 0011): error is why, as the call raised it, and the rest is what the attempt still records of its tool
    phase, as an LlmReply would have it."""

    def __init__(
        self,
        error: Exception,
        tool_calls: tuple[ToolCall, ...],
        tool_messages: tuple[Message, ...],
        tool_call_as_text: bool,
    ) -> None:
        super().__init__(str(error))
        self.error = error
        self.tool_calls = tool_calls
        self.tool_messages = tool_messages
        self.tool_call_as_text = tool_call_as_text


class MoveAnswer(BaseModel):
    """The answer schema with thinking on. The move is a free string, unless Enforced decoding limits it to the
    legal moves."""

    move: str


class ReasonedMoveAnswer(BaseModel):
    """The answer schema with thinking off: the reasoning comes first, so the model reasons before it moves."""

    reasoning: str
    move: str


class LlmPlayer(Protocol):
    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Tools | None = None
    ) -> LlmReply:
        """Ask the model for its answer. Raises LlmTimeout if it takes longer than the time limit.

        Under Enforced decoding allowed_moves are the legal moves in standard SAN, and the move must be one of
        them; None leaves the move free. With tools, it may call them before it is asked for its move (ADR 0011)."""
        ...

