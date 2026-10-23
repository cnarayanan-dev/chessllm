"""Evaluation: the one place an engine's score becomes the Evaluation a ply records (CONTEXT.md), from White's point of
view, in pawns capped at ±10, or a mate in so many moves.

A position that isn't valid chess, as a Chaos move can leave (ADR 0006), is never sent to the engine: Stockfish quits
on such positions. It gets a written reason instead, and is never patched up to be judged."""

import logging

import chess
from chess.engine import PovScore

from chessllm.engines.evaluator import Evaluator
from chessllm.game.records import Evaluation

PAWN_CAP = 10.0

# Why a position isn't valid chess, by python-chess's status flags, the first that applies.
UNJUDGED_REASONS = [
    (chess.STATUS_NO_WHITE_KING | chess.STATUS_NO_BLACK_KING, "a king is missing"),
    (chess.STATUS_TOO_MANY_KINGS, "a side has more than one king"),
    (chess.STATUS_PAWNS_ON_BACKRANK, "a pawn stands on a back rank"),
    (chess.STATUS_TOO_MANY_WHITE_PAWNS | chess.STATUS_TOO_MANY_BLACK_PAWNS, "a side has more than 8 pawns"),
    (chess.STATUS_TOO_MANY_WHITE_PIECES | chess.STATUS_TOO_MANY_BLACK_PIECES, "a side has more than 16 pieces"),
    (chess.STATUS_OPPOSITE_CHECK, "the side not to move is in check"),
    (chess.STATUS_TOO_MANY_CHECKERS | chess.STATUS_IMPOSSIBLE_CHECK, "the check can't arise in a game of chess"),
]
OTHER_REASON = "it isn't a position a game of chess can reach"


def unjudged_reason(board: chess.Board) -> str | None:
    """Why the position can't be judged, or None if it is valid chess."""
    status = board.status()
    if status == chess.STATUS_VALID:
        return None
    return next((reason for flags, reason in UNJUDGED_REASONS if status & flags), OTHER_REASON)


def evaluation_of(score: PovScore) -> Evaluation:
    """An engine's score as an Evaluation, from White's point of view."""
    white = score.white()
    mate = white.mate()
    if mate is not None:
        return Evaluation(pawns=PAWN_CAP if mate > 0 else -PAWN_CAP, mate=mate, unjudged=None)
    centipawns = white.score()
    assert centipawns is not None
    return Evaluation(pawns=max(-PAWN_CAP, min(PAWN_CAP, centipawns / 100)), mate=None, unjudged=None)


def judge(board: chess.Board, evaluator: Evaluator) -> Evaluation:
    """The Evaluation of the position on board, which mustn't be over. An engine that fails leaves it not judged,
    with the engine's error as the reason: the game goes on either way."""
    reason = unjudged_reason(board)
    if reason is not None:
        return Evaluation(pawns=None, mate=None, unjudged=reason)
    try:
        score = evaluator.evaluate(board.fen())
    except Exception as error:  # an engine that crashed or quit must never stop the game
        logging.getLogger(__name__).exception("could not evaluate %s", board.fen())
        return Evaluation(pawns=None, mate=None, unjudged=f"the engine failed: {error}")
    return evaluation_of(PovScore(score, board.turn))
