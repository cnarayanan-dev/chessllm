"""Run the tools experiment for a model from the command line (ADR 0011): does it play better with Tools than
without them?

    uv run tools-experiment --model qwen3.8:latest --thinking-level medium \\
        --tools board,legal_moves,material,move_history --anchor-games 30 --faceoff-games 10 --dragon PATH

In order: an Anchor ladder of --anchor-games for the Player configuration without tools, the same for the
configuration with them, then --faceoff-games LLM faceoffs of the model against itself, tools on one side, White in
the first game and colours swapped each game (0 skips them); then the report. The two configurations differ only in
the tools and the Prompt template that goes with them: they take the same arguments as anchor-batch, --tools all four
by default here. Both are checked, the tools side's rules among them, before the first game. Each ladder goes on
from the earlier games of its configuration, as anchor-batch does, and games run one after another, each analysed as
it ends unless --no-analysis.

Carrying on. A run keeps the games it has finished in a run file next to the logs, named after the model and both
configurations, so running the same command again after an interruption carries on where it stopped (an unfinished
game is not counted, and a new one is played in its place). The run file goes once the report is written: the next
run of the command is a new one, extending both ladders again.

The report, reports/tools-comparison-<model>-<date>.md in the working directory (the model as in a log's name,
e.g. qwen3.8-latest, so two models reported on one day keep a report each), compares the model's configurations that
differ only in their tools, one column per tool set played (none, all four, any subset; a Tool-call cap other than
the default is a column of its own), over every finished game of each in the games directory, not only this run's
(chessllm.analytics.tools_comparison). --report-only writes it from the logs without playing."""

import argparse
import hashlib
import json
import statistics
import sys
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from chessllm.analytics.leaderboard import PlayerConfiguration, finished_game, settings_configuration
from chessllm.analytics.move_quality import MoveQuality
from chessllm.analytics.rating import Rating
from chessllm.analytics.tools_comparison import Column, comparison
from chessllm.cli.common import (
    Analyser,
    add_analysis_argument,
    add_configuration_arguments,
    anchor_match_settings,
    benchmark_llm_side,
    default_anchor,
    default_evaluator,
    default_move_model,
    fail,
    rung,
    score_word,
)
from chessllm.cli.common import player_for as default_player_for
from chessllm.core.config import SAMPLING_FILE
from chessllm.core.types import COLORS, Color, opponent, score_for
from chessllm.engines.anchors import Anchor
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.exceptions import AnchorUnavailable, InvalidSamplingConfig, InvalidSettings
from chessllm.game.ladder import FIRST_SKILL, AnchoredGame, earlier_games, next_color, next_skill
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import DEFAULT_TOOL_CALL_CAP, TOOLS, AnchorSide
from chessllm.llm.models import LLM_MODELS, load_sampling
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog, file_name_part

DEFAULT_ANCHOR_GAMES = 30
DEFAULT_FACEOFF_GAMES = 10
REPORTS_DIR = Path("reports")  # in the working directory
INTERRUPTED_EXIT_CODE = 130
FAILED = "Tools experiment stopped"
CARRY_ON = "Run the same command again to carry on."
NOT_APPLICABLE = "n/a"
NONE = "–"

# The stages of a run, in order: the two Anchor ladders and the head to head.
Stage = Literal["without_tools", "with_tools", "faceoff"]
LADDERS: tuple[Stage, Stage] = ("without_tools", "with_tools")
STAGE_NAMES: dict[Stage, str] = {"without_tools": "Without tools", "with_tools": "With tools", "faceoff": "Faceoff"}


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools-experiment",
        description="Play an Anchor ladder of an LLM without tools and one with them, then LLM faceoffs of the two, "
        "and write the comparison of every finished game of both as Markdown. --tools is all four by default here.",
    )
    add_configuration_arguments(parser)
    parser.set_defaults(tools=frozenset(TOOLS))
    parser.add_argument(
        "--anchor-games",
        type=int,
        default=DEFAULT_ANCHOR_GAMES,
        help=f"the Anchor matches of each ladder (default {DEFAULT_ANCHOR_GAMES})",
    )
    parser.add_argument(
        "--faceoff-games",
        type=int,
        default=DEFAULT_FACEOFF_GAMES,
        help=f"the faceoffs of the model with tools against itself without (default {DEFAULT_FACEOFF_GAMES}; 0 skips)",
    )
    parser.add_argument("--report-only", action="store_true", help="write the report from the logs without playing")
    add_analysis_argument(parser)
    return parser


