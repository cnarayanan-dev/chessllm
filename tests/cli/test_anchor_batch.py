"""Anchor match batches: a budget of Anchor matches against Dragon, played unattended up and down the Skill ladder.

The LLM is a ScriptedPlayer and the Anchor a ScriptedAnchor, scripted per game so that each game ends in a planted
result. Every assertion is on the game logs the batch writes."""

import json
from datetime import datetime

import pytest

from tests.conftest import ScriptedAnchor, ScriptedPlayer
from tests.analytics.test_analysis import PeakedMoveModel
from tests.analytics.test_centipawn_loss_and_accuracy import UnavailableMoveModel
from tests.fakes import FixedEvaluator, UnavailableEvaluator

from chessllm.cli.anchor_batch import main
from chessllm.exceptions import AnchorUnavailable

# The moves of each side for each planted result, by the LLM's colour. A win is a quick mate by the LLM, a loss a
# Forfeit at the LLM's first turn (its call fails), and a draw a threefold repetition of the start position.
SHUFFLE = ["Nf3", "Ng1", "Nf3", "Ng1"], ["Nf6", "Ng8", "Nf6", "Ng8"]
SCRIPTS = {
    ("win", "white"): (["e4", "Bc4", "Qh5", "Qxf7#"], ["e5", "Nc6", "Nf6"]),
    ("win", "black"): (["e5", "Qh4#"], ["f3", "g4"]),
    ("loss", "white"): ([ConnectionError("planted loss")], []),
    ("loss", "black"): ([ConnectionError("planted loss")], ["e4"]),
    ("draw", "white"): SHUFFLE,
    ("draw", "black"): (SHUFFLE[1], SHUFFLE[0]),
    # The batch is stopped (Ctrl-C) at the LLM's second turn.
    ("interrupted", "white"): (["e4", KeyboardInterrupt()], ["e5"]),
    ("interrupted", "black"): ([KeyboardInterrupt()], ["e4"]),
}


class PlantedResults:
    """Builds, for each game in turn, a ScriptedPlayer and a ScriptedAnchor that play to the next planted result
    ("win", "loss" or "draw", for the LLM, or "interrupted"). The Anchor is built first and plays the side to move when first asked."""

    def __init__(self, results: list[str]) -> None:
        self.results = list(results)
        self.anchors_built = 0
        self.anchors: list["PlantedAnchor"] = []

    def anchor_for(self, side) -> "PlantedAnchor":
        anchor = PlantedAnchor(self.results[self.anchors_built])
        self.anchors_built += 1
        self.anchors.append(anchor)
        return anchor

    def player_for(self, settings, color) -> ScriptedPlayer:
        llm, anchor = SCRIPTS[(self.results[self.anchors_built - 1], color)]
        self.anchors[-1].script(anchor)
        return ScriptedPlayer(llm).for_settings(settings, color)


class PlantedAnchor(ScriptedAnchor):
    def __init__(self, result: str) -> None:
        super().__init__([])
        self.result = result

    def script(self, moves: list[str]) -> None:
        self.moves = list(moves)


def logs(games_dir) -> list[list[dict]]:
    """Every game log's events, in the order the games started (several can start within the second the log's
    name is stamped with)."""
    events = [
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        for path in games_dir.glob("*.jsonl")
    ]
    return sorted(events, key=lambda log: datetime.fromisoformat(log[0]["started_at"]))


def games(games_dir) -> list[tuple[int, str, str]]:
    """Each logged game as (Dragon's Skill, the LLM's colour, the LLM's result), oldest first. An unfinished game's
    result is None."""
    played = []
    for start, *_, end in logs(games_dir):
        llm_color = "white" if start["white"]["player"] == "llm" else "black"
        anchor = start["black" if llm_color == "white" else "white"]
        if end["type"] != "game_end":
            result = None
        elif end["result"] == "1/2-1/2":
            result = "draw"
        else:
            result = "win" if end["result"] == ("1-0" if llm_color == "white" else "0-1") else "loss"
        played.append((anchor["skill"], llm_color, result))
    return played


