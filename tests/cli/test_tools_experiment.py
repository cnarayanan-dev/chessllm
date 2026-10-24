"""The Tools experiment: an Anchor ladder of a Player configuration without Tools, the same with them, a head to head
of the model against itself, tools on one side, then the Markdown comparison.

The ladders' LLM and Anchors are planted as in the anchor-batch tests; in a faceoff each side is a ScriptedPlayer
scripted to the planted result. Every assertion is on the game logs and the report the command writes."""

from datetime import date

import pytest

from tests.cli.test_anchor_batch import SHUFFLE, PlantedResults, logs, not_built
from tests.conftest import ScriptedPlayer
from tests.analytics.test_analysis import PeakedMoveModel

from chessllm.cli.tools_experiment import main
from chessllm.game.sides import side_tools

QWEN = ["--model", "qwen3.5:9b", "--thinking"]
DAY = date(2026, 10, 24)
# The moves of White and Black for a faceoff won by White, by Black, or drawn.
FACEOFFS = {
    "white": (["e4", "Bc4", "Qh5", "Qxf7#"], ["e5", "Nc6", "Nf6"]),
    "black": (["f3", "g4"], ["e5", "Qh4#"]),
    "draw": SHUFFLE,
}


class Planted:
    """The ladders' games to the planted results in turn, as PlantedResults plays them, and each faceoff to its
    planted result: "tools" or "plain" for the side with or without Tools winning, "draw", or "interrupted" (Ctrl-C at
    White's first turn)."""

    def __init__(self, ladder: list[str], faceoffs: list[str]) -> None:
        self.ladder = PlantedResults(ladder)
        self.faceoffs = list(faceoffs)
        self._black: list | None = None

    def player_for(self, settings, color):
        if settings.mode == "anchor_match":
            return self.ladder.player_for(settings, color)
        if color == "black":
            assert self._black is not None
            return ScriptedPlayer(self._black).for_settings(settings, color)
        result = self.faceoffs.pop(0)
        if result == "interrupted":
            white, self._black = [KeyboardInterrupt()], []
        else:
            tools_color = next(c for c in ("white", "black") if side_tools(settings.side(c)))
            plain_color = "black" if tools_color == "white" else "white"
            winner = {"tools": tools_color, "plain": plain_color, "draw": "draw"}[result]
            white, self._black = FACEOFFS[winner]
        return ScriptedPlayer(list(white)).for_settings(settings, color)


@pytest.fixture
def experiment(tmp_path):
    """Runs the command into tmp_path / "games" and tmp_path / "reports" with the planted results. Returns the exit
    code and the Planted."""

    def run(ladder: list[str], faceoffs: list[str], *args: str, move_model_for=lambda: None):
        planted = Planted(ladder, faceoffs)
        code = main(
            ["--games-dir", str(tmp_path / "games"), "--reports-dir", str(tmp_path / "reports"), *args],
            player_for=planted.player_for,
            anchor_for=planted.ladder.anchor_for,
            sampling_file=tmp_path / "no-sampling.toml",
            move_model_for=move_model_for,
            evaluator_for=lambda: None,
            today=lambda: DAY,
        )
        return code, planted

    return run


def played(games_dir) -> list[tuple[str, tuple[str, ...], str]]:
    """Each logged game as (its mode, the tools of White and Black's LLM sides or "-" for an Anchor, its result or
    None while unfinished), oldest first."""
    games = []
    for events in logs(games_dir):
        start, end = events[0], events[-1]
        tools = tuple(
            "+".join(start[color].get("tools", [])) or "none" if start[color]["player"] == "llm" else "-"
            for color in ("white", "black")
        )
        games.append((start["mode"], tools, end["result"] if end["type"] == "game_end" else None))
    return games


def test_the_ladder_without_tools_then_with_them_then_the_head_to_head_with_colours_swapped(experiment, tmp_path):
    code, _ = experiment(["win", "draw", "loss", "win"], ["tools", "plain", "draw"],
                         *QWEN, "--tools", "board,legal_moves", "--anchor-games", "2", "--faceoff-games", "3")

    assert code == 0
    assert played(tmp_path / "games") == [
        ("anchor_match", ("none", "-"), "1-0"),
        ("anchor_match", ("-", "none"), "1/2-1/2"),
        ("anchor_match", ("board+legal_moves", "-"), "0-1"),
        ("anchor_match", ("-", "board+legal_moves"), "0-1"),
        ("llm_faceoff", ("board+legal_moves", "none"), "1-0"),
        ("llm_faceoff", ("none", "board+legal_moves"), "1-0"),
        ("llm_faceoff", ("board+legal_moves", "none"), "1/2-1/2"),
    ]
    starts = [start for start, *_ in logs(tmp_path / "games")]
    templates = {(bool(start[color].get("tools")), start[color]["prompt_template"]["id"].partition("@")[0])
                 for start in starts for color in ("white", "black") if start[color]["player"] == "llm"}
    assert templates == {(False, "default"), (True, "tools")}  # the side with Tools plays the Tools template


def test_the_report_is_written_after_the_games_with_a_column_per_tool_set(experiment, tmp_path, capsys):
    code, _ = experiment(["win", "draw", "loss", "win"], ["tools", "plain"],
                         *QWEN, "--anchor-games", "2", "--faceoff-games", "2")

    assert code == 0
    report = (tmp_path / "reports" / "tools-comparison-2026-10-24.md").read_text(encoding="utf-8")
    assert "## qwen3.5:9b" in report
    assert "| | no tools | all four |" in report
    # Every finished game, the faceoffs included, as the Rating counts them.
    assert "| games | 4 | 4 |" in report
    assert "| W · D · L | 2 · 1 · 1 | 2 · 0 · 2 |" in report
    assert "- all four vs no tools: 1 W · 0 D · 1 L, 1 - 1 in 2 games" in report
    assert "tools-comparison-2026-10-24.md" in capsys.readouterr().out