def main(
    argv: list[str] | None = None,
    player_for: Callable[[Settings, Color], LlmPlayer] = default_player_for,
    anchor_for: Callable[[AnchorSide], Anchor] | None = None,
    sampling_file: Path = SAMPLING_FILE,
    move_model_for: Callable[[], MoveModel | None] = default_move_model,
    evaluator_for: Callable[[], Evaluator | None] = default_evaluator,
) -> int:
    """Run the command; returns its exit code. anchor_for builds each Anchor match's Anchor, by default Dragon from
    --dragon; move_model_for and evaluator_for the engines the games are analysed with (None leaves one out)."""
    args = parser().parse_args(argv)
    if args.anchor_games < 0 or args.faceoff_games < 0:
        return fail(FAILED, "--anchor-games and --faceoff-games can't be negative")
    stage_args: dict[Stage, argparse.Namespace] = {"without_tools": without_tools(args), "with_tools": args}
    try:
        configurations = {
            stage: settings_configuration(anchor_match_settings(given, "white", FIRST_SKILL, sampling_file), "white")
            for stage, given in stage_args.items()
        }
        if not args.report_only and args.faceoff_games:
            faceoff_settings(args, "white", sampling_file)
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return fail(FAILED, str(error))
    if not args.report_only:
        if anchor_for is None:
            anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
        analyser = Analyser(None, None) if args.no_analysis else Analyser(move_model_for(), evaluator_for())
        run = Run(args, configurations, sampling_file, player_for, anchor_for, analyser)
        try:
            code = run.play()
        finally:
            analyser.close()
        if code:
            return code
    path = write_report(args, configurations["without_tools"], sampling_file)
    print(f"Report: {path}")
    if not args.report_only:
        run.file.unlink(missing_ok=True)
    return 0


def without_tools(args: argparse.Namespace) -> argparse.Namespace:
    """The arguments of the configuration without tools: the same, but no tools and no cap."""
    return argparse.Namespace(**vars(args) | {"tools": frozenset(), "tool_call_cap": None})


def faceoff_settings(args: argparse.Namespace, tools_color: Color, sampling_file: Path) -> Settings:
    """The settings of an LLM faceoff of the model against itself, with tools at tools_color. Raises InvalidSettings
    when they can't be played, and InvalidSamplingConfig for a broken config."""
    tools_side, other = benchmark_llm_side(args), benchmark_llm_side(without_tools(args))
    white, black = (tools_side, other) if tools_color == "white" else (other, tools_side)
    settings = Settings(
        "llm_faceoff",
        white,
        black,
        sampling=load_sampling(sampling_file),
        rules=args.rules,
        max_attempts=args.max_attempts,
        legal_counterpart=not args.no_legal_counterpart,
    )
    settings.check(LLM_MODELS)
    return settings


