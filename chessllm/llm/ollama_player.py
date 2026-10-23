"""The Ollama adapter for the LLM player port."""

import json
import re
import time
from collections.abc import Callable, Collection, Iterable, Sequence
from typing import Any

import httpx
import ollama

from chessllm.core.config import OLLAMA_REPLY_TIMEOUT_S
from chessllm.core.types import Sampling
from chessllm.llm.models import BUDGET_SENTENCE, FORCED_ANSWER_TOKENS
from chessllm.llm.players import (
    FailedAfterToolCalls,
    LlmReply,
    Message,
    MoveAnswer,
    ReasonedMoveAnswer,
    Tool,
    ToolCall,
)
from chessllm.exceptions import LlmTimeout


def time_limit_s(budget: int | None, tokens_per_s: float | None) -> float:
    """The per-call time limit of a side with this Thinking budget, generating at tokens_per_s (ADR 0007): the
    budget's time with 50% to spare, plus 60 s for the prompt, a re-prefill for the forced answer and a model swap,
    and never below the limit without a budget."""
    if budget is None or tokens_per_s is None:
        return OLLAMA_REPLY_TIMEOUT_S
    return max(OLLAMA_REPLY_TIMEOUT_S, 60 + 1.5 * budget / tokens_per_s)


class OllamaPlayer:
    """Asks a local Ollama model for a move, with the answer shaped by the move schema.

    With thinking off, the schema asks for the reasoning before the move instead. Under Enforced decoding the move
    is an enum of the allowed moves, so Ollama can only produce one of them; the reasoning stays free.

    A call that takes longer than timeout_s is cancelled: closing the connection also stops Ollama generating.

    thinking is sent to Ollama exactly as given: on, off, or a Thinking level the model offers, e.g. "xhigh".

    With a Thinking budget, a call generates at most budget tokens; a reply cut there is made to answer in one more
    call (ADR 0007). Each call gets the whole time limit.

    With Tools, an attempt is a tool phase of up to tool_call_cap Tool calls, then a forced answer (ADR 0011)."""

    def __init__(
        self,
        model: str,
        thinking: bool | str = True,
        chat: Callable[..., ollama.ChatResponse] | None = None,
        timeout_s: float = OLLAMA_REPLY_TIMEOUT_S,
        sampling: Sampling | None = None,
        budget: int | None = None,
        tool_call_cap: int = 10,
    ) -> None:
        self._model = model
        self._thinking = thinking
        self._sampling = sampling or None  # None plays at the model's own defaults
        self.budget = budget
        self.tool_call_cap = tool_call_cap
        self._chat = chat or ollama.Client(timeout=timeout_s).chat
        self.timeout_s = timeout_s

    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Sequence[Tool] = ()
    ) -> LlmReply:
        schema = (MoveAnswer if self._thinking else ReasonedMoveAnswer).model_json_schema()
        if allowed_moves is not None:
            schema["properties"]["move"] = schema["properties"]["move"] | {"enum": allowed_moves}
        turn: list[dict[str, Any]] = [{"role": message.role, "content": message.content} for message in messages]
        started = time.perf_counter()
        if tools:
            return self._tool_reply(turn, schema, tools, started)
        response = self._call(turn, schema, self.budget)
        raw, thinking = response.message.content or "", response.message.thinking
        if self.budget is None or response.done_reason != "length":
            thinking_tokens, answer_tokens, estimated = split_tokens(response.eval_count, thinking or "", raw)
            return LlmReply(
                raw=raw,
                thinking=thinking,
                latency_s=time.perf_counter() - started,
                thinking_tokens=thinking_tokens,
                answer_tokens=answer_tokens,
                prompt_tokens=response.prompt_eval_count,
                stop_reason=response.done_reason,
                token_split_estimated=estimated,
            )
        # The budget ran out: hand the thinking back and take the answer under the same schema, in one more call.
        # Cut while thinking, the thinking so far is closed with the budget sentence; cut while answering, the
        # thinking was complete and goes back unchanged. The content must be a space: with none the model thinks
        # again instead of answering (docs/research/thinking-budget.md).
        cut_while_thinking = not raw
        handed_back = (thinking or "") + BUDGET_SENTENCE if cut_while_thinking else thinking or ""
        forced = self._call(
            [*turn, {"role": "assistant", "thinking": handed_back, "content": " "}], schema, FORCED_ANSWER_TOKENS
        )
        # Cut while thinking, all of the first call was thinking; cut while answering, its cut answer is split off.
        thinking_tokens, _, estimated = split_tokens(response.eval_count, thinking or "", raw)
        return LlmReply(
            raw=forced.message.content or "",
            thinking=thinking,
            latency_s=time.perf_counter() - started,
            thinking_tokens=thinking_tokens,
            answer_tokens=forced.eval_count,
            prompt_tokens=response.prompt_eval_count,
            stop_reason=forced.done_reason,
            token_split_estimated=estimated,
            forced=True,
        )

    def _tool_reply(
        self, turn: list[dict[str, Any]], schema: dict[str, Any], tools: Sequence[Tool], started: float
    ) -> LlmReply:
        """An attempt with Tools (ADR 0011): calls with the tools and no schema, each Tool call run and answered with
        a tool message, until a reply calls none or the Tool-call cap is used up; a reply's calls past the cap are
        neither run nor sent back. Then the move, in one more call under the schema and with no tools. After a reply
        that called none its thinking is handed back, as a Thinking budget's forced answer does (ADR 0007); what it
        wrote is not, as the move is asked for under the schema, but it ends the recorded tool messages.

        A call that fails once Tool calls were made raises FailedAfterToolCalls, so the attempt keeps them."""
        phase = ToolPhase(turn, tools)
        try:
            while phase.calling(self._call(phase.sent, None, None, tools), self.tool_call_cap):
                pass
            forced = self._call(phase.forced_messages(), schema, None)
        except Exception as error:
            if not phase.calls:
                raise
            raise FailedAfterToolCalls(error, phase.calls, phase.added) from error
        raw = forced.message.content or ""
        made = [*phase.made, (forced, raw)]
        split = [split_tokens(response.eval_count, response.message.thinking or "", text) for response, text in made]
        return LlmReply(
            raw=raw,
            thinking=phase.handed_back or forced.message.thinking,
            latency_s=time.perf_counter() - started,
            thinking_tokens=total(thinking for thinking, _, _ in split),
            answer_tokens=total(answer for _, answer, _ in split),
            # Every call's prompt adds up, as Time used does: Tools need fresh Turn memory, so no conversation is
            # sized from it (one would need the first call's alone).
            prompt_tokens=total(response.prompt_eval_count for response, _ in made),
            stop_reason=forced.done_reason,
            token_split_estimated=any(estimated for _, _, estimated in split),
            tool_calls=tuple(phase.calls),
            tool_messages=tuple(phase.added),
            tool_call_as_text=phase.as_text,
        )

    def _call(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        cap: int | None,
        tools: Sequence[Tool] = (),
    ) -> ollama.ChatResponse:
        """One chat call, its generation capped at cap tokens when given: under the answer schema, or in an attempt's
        tool phase with the tools and no schema (ADR 0011)."""
        shape: dict[str, Any] = {"tools": tools} if tools else {"format": schema}
        try:
            return self._chat(
                model=self._model,
                messages=messages,
                think=self._thinking,
                **shape,
                options=self._sampling if cap is None else (self._sampling or {}) | {"num_predict": cap},
            )
        except httpx.TimeoutException:
            raise LlmTimeout(self.timeout_s) from None


