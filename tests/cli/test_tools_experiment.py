"""The tools experiment: an Anchor ladder of a model without tools, the same with tools, a head to head of the two,
and the Markdown comparison of every finished game of the two Player configurations.

The LLM is a ScriptedPlayer per game that calls every tool it is given on each attempt, and the Anchor a MatedAnchor,
so each Anchor match is a quick win for the LLM and each faceoff is Fool's mate, Black winning. Every assertion is
on the game logs and the report the command writes."""

import json
from dataclasses import replace
from datetime import date, datetime

import chess
import pytest

from tests.conftest import ScriptedPlayer

from chessllm.analytics.tools_comparison import ToolUseTally, comparison
from chessllm.cli import tools_experiment
from chessllm.cli.tools_experiment import main
from chessllm.llm.players import LlmReply, Message, ToolCall, Tools

# The LLM's moves by mode and colour. As White in an Anchor match it first tries Qh5, which the e2 pawn blocks: one
# illegal move, then Scholar's mate. As Black it mates at once. In a faceoff, Black mates in two (Fool's mate).
LLM_SCRIPTS = {
    ("anchor_match", "white"): ["Qh5", "e4", "Bc4", "Qh5", "Qxf7#"],
    ("anchor_match", "black"): ["e5", "Qh4#"],
    ("llm_faceoff", "white"): ["f3", "g4"],
    ("llm_faceoff", "black"): ["e5", "Qh4#"],
}
ANCHOR_SCRIPTS = {chess.WHITE: ["f3", "g4"], chess.BLACK: ["e5", "Nc6", "Nf6"]}
MODEL = ["--model", "qwen3.5:9b", "--thinking"]


class CallingPlayer(ScriptedPlayer):
    """A ScriptedPlayer that, given Tools, calls each of them once on every attempt before it answers."""

    def reply(
        self, messages: list[Message], allowed_moves: list[str] | None = None, tools: Tools | None = None
    ) -> LlmReply:
        answer = super().reply(messages, allowed_moves, tools)
        if tools is None:
            return answer
        calls = tuple(ToolCall(function.__name__, {}, function(), None, 0.0) for function in tools.functions)
        return replace(answer, tool_calls=calls)


