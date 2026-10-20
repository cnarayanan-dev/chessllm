"""The Ollama adapter for the LLM player port."""

import time
from collections.abc import Callable

import httpx
import ollama

from chessllm.players import LlmReply, LlmTimeout, Message, MoveAnswer, ReasonedMoveAnswer

# Long thinking can run for many minutes and still end without an answer, so a turn is cut off here.
TIMEOUT_S = 300.0


class OllamaPlayer:
    """Asks a local Ollama model for a move, with the answer shaped by the move schema.

    With thinking off, the schema asks for the reasoning before the move instead. Under Enforced decoding the move
    is an enum of the allowed moves, so Ollama can only produce one of them; the reasoning stays free.

    A call that takes longer than timeout_s is cancelled: closing the connection also stops Ollama generating."""

    def __init__(
        self,
        model: str,
        thinking: bool = True,
        chat: Callable[..., ollama.ChatResponse] | None = None,
        timeout_s: float = TIMEOUT_S,
        sampling: dict[str, float] | None = None,
    ) -> None:
        self._model = model
        self._thinking = thinking
        self._sampling = sampling or None  # None plays at the model's own defaults
        self._chat = chat or ollama.Client(timeout=timeout_s).chat
        self.timeout_s = timeout_s

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        schema = (MoveAnswer if self._thinking else ReasonedMoveAnswer).model_json_schema()
        if allowed_moves is not None:
            schema["properties"]["move"] = schema["properties"]["move"] | {"enum": allowed_moves}
        started = time.perf_counter()
        try:
            response = self._chat(
                model=self._model,
                messages=[{"role": message.role, "content": message.content} for message in messages],
                think=self._thinking,
                format=schema,
                options=self._sampling,
            )
        except httpx.TimeoutException:
            raise LlmTimeout(self.timeout_s) from None
        latency_s = time.perf_counter() - started
        raw, thinking = response.message.content or "", response.message.thinking
        thinking_tokens, answer_tokens, estimated = split_tokens(response.eval_count, thinking or "", raw)
        return LlmReply(
            raw=raw,
            thinking=thinking,
            latency_s=latency_s,
            thinking_tokens=thinking_tokens,
            answer_tokens=answer_tokens,
            prompt_tokens=response.prompt_eval_count,
            stop_reason=response.done_reason,
            token_split_estimated=estimated,
        )


def split_tokens(generated: int | None, thinking: str, answer: str) -> tuple[int | None, int | None, bool]:
    """The thinking and answer tokens, and whether the split is estimated. Ollama gives one count for both, so
    when the reply has both they are split by their share of the characters."""
    if generated is None:
        return None, None, False
    if not thinking or not answer:
        return (generated, 0, False) if thinking else (0, generated, False)
    thinking_tokens = round(generated * len(thinking) / (len(thinking) + len(answer)))
    return thinking_tokens, generated - thinking_tokens, True
