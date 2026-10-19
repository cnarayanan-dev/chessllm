"""Faceoff batch: two models play each other from the command line, alternating colours."""

import json

from conftest import ScriptedPlayer

from chessllm.faceoff_batch import main

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