def test_no_faceoff_games_skips_the_head_to_head(experiment, tmp_path):
    code, _ = experiment(["win", "win"], [], *QWEN, "--anchor-games", "1", "--faceoff-games", "0")

    assert code == 0
    assert [mode for mode, *_ in played(tmp_path / "games")] == ["anchor_match", "anchor_match"]


def test_run_again_after_an_interruption_it_carries_on_where_it_stopped(experiment, tmp_path, capsys):
    code, _ = experiment(["win", "win", "win", "interrupted"], [], *QWEN, "--anchor-games", "2",
                         "--faceoff-games", "2")
    assert code == 130
    assert not (tmp_path / "reports").exists()
    assert "Run it again to carry on" in capsys.readouterr().err

    # Only the game left unfinished is played again; then the head to head, interrupted in its second game.
    code, _ = experiment(["draw"], ["tools", "interrupted"], *QWEN, "--anchor-games", "2", "--faceoff-games", "2")
    assert code == 130

    code, _ = experiment([], ["plain"], *QWEN, "--anchor-games", "2", "--faceoff-games", "2")
    assert code == 0
    finished = [game for game in played(tmp_path / "games") if game[2] is not None]
    assert finished == [
        ("anchor_match", ("none", "-"), "1-0"),
        ("anchor_match", ("-", "none"), "0-1"),
        ("anchor_match", ("board+legal_moves+material+move_history", "-"), "1-0"),
        ("anchor_match", ("-", "board+legal_moves+material+move_history"), "1/2-1/2"),
        ("llm_faceoff", ("board+legal_moves+material+move_history", "none"), "1-0"),
        ("llm_faceoff", ("none", "board+legal_moves+material+move_history"), "1-0"),
    ]
    assert (tmp_path / "reports" / "tools-comparison-2026-10-24.md").exists()


def test_a_later_run_extends_the_earlier_games_of_each_configuration(experiment, tmp_path, capsys):
    experiment(["win", "win", "loss", "loss"], [], *QWEN, "--anchor-games", "2", "--faceoff-games", "0")
    capsys.readouterr()

    experiment(["win", "win", "loss", "loss"], [], *QWEN, "--anchor-games", "4", "--faceoff-games", "0")

    starts = [start for start, *_ in logs(tmp_path / "games")]
    rungs = [(bool(side.get("tools")), opponent.get("skill", 0))
             for start in starts for side, opponent in [(start["white"], start["black"]), (start["black"], start["white"])]
             if side["player"] == "llm"]
    # Without Tools: two wins at the random mover, then the next pair at Skill 1; with Tools, losses at the bottom.
    assert [skill for tools, skill in rungs if not tools] == [0, 0, 1, 1]
    assert [skill for tools, skill in rungs if tools] == [0, 0, 0, 0]
    assert "Going on from 2 earlier Anchor matches" in capsys.readouterr().out


def test_the_report_only_writes_the_report_from_the_logs_without_playing(experiment, tmp_path):
    experiment(["win", "win"], ["tools"], *QWEN, "--anchor-games", "1", "--faceoff-games", "1")
    (tmp_path / "reports" / "tools-comparison-2026-10-24.md").unlink()
    before = played(tmp_path / "games")

    code, planted = experiment([], [], *QWEN, "--anchor-games", "5", "--report-only")

    assert code == 0
    assert played(tmp_path / "games") == before and planted.ladder.anchors == []
    report = (tmp_path / "reports" / "tools-comparison-2026-10-24.md").read_text(encoding="utf-8")
    assert "- all four vs no tools: 1 W · 0 D · 0 L, 1 - 0 in 1 games" in report


def test_each_game_is_analysed_so_the_report_has_a_move_quality_estimate(experiment, tmp_path):
    code, _ = experiment(["win", "win"], [], *QWEN, "--anchor-games", "1", "--faceoff-games", "0",
                         move_model_for=PeakedMoveModel)

    assert code == 0
    report = (tmp_path / "reports" / "tools-comparison-2026-10-24.md").read_text(encoding="utf-8")
    [quality] = [line for line in report.splitlines() if line.startswith("| Move-quality estimate")]
    assert "| - |" not in quality


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--model", "llama3:8b"], "llama3:8b (white) cannot call tools natively"),
        (["--model", "qwen3.5:9b"], "has Tools, so thinking must be on"),
        ([*QWEN, "--llm-constraints", "listed"], "must be free or blind_enforced, not listed"),
        ([*QWEN, "--turn-memory", "chat_position"], "its Turn memory must be fresh"),
        ([*QWEN, "--engine", "random"], "the random mover is the ladder's bottom rung"),
        ([*QWEN, "--anchor-games", "-1"], "at least 0"),
    ],
)
def test_the_tools_sides_rules_are_checked_before_the_first_game(experiment, tmp_path, capsys, args, error):
    code, planted = experiment([], [], *args, move_model_for=not_built)

    assert code == 1
    assert error in capsys.readouterr().err
    assert planted.ladder.anchors == [] and not (tmp_path / "games").exists()
