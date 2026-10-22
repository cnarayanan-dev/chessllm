"""Scripted fakes for the LLM player and Anchor ports, so games play without Ollama or an engine. Shared by the tests
(through conftest.py) and the sample games (scripts/sample_logs.py)."""

import json
from typing import Any

import chess

from chessllm.game import Color, Settings
from chessllm.players import LlmReply, Message


class Raw(str):
    """A scripted reply sent to the game exactly as written, instead of wrapped as {"move": ...}."""


class ScriptedPlayer:
    """Test fake for the LLM player port: answers with the scripted SAN moves in order, as the JSON
    {"move": "<san>"}, and records every prompt and the allowed moves it came with. A scripted exception is
    raised instead of answering.
    Thinking texts, if given, go with the replies in order, and so do usages: the token counts and stop reason
    each reply reports (none by default). It serves every game, recording the settings of each game it is built
    for."""

    def __init__(self, replies: list[str | BaseException], thinking: list[str] | None = None) -> None:
        self.replies = list(replies)
        self.thinking = list(thinking) if thinking is not None else None
        self.usage: list[dict[str, Any]] = []
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
        move = self.replies.pop(0)
        if isinstance(move, BaseException):
            raise move
        raw = move if isinstance(move, Raw) else json.dumps({"move": move})
        thinking = self.thinking.pop(0) if self.thinking is not None else None
        usage = self.usage.pop(0) if self.usage else {}
        return LlmReply(raw=raw, thinking=thinking, latency_s=0.0, **usage)


class ScriptedAnchor:
    """Test fake for the Anchor port: plays the scripted SAN moves in order, and records every position it was
    asked to move in (as FEN) and whether it was closed."""

    def __init__(self, moves: list[str]) -> None:
        self.moves = list(moves)
        self.positions: list[str] = []
        self.closed = False

    def move(self, board: chess.Board) -> chess.Move:
        self.positions.append(board.fen())
        return board.parse_san(self.moves.pop(0))

    def close(self) -> None:
        self.closed = True