@pytest.fixture
def batch(tmp_path):
    """Runs the batch command into tmp_path / "games" with the planted results. Returns the exit code and the
    PlantedResults."""

    def run(results: list[str], *args: str, games_dir=None):
        planted = PlantedResults(results)
        code = main(
            ["--games-dir", str(games_dir or tmp_path / "games"), "--no-analysis", *args],
            player_for=planted.player_for,
            anchor_for=planted.anchor_for,
            sampling_file=tmp_path / "no-sampling.toml",
        )
        return code, planted

    return run


def test_a_batch_plays_its_budget_of_games_alternating_colours(batch, tmp_path):
    code, planted = batch(["draw"] * 6, "--games", "6")

    assert code == 0
    played = games(tmp_path / "games")
    assert [color for _, color, _ in played] == ["white", "black"] * 3
    assert [result for *_, result in played] == ["draw"] * 6
    assert all(anchor.closed for anchor in planted.anchors)


def test_the_ladder_steps_up_after_over_50_percent_down_after_under_and_stays_at_50(batch, tmp_path):
    results = ["win", "win", "win", "draw", "win", "loss", "loss", "draw", "loss", "loss", "draw", "draw"]

    code, _ = batch(results, "--games", "12")

    assert code == 0
    # Judged on each pair of games at a Skill: 2 points up, 1.5 up, 1 stays, 0.5 down, 0 down, 1 stays.
    assert games(tmp_path / "games") == [
        (1, "white", "win"), (1, "black", "win"),
        (2, "white", "win"), (2, "black", "draw"),
        (3, "white", "win"), (3, "black", "loss"),
        (3, "white", "loss"), (3, "black", "draw"),
        (2, "white", "loss"), (2, "black", "loss"),
        (1, "white", "draw"), (1, "black", "draw"),
    ]  # fmt: skip


def test_the_ladder_never_leaves_skill_1_to_7(batch, tmp_path):
    batch(["loss"] * 4, "--games", "4", games_dir=tmp_path / "bottom")
    batch(["win"] * 4, "--games", "4", "--skill", "6", games_dir=tmp_path / "top")

    assert [skill for skill, *_ in games(tmp_path / "bottom")] == [1, 1, 1, 1]
    assert [skill for skill, *_ in games(tmp_path / "top")] == [6, 6, 7, 7]


def test_the_same_results_pick_the_same_opponents(batch, tmp_path):
    results = ["win", "win", "loss", "win", "win", "draw", "loss", "loss"]

    batch(results, "--games", "8", games_dir=tmp_path / "first")
    batch(results, "--games", "8", games_dir=tmp_path / "second")

    first, second = games(tmp_path / "first"), games(tmp_path / "second")
    assert first == second
    assert [skill for skill, *_ in first] == [1, 1, 2, 2, 2, 2, 3, 3]


def test_a_later_batch_extends_the_configurations_games_where_the_ladder_left_off(batch, tmp_path, capsys):
    batch(["win", "win", "win"], "--games", "3")
    # Another Player configuration's games at the bottom of the ladder have no bearing on this one's.
    batch(["loss", "loss"], "--games", "2", "--llm-constraints", "listed")
    capsys.readouterr()

    code, _ = batch(["win", "loss", "loss"], "--games", "3")

    assert code == 0
    played = games(tmp_path / "games")
    assert len(played) == 8
    # The first batch left off at Skill 2 after one game, as White: the next is its pair, as Black.
    assert played[5:] == [(2, "black", "win"), (3, "white", "loss"), (3, "black", "loss")]
    assert "Going on from 3 earlier Anchor matches" in capsys.readouterr().out


def test_a_batch_with_tools_has_a_ladder_of_its_own(batch, tmp_path):
    thinking = ["--model", "qwen3.5:9b", "--thinking"]
    batch(["win", "win"], "--games", "2", *thinking)

    code, _ = batch(["win", "win"], "--games", "2", *thinking, "--tools", "board")

    assert code == 0
    assert [skill for skill, *_ in games(tmp_path / "games")] == [1, 1, 1, 1]
    sides = [start[color] for start, *_ in logs(tmp_path / "games") for color in ("white", "black")]
    assert [side["tools"] for side in sides if "tools" in side] == [["board"], ["board"]]


