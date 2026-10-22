"""The Stockfish Anchor against the real engine. Excluded from the default run; run it with `pytest -m stockfish`.
Skipped when Stockfish isn't installed (`brew install stockfish`)."""

import shutil

import chess
import pytest

from chessllm.engines.anchors import STOCKFISH_LEVELS, StockfishAnchor, configured_stockfish_path, greedy_move

pytestmark = pytest.mark.stockfish


@pytest.mark.skipif(shutil.which("stockfish") is None, reason="Stockfish isn't installed")
@pytest.mark.parametrize("skill", sorted(STOCKFISH_LEVELS))
def test_stockfish_plays_a_legal_move_at_every_skill(skill):
    anchor = StockfishAnchor(configured_stockfish_path(), skill)
    try:
        board = chess.Board()
        assert anchor.move(board) in board.legal_moves
        assert board == chess.Board()
    finally:
        anchor.close()


@pytest.mark.skipif(shutil.which("stockfish") is None, reason="Stockfish isn't installed")
@pytest.mark.parametrize(
    ("fen", "expected"),
    [
        ("4k3/8/8/8/8/8/4R3/K7 w - - 0 1", "e2e8"),  # the enemy king was left en prise: take it
        ("P3k3/8/8/8/8/8/8/4K3 w - - 0 1", None),  # a pawn on the back rank, as a chaos move can leave
        ("rnbqkbnr/pppppppp/n7/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 1", None),  # 17 pieces, after a spawn
    ],
)
def test_stockfish_plays_on_in_positions_only_chaos_rules_reach(fen, expected):
    board = chess.Board(fen)
    anchor = StockfishAnchor(configured_stockfish_path(), 1)
    try:
        move = anchor.move(board.copy())
        assert move in board.legal_moves
        assert expected is None or move.uci() == expected
        assert anchor.move(chess.Board()) in chess.Board().legal_moves  # and is still there afterwards
    finally:
        anchor.close()


def test_the_greedy_move_takes_the_most_valuable_piece():
    board = chess.Board("4k3/8/8/3q4/5n2/3R4/8/4K3 w - - 0 1")
    assert greedy_move(board).uci() == "d3d5"