class Run:
    """One run of the experiment: its stages in order, each from where the run file says it stopped."""

    def __init__(
        self,
        args: argparse.Namespace,
        configurations: dict[Stage, PlayerConfiguration],
        sampling_file: Path,
        player_for: Callable[[Settings, Color], LlmPlayer],
        anchor_for: Callable[[AnchorSide], Anchor],
        analyser: Analyser,
    ) -> None:
        self.args = args
        self.configurations = configurations
        self.sampling_file = sampling_file
        self.player_for = player_for
        self.anchor_for = anchor_for
        self.analyser = analyser
        self.file = run_file(args.games_dir, args.model, configurations, args.engine)
        self.games = read_run(self.file, args.games_dir)
        self.log: GameLog | None = None  # the game being played

    def play(self) -> int:
        """Play what is left of the run; returns 0 once it is all played, else the exit code."""
        if any(self.games.values()):
            done = ", ".join(f"{STAGE_NAMES[stage].lower()} {len(names)}" for stage, names in self.games.items())
            print(f"Carrying on the run in {self.file.name}: games finished so far, {done}.")
        try:
            for stage in LADDERS:
                if (code := self.ladder(stage)) != 0:
                    return code
            return self.faceoffs()
        except KeyboardInterrupt:
            unfinished = f"; {self.log.path} was left unfinished" if self.log is not None else ""
            print(f"Interrupted{unfinished}. {CARRY_ON}", file=sys.stderr)
            return INTERRUPTED_EXIT_CODE

    def ladder(self, stage: Stage) -> int:
        """Play the rest of the stage's Anchor ladder; returns 0, or 1 when a game can't be played or fails."""
        args, budget = self.args, self.args.anchor_games
        if len(self.games[stage]) >= budget:
            return 0  # finished: its history isn't read again
        given = without_tools(args) if stage == "without_tools" else args
        history = earlier_games(args.games_dir, self.configurations[stage], args.engine)
        if history:
            print(f"{STAGE_NAMES[stage]}: Going on from {len(history)} earlier Anchor matches of this configuration.")
        for number in range(len(self.games[stage]) + 1, budget + 1):
            skill, llm_color = next_skill(history), next_color(history)
            anchor_color = opponent(llm_color)
            where = f"{STAGE_NAMES[stage].lower()}, game {number} at {rung(skill)}"
            try:
                settings = anchor_match_settings(given, llm_color, skill, self.sampling_file)
                anchor = self.anchor_for(settings.anchor_sides()[anchor_color])
            except (InvalidSettings, AnchorUnavailable) as error:
                return fail(FAILED, f"{where} can't be played: {error}. {CARRY_ON}")
            try:
                players = {llm_color: self.player_for(settings, llm_color)}
                self.log = GameLog(args.games_dir, *settings.side_names())
                state = play_anchor_match(settings, players, {anchor_color: anchor}, self.log)
            except Exception as error:
                return self.failed(where, error)
            finally:
                anchor.close()
            assert state.result is not None  # played to its end
            history.append(AnchoredGame(skill, llm_color, score_for(state.result, llm_color)))
            outcome = f"{score_word(history[-1].score)} ({state.result}, {state.end_reason})"
            print(f"{STAGE_NAMES[stage]} {number}/{budget}: {rung(skill)}, LLM as {llm_color}: {outcome}", flush=True)
            self.finished(stage)
        return 0

    def faceoffs(self) -> int:
        """Play the rest of the head to head, tools as White in odd games and as Black in even ones; returns 0, or 1
        when a game can't be played or fails."""
        args, budget = self.args, self.args.faceoff_games
        for number in range(len(self.games["faceoff"]) + 1, budget + 1):
            tools_color: Color = "white" if number % 2 else "black"
            where = f"faceoff {number}, tools as {tools_color}"
            try:
                settings = faceoff_settings(args, tools_color, self.sampling_file)
            except (InvalidSettings, InvalidSamplingConfig) as error:
                return fail(FAILED, f"{where} can't be played: {error}. {CARRY_ON}")
            try:
                players = {color: self.player_for(settings, color) for color in COLORS}
                self.log = GameLog(args.games_dir, *settings.side_names())
                state = play_anchor_match(settings, players, {}, self.log)
            except Exception as error:
                return self.failed(where, error)
            assert state.result is not None  # played to its end
            outcome = f"{score_word(score_for(state.result, tools_color))} for tools"
            print(
                f"Faceoff {number}/{budget}: tools as {tools_color}: {outcome} ({state.result}, {state.end_reason})",
                flush=True,
            )
            self.finished("faceoff")
        return 0

    def failed(self, where: str, error: Exception) -> int:
        """Stop the run after a game failed: say which, and where its log was left unfinished."""
        unfinished = f"; it was left unfinished in {self.log.path}" if self.log is not None else ""
        self.log = None
        return fail(FAILED, f"{where} failed: {error}{unfinished}. {CARRY_ON}")

    def finished(self, stage: Stage) -> None:
        """Record the game just finished in the run file, then analyse it."""
        assert self.log is not None
        path, self.log = self.log.path, None
        self.games[stage].append(path.name)
        self.file.write_text(json.dumps({"games": self.games}, indent=2) + "\n", encoding="utf-8")
        self.analyser.analyse(path)