def test_an_unfinished_game_is_not_part_of_the_history_and_skill_overrides_where_a_batch_starts(batch, tmp_path):
    batch(["win", "win", "interrupted"], "--games", "3")

    batch(["draw", "draw"], "--games", "2", "--skill", "5")

    played = games(tmp_path / "games")
    assert played[:2] == [(1, "white", "win"), (1, "black", "win")]
    assert played[2] == (2, "white", None)
    assert played[3:] == [(5, "white", "draw"), (5, "black", "draw")]


def test_a_batch_prints_each_games_progress_and_a_summary(batch, capsys):
    batch(["win", "draw", "loss"], "--games", "3")

    out = capsys.readouterr().out.splitlines()
    assert out[:3] == [
        "Game 1/3: Skill 1, LLM as white: win (1-0, checkmate)",
        "Game 2/3: Skill 1, LLM as black: draw (1/2-1/2, threefold_repetition)",
        "Game 3/3: Skill 2, LLM as white: loss (0-1, forfeit)",
    ]
    assert out[3:] == [
        "Batch: 3 games, 1 wins, 1 draws, 1 losses.",
        "  Skill 1: 1 W · 1 D · 0 L",
        "  Skill 2: 0 W · 0 D · 1 L",
        "Next game: Skill 2, LLM as black.",
    ]


def test_an_interrupted_batch_leaves_every_finished_games_log_complete(batch, tmp_path, capsys):
    code, planted = batch(["win", "draw", "interrupted", "win"], "--games", "4")

    assert code == 130
    played = games(tmp_path / "games")
    assert played == [(1, "white", "win"), (1, "black", "draw"), (2, "white", None)]
    first, second, third = logs(tmp_path / "games")
    assert first[-1]["type"] == second[-1]["type"] == "game_end"
    assert [event["type"] for event in third] == ["game_start", "llm_attempt", "anchor_move"]
    assert all(anchor.closed for anchor in planted.anchors)
    err = capsys.readouterr().err
    assert "Interrupted after 2 of 4 games; game 3 was left unfinished in" in err


def run_analysed(tmp_path, results: list[str], move_model_for, evaluator_for, *args: str) -> int:
    """Runs the batch with the planted results and the given engine fakes for the analysis (None for none)."""
    planted = PlantedResults(results)
    return main(
        ["--games-dir", str(tmp_path / "games"), "--games", str(len(results)), *args],
        player_for=planted.player_for,
        anchor_for=planted.anchor_for,
        sampling_file=tmp_path / "no-sampling.toml",
        move_model_for=move_model_for,
        evaluator_for=evaluator_for,
    )


def analysis_files(games_dir) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(games_dir.glob("*.analysis.json"))]


def test_each_game_is_analysed_after_it_ends_with_both_engines(tmp_path):
    code = run_analysed(
        tmp_path, ["win", "win"], lambda: PeakedMoveModel(white_peak=900, black_peak=1300), FixedEvaluator
    )

    assert code == 0
    [as_white, as_black] = sorted(
        analysis_files(tmp_path / "games"), key=lambda analysis: analysis["move_quality"]["sides"]["white"] is None
    )
    assert as_white["versions"] == {"move_model": "fake-move-model 1", "stockfish": "fake-engine 1"}
    assert as_white["move_quality"]["sides"]["black"] is None
    assert as_white["move_quality"]["sides"]["white"]["estimate"] == 900
    assert as_black["move_quality"]["sides"]["black"]["estimate"] == 1300
    assert as_white["centipawn_loss_and_accuracy"]["sides"]["white"]["average_centipawn_loss"] == 0
    assert as_black["centipawn_loss_and_accuracy"]["sides"]["white"] is None


