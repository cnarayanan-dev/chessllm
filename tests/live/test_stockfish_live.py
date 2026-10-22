"""Live test of the Stockfish adapter: one short game analysed with the real engine.

Excluded from the default run; run it with `pytest -m stockfish`. Skipped when Stockfish isn't installed
(`brew install stockfish`)."""

import json

import pytest

from tests.conftest import play_llm, play_move

from chessllm.engines.stockfish_evaluator import StockfishEvaluator
from chessllm.exceptions import StockfishUnavailable

pytestmark = pytest.mark.stockfish


@pytest.fixture(scope="module")
def stockfish():
    evaluator = StockfishEvaluator(depth=10)
    try:
        evaluator.version
    except StockfishUnavailable as error:
        pytest.skip(f"Stockfish is not available: {error}")
    yield evaluator
    evaluator.close()


def test_a_short_game_is_analysed_with_stockfish(stockfish, scripted, tmp_path):
    client, _ = scripted(["e5", "Nc6", "Nf6"], evaluator=stockfish)
    client.post("/api/games", json=play_llm())
    for uci in ("e2e4", "f1c4", "d1h5", "h5f7"):  # Scholar's mate: 3...Nf6 allows mate in one
        play_move(client, uci)
    [log] = (tmp_path / "games").glob("*.jsonl")

    analysis = json.loads(log.with_name(f"{log.stem}.analysis.json").read_text(encoding="utf-8"))

    assert analysis["versions"]["stockfish"].startswith("Stockfish")
    diagnostics = analysis["centipawn_loss_and_accuracy"]
    assert diagnostics["search"] == {"depth": 10, "threads": 1, "hash_mb": 64}
    moves = diagnostics["sides"]["black"]["moves"]
    assert [move["move"] for move in moves] == ["e7e5", "b8c6", "g8f6"]
    assert moves[2]["evaluation_after"] == -1000  # the blunder into mate
    assert moves[2]["accuracy"] < 20 < 80 < moves[0]["accuracy"]


def test_the_same_position_gets_the_same_evaluation(stockfish):
    e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    first = stockfish.evaluate(e4)
    stockfish.evaluate("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")

    assert stockfish.evaluate(e4) == first
