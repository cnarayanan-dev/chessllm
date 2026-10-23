"""The Legal counterpart of a chaos move: the same LLM asked once more for a legal move in the same position, under
Listed enforced whatever its side's own LLM constraints, in one attempt without a Retry. It is recorded, never played,
and its failure never ends the game."""

import random
from dataclasses import dataclass

import chess

from chessllm.core.types import Color
from chessllm.game.llm_turn.judging import answered, judge, no_answer
from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES, describe_position, turn_messages
from chessllm.game.records import LegalCounterpart, PromptMessage
from chessllm.game.sides import LlmConstraints, LlmSide
from chessllm.llm.players import LlmPlayer, LlmReply

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


def ask_legal_counterpart(
    player: LlmPlayer, side: LlmSide, color: Color, board: chess.Board, pgn: str, last_move: str | None
) -> CounterpartAnswer:
    """Ask the side's LLM for a legal move in the position its chaos move was made in, with a fresh Prompt: the
    Listed enforced System prompt and the position as a fresh Listed enforced turn shows it, in the side's position
    format. board is that position, pgn the Move record before the chaos move and last_move its last ply.

    The legal moves are shuffled by an order of the position's own, so asking never moves on the game's random
    order of the Listed sides' lists."""
    legal_moves = [board.san(legal) for legal in board.legal_moves]
    allowed_moves = list(legal_moves)
    random.Random(board.fen()).shuffle(legal_moves)
    listed_moves = " ".join(legal_moves)
    description = describe_position(board, last_move) if side.position == "described" else None
    prompt_file = SYSTEM_PROMPT_FILES[COUNTERPART_CONSTRAINTS]
    messages = turn_messages(pgn, board.fen(), color, prompt_file, listed_moves, description)
    prompt = [PromptMessage(role=message.role, content=message.content) for message in messages]
    fen = board.fen()
    try:
        reply = player.reply(messages, allowed_moves)
    except Exception as error:
        failed = LegalCounterpart(move=None, san=None, fen_after=None, attempt=no_answer(side.model, error, prompt, None))
        return CounterpartAnswer(failed, None, listed_moves, fen, pgn)
    written, move, result = judge(board, reply.raw)
    attempt = answered(board, reply, written, move, result, side.thinking, prompt, None)
    fen_after = None
    if move is not None:
        after = board.copy(stack=False)
        after.push(move)
        fen_after = after.fen()
    uci = move.uci() if move is not None else None
    counterpart = LegalCounterpart(move=uci, san=attempt.san, fen_after=fen_after, attempt=attempt)
    return CounterpartAnswer(counterpart, reply, listed_moves, fen, pgn)