class ToolPhase:
    """The tool phase of one attempt with Tools, as its replies come: what is sent next, the Tool calls made and the
    messages they add to the attempt's recorded Prompt, and each reply with the text its answer tokens went to."""

    def __init__(self, turn: list[dict[str, Any]], tools: Sequence[Tool]) -> None:
        self.by_name = {tool.__name__: tool for tool in tools}
        self.sent = list(turn)
        self.calls: list[ToolCall] = []
        self.added: list[Message] = []
        self.made: list[tuple[ollama.ChatResponse, str]] = []  # a tool call's answer tokens are its calls, written
        self.handed_back: str | None = None
        self.as_text = False
        self._started = time.perf_counter()

    def calling(self, response: ollama.ChatResponse, cap: int) -> bool:
        """Take a reply: run and answer the Tool calls it makes within the cap. Whether the phase goes on."""
        latency_s = time.perf_counter() - self._started
        message = response.message
        content = message.content or ""
        requested = list(message.tool_calls or [])[: cap - len(self.calls)]
        if not requested:
            self.made.append((response, content))
            self.as_text = written_as_tool_call(content, self.by_name)
            self.handed_back = message.thinking
            if content:
                self.added.append(Message("assistant", content))
            return False
        names = [call.function.name for call in requested]
        arguments = [dict(call.function.arguments) for call in requested]
        self.made.append((response, content + json.dumps(names)))
        self.sent.append(
            {"role": "assistant", "content": content}
            | ({"thinking": message.thinking} if message.thinking else {})
            | {"tool_calls": [{"function": {"name": n, "arguments": a}} for n, a in zip(names, arguments)]}
        )
        self.added.append(Message("assistant", content, tool_calls=tuple(names)))
        for index, (name, given) in enumerate(zip(names, arguments)):
            result = self.by_name[name]() if name in self.by_name else f"There is no tool {name}."
            self.sent.append({"role": "tool", "content": result, "tool_name": name})
            self.added.append(Message("tool", result, tool_name=name))
            first = index == 0
            self.calls.append(
                ToolCall(
                    tool=name, arguments=given, result=result, thinking=message.thinking if first else None,
                    latency_s=latency_s if first else None,
                )
            )
        self._started = time.perf_counter()  # the next reply's latency starts once these are answered
        return len(self.calls) < cap

    def forced_messages(self) -> list[dict[str, Any]]:
        """What the forced answer is sent: the phase so far, and the thinking of a reply that called none, handed
        back with a blank answer."""
        if not self.handed_back:
            return self.sent
        return [*self.sent, {"role": "assistant", "thinking": self.handed_back, "content": " "}]

def written_as_tool_call(text: str, tools: Collection[str]) -> bool:
    """Whether a reply writes a Tool call as text instead of calling it: a <tool_call> tag, a JSON call naming one of
    the tools, or one of them followed by "(". A tool named in words, e.g. "the board", is no call."""
    names = "|".join(re.escape(name) for name in tools)
    return bool(re.search(rf'<tool_call>|"name"\s*:\s*"({names})"|\b({names})\s*\(', text))


def total(counts: Iterable[int | None]) -> int | None:
    """The sum of the counts reported; None when none was."""
    reported = [count for count in counts if count is not None]
    return sum(reported) if reported else None


def split_tokens(generated: int | None, thinking: str, answer: str) -> tuple[int | None, int | None, bool]:
    """The thinking and answer tokens, and whether the split is estimated. Ollama gives one count for both, so
    when the reply has both they are split by their share of the characters."""
    if generated is None:
        return None, None, False
    if not thinking or not answer:
        return (generated, 0, False) if thinking else (0, generated, False)
    thinking_tokens = round(generated * len(thinking) / (len(thinking) + len(answer)))
    return thinking_tokens, generated - thinking_tokens, True
