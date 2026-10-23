"""A Probe (CONTEXT.md, ADR 0010): the LLM of a past turn asked once more about that turn's position, with any Prompt
template, by the side's own model and settings, in one attempt judged as an attempt is. It is outside the game: never
played, never counted in the side's totals, and kept in its own log (logs/probe_log.py), never in the game log."""

import random
from collections.abc import Sequence
from dataclasses import dataclass

import chess
from pydantic import BaseModel

from chessllm.core.types import Color, Sampling
from chessllm.game.llm_turn.judging import answered, judge, no_answer
from chessllm.game.llm_turn.prompt import TurnPosition, fresh_prompt
from chessllm.game.records import Attempt, AttemptResult, PromptMessage
from chessllm.game.rules import Rules
from chessllm.game.sides import ENFORCED, LISTED, LlmSide, PromptTemplate
from chessllm.llm.players import LlmPlayer, LlmReply


class ProbeTemplate(BaseModel):
    """The Prompt template a probe was asked with, in full, as a game's game_start records its sides' (ADR 0010)."""

    id: str | None  # None for a text not saved in the Prompt library
    name: str | None
    system_prompt: str
    turn_template: str

    @classmethod
    def of(cls, template: PromptTemplate) -> "ProbeTemplate":
        return cls(
            id=template.id, name=template.name, system_prompt=template.system_prompt,
            turn_template=template.turn_template,
        )


class Probe(BaseModel):
    """One probe of a past LLM turn, as the API returns it and the probe log keeps it: the game and its log's file, the
    turn's ply and colour, the position probed (its Move record and FEN), the side's model and settings with the game's
    sampling, the template asked with, and the attempt: the full Prompt sent, the raw answer, its Thinking or
    Reasoning, how it was judged and its latency."""

    game_id: str
    game_log: str  # the game log's file name, in the same folder as the probes' own
    ply: int
    color: Color
    pgn: str  # the Move record before the ply
    fen: str  # the position before the ply, the one probed
    side: LlmSide
    sampling: Sampling
    template: ProbeTemplate
    attempt: Attempt
    probed_at: str


@dataclass(frozen=True)
class ProbeAnswer:
    """A probe's attempt, with the reply it came from, if there was one, for the probe log's token counts."""

    attempt: Attempt
    reply: LlmReply | None


def ask_probe(
    player: LlmPlayer,
    side: LlmSide,
    template: PromptTemplate,
    color: Color,
    board: chess.Board,
    moves: Sequence[str],
    rules: Rules,
) -> ProbeAnswer:
    """Ask the side's LLM for a move in the position board, with a fresh Prompt built from template, even for a side
    whose Turn memory keeps a conversation: its System prompt, then the position as a fresh turn of the side shows
    it. moves are the plies before the position as written in the Move record. The template fits the side's LLM
    constraints (check_prompt_template): under Listed it places the Legal-move list, and under Enforced decoding the
    answer is held to the legal moves.

    The list is shuffled by an order of the position's own, as a Legal counterpart's is, so probing never moves on the
    game's random order of the Listed sides' lists.

    The answer is judged as an attempt is (ADR 0002), resolved under the game's Rules, and never played."""
    legal_moves = [board.san(legal) for legal in board.legal_moves]
    allowed_moves = list(legal_moves) if side.llm_constraints in ENFORCED else None
    listed = side.llm_constraints in LISTED
    if listed:
        random.Random(board.fen()).shuffle(legal_moves)
    position = TurnPosition(board, moves, " ".join(legal_moves) if listed else None)
    messages = fresh_prompt(template, color, position)
    prompt = [PromptMessage(role=message.role, content=message.content) for message in messages]
    try:
        reply = player.reply(messages, allowed_moves)
    except Exception as error:
        return ProbeAnswer(no_answer(side.model, error, prompt, None), None)
    result: AttemptResult
    written, move, result = judge(board, reply.raw)
    if result == "invalid" and reply.forced and reply.stop_reason == "length":
        result = "cut_off"  # as in a turn: the forced answer ran out of tokens, so there is no answer to judge
    resolution = rules.resolve(board, written, result)
    recorded = resolution.record() if resolution is not None else None
    return ProbeAnswer(answered(board, reply, written, move, result, side.thinking, prompt, None, recorded), reply)
