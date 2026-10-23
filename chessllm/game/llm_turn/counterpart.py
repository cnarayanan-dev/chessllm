"""The Legal counterpart of a chaos move: the same LLM asked once more for a legal move in the same position, under
Listed enforced whatever its side's own LLM constraints, in one attempt without a Retry. It is recorded, never played,
and its failure never ends the game. A fresh side is asked with a fresh Prompt; in a conversation kept by Turn
memory it is asked at the end of the conversation and then dropped from it, so the LLM answers with what it knew when
it made the chaos move, and never remembers being asked."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from string import Template

import chess

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import Aside, Conversation, reply_reserve
from chessllm.game.llm_turn.judging import answered, judge, no_answer
from chessllm.game.llm_turn.prompt import TurnPosition, default_template, fresh_prompt, move_record
from chessllm.game.records import LegalCounterpart, PromptMessage
from chessllm.game.sides import LlmConstraints, LlmSide, PromptTemplate
from chessllm.llm.players import LlmPlayer, LlmReply

# The constraints it is asked under: the legal moves shown, and the answer held to them.
COUNTERPART_CONSTRAINTS: LlmConstraints = "listed_enforced"


@dataclass(frozen=True)
class CounterpartAnswer:
    """The Legal counterpart, with what the game log needs of how it was asked: the reply it came from, if there was
    one, for its token counts, and the position it was asked in. In a conversation, also how it was asked aside: how
    many earlier turns its Prompt held, and whether it fit the context."""

    counterpart: LegalCounterpart
    reply: LlmReply | None
    listed_moves: str  # the legal moves as shown
    fen: str
    pgn: str
    aside: Aside | None = None


def counterpart_request(listed_moves: str) -> str:
    """What a Legal counterpart asks at the end of a conversation, right after the chaos move: a legal move for the
    same position, from the Legal-move list."""
    return (
        "That move breaks the rules of chess. Reply with a legal move for the same position instead.\n"
        f"Legal moves: {listed_moves}"
    )


def counterpart_template(template: PromptTemplate) -> PromptTemplate:
    """The Prompt template a fresh side's Legal counterpart is asked with: the side's own if it places the Legal-move
    list, else the default one under Listed enforced, Described if the side's places the position's description. Never
    one that gives only the opponent's last move (chat_moves), which shows a fresh Prompt no position."""
    placed = Template(template.turn_template).get_identifiers()
    if "legal_moves" in placed and "opponent_played" not in placed:
        return template
    described = "description" in placed
    return default_template(COUNTERPART_CONSTRAINTS, "described" if described else "default")


def ask_legal_counterpart(
    player: LlmPlayer,
    side: LlmSide,
    template: PromptTemplate,
    color: Color,
    board: chess.Board,
    moves: Sequence[str],
    conversation: Conversation,
) -> CounterpartAnswer:
    """Ask the side's LLM for a legal move in the position its chaos move was made in. A fresh side is sent a fresh
    Prompt built from counterpart_template of its Prompt template, as a fresh Listed enforced turn shows the
    position. In a conversation kept by Turn memory the request is asked aside at its end, right after the chaos
    move, and the attempt records only the request (ADR 0009), and how many earlier turns it held only when it was
    trimmed alone (counterpart_prompt rebuilds it). board is the position, and moves every ply before the chaos move
    as written in the Move record; conversation is the side's, as the chaos move's turn left it.

    The legal moves are shuffled by an order of the position's own, so asking never moves on the game's random
    order of the Listed sides' lists."""
    legal_moves = [board.san(legal) for legal in board.legal_moves]
    allowed_moves = list(legal_moves)
    random.Random(board.fen()).shuffle(legal_moves)
    listed_moves = " ".join(legal_moves)
    aside, trimmed = None, None
    if conversation.kept:
        aside = conversation.aside(counterpart_request(listed_moves), reply_reserve(side))
        messages, sent = aside.messages, aside.messages[-1:]
        trimmed = aside.remembered if aside.remembered != conversation.remembered else None
    else:
        messages = sent = fresh_prompt(counterpart_template(template), color, TurnPosition(board, moves, listed_moves))
    pgn = move_record(moves)
    prompt = [PromptMessage(role=message.role, content=message.content) for message in sent]
    fen = board.fen()
    try:
        reply = player.reply(messages, allowed_moves)
    except Exception as error:
        attempt = no_answer(side.model, error, prompt, None)
        attempt.remembered = trimmed
        failed = LegalCounterpart(move=None, san=None, fen_after=None, attempt=attempt)
        return CounterpartAnswer(failed, None, listed_moves, fen, pgn, aside)
    written, move, result = judge(board, reply.raw)
    attempt = answered(board, reply, written, move, result, side.thinking, prompt, None)
    attempt.remembered = trimmed
    fen_after = None
    if move is not None:
        after = board.copy(stack=False)
        after.push(move)
        fen_after = after.fen()
    uci = move.uci() if move is not None else None
    counterpart = LegalCounterpart(move=uci, san=attempt.san, fen_after=fen_after, attempt=attempt)
    return CounterpartAnswer(counterpart, reply, listed_moves, fen, pgn, aside)
