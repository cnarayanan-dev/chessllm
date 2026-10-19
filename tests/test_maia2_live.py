"""Live test of the Maia-2 adapter: one short game analysed with the real rapid model.

Excluded from the default run; run it with `pytest -m maia2`. Skipped when Maia-2 can't be started (no uv, or
its environment or model can't be set up). The first run downloads torch and the model, which takes a while."""

import json

import pytest

from conftest import play_llm, play_move

from chessllm.analysis import analyse_game
from chessllm.maia2_model import Maia2MoveModel, Maia2Unavailable

pytestmark = pytest.mark.maia2


@pytest.fixture(scope="module")
def maia2():
    move_model = Maia2MoveModel()
    try:
        move_model.version
    except Maia2Unavailable as error:
        pytest.skip(f"Maia-2 is not available: {error}")
    yield move_model
    move_model.close()


def test_a_short_game_is_analysed_with_maia2(maia2, scripted, tmp_path):
    client, _ = scripted(["e5", "Nc6", "Nf6"], move_model=maia2)
    client.post("/api/games", json=play_llm())
    for uci in ("e2e4", "f1c4", "d1h5", "h5f7"):  # Scholar's mate: the LLM plays three plausible moves
        play_move(client, uci)
    [log] = (tmp_path / "games").glob("*.jsonl")

    analysis = json.loads(log.with_name(f"{log.stem}.analysis.json").read_text(encoding="utf-8"))

    assert analysis["versions"]["move_model"].startswith("maia2 0.11.0, rapid model")
    quality = analysis["move_quality"]
    assert quality["ratings"] == list(range(1000, 2001, 100))
    black = quality["sides"]["black"]
    assert black["estimate"] in quality["ratings"]
    low, high = black["interval"]
    assert 1000 <= low <= black["estimate"] <= high <= 2000
    assert [move["move"] for move in black["moves"]] == ["e7e5", "b8c6", "g8f6"]
    for move in black["moves"]:
        assert all(-20 < log_probability < 0 for log_probability in move["log_probabilities"])


def test_a_common_move_is_likelier_than_a_rare_one(maia2):
    e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

    common, rare = maia2.probabilities(e4, "e7e5"), maia2.probabilities(e4, "g7g5")

    assert all(c > r for c, r in zip(common, rare))
