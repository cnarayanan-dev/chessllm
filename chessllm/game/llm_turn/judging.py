"""Judging an LLM's answer: the move it gives, legal or which kind of illegal move (ADR 0002), and its Reasoning."""

from typing import Literal

import chess
from pydantic import ValidationError

from chessllm.game.records import IllegalResult
from chessllm.llm.players import MoveAnswer, ReasonedMoveAnswer


def judge(board: chess.Board, raw: str) -> tuple[str, chess.Move | None, Literal["legal", IllegalResult]]:
    """Judge the raw answer as given: (the move as written, the legal move or None, "legal" or the failure kind).

    The move is read from either answer schema, since MoveAnswer ignores the reasoning field. An answer that
    isn't the move schema is an invalid move, written as the raw reply."""
    try:
        san = MoveAnswer.model_validate_json(raw).move
    except ValidationError:
        return raw, None, "invalid"
    try:
        move = board.parse_san(san)
    except chess.AmbiguousMoveError:
        return san, None, "ambiguous"
    except chess.IllegalMoveError:
        return san, None, "illegal"
    except chess.InvalidMoveError:
        return san, None, "invalid"
    if not move:  # python-chess reads "--", "0000" and "Z0" as a null move, which would let the LLM pass
        return san, None, "invalid"
    return san, move, "legal"


def reasoning(raw: str) -> str | None:
    """The Reasoning of an answer in the thinking-off schema, or None if the answer has none."""
    try:
        return ReasonedMoveAnswer.model_validate_json(raw).reasoning
    except ValidationError:
        return None
