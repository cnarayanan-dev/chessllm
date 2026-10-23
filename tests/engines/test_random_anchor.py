"""The random legal mover: an Anchor that plays a uniformly random legal move, seeded per game (ADR 0011)."""

import chess
import pytest

from chessllm.engines.anchors import ANCHOR_RATINGS, RandomAnchor
from chessllm.exceptions import AnchorUnavailable


def self_play(seed: int, plies: int = 200) -> list[str]:
    """The moves of a game of two random movers sharing one seed, to its end or the given number of plies."""
    anchor, board, moves = RandomAnchor(seed), chess.Board(), []
    while not board.is_game_over() and len(moves) < plies:
        fen = board.fen()
        move = anchor.move(board)
        assert board.fen() == fen  # the board is left unchanged
        assert move in board.legal_moves
        moves.append(move.uci())
        board.push(move)
    return moves


def test_every_move_it_plays_is_legal_and_the_seed_reproduces_its_moves():
    first = self_play(seed=7)

    assert len(first) > 20
    assert self_play(seed=7) == first
    assert self_play(seed=8) != first


def test_it_plays_every_legal_move_of_a_position_given_enough_seeds():
    board = chess.Board()

    played = {RandomAnchor(seed).move(board) for seed in range(400)}

    assert played == set(board.legal_moves)  # all 20 opening moves


def test_with_no_legal_move_it_is_unavailable():
    mated = chess.Board("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3")

    with pytest.raises(AnchorUnavailable):
        RandomAnchor(1).move(mated)


def test_it_is_rated_at_llm_chess_calibration_with_a_wider_prior_than_dragon():
    random_mover = ANCHOR_RATINGS["anchor:random"]

    assert random_mover.rating == -122
    assert random_mover.uncertainty > ANCHOR_RATINGS["anchor:dragon:1"].uncertainty
