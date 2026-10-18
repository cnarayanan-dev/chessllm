"""The Ollama adapter for the LLM player port."""

import time
from collections.abc import Callable

import httpx
import ollama

from chessllm.players import LlmReply, LlmTimeout, Message, MoveAnswer

# Long thinking can run for many minutes and still end without an answer, so a turn is cut off here.
TIMEOUT_S = 300.0


class OllamaPlayer:
    """Asks a local Ollama model for a move, with thinking on and the answer shaped by the move schema.

    A call that takes longer than timeout_s is cancelled: closing the connection also stops Ollama generating."""

    def __init__(
        self, model: str, chat: Callable[..., ollama.ChatResponse] | None = None, timeout_s: float = TIMEOUT_S
    ) -> None:
        self._model = model
        self._chat = chat or ollama.Client(timeout=timeout_s).chat
        self.timeout_s = timeout_s

    def reply(self, messages: list[Message]) -> LlmReply:
        started = time.perf_counter()
        try:
            response = self._chat(
                model=self._model,
                messages=[{"role": message.role, "content": message.content} for message in messages],
                think=True,
                format=MoveAnswer.model_json_schema(),
            )
        except httpx.TimeoutException:
            raise LlmTimeout(self.timeout_s) from None
        latency_s = time.perf_counter() - started
        return LlmReply(raw=response.message.content or "", thinking=response.message.thinking, latency_s=latency_s)
