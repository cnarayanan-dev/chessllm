"""Judging an LLM's answer: the move it gives, legal or which kind of illegal move (ADR 0002), its Reasoning, and the
Attempt it makes."""

from typing import Literal

import chess
from pydantic import ValidationError

from chessllm.exceptions import LlmTimeout
from chessllm.game.records import Attempt, AttemptResult, IllegalResult, PromptMessage, Resolution
from chessllm.llm.players import LlmReply, MoveAnswer, ReasonedMoveAnswer


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


def no_answer(model: str, error: Exception, prompt: list[PromptMessage], feedback: str | None) -> Attempt:
    """The attempt of a call that gave no answer, with why: it timed out, or it failed."""
    if isinstance(error, LlmTimeout):
        minutes = error.timeout_s / 60
        failed: AttemptResult = "timeout"
        why = f"Too long thinking: {model} gave no answer within {minutes:g} minutes."
    else:
        failed, why = "error", f"{model} did not reply: {error}"
    return Attempt(
        move=None, san=None, notation_slip=False, result=failed, feedback_sent=feedback, raw_reply=None,
        thinking=None, reasoning=None, error=why, latency_s=None, prompt=prompt,
    )


def answered(
    board: chess.Board,
    reply: LlmReply,
    written: str,
    move: chess.Move | None,
    result: AttemptResult,
    thinks: bool,
    prompt: list[PromptMessage],
    feedback: str | None,
    resolution: Resolution | None = None,
) -> Attempt:
    """The attempt of an answer judged as written, move and result: with thinking on its Thinking, with it off the
    Reasoning written in the answer instead; a slip if the legal move isn't written exactly as its standard SAN
    (ADR 0002)."""
    thinking, reasoned = (reply.thinking, None) if thinks else (None, reasoning(reply.raw))
    san = board.san(move) if move is not None else None
    return Attempt(
        move=written, san=san, notation_slip=san is not None and written != san, result=result,
        feedback_sent=feedback, raw_reply=reply.raw, thinking=thinking, reasoning=reasoned, error=None,
        latency_s=reply.latency_s, prompt=prompt, resolution=resolution,
    )
