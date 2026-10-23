"""The random legal mover, the lowest Anchor (ADR 0011): a uniformly random legal move, from a seed per game, with no
engine binary."""

import chess
import pytest

from chessllm.engines.anchors import ANCHOR_RATINGS, RANDOM_MOVER_RATING, RandomAnchor, anchor_name
from chessllm.exceptions import AnchorUnavailable


def self_play(seed: int, plies: int = 400) -> list[str]:
    """A game of the random mover against itself from the seed, as UCI moves, to its end or the ply limit."""
    anchor, board, moves = RandomAnchor(seed), chess.Board(), []
    while not board.is_game_over() and len(moves) < plies:
        before = board.fen()
        move = anchor.move(board)
        assert board.fen() == before  # the board is left unchanged
        assert board.is_legal(move)
        board.push(move)
        moves.append(move.uci())
    return moves


@pytest.mark.parametrize("seed", [0, 1, 121, 2**31])
def test_every_move_it_plays_is_legal(seed):
    assert len(self_play(seed)) > 10


def test_the_same_seed_plays_the_same_moves_and_another_seed_others():
    assert self_play(7) == self_play(7)
    assert self_play(7) != self_play(8)


def test_it_draws_every_legal_move_alike():
    anchor, board = RandomAnchor(3), chess.Board()
    counts = {move: 0 for move in board.legal_moves}

    for _ in range(4000):
        counts[anchor.move(board)] += 1

    assert len(counts) == 20 and min(counts.values()) > 100  # 200 expected each


def test_it_plays_a_position_python_chess_calls_invalid_as_under_chaos_rules():
    board = chess.Board("4k3/8/8/8/8/8/8/R7 w - - 0 1")
    board.remove_piece_at(chess.E8)  # no Black King, as after a King capture

    assert board.is_legal(RandomAnchor(1).move(board))


def test_with_no_legal_move_it_is_unavailable():
    board = chess.Board("7k/5QQ1/8/8/8/8/8/K7 b - - 0 1")  # mated

    with pytest.raises(AnchorUnavailable, match="no legal move"):
        RandomAnchor(1).move(board)


def test_it_is_rated_at_minus_122_with_a_prior_wider_than_dragons():
    side = {"player": "anchor", "engine": "random", "seed": 5}

    assert anchor_name(side) == "anchor:random"
    assert ANCHOR_RATINGS["anchor:random"] == RANDOM_MOVER_RATING
    assert RANDOM_MOVER_RATING.rating == -122
    assert RANDOM_MOVER_RATING.uncertainty > ANCHOR_RATINGS["anchor:dragon:1"].uncertainty
