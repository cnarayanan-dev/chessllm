"""A Probe (CONTEXT.md, ADR 0010): the LLM of a side asked once more about the position of one of its past turns, with
any Prompt template, outside the game. A fresh Prompt for that position, even for a side whose Turn memory keeps a
conversation, sent in one attempt with no Retry and judged as an attempt is. It changes nothing in the game: it is
recorded only in the game's probe log (logs/probe_log.py)."""

import random
from collections.abc import Sequence

import chess
from pydantic import BaseModel

from chessllm.core.types import Color, Sampling
from chessllm.game.llm_turn.judging import answered, judge, no_answer
from chessllm.game.llm_turn.prompt import TurnPosition, fresh_prompt
from chessllm.game.records import Attempt, AttemptResult, PromptMessage
from chessllm.game.rules import Rules
from chessllm.game.sides import ENFORCED, LISTED, LlmConstraints, LlmSide, PromptTemplate
from chessllm.llm.players import LlmPlayer


class Probe(BaseModel):
    """One Probe as the probe log and the API have it: the turn it asked about (its ply and the side's colour), the
    model and the settings it was asked with, the side's, the Prompt template in full, and the attempt, with the
    whole Prompt sent, the raw answer, the Thinking or the Reasoning, how it was judged and its latency."""

    game_id: str
    ply: int
    color: Color
    model: str
    thinking: bool
    llm_constraints: LlmConstraints
    sampling: Sampling  # the game's, from the config file; empty means the model's defaults
    prompt_template: PromptTemplate
    attempt: Attempt
    asked_at: str


def ask_probe(
    player: LlmPlayer,
    side: LlmSide,
    template: PromptTemplate,
    color: Color,
    rules: Rules,
    board: chess.Board,
    moves: Sequence[str],
) -> Attempt:
    """Ask the side's LLM for a move in the position of one of its turns, with a fresh Prompt built from the template,
    as a fresh turn of the side shows the position: under Listed with the legal moves in a new random order, as each
    turn has them, and under Enforced decoding with the answer held to them. board is that position, and moves every
    ply before the turn as written in the Move record. The template has been checked against the side's LLM
    constraints (check_prompt_template).

    The legal moves are shuffled by a random order of its own, so asking never moves on the game's."""
    legal_moves = [board.san(legal) for legal in board.legal_moves]
    allowed_moves = list(legal_moves) if side.llm_constraints in ENFORCED else None
    listed = side.llm_constraints in LISTED
    if listed:
        random.Random().shuffle(legal_moves)
    position = TurnPosition(board, moves, " ".join(legal_moves) if listed else None)
    messages = fresh_prompt(template, color, position)
    prompt = [PromptMessage(role=message.role, content=message.content) for message in messages]
    try:
        reply = player.reply(messages, allowed_moves)
    except Exception as error:
        return no_answer(side.model, error, prompt, None)
    result: AttemptResult
    written, move, result = judge(board, reply.raw)
    if result == "invalid" and reply.forced and reply.stop_reason == "length":
        result = "cut_off"  # as a turn's attempt: no answer, rather than a bad one
    resolution = rules.resolve(board, written, result)
    recorded = resolution.record() if resolution is not None else None
    return answered(board, reply, written, move, result, side.thinking, prompt, None, recorded)
