"""The Ollama adapter for the LLM player port."""

import re
import time
from collections.abc import Callable, Iterable
from typing import Any

import httpx
import ollama

from chessllm.core.config import OLLAMA_REPLY_TIMEOUT_S
from chessllm.core.types import Sampling
from chessllm.llm.models import BUDGET_SENTENCE, CONTEXT_TOKENS, FORCED_ANSWER_TOKENS
from chessllm.llm.players import (
    FailedAfterToolCalls,
    LlmReply,
    Message,
    MoveAnswer,
    ReasonedMoveAnswer,
    ToolCall,
    Tools,
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

    With Tools, an attempt first lets the model call them, then asks for its move (ADR 0011)."""

    def __init__(
        self,
        model: str,
        thinking: bool | str = True,
        chat: Callable[..., ollama.ChatResponse] | None = None,
        timeout_s: float = OLLAMA_REPLY_TIMEOUT_S,
        sampling: Sampling | None = None,
        budget: int | None = None,
    ) -> None:
        self._model = model
        self._thinking = thinking
        self._sampling = sampling or None  # None plays at the model's own defaults
        self.budget = budget
        self._chat = chat or ollama.Client(timeout=timeout_s).chat
        self.timeout_s = timeout_s

    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Tools | None = None
    ) -> LlmReply:
        schema = (MoveAnswer if self._thinking else ReasonedMoveAnswer).model_json_schema()
        if allowed_moves is not None:
            schema["properties"]["move"] = schema["properties"]["move"] | {"enum": allowed_moves}
        turn: list[dict[str, Any]] = [{"role": message.role, "content": message.content} for message in messages]
        if tools is not None:
            return self._reply_with_tools(turn, schema, tools)
        started = time.perf_counter()
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

    def _reply_with_tools(self, turn: list[dict[str, Any]], schema: dict[str, Any], tools: Tools) -> LlmReply:
        """An attempt with Tools (ADR 0011). The tool phase calls with the tools and no answer schema; every tool call
        of a reply is run and answered with a tool message, until the model replies without one or has made its last
        allowed call (calls beyond the cap are left out, neither run nor sent back). A reply that writes a tool call
        as text instead is not run and ends the phase. Then one more call, with the answer schema and no tools, gives
        the move. A reply that ended the phase is handed back first, its thinking with it, as for a Thinking budget's
        forced answer (ADR 0007): with its text, or a single space when it has none.

        The reply's Thinking is every call's, in order. A call that fails or times out once the attempt has made a
        tool call, or written one as text, raises FailedAfterToolCalls, so the attempt still records them."""
        started = time.perf_counter()
        by_name = {function.__name__: function for function in tools.functions}
        sent = list(turn)
        added: list[Message] = []
        calls: list[ToolCall] = []
        responses: list[ollama.ChatResponse] = []
        as_text = False

        def ask(offered: tuple[Callable[[], str], ...], answer_schema: dict[str, Any] | None) -> ollama.ChatResponse:
            try:
                return self._call(list(sent), answer_schema, None, offered)  # sent grows: each call has its own
            except Exception as error:
                if not calls and not as_text:
                    raise
                raise FailedAfterToolCalls(error, tuple(calls), tuple(added), as_text) from error

        while len(calls) < tools.cap:
            called = time.perf_counter()
            response = ask(tools.functions, None)
            latency_s = time.perf_counter() - called
            responses.append(response)
            message = response.message
            content = message.content or ""
            asked = list(message.tool_calls or [])[: tools.cap - len(calls)]
            if not asked:
                as_text = written_tool_call(content, by_name)
                sent.append({"role": "assistant", "thinking": message.thinking, "content": content or " "})
                added.append(Message("assistant", content or " "))
                break
            sent.append(
                {
                    "role": "assistant",
                    "content": content,
                    "thinking": message.thinking,
                    "tool_calls": [
                        {"function": {"name": call.function.name, "arguments": call.function.arguments}}
                        for call in asked
                    ],
                }
            )
            added.append(Message("assistant", content, tool_calls=tuple(call.function.name for call in asked)))
            for number, call in enumerate(asked):
                name = call.function.name
                function = by_name.get(name)
                result = function() if function is not None else f"No tool {name}: the tools are {', '.join(by_name)}."
                sent.append({"role": "tool", "tool_name": name, "content": result})
                added.append(Message("tool", result, tool_name=name))
                first = number == 0
                calls.append(
                    ToolCall(
                        tool=name,
                        arguments=dict(call.function.arguments),
                        result=result,
                        thinking=message.thinking if first else None,
                        latency_s=latency_s if first else None,
                    )
                )
        answer = ask((), schema)
        # Each reply's count is split between its thinking and its text; a tool call's own tokens count with its
        # reply's thinking.
        every = [*responses, answer]
        splits = [
            split_tokens(response.eval_count, response.message.thinking or "", response.message.content or "")
            for response in every
        ]
        return LlmReply(
            raw=answer.message.content or "",
            thinking="\n\n".join(text for response in every if (text := response.message.thinking)) or None,
            latency_s=time.perf_counter() - started,
            thinking_tokens=total(split[0] for split in splits),
            answer_tokens=total(split[1] for split in splits),
            prompt_tokens=total(response.prompt_eval_count for response in every),
            stop_reason=answer.done_reason,
            token_split_estimated=any(split[2] for split in splits),
            tool_calls=tuple(calls),
            tool_messages=tuple(added),
            tool_call_as_text=as_text,
        )

    def _call(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any] | None,
        cap: int | None,
        tools: tuple[Callable[[], str], ...] = (),
    ) -> ollama.ChatResponse:
        """One chat call in the CONTEXT_TOKENS context, its generation capped at cap tokens when given: with the
        answer schema as its format, or in a tool phase with the tools and no format (the ollama SDK builds their
        schemas from the functions)."""
        capped = {} if cap is None else {"num_predict": cap}
        offered: dict[str, Any] = {"tools": list(tools)} if tools else {}  # sent only in a tool phase
        try:
            return self._chat(
                model=self._model,
                messages=messages,
                think=self._thinking,
                format=schema,
                options=(self._sampling or {}) | {"num_ctx": CONTEXT_TOKENS} | capped,
                **offered,
            )
        except httpx.TimeoutException:
            raise LlmTimeout(self.timeout_s) from None


def written_tool_call(content: str, tools: Iterable[str]) -> bool:
    """Whether a reply writes a tool call in its text instead of making it: one of the tools named with () right after
    it, e.g. legal_moves(), or a JSON object whose "name" is one of the tools, e.g. {"name": "board"}. Mentioning a
    tool, even before brackets as in "the board (after e4)", is no call."""
    names = "|".join(re.escape(name) for name in tools)
    if not names:
        return False
    return re.search(rf'\b(?:{names})\(\)|\{{\s*"name"\s*:\s*"(?:{names})"', content) is not None


def total(counts: Iterable[int | None]) -> int | None:
    """The sum of the counts the calls reported; None if none reported one."""
    known = [count for count in counts if count is not None]
    return sum(known) if known else None


def split_tokens(generated: int | None, thinking: str, answer: str) -> tuple[int | None, int | None, bool]:
    """The thinking and answer tokens, and whether the split is estimated. Ollama gives one count for both, so
    when the reply has both they are split by their share of the characters."""
    if generated is None:
        return None, None, False
    if not thinking or not answer:
        return (generated, 0, False) if thinking else (0, generated, False)
    thinking_tokens = round(generated * len(thinking) / (len(thinking) + len(answer)))
    return thinking_tokens, generated - thinking_tokens, True