def run_file(games_dir: Path, model: str, configurations: dict[Stage, PlayerConfiguration], engine: str) -> Path:
    """Where a run of the experiment keeps its finished games: in the games directory, named after the model and a
    fingerprint of both configurations and the ladder's engine, e.g.
    games/tools-experiment_qwen3.8-latest_1a2b3c4d5e6f.json. It isn't a game log, so nothing reading the logs
    (*.jsonl) reads it."""
    ids = " ".join([*(configurations[stage].id() for stage in LADDERS), engine])
    return games_dir / f"tools-experiment_{file_name_part(model)}_{hashlib.sha256(ids.encode()).hexdigest()[:12]}.json"


def read_run(file: Path, games_dir: Path) -> dict[Stage, list[str]]:
    """The finished games of the run, by stage, from its run file: none for a new run. A game the file names that is
    no longer a finished log is left out."""
    games: dict[Stage, list[str]] = {"without_tools": [], "with_tools": [], "faceoff": []}
    try:
        recorded = json.loads(file.read_text(encoding="utf-8"))["games"]
    except (OSError, ValueError, KeyError, TypeError):
        return games
    for stage in games:
        names = recorded.get(stage, []) if isinstance(recorded, dict) else []
        games[stage] = [name for name in names if finished_game(games_dir / str(name)) is not None]
    return games


# --- the report ---------------------------------------------------------------------------------------------------


def write_report(args: argparse.Namespace, base: PlayerConfiguration, sampling_file: Path) -> Path:
    """Write the comparison of the configurations of args that differ only in their tools to the reports directory;
    returns its path."""

    def belongs(configuration: PlayerConfiguration) -> bool:
        """Whether the configuration is the one args give with its tools and cap instead."""
        if configuration.model != base.model:
            return False
        tools = frozenset(configuration.tools or ())
        cap = configuration.tool_call_cap if tools else None
        given = argparse.Namespace(**vars(args) | {"tools": tools, "tool_call_cap": cap})
        try:
            settings = anchor_match_settings(given, "white", FIRST_SKILL, sampling_file)
        except (InvalidSettings, InvalidSamplingConfig):
            return False
        return configuration == settings_configuration(settings, "white")

    columns = comparison(args.games_dir, belongs) if args.games_dir.is_dir() else []
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"tools-comparison-{file_name_part(base.model)}-{date.today().isoformat()}.md"
    path.write_text(render(base, columns), encoding="utf-8")
    return path


def render(base: PlayerConfiguration, columns: list[Column]) -> str:
    """The report as Markdown: the configuration the columns share, then the comparison table."""
    out = [
        f"# Tools comparison, {date.today().isoformat()}",
        "",
        f"Written {datetime.now():%Y-%m-%d %H:%M} from every finished game in the games directory of the Player "
        "configurations below, not only one run's. They differ only in their Tools and the Prompt template that goes "
        "with them; each column is a tool set played.",
        "",
        f"## {base.model}",
        "",
        f"Shared settings: {shared_settings(base)}.",
        "",
    ]
    if not columns:
        return "\n".join([*out, "No finished games of these configurations yet.", ""])
    tools = [tool for tool in TOOLS if any(tool in (column.configuration.tools or ()) for column in columns)]
    rows: list[tuple[str, Callable[[Column], str]]] = [
        ("Games", lambda column: str(column.entry.games)),
        ("W / D / L", lambda column: f"{column.entry.wins} / {column.entry.draws} / {column.entry.losses}"),
        ("Rating", lambda column: rating_text(column.entry.rating)),
        ("Move-quality estimate", lambda column: move_quality_text(column.entry.move_quality)),
        ("Illegal moves per game", illegal_moves_per_game),
        ("Median Legal-move streak", median_streak),
        ("Forfeits", lambda column: str(column.entry.forfeits)),
        ("Time used per move", time_per_move),
        ("Tool calls per attempt", with_tools(calls_per_attempt)),
        *((f"Attempts calling {tool}", attempts_calling(tool)) for tool in tools),
        ("Attempts at the Tool-call cap", with_tools(lambda column: share(column.tool_use.attempts_at_cap, column))),
        (
            "Attempts with no tool call",
            with_tools(lambda column: share(column.tool_use.attempts_without_tool_calls, column)),
        ),
        ("Tool calls written as text", with_tools(lambda column: share(column.tool_use.tool_calls_as_text, column))),
        ("Head to head against no tools", head_to_head),
    ]
    out.append("| | " + " | ".join(column_title(column.configuration) for column in columns) + " |")
    out.append("|---" * (len(columns) + 1) + "|")
    for label, cell in rows:
        out.append(f"| {label} | " + " | ".join(cell(column) for column in columns) + " |")
    out += [
        "",
        "Rating and Move-quality estimate on the chess.com scale, with their 95% interval; the Rating is fitted over "
        "every Player configuration's games together. Illegal moves and the Legal-move streak are not applicable "
        "(n/a) under Enforced decoding. Time used per move is per legal move. Tool use is over the attempts that "
        "could use the tools (answered, or failed after a tool call), as the game logs count them; an attempt at "
        "the Tool-call cap made as many tool calls as the cap allowed. Head to head is the LLM faceoffs against "
        "the configuration without tools, W / D / L from the side with tools.",
        "",
    ]
    return "\n".join(out)


