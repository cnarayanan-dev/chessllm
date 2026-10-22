"""The Ollama adapter for the LLM player port."""

import time
from collections.abc import Callable
from typing import Any

import httpx
import ollama

from chessllm.core.config import OLLAMA_REPLY_TIMEOUT_S
from chessllm.core.types import Sampling
from chessllm.llm.models import FORCED_ANSWER_TOKENS
from chessllm.llm.players import LlmReply, Message, MoveAnswer, ReasonedMoveAnswer
from chessllm.exceptions import LlmTimeout

# Closes the thinking handed back when a Thinking budget runs out, so the model gives its move (ADR 0007).
BUDGET_SENTENCE = "\n\nConsidering the limited time, I have to give my move now, based on the thinking so far."


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
    call (ADR 0007). Each call gets the whole time limit."""

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

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        schema = (MoveAnswer if self._thinking else ReasonedMoveAnswer).model_json_schema()
        if allowed_moves is not None:
            schema["properties"]["move"] = schema["properties"]["move"] | {"enum": allowed_moves}
        turn: list[dict[str, str]] = [{"role": message.role, "content": message.content} for message in messages]
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

    def _call(self, messages: list[dict[str, str]], schema: dict[str, Any], cap: int | None) -> ollama.ChatResponse:
        """One chat call, its generation capped at cap tokens when given."""
        try:
            return self._chat(
                model=self._model,
                messages=messages,
                think=self._thinking,
                format=schema,
                options=self._sampling if cap is None else (self._sampling or {}) | {"num_predict": cap},
            )
        except httpx.TimeoutException:
            raise LlmTimeout(self.timeout_s) from None


def split_tokens(generated: int | None, thinking: str, answer: str) -> tuple[int | None, int | None, bool]:
    """The thinking and answer tokens, and whether the split is estimated. Ollama gives one count for both, so
    when the reply has both they are split by their share of the characters."""
    if generated is None:
        return None, None, False
    if not thinking or not answer:
        return (generated, 0, False) if thinking else (0, generated, False)
    thinking_tokens = round(generated * len(thinking) / (len(thinking) + len(answer)))
    return thinking_tokens, generated - thinking_tokens, True
