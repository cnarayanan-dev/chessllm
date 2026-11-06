"""Scripted fakes for the LLM player, Anchor and Evaluator ports, so games play without Ollama or an engine. Shared by the tests
(through conftest.py) and the sample games (scripts/sample_logs.py)."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import chess
from chess.engine import Cp, Score

from chessllm.core.types import Color
from chessllm.exceptions import StockfishUnavailable
from chessllm.game.settings import Settings
from chessllm.llm.players import LlmReply, Message, Tool


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
    each reply reports (none by default) and its latency (0 by default). It serves every game, recording the
    settings of each game it is built for. With a clock, each reply advances it by the next of reply_s, the time it
    took."""

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

    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Sequence[Tool] = ()
    ) -> LlmReply:
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
        return LlmReply(**{"raw": raw, "thinking": thinking, "latency_s": 0.0} | usage)


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


class FixedEvaluator:
    """Test fake for the Evaluator port: each position's evaluation, relative to the side to move, from a table,
    and 0 for any other position. Records every position it is asked about."""

    version = "fake-engine 1"
    search = {"depth": 1}

    def __init__(self, scores: dict[str, Score] | None = None) -> None:
        self.scores = scores or {}
        self.asked: list[str] = []

    def evaluate(self, fen: str) -> Score:
        self.asked.append(fen)
        return self.scores.get(fen, Cp(0))


class UnavailableEvaluator:
    """Test fake for the Evaluator port when Stockfish isn't installed."""

    search = {"depth": 1}

    @property
    def version(self) -> str:
        raise StockfishUnavailable("stockfish is not on the PATH")

    def evaluate(self, fen: str) -> Score:
        raise StockfishUnavailable("stockfish is not on the PATH")


PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 300, chess.ROOK: 500, chess.QUEEN: 900}


class MaterialEvaluator:
    """Test fake for the Evaluator port that judges a position by its material alone, relative to the side to move:
    deterministic, so the sample games and the Playwright journeys get Evaluations without Stockfish."""

    version = "material count"
    search = {"depth": 0}

    def evaluate(self, fen: str) -> Score:
        board = chess.Board(fen)
        balance = sum(
            value * (len(board.pieces(piece, board.turn)) - len(board.pieces(piece, not board.turn)))
            for piece, value in PIECE_VALUES.items()
        )
        return Cp(balance)


class NotInstalled:
    """Test fake for the check of which models Ollama doesn't have (missing_models): an Ollama without the given
    models. Records the models it is asked about."""

    def __init__(self, *missing: str) -> None:
        self.missing = missing
        self.asked: list[list[str]] = []

    def __call__(self, models: list[str]) -> list[str]:
        self.asked.append(models)
        return [model for model in models if model in self.missing]


@dataclass(frozen=True)
class Asked:
    """One question put to a FakeDecisionModel."""

    state: str
    question: str
    options: list[str]


class FakeDecisionModel:
    """Test fake for the decision model port: answers each question from the script in order, then every one
    with equal probabilities. An entry is the weights of the moves it favours, e.g. {"e4": 3, "d4": 1}, taken as
    probabilities once the options it doesn't mention (weight 0) are left out; one that mentions none of the
    options gives equal probabilities. An exception is raised instead of answering. Records every question put to
    it, and with a clock, advances it by the next of think_s, the time each answer took."""

    def __init__(self, script: Sequence[Mapping[str, float] | BaseException] = ()) -> None:
        self.script = list(script)
        self.asked: list[Asked] = []
        self.clock: FakeClock | None = None
        self.think_s: list[float] = []

    @classmethod
    def favouring(cls, *moves: str) -> "FakeDecisionModel":
        """A fake that gives the SAN moves in turn all the probability, then equal probabilities."""
        return cls([{move: 1.0} for move in moves])

    def decide(self, state: str, question: str, options: Sequence[str]) -> list[float]:
        self.asked.append(Asked(state, question, list(options)))
        if self.clock is not None and self.think_s:
            self.clock.advance(self.think_s.pop(0))
        step = self.script.pop(0) if self.script else {}
        if isinstance(step, BaseException):
            raise step
        weights = [step.get(option, 0.0) for option in options]
        if not sum(weights):
            weights = [1.0] * len(options)
        return [weight / sum(weights) for weight in weights]