def shared_settings(configuration: PlayerConfiguration) -> str:
    thinking = "thinking" if configuration.thinking else "no thinking"
    if configuration.thinking_level is not None:
        thinking = f"thinking {configuration.thinking_level}"
    if configuration.thinking_budget is not None:
        thinking += f", budget {configuration.thinking_budget}"
    parts = [
        configuration.llm_constraints,
        thinking,
        f"{configuration.rules} rules",
        f"{configuration.retry_feedback} feedback",
        f"{configuration.max_retries + 1} attempts per turn",
    ]
    if configuration.turn_memory is not None:
        parts.append(f"Turn memory {configuration.turn_memory}")
    if configuration.sampling:
        parts.append("sampling " + ", ".join(f"{key} {value}" for key, value in sorted(configuration.sampling.items())))
    return " / ".join(parts)


def column_title(configuration: PlayerConfiguration) -> str:
    if configuration.tools is None:
        return "No tools"
    cap = f", cap {configuration.tool_call_cap}" if configuration.tool_call_cap != DEFAULT_TOOL_CALL_CAP else ""
    return f"Tools {'+'.join(configuration.tools)}{cap}"


def interval(estimate: int | None, low: int | None, high: int | None) -> str:
    """An estimate with its 95% interval, or a bound when only one end is known."""
    if estimate is None:
        return f"< {high}" if low is None else f"> {low}"
    return f"{estimate} [{'open' if low is None else low}, {'open' if high is None else high}]"


def rating_text(rating: Rating | None) -> str:
    return NONE if rating is None else interval(rating.estimate, rating.low, rating.high)


def move_quality_text(quality: MoveQuality | None) -> str:
    if quality is None:
        return NONE
    validated = "" if quality.validated else ", unvalidated"
    return f"{interval(quality.estimate, quality.low, quality.high)}{validated}"


def illegal_moves_per_game(column: Column) -> str:
    if column.enforced:
        return NOT_APPLICABLE
    return f"{column.illegal_moves / column.entry.games:.2f}"


def median_streak(column: Column) -> str:
    if column.enforced:
        return NOT_APPLICABLE
    return f"{statistics.median(column.streaks):g}" if column.streaks else NONE


def time_per_move(column: Column) -> str:
    return NONE if not column.timed_moves else f"{column.time_used_s / column.timed_moves:.1f} s"


def with_tools(cell: Callable[[Column], str]) -> Callable[[Column], str]:
    """A tool-use cell, for a configuration with tools and attempts only."""
    return lambda column: cell(column) if column.configuration.tools is not None and column.tool_use.attempts else NONE


def calls_per_attempt(column: Column) -> str:
    return f"{column.tool_use.tool_calls / column.tool_use.attempts:.2f}"


def share(count: int, column: Column) -> str:
    return f"{count} ({100 * count / column.tool_use.attempts:.0f}%)"


def attempts_calling(tool: str) -> Callable[[Column], str]:
    def cell(column: Column) -> str:
        if tool not in (column.configuration.tools or ()):
            return NONE
        return f"{100 * column.tool_use.attempts_calling[tool] / column.tool_use.attempts:.0f}%"

    return with_tools(cell)


def head_to_head(column: Column) -> str:
    tally = column.head_to_head
    if column.configuration.tools is None or not tally.games:
        return NONE
    score = (tally.wins + tally.draws / 2) / tally.games
    return f"{tally.wins} / {tally.draws} / {tally.losses} ({100 * score:.0f}%)"


if __name__ == "__main__":
    sys.exit(main())
