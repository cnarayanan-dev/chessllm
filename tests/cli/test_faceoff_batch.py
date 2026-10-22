"""Faceoff batch: two models play each other from the command line, alternating colours."""

import json

from tests.conftest import ScriptedPlayer

from chessllm.cli.faceoff_batch import main

FOOLS_MATE = ["f3", "e5", "g4", "Qh4#"]


def test_colours_alternate_and_every_game_is_logged_as_a_faceoff(tmp_path, capsys):
    player = ScriptedPlayer(FOOLS_MATE * 3)

    code = main(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "3", "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    starts = sorted(
        (json.loads(log.read_text().splitlines()[0]) for log in tmp_path.glob("*.jsonl")),
        key=lambda start: start["started_at"],
    )
    assert [start["mode"] for start in starts] == ["llm_faceoff"] * 3
    assert [(s["white"]["model"], s["black"]["model"]) for s in starts] == [
        ("gemma3:12b", "llama3:8b"), ("llama3:8b", "gemma3:12b"), ("gemma3:12b", "llama3:8b"),
    ]
    # Black mates every game: llama3:8b twice, gemma3:12b once.
    assert "Batch: gemma3:12b 1 - 2 llama3:8b" in capsys.readouterr().out


def test_a_model_not_in_the_list_is_refused_before_any_game(tmp_path, capsys):
    code = main(
        ["--models", "nonesuch:1b", "llama3:8b", "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=ScriptedPlayer([]).for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert "nonesuch:1b" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))


def test_thinking_can_be_turned_on_for_one_model_only(tmp_path):
    player = ScriptedPlayer(FOOLS_MATE)

    code = main(
        ["--models", "qwen3.8:latest", "gemma3:12b", "--games", "1", "--thinking-for", "qwen3.8:latest",
         "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    [log] = tmp_path.glob("*.jsonl")
    start = json.loads(log.read_text().splitlines()[0])
    assert (start["white"]["thinking"], start["black"]["thinking"]) == (True, False)


def test_gemma4_plays_with_thinking_on_against_a_model_that_cannot_think(tmp_path):
    player = ScriptedPlayer(FOOLS_MATE)

    code = main(
        ["--models", "gemma4:26b", "llama3:8b", "--games", "1", "--thinking-for", "gemma4:26b",
         "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    [log] = tmp_path.glob("*.jsonl")
    start = json.loads(log.read_text().splitlines()[0])
    assert (start["white"]["model"], start["white"]["thinking"]) == ("gemma4:26b", True)
    assert (start["black"]["model"], start["black"]["thinking"]) == ("llama3:8b", False)
    assert json.loads(log.read_text().splitlines()[-1])["result"] == "0-1"
