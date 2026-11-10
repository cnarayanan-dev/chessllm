"""The benchmark's commands with a Hosted model, Claude Haiku 5.5 (ADR 0013): it needs the provider's token, a refusal
or a timeout is a Forfeit, and a failure of the provider ends the game as an Aborted game and stops the batch. The
player is a ScriptedPlayer, so no test calls the real API or needs a token."""

import json
from pathlib import Path

import pytest

from tests.cli.test_anchor_batch import PlantedResults, logs
from tests.conftest import ScriptedAnchor, ScriptedPlayer

from chessllm.cli import anchor_batch, anchor_match, faceoff_batch
from chessllm.core.config import CLAUDE_TOKEN_VARIABLE
from chessllm.exceptions import HostedModelFailed, LlmTimeout, ReplyDeclined

HAIKU = "claude-haiku-5-5"
FAILED = HostedModelFailed("claude-haiku-5-5: no credit left, or a billing problem: Your credit balance is too low")


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "a-token-for-a-test")


def no_player(settings, color):
    pytest.fail("a player was built before the command found there is no token")


def games(tmp_path) -> list[Path]:
    return sorted((tmp_path / "games").glob("*.jsonl")) if (tmp_path / "games").exists() else []



@pytest.mark.parametrize(
    ("command", "args"),
    [
        (anchor_batch, ["--games", "2", "--skill", "1"]),
        (anchor_match, ["--engine", "random"]),
        (faceoff_batch, ["--models", HAIKU, "llama3:8b", "--games", "2"]),
        (faceoff_batch, ["--models", "llama3:8b", HAIKU, "--games", "2"]),
    ],
)
def test_a_command_asked_for_the_hosted_model_without_a_token_stops_before_the_first_game(
    command, args, tmp_path, capsys
):
    model = ["--model", HAIKU] if command is not faceoff_batch else []
    scripted = ScriptedAnchor([])

    code = command.main(
        [
            "--games-dir", str(tmp_path / "games"), *model, *args,
            *([] if command is anchor_match else ["--no-analysis"]),
        ],
        player_for=no_player,
        **({"anchor_for": lambda side: scripted} if command is not faceoff_batch else {}),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    error = capsys.readouterr().err
    assert HAIKU in error and CLAUDE_TOKEN_VARIABLE in error
    assert games(tmp_path) == []
    assert "a-token-for-a-test" not in error


def test_the_hosted_model_is_never_asked_of_ollama(token, tmp_path):
    asked: list[list[str]] = []

    def missing_models(models):
        asked.append(models)
        return []

    planted = PlantedResults(["draw"])
    code = anchor_batch.main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--model", HAIKU, "--games", "1"],
        player_for=planted.player_for,
        anchor_for=planted.anchor_for,
        sampling_file=tmp_path / "no-sampling.toml",
        missing_models=missing_models,
    )

    assert code == 0
    assert all(HAIKU not in models for models in asked)


def test_a_batch_plays_the_hosted_model_with_a_token_and_logs_it_as_an_llm(token, tmp_path):
    planted = PlantedResults(["draw", "draw"])

    code = anchor_batch.main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--model", HAIKU, "--thinking", "--games", "2"],
        player_for=planted.player_for,
        anchor_for=planted.anchor_for,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    for start, *_ in logs(tmp_path / "games"):
        llm = next(side for side in (start["white"], start["black"]) if side["player"] == "llm")
        assert (llm["model"], llm["thinking"]) == (HAIKU, True)


@pytest.mark.parametrize(
    "flags",
    [["--thinking-level", "high"], ["--thinking-budget", "1024", "--thinking"], ["--tools", "board", "--thinking"]],
)
def test_a_thinking_level_thinking_budget_or_tools_are_refused_for_the_hosted_model(token, tmp_path, capsys, flags):
    code = anchor_batch.main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--model", HAIKU, *flags],
        player_for=no_player,
        anchor_for=lambda side: ScriptedAnchor([]),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert "is a Hosted model, so it has no" in capsys.readouterr().err
    assert games(tmp_path) == []


