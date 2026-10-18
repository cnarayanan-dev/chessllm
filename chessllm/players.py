"""The LLM player port: the one place the game talks to a language model."""

from dataclasses import dataclass
from typing import Literal, Protocol

import chess


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LlmReply:
    raw: str
    thinking: str | None
    latency_s: float


class LlmPlayer(Protocol):
    def reply(self, messages: list[Message]) -> LlmReply: ...


class FirstLegalMovePlayer:
    """Placeholder opponent until the Ollama adapter exists: plays the first legal move in the position.

    It reads the position from the "FEN: ..." line of the turn message, like a model would."""

    def reply(self, messages: list[Message]) -> LlmReply:
        fen = next(
            line.removeprefix("FEN: ")
            for line in reversed(messages[-1].content.splitlines())
            if line.startswith("FEN: ")
        )
        board = chess.Board(fen)
        move = next(iter(board.legal_moves))
        return LlmReply(raw=board.san(move), thinking=None, latency_s=0.0)
