"""The Legal counterpart of a chaos move: the same LLM asked once more for a legal move in the same position, under
Listed enforced whatever its side's own LLM constraints, in one attempt without a Retry. It is recorded, never played,
and its failure never ends the game.

In a conversation kept by Turn memory it is asked aside, at the end of the conversation so far, and then dropped
from it: the LLM answers with what it knew when it made the chaos move, and never remembers being asked. The
conversation keeps its own System prompt, written for the side's own LLM constraints; the request after it carries
the Legal-move list, and the answer is held to it."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from string import Template

import chess

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import Conversation, reply_reserve
from chessllm.game.llm_turn.judging import answered, judge, no_answer
from chessllm.game.llm_turn.prompt import TurnPosition, default_template, fresh_prompt, move_record
from chessllm.game.records import LegalCounterpart, PromptMessage
from chessllm.game.sides import LlmConstraints, LlmSide, PromptTemplate
from chessllm.llm.players import LlmPlayer, LlmReply, Message

# The constraints it is asked under: the legal moves shown, and the answer held to them.
COUNTERPART_CONSTRAINTS: LlmConstraints = "listed_enforced"


@dataclass(frozen=True)
class CounterpartAnswer:
    """The Legal counterpart, with what the game log needs of how it was asked: the reply it came from, if there was
    one, for its token counts, and the position it was asked in."""

    counterpart: LegalCounterpart
    reply: LlmReply | None
    listed_moves: str  # the legal moves as shown
    fen: str
    pgn: str
    fits: bool = True  # whether its Prompt fitted the context, which only a conversation's may not


def counterpart_template(template: PromptTemplate) -> PromptTemplate:
    """The Prompt template a Legal counterpart is asked with: the side's own if it places the Legal-move list, else
    the default one under Listed enforced, Described if the side's places the position's description."""
    if "legal_moves" in Template(template.turn_template).get_identifiers():
        return template
    described = "description" in Template(template.turn_template).get_identifiers()
    return default_template(COUNTERPART_CONSTRAINTS, "described" if described else "default")


def counterpart_request(listed_moves: str) -> str:
    """The message a conversation's Legal counterpart is asked with, after the chaos move's answer."""
    return f"Your move is illegal in this position. Reply with a legal move instead.\nLegal moves: {listed_moves}"


def ask_legal_counterpart(
    player: LlmPlayer,
    side: LlmSide,
    template: PromptTemplate,
    color: Color,
    board: chess.Board,
    moves: Sequence[str],
    conversation: Conversation,
) -> CounterpartAnswer:
    """Ask the side's LLM for a legal move in the position its chaos move was made in. A fresh side is asked with a
    fresh Prompt built from counterpart_template of the side's Prompt template, as a fresh Listed enforced turn
    shows the position, and records it whole. A side whose conversation is kept is asked aside from it, at its end
    (Conversation.aside), and records only its request, with how many earlier turns its Prompt held (ADR 0009).
    board is that position, and moves every ply before the chaos move as written in the Move record.

    The legal moves are shuffled by an order of the position's own, so asking never moves on the game's random
    order of the Listed sides' lists."""
    legal_moves = [board.san(legal) for legal in board.legal_moves]
    allowed_moves = list(legal_moves)
    random.Random(board.fen()).shuffle(legal_moves)
    listed_moves = " ".join(legal_moves)
    messages: list[Message]
    if conversation.kept:
        aside = conversation.aside(counterpart_request(listed_moves), reply_reserve(side))
        messages, recorded, remembered, fits = aside.messages, aside.messages[-1:], aside.remembered, aside.fits
    else:
        messages = fresh_prompt(counterpart_template(template), color, TurnPosition(board, moves, listed_moves))
        recorded, remembered, fits = messages, None, True
    pgn = move_record(moves)
    prompt = [PromptMessage(role=message.role, content=message.content) for message in recorded]
    own = {"remembered": remembered}
    fen = board.fen()
    try:
        reply = player.reply(messages, allowed_moves)
    except Exception as error:
        attempt = no_answer(side.model, error, prompt, None).model_copy(update=own)
        failed = LegalCounterpart(move=None, san=None, fen_after=None, attempt=attempt)
        return CounterpartAnswer(failed, None, listed_moves, fen, pgn, fits)
    written, move, result = judge(board, reply.raw)
    attempt = answered(board, reply, written, move, result, side.thinking, prompt, None).model_copy(update=own)
    fen_after = None
    if move is not None:
        after = board.copy(stack=False)
        after.push(move)
        fen_after = after.fen()
    uci = move.uci() if move is not None else None
    counterpart = LegalCounterpart(move=uci, san=attempt.san, fen_after=fen_after, attempt=attempt)
    return CounterpartAnswer(counterpart, reply, listed_moves, fen, pgn, fits)
