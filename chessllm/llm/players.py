"""The LLM player port: the one place the game talks to a language model."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel


# Who a message of the Prompt is from: a tool message answers one of the LLM's Tool calls (ADR 0011).
MessageRole = Literal["system", "user", "assistant", "tool"]
# A Tool as the LLM player takes it: bound to the turn's position, without parameters (game.tools.bound_tools).
Tool = Callable[[], str]


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str
    # Only in an attempt with Tools: the tools an assistant message called, in order, and the tool a tool message
    # answers.
    tool_calls: tuple[str, ...] = ()
    tool_name: str | None = None


class ToolCall(BaseModel):
    """One Tool call of an attempt (ADR 0011), as it was asked for and answered. thinking and latency_s are the reply
    that made it: given with the first of a reply's calls, None for the calls after it in the same reply."""

    tool: str
    arguments: dict[str, Any]  # as the LLM gave them; no tool takes any, so they are never used
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
    # Only with Tools (ADR 0011), where the counts and the latency add up all of the attempt's calls and the stop
    # reason is the forced answer's: its Tool calls in order, the messages of its tool phase (the calls, their
    # results, and the reply that called none, as written), and whether that reply wrote a tool call as text instead
    # of calling it.
    tool_calls: tuple[ToolCall, ...] = ()
    tool_messages: tuple[Message, ...] = ()
    tool_call_as_text: bool = False


class MoveAnswer(BaseModel):
    """The answer schema with thinking on. The move is a free string, unless Enforced decoding limits it to the
    legal moves."""

    move: str


class ReasonedMoveAnswer(BaseModel):
    """The answer schema with thinking off: the reasoning comes first, so the model reasons before it moves."""

    reasoning: str
    move: str


class FailedAfterToolCalls(Exception):
    """A call of an attempt with Tools failed or timed out after it had made Tool calls: error is why, and the calls
    and their messages are as made, so the attempt can record them."""

    def __init__(self, error: Exception, tool_calls: Sequence[ToolCall], tool_messages: Sequence[Message]) -> None:
        super().__init__(str(error))
        self.error = error
        self.tool_calls = tuple(tool_calls)
        self.tool_messages = tuple(tool_messages)


class LlmPlayer(Protocol):
    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Sequence[Tool] = ()
    ) -> LlmReply:
        """Ask the model for its answer. Raises LlmTimeout if it takes longer than the time limit.

        Under Enforced decoding allowed_moves are the legal moves in standard SAN, and the move must be one of
        them; None leaves the move free. tools are the side's Tools, which it may call before it answers; a call
        that fails after some Tool calls raises FailedAfterToolCalls, with the LlmTimeout or other error in it."""
        ...

