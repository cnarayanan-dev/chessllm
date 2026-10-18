"""The Ollama adapter for the LLM player port."""

import time
from collections.abc import Callable

import ollama

from chessllm.players import LlmReply, Message, MoveAnswer


class OllamaPlayer:
    """Asks a local Ollama model for a move, with thinking on and the answer shaped by the move schema."""

    def __init__(self, model: str, chat: Callable[..., ollama.ChatResponse] = ollama.chat) -> None:
        self._model = model
        self._chat = chat

    def reply(self, messages: list[Message]) -> LlmReply:
        started = time.perf_counter()
        response = self._chat(
            model=self._model,
            messages=[{"role": message.role, "content": message.content} for message in messages],
            think=True,
            format=MoveAnswer.model_json_schema(),
        )
        latency_s = time.perf_counter() - started
        return LlmReply(raw=response.message.content or "", thinking=response.message.thinking, latency_s=latency_s)
