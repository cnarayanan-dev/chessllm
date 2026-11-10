"""An Aborted game (ADR 0013): a game stopped because the Hosted model's provider failed for a reason that is not the
model's play. No side loses; the game stays in the log with its reason and counts towards nothing."""

import json

import pytest

from tests.conftest import play_llm

from chessllm.analytics.leaderboard import leaderboard
from chessllm.analytics.ranking import ranking
from chessllm.exceptions import HostedModelFailed, LlmTimeout, ReplyDeclined
from chessllm.llm.models import KNOWN_MODELS

HAIKU = "claude-haiku-5-5"


@pytest.fixture(autouse=True)
def claude_token(monkeypatch):
    monkeypatch.setenv("CLAUDE_TOKEN", "a-token-for-a-test")


FAILED = HostedModelFailed("claude-haiku-5-5: the provider refused the token: invalid x-api-key")


def start(scripted, replies, **options):
    client, player = scripted(replies, models=KNOWN_MODELS, **options)
    assert client.post("/api/games", json=play_llm("white", model=HAIKU)).status_code == 200
    return client, player


def events(tmp_path) -> list[dict]:
    [log] = (tmp_path / "games").glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_a_provider_failure_aborts_the_game_without_a_result(scripted, tmp_path):
    client, _ = start(scripted, [FAILED])
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    response = client.post("/api/games/current/llm-turn")

    assert response.status_code == 200
    state = response.json()
    assert state["status"] == "aborted"
    assert state["abort_reason"] == str(FAILED)
    assert state["result"] is None
    assert state["end_reason"] is None
    assert state["human_legal_moves"] == []
    assert state["running_s"] is None
    assert state["llm_turn"] is None  # the turn that failed is no turn of the game


def test_an_aborted_game_stays_in_the_log_with_its_reason_and_no_game_end(scripted, tmp_path):
    client, _ = start(scripted, [FAILED])
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    client.post("/api/games/current/llm-turn")

    logged = events(tmp_path)
    assert [event["type"] for event in logged] == ["game_start", "human_move", "game_aborted"]
    aborted = logged[-1]
    assert aborted["reason"] == str(FAILED)
    assert aborted["color"] == "black"
    assert aborted["ply"] == 2
    assert aborted["aborted_at"]
    assert not list((tmp_path / "games").glob("*.pgn"))  # no result to export


def test_the_attempts_made_before_the_failure_are_kept(scripted, tmp_path):
    client, _ = start(scripted, ["Qh5", FAILED])  # an illegal first attempt, then the provider fails
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    client.post("/api/games/current/llm-turn")

    assert [event["type"] for event in events(tmp_path)] == ["game_start", "human_move", "llm_attempt", "game_aborted"]


def test_nothing_more_is_played_in_an_aborted_game(scripted):
    client, _ = start(scripted, [FAILED])
    client.post("/api/games/current/moves", json={"uci": "e2e4"})
    client.post("/api/games/current/llm-turn")

    turn = client.post("/api/games/current/llm-turn")
    move = client.post("/api/games/current/moves", json={"uci": "d2d4"})

    assert (turn.status_code, turn.json()["code"]) == (409, "game_aborted")
    assert (move.status_code, move.json()["code"]) == (400, "game_aborted")
    assert client.get("/api/games/current").json()["status"] == "aborted"


def test_a_faceoff_with_a_hosted_model_aborts_on_its_turn_too(faceoff, tmp_path):
    client, state, players = faceoff([FAILED], [], white_settings={"model": HAIKU}, models=KNOWN_MODELS)

    response = client.post("/api/games/current/llm-turn")

    assert response.json()["status"] == "aborted"
    assert events(tmp_path)[-1]["type"] == "game_aborted"


def test_an_aborted_game_counts_in_no_leaderboard_or_ranking(scripted, tmp_path):
    client, _ = start(scripted, [FAILED])
    client.post("/api/games/current/moves", json={"uci": "e2e4"})
    client.post("/api/games/current/llm-turn")

    assert leaderboard(tmp_path / "games").configurations == []
    assert ranking(tmp_path / "games").models == []


def test_a_declined_reply_is_a_forfeit_and_so_is_one_that_times_out(scripted):
    for failure in (ReplyDeclined("claude-haiku-5-5 declined to answer"), LlmTimeout(300)):
        client, _ = start(scripted, [failure])
        client.post("/api/games/current/moves", json={"uci": "e2e4"})

        state = client.post("/api/games/current/llm-turn").json()

        assert (state["status"], state["result"], state["end_reason"]) == ("over", "1-0", "forfeit")
        assert "abort_reason" not in state