class MatedAnchor:
    """An Anchor that walks into the LLM's mate, whichever colour it plays."""

    def __init__(self) -> None:
        self.closed = False

    def move(self, board: chess.Board) -> chess.Move:
        return board.parse_san(ANCHOR_SCRIPTS[board.turn][len(board.move_stack) // 2])

    def close(self) -> None:
        self.closed = True


class Players:
    """Builds each game's players; interrupt_at stops the run (Ctrl-C) when that game's first LLM is asked to move."""

    def __init__(self, interrupt_at: int | None = None) -> None:
        self.interrupt_at = interrupt_at
        self.games = 0
        self.settings = None  # the last game's

    def player_for(self, settings, color) -> ScriptedPlayer:
        if settings is not self.settings:  # a faceoff asks once for each colour
            self.settings = settings
            self.games += 1
        script: list = list(LLM_SCRIPTS[(settings.mode, color)])
        if self.games == self.interrupt_at:
            script = [KeyboardInterrupt()]
        return CallingPlayer(script).for_settings(settings, color)


def never_played(settings, color):
    raise AssertionError("no game should be played")


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    """Runs the command in tmp_path, its games in tmp_path / "games"; returns the exit code."""
    monkeypatch.chdir(tmp_path)

    def run(*args: str, players: Players | None = None, player_for=None) -> int:
        return main(
            ["--games-dir", str(tmp_path / "games"), "--no-analysis", *MODEL, *args],
            player_for=player_for or (players or Players()).player_for,
            anchor_for=lambda side: MatedAnchor(),
            sampling_file=tmp_path / "no-sampling.toml",
        )

    return run


def starts(games_dir, finished_only: bool = True) -> list[dict]:
    """Each game's game_start, oldest first."""
    logs = []
    for path in games_dir.glob("*.jsonl"):
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if not finished_only or events[-1]["type"] == "game_end":
            logs.append(events[0])
    return sorted(logs, key=lambda start: datetime.fromisoformat(start["started_at"]))


def shape(start: dict) -> tuple:
    """A game as (mode, White's tools, Black's tools), None for an Anchor."""
    sides = start["white"], start["black"]
    tools = [tuple(side.get("tools", ())) if side["player"] == "llm" else None for side in sides]
    return start["mode"], *tools


def report_path(tmp_path):
    return tmp_path / "reports" / f"tools-comparison-qwen3.5-9b-{date.today().isoformat()}.md"


def report(tmp_path) -> str:
    return report_path(tmp_path).read_text(encoding="utf-8")


def row(markdown: str, label: str) -> list[str]:
    """The cells of the comparison table's row with the label, after the label."""
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells[0] == label:
            return cells[1:]
    raise AssertionError(f"no row {label!r} in\n{markdown}")


BOARD_AND_LEGAL = ("board", "legal_moves")


def test_the_ladder_without_tools_then_with_then_the_head_to_head_colours_swapped(experiment, tmp_path):
    code = experiment("--tools", "board,legal_moves", "--anchor-games", "2", "--faceoff-games", "2")

    assert code == 0
    assert [shape(start) for start in starts(tmp_path / "games")] == [
        ("anchor_match", (), None), ("anchor_match", None, ()),
        ("anchor_match", BOARD_AND_LEGAL, None), ("anchor_match", None, BOARD_AND_LEGAL),
        ("llm_faceoff", BOARD_AND_LEGAL, ()), ("llm_faceoff", (), BOARD_AND_LEGAL),
    ]  # fmt: skip
    # The two configurations differ only in the tools and their Prompt template.
    without, with_tools = (start["white"] for start in starts(tmp_path / "games")[::2][:2])
    assert with_tools["prompt_template"]["id"].startswith("tools@")
    assert not without["prompt_template"]["id"].startswith("tools@")
    differing = {key for key in without.keys() | with_tools.keys() if without.get(key) != with_tools.get(key)}
    assert differing == {"tools", "tool_call_cap", "prompt_template"}


def test_the_report_compares_the_configurations_column_by_column(experiment, tmp_path):
    experiment("--tools", "board,legal_moves", "--anchor-games", "2", "--faceoff-games", "2")

    markdown = report(tmp_path)
    assert "## qwen3.5:9b" in markdown
    assert row(markdown, "") == ["No tools", "Tools board+legal_moves"]
    # Each column: the two Anchor matches won and the two faceoffs, one won as Black, one lost as White.
    assert row(markdown, "Games") == ["4", "4"]
    assert row(markdown, "W / D / L") == ["3 / 0 / 1", "3 / 0 / 1"]
    assert all(cell != "–" for cell in row(markdown, "Rating"))
    assert row(markdown, "Move-quality estimate") == ["–", "–"]  # not analysed
    assert row(markdown, "Illegal moves per game") == ["0.25", "0.25"]  # Qh5 as White in its Anchor match
    assert row(markdown, "Median Legal-move streak") == ["2", "2"]
    assert row(markdown, "Forfeits") == ["0", "0"]
    assert row(markdown, "Time used per move")[0].endswith(" s")
    # Every attempt with tools calls both: 2 calls each.
    assert row(markdown, "Tool calls per attempt") == ["–", "2.00"]
    assert row(markdown, "Attempts calling board") == ["–", "100%"]
    assert row(markdown, "Attempts calling legal_moves") == ["–", "100%"]
    assert row(markdown, "Attempts at the Tool-call cap") == ["–", "0 (0%)"]
    assert row(markdown, "Attempts with no tool call") == ["–", "0 (0%)"]
    assert row(markdown, "Tool calls written as text") == ["–", "0 (0%)"]
    # Fool's mate both games: the tools side lost as White and won as Black.
    assert row(markdown, "Head to head against no tools") == ["–", "1 / 0 / 1 (50%)"]


def test_a_tool_call_cap_reached_is_counted_and_named_in_the_column(experiment, tmp_path):
    experiment("--tools", "board,legal_moves", "--tool-call-cap", "2", "--anchor-games", "1", "--faceoff-games", "0")

    markdown = report(tmp_path)
    assert row(markdown, "") == ["No tools", "Tools board+legal_moves, cap 2"]
    # Its one game, as White: an illegal Qh5 and four legal moves, each attempt at the cap.
    assert row(markdown, "Attempts at the Tool-call cap") == ["–", "5 (100%)"]


def test_every_finished_game_of_each_tool_set_gets_a_column_not_only_this_runs(experiment, tmp_path):
    experiment("--tools", "board", "--anchor-games", "1", "--faceoff-games", "0")
    experiment("--tools", "--anchor-games", "1", "--faceoff-games", "0")

    markdown = report(tmp_path)
    assert row(markdown, "") == ["No tools", "Tools board+legal_moves+material+move_history", "Tools board"]
    assert row(markdown, "Games") == ["2", "1", "1"]


def test_another_player_configuration_of_the_model_is_left_out(experiment, tmp_path):
    experiment("--retry-feedback", "bare", "--anchor-games", "1", "--faceoff-games", "0")

    experiment("--anchor-games", "1", "--faceoff-games", "0")

    assert row(report(tmp_path), "Games") == ["1", "1"]


def test_the_legal_move_streak_and_illegal_moves_are_not_applicable_under_blind_enforced(experiment, tmp_path):
    experiment("--llm-constraints", "blind_enforced", "--anchor-games", "1", "--faceoff-games", "0")

    markdown = report(tmp_path)
    assert row(markdown, "Median Legal-move streak") == ["n/a", "n/a"]
    assert row(markdown, "Illegal moves per game") == ["n/a", "n/a"]


def test_running_again_after_an_interruption_carries_on_where_the_run_stopped(experiment, tmp_path, capsys):
    # Stopped at the first game of the ladder with tools.
    code = experiment("--anchor-games", "2", "--faceoff-games", "2", players=Players(interrupt_at=3))
    assert code == 130
    assert not (tmp_path / "reports").exists()
    capsys.readouterr()

    code = experiment("--anchor-games", "2", "--faceoff-games", "2")

    assert code == 0
    assert "Carrying on" in capsys.readouterr().out
    assert [shape(start)[0] for start in starts(tmp_path / "games")] == ["anchor_match"] * 4 + ["llm_faceoff"] * 2
    assert len(starts(tmp_path / "games", finished_only=False)) == 7  # the interrupted game stays unfinished
    assert row(report(tmp_path), "Games") == ["4", "4"]

    # A finished run is over: the next one is a new run, extending both ladders.
    capsys.readouterr()
    experiment("--anchor-games", "1", "--faceoff-games", "0")
    assert "Carrying on" not in (out := capsys.readouterr().out)
    assert "Going on from 2 earlier Anchor matches" in out
    assert len(starts(tmp_path / "games")) == 8


def test_report_only_writes_the_report_from_the_logs_without_playing(experiment, tmp_path):
    experiment("--anchor-games", "1", "--faceoff-games", "0")
    (tmp_path / "reports" / f"tools-comparison-qwen3.5-9b-{date.today().isoformat()}.md").unlink()

    code = experiment("--report-only", player_for=never_played)

    assert code == 0
    assert row(report(tmp_path), "Games") == ["1", "1"]
    assert len(starts(tmp_path / "games")) == 2


def test_a_tools_side_that_cant_be_played_is_refused_before_the_first_game(experiment, tmp_path, capsys):
    code = main(
        ["--games-dir", str(tmp_path / "games"), "--no-analysis", "--model", "llama3:8b"],
        player_for=never_played,
        anchor_for=lambda side: MatedAnchor(),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert "can't call tools natively" in capsys.readouterr().err
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*.jsonl"))


def test_a_failed_faceoff_stops_the_run_cleanly_and_running_again_carries_on_without_rereading_the_ladders(
    experiment, tmp_path, capsys, monkeypatch
):
    def failing_faceoff(settings, color):
        if settings.mode == "llm_faceoff":
            raise RuntimeError("Ollama is not running")
        return Players().player_for(settings, color)

    code = experiment("--anchor-games", "1", "--faceoff-games", "1", player_for=failing_faceoff)

    assert code == 1
    err = capsys.readouterr().err
    assert "Tools experiment stopped: faceoff 1, tools as white failed: Ollama is not running" in err
    assert "Run the same command again to carry on." in err
    # Once both ladders are played, a run carrying on doesn't read their games again.
    read = []
    earlier_games = tools_experiment.earlier_games
    monkeypatch.setattr(tools_experiment, "earlier_games", lambda *args: read.append(args) or earlier_games(*args))

    code = experiment("--anchor-games", "1", "--faceoff-games", "1")

    assert code == 0
    assert read == []
    assert [shape(start)[0] for start in starts(tmp_path / "games")] == ["anchor_match"] * 2 + ["llm_faceoff"]


def test_without_a_configuration_without_tools_there_is_no_head_to_head(experiment, tmp_path):
    experiment("--anchor-games", "1", "--faceoff-games", "2")

    columns = comparison(tmp_path / "games", lambda configuration: configuration.tools is not None)

    assert [column.entry.games for column in columns] == [3]  # its Anchor match and both faceoffs
    assert columns[0].head_to_head.games == 0


def test_tool_use_counts_the_attempts_game_ends_tool_use_counts():
    tally = ToolUseTally()
    call = {"tool": "board", "arguments": {}, "result": "...", "thinking": None, "latency_s": 0.1}

    tally.add({"result": "legal", "raw_reply": '{"move": "e4"}'}, cap=2)
    tally.add({"result": "error", "raw_reply": None}, cap=2)  # failed before it could call a tool: not counted
    tally.add({"result": "timeout", "raw_reply": None, "tool_calls": [call, call]}, cap=2)
    tally.add({"result": "error", "raw_reply": None, "tool_call_as_text": True}, cap=2)

    assert tally.attempts == 3
    assert (tally.tool_calls, tally.attempts_at_cap, tally.attempts_without_tool_calls) == (2, 1, 2)
    assert tally.tool_calls_as_text == 1
