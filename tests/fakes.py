"""Scripted fakes for the LLM player and Anchor ports, so games play without Ollama or an engine. Shared by the tests
(through conftest.py) and the sample games (scripts/sample_logs.py)."""

import json
from typing import Any

import chess

from chessllm.core.types import Color
from chessllm.game.settings import Settings
from chessllm.llm.players import LlmReply, Message


class FakeClock:
    """Test fake for the monotonic clock a game times its moves with: it stands still until advanced, by a test or
    by a scripted player or Anchor taking its time."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Raw(str):
    """A scripted reply sent to the game exactly as written, instead of wrapped as {"move": ...}."""


class ScriptedPlayer:
    """Test fake for the LLM player port: answers with the scripted SAN moves in order, as the JSON
    {"move": "<san>"}, and records every prompt and the allowed moves it came with. A scripted exception is
    raised instead of answering.
    Thinking texts, if given, go with the replies in order, and so do usages: the token counts and stop reason
    each reply reports (none by default). It serves every game, recording the settings of each game it is built
    for. With a clock, each reply advances it by the next of reply_s, the time it took."""

    def __init__(self, replies: list[str | BaseException], thinking: list[str] | None = None) -> None:
        self.replies = list(replies)
        self.thinking = list(thinking) if thinking is not None else None
        self.usage: list[dict[str, Any]] = []
        self.clock: FakeClock | None = None
        self.reply_s: list[float] = []
        self.prompts: list[list[Message]] = []
        self.allowed_moves: list[list[str] | None] = []
        self.built_for: list[Settings] = []
        self.colors: list[Color] = []  # the side each build was for

    def for_settings(self, settings: Settings, color: Color) -> "ScriptedPlayer":
        self.built_for.append(settings)
        self.colors.append(color)
        return self

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        self.prompts.append(messages)
        self.allowed_moves.append(allowed_moves)
        if self.clock is not None and self.reply_s:
            self.clock.advance(self.reply_s.pop(0))
        move = self.replies.pop(0)
        if isinstance(move, BaseException):
            raise move
        raw = move if isinstance(move, Raw) else json.dumps({"move": move})
        thinking = self.thinking.pop(0) if self.thinking is not None else None
        usage = self.usage.pop(0) if self.usage else {}
        return LlmReply(raw=raw, thinking=thinking, latency_s=0.0, **usage)


class ScriptedAnchor:
    """Test fake for the Anchor port: plays the scripted SAN moves in order, and records every position it was
    asked to move in (as FEN) and whether it was closed. With a clock, each move advances it by the next of move_s."""

    def __init__(self, moves: list[str]) -> None:
        self.moves = list(moves)
        self.clock: FakeClock | None = None
        self.move_s: list[float] = []
        self.positions: list[str] = []
        self.closed = False

    def move(self, board: chess.Board) -> chess.Move:
        self.positions.append(board.fen())
        if self.clock is not None and self.move_s:
            self.clock.advance(self.move_s.pop(0))
        return board.parse_san(self.moves.pop(0))

    def close(self) -> None:
        self.closed = True