def test_no_analysis_leaves_the_games_unanalysed(tmp_path):
    built = []

    code = run_analysed(
        tmp_path,
        ["win"],
        lambda: built.append("move model") or PeakedMoveModel(),
        lambda: built.append("evaluator") or FixedEvaluator(),
        "--no-analysis",
    )

    assert code == 0 and built == []
    assert analysis_files(tmp_path / "games") == []


def test_an_engine_that_cant_start_is_left_out_with_one_warning(tmp_path, capsys):
    code = run_analysed(tmp_path, ["win", "draw", "loss"], UnavailableMoveModel, FixedEvaluator)

    assert code == 0
    analyses = analysis_files(tmp_path / "games")
    assert len(analyses) == 3
    assert all(analysis["versions"] == {"stockfish": "fake-engine 1"} for analysis in analyses)
    assert all(analysis["move_quality"] is None for analysis in analyses)
    assert all(analysis["centipawn_loss_and_accuracy"] is not None for analysis in analyses)
    err = capsys.readouterr().err
    assert err.count("No Move-quality estimate in this batch: Maia-2 can't start (uv is not installed)") == 1
    assert "analyse-games" in err


def test_a_batch_goes_on_unanalysed_when_neither_engine_can_start(tmp_path, capsys):
    code = run_analysed(tmp_path, ["win", "draw", "loss"], UnavailableMoveModel, UnavailableEvaluator)

    assert code == 0
    assert len(games(tmp_path / "games")) == 3 and analysis_files(tmp_path / "games") == []
    err = capsys.readouterr().err
    assert err.count("Maia-2 can't start") == 1
    assert err.count("No centipawn loss or accuracy in this batch: Stockfish can't start") == 1


def test_a_missing_dragon_stops_the_batch_before_the_first_game(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("CHESSLLM_DRAGON", raising=False)
    player = ScriptedPlayer([])

    code = main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert "Dragon isn't configured: pass --dragon or set CHESSLLM_DRAGON" in capsys.readouterr().err
    assert player.built_for == [] and not (tmp_path / "games").exists()


def test_a_dragon_that_fails_mid_batch_stops_it_with_the_finished_games_logged(tmp_path, capsys):
    planted = PlantedResults(["win", "win"])
    built = []

    def anchor_for(side):
        if built:
            raise AnchorUnavailable("Dragon at dragon-osx won't start: gone")
        built.append(side)
        return planted.anchor_for(side)

    code = main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--games", "2"],
        player_for=planted.player_for,
        anchor_for=anchor_for,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert games(tmp_path / "games") == [(1, "white", "win")]
    assert "Anchor match batch stopped: Dragon at dragon-osx won't start: gone" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--rules", "chaos"], "Only Stockfish can be the Anchor under Chaos rules"),
        (["--skill", "8"], "plays at Skill 1-7, not 8"),
        (["--model", "llama3:8b", "--thinking"], "llama3:8b (white) cannot think"),
        (["--model", "qwen3.8:latest", "--thinking-level", "high"], "has no Thinking level high: it offers low"),
        (["--model", "qwen3.8:latest", "--thinking-budget", "1024"], "has a Thinking budget, so thinking must be on"),
        (["--model", "qwen3.5:9b", "--thinking", "--thinking-budget", "16"], "too few to hold an answer: at least 64"),
        (["--games", "0"], "the budget must be at least one game"),
    ],
)
def test_a_batch_that_cant_be_played_is_refused_before_it_starts(batch, tmp_path, capsys, args, error):
    code, planted = batch([], *args)

    assert code == 1
    assert error in capsys.readouterr().err
    assert planted.anchors == [] and not (tmp_path / "games").exists()


def test_a_broken_sampling_config_stops_the_batch_before_the_first_game(tmp_path, capsys):
    config = tmp_path / "sampling.toml"
    config.write_text("temperature = \n")
    planted = PlantedResults(["win"])

    code = main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis"],
        player_for=planted.player_for,
        anchor_for=planted.anchor_for,
        sampling_file=config,
    )

    assert code == 1
    assert "Invalid value" in capsys.readouterr().err
    assert not (tmp_path / "games").exists()
