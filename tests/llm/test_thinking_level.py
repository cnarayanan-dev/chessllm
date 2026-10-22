"""Thinking level: in the benchmark only, an LLM side's thinking can be one of the levels its model offers, e.g.
qwen3.8 at xhigh. It is sent to Ollama as it is, logged when set, and part of the Player configuration."""

import json

import pytest

from tests.conftest import ScriptedPlayer, play_llm

from chessllm.cli.faceoff_batch import main
from chessllm.analytics.leaderboard import llm_configuration

FOOLS_MATE = ["f3", "e5", "g4", "Qh4#"]
# How an LLM side's game_start entry has looked since log version 2 with the default position (ADR 0004).
PLAIN_SIDE_KEYS = {"player", "model", "thinking", "llm_constraints", "retry_feedback"}


def faceoff(tmp_path, *args: str) -> tuple[int, ScriptedPlayer]:
    player = ScriptedPlayer(FOOLS_MATE)
    code = main(
        ["--games", "1", *args, "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )
    return code, player


def game_start(tmp_path) -> dict:
    [log] = tmp_path.glob("*.jsonl")
    return json.loads(log.read_text().splitlines()[0])


def test_a_level_given_for_one_model_reaches_only_its_side_and_is_logged(tmp_path):
    code, player = faceoff(
        tmp_path, "--models", "qwen3.8:latest", "gemma3:12b", "--thinking-for", "qwen3.8:latest=xhigh"
    )

    assert code == 0
    start = game_start(tmp_path)
    assert (start["white"]["thinking"], start["white"]["thinking_level"]) == (True, "xhigh")
    assert set(start["black"]) == PLAIN_SIDE_KEYS and start["black"]["thinking"] is False
    # What each side's player is built to send to Ollama as its thinking.
    settings = player.built_for[0]
    assert (settings.white.think(), settings.black.think()) == ("xhigh", False)


def test_plain_on_and_off_log_as_before_and_send_true_and_false(tmp_path):
    code, player = faceoff(tmp_path, "--models", "qwen3.8:latest", "gemma3:12b", "--thinking-for", "qwen3.8:latest")

    assert code == 0
    start = game_start(tmp_path)
    assert set(start["white"]) == set(start["black"]) == PLAIN_SIDE_KEYS
    settings = player.built_for[0]
    assert (settings.white.think(), settings.black.think()) == (True, False)


def test_a_level_is_its_own_player_configuration_and_plain_on_keeps_its_id(tmp_path):
    faceoff(tmp_path / "xhigh", "--models", "qwen3.8:latest", "gemma3:12b", "--thinking-for", "qwen3.8:latest=xhigh")
    faceoff(tmp_path / "on", "--models", "qwen3.8:latest", "gemma3:12b", "--thinking-for", "qwen3.8:latest")

    xhigh, on = game_start(tmp_path / "xhigh"), game_start(tmp_path / "on")
    with_level = llm_configuration(xhigh, "white", xhigh["white"])
    plain = llm_configuration(on, "white", on["white"])
    # The id a qwen3.8 side with plain thinking on had before levels existed, from a log of that time.
    before = llm_configuration(on, "white", {k: v for k, v in xhigh["white"].items() if k != "thinking_level"})
    assert plain.id() == before.id()
    assert with_level.id() != plain.id()
    assert with_level.thinking_level == "xhigh" and plain.thinking_level is None


@pytest.mark.parametrize(
    ("thinking_for", "reason"),
    [
        ("qwen3.8:latest=high", "qwen3.8:latest (white) has no Thinking level high: it offers low, medium, xhigh"),
        ("gemma4:26b=low", "gemma4:26b (black) has no Thinking levels, only thinking on or off"),
        ("gemma3:12b=low", "gemma3:12b (black) cannot think, so it has no Thinking levels"),
    ],
)
def test_a_level_the_model_doesnt_offer_is_refused_before_any_game(tmp_path, capsys, thinking_for, reason):
    model = thinking_for.split("=")[0]
    first = "qwen3.8:latest" if model == "qwen3.8:latest" else "llama3:8b"
    second = "llama3:8b" if model == "qwen3.8:latest" else model

    code, _ = faceoff(tmp_path, "--models", first, second, "--thinking-for", thinking_for)

    assert code == 1
    assert reason in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))


def test_two_levels_for_one_model_are_refused_before_any_game(tmp_path, capsys):
    code, _ = faceoff(
        tmp_path, "--models", "qwen3.8:latest", "qwen3.8:latest",
        "--thinking-for", "qwen3.8:latest=low", "--thinking-for", "qwen3.8:latest=xhigh",
    )

    assert code == 1
    assert "--thinking-for gives qwen3.8:latest two Thinking levels, low and xhigh" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))


def test_the_api_refuses_a_level_and_plays_plain_thinking(scripted):
    client, player = scripted([])

    refused = client.post("/api/games", json=play_llm(model="qwen3.8:latest", thinking=True, thinking_level="xhigh"))
    response = client.post("/api/games", json=play_llm(model="qwen3.8:latest", thinking=True))

    assert refused.status_code == 422 and "thinking_level" in refused.text
    assert response.status_code == 200
    [settings] = player.built_for
    assert settings.black.think() is True
    assert "thinking_level" not in response.json()["settings"]["black"]


def test_the_leaderboard_shows_a_levels_configuration_without_the_level_under_its_own_id(scripted, tmp_path):
    faceoff(tmp_path / "games", "--models", "qwen3.8:latest", "gemma3:12b", "--thinking-for", "qwen3.8:latest=xhigh")
    faceoff(tmp_path / "games", "--models", "qwen3.8:latest", "gemma3:12b", "--thinking-for", "qwen3.8:latest")
    client, _ = scripted([], games_dir=tmp_path / "games")

    configurations = client.get("/api/leaderboard").json()["configurations"]

    qwen = [entry for entry in configurations if entry["configuration"]["model"] == "qwen3.8:latest"]
    assert len(qwen) == 2 and qwen[0]["id"] != qwen[1]["id"]
    assert qwen[0]["configuration"] == qwen[1]["configuration"]
    assert "thinking_level" not in qwen[0]["configuration"]