def test_a_provider_failure_aborts_the_game_and_stops_the_batch_after_it(token, tmp_path, capsys):
    results = PlantedResults(["draw", "draw", "draw"])

    def player_for(settings, color):
        player = results.player_for(settings, color)
        player.replies = [FAILED]
        return player

    code = anchor_batch.main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--model", HAIKU, "--games", "3"],
        player_for=player_for,
        anchor_for=results.anchor_for,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert len(games(tmp_path)) == 1  # the batch stops instead of carrying on
    [aborted] = logs(tmp_path / "games")
    assert aborted[-1]["type"] == "game_aborted"
    assert aborted[-1]["reason"] == str(FAILED)
    error = capsys.readouterr().err
    assert "Anchor match batch stopped" in error
    assert "game 1 was aborted" in error
    assert "credit" in error
    assert "no Rating" in error  # it says the game counts for nothing


def test_an_aborted_game_leaves_the_ladder_as_it_was(token, tmp_path):
    results = PlantedResults(["draw"])

    def aborting(settings, color):
        player = results.player_for(settings, color)
        player.replies = [FAILED]
        return player

    args = ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--model", HAIKU]
    anchor_batch.main([*args, "--games", "1"], player_for=aborting, anchor_for=results.anchor_for,
                      sampling_file=tmp_path / "no-sampling.toml")

    # Run again: the ladder starts at the random mover as White, as no game counts
    again = PlantedResults(["draw"])
    anchor_batch.main([*args, "--games", "1"], player_for=again.player_for, anchor_for=again.anchor_for,
                      sampling_file=tmp_path / "no-sampling.toml")
    [first] = [log for log in logs(tmp_path / "games") if log[-1]["type"] == "game_end"]
    assert first[0]["white"]["player"] == "llm"  # White again: the aborted game was no game of the ladder
    assert again.sides[0].engine == "random"


@pytest.mark.parametrize("failure", [ReplyDeclined("claude-haiku-5-5 declined to answer"), LlmTimeout(300)])
def test_a_declined_or_timed_out_reply_is_a_forfeit_and_the_batch_goes_on(token, tmp_path, failure):
    results = PlantedResults(["draw", "draw"])

    def player_for(settings, color):
        player = results.player_for(settings, color)
        player.replies = [failure]
        return player

    code = anchor_batch.main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--model", HAIKU, "--games", "2"],
        player_for=player_for,
        anchor_for=results.anchor_for,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    ends = [log[-1] for log in logs(tmp_path / "games")]
    assert [(end["type"], end["reason"]) for end in ends] == [("game_end", "forfeit")] * 2


def test_anchor_match_reports_an_aborted_game_and_exits_with_an_error(token, tmp_path, capsys):
    player, anchor = ScriptedPlayer([FAILED]), ScriptedAnchor([])

    code = anchor_match.main(
        ["--games-dir", str(tmp_path / "games"), "--model", HAIKU, "--engine", "random"],
        player_for=player.for_settings,
        anchor_for=lambda side: anchor,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert "aborted" in capsys.readouterr().err
    [log] = games(tmp_path)
    assert json.loads(log.read_text(encoding="utf-8").splitlines()[-1])["type"] == "game_aborted"


def test_a_faceoff_batch_stops_at_an_aborted_game_and_scores_the_games_before_it(token, tmp_path, capsys):
    players = iter([ScriptedPlayer([FAILED]), ScriptedPlayer([])])

    code = faceoff_batch.main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--models", HAIKU, "llama3:8b", "--games", "4"],
        player_for=lambda settings, color: next(players).for_settings(settings, color),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert len(games(tmp_path)) == 1
    error = capsys.readouterr().err
    assert "Faceoff batch stopped" in error and "game 1 was aborted" in error
