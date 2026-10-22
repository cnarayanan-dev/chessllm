"""The vocabularies every part of the game shares: colours and results."""

import chess

from chessllm.core.types import color_of, opponent, score_for


def test_a_colour_from_python_chess_and_its_opponent():
    assert color_of(chess.WHITE) == "white"
    assert color_of(chess.BLACK) == "black"
    assert opponent("white") == "black"
    assert opponent("black") == "white"


def test_a_result_scores_one_for_the_winner_none_for_the_loser_and_a_half_each_for_a_draw():
    assert (score_for("1-0", "white"), score_for("1-0", "black")) == (1.0, 0.0)
    assert (score_for("0-1", "white"), score_for("0-1", "black")) == (0.0, 1.0)
    assert (score_for("1/2-1/2", "white"), score_for("1/2-1/2", "black")) == (0.5, 0.5)
