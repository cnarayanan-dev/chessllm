"""Run the Tools experiment for a model from the command line: does it play better with Tools (ADR 0011)?

    uv run tools-experiment --model qwen3.8 --thinking-level medium --tools board,legal_moves,material,move_history \\
        --anchor-games 30 --faceoff-games 10

In order, one game after another: an Anchor ladder of the Player configuration without Tools, the same for the
configuration with them (--tools; all four when not given), then a head to head of the model against itself, Tools
on one side, colours swapped each game; then the comparison, written to reports/tools-comparison-<date>.md. The two
configurations differ only in the Tools and the Prompt template a side with Tools plays; the rest of the
configuration is anchor-batch's arguments, and the side with Tools is checked against what Tools allow before the
first game.

Counts are totals. --anchor-games is how many finished Anchor matches each configuration's ladder should have, its
earlier games in the games directory included, so a ladder goes on from them as anchor-batch does and only the
games still missing are played; --faceoff-games is the same for the finished faceoffs between the two (0 skips the
head to head). So running the command again after an interruption carries on where it stopped, the game left
unfinished played again, and raising a count extends the experiment. --report-only writes the report from the logs
without playing. The report covers every finished game in the games directory of every model's configurations with
and without Tools (chessllm.analytics.tools_comparison), not only this run's."""

import argparse
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

from chessllm.analytics.leaderboard import (
    PlayerConfiguration,
    finished_game,
    llm_configuration,
    logged_mode,
    read_sides,
    settings_configuration,
)
from chessllm.analytics.tools_comparison import markdown, tools_comparison
from chessllm.cli.common import (
    INTERRUPTED_EXIT_CODE,
    Analyser,
    add_analysis_argument,
    add_configuration_arguments,
    anchor_match_settings,
    benchmark_llm_side,
    check_ladder,
    default_anchor,
    default_evaluator,
    default_move_model,
    fail,
    first_rung,
    play_ladder,
)
from chessllm.cli.common import player_for as default_player_for
from chessllm.core.config import REPORTS_DIR, SAMPLING_FILE
from chessllm.core.types import COLORS, Color, opponent
from chessllm.engines.anchors import Anchor
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.exceptions import InvalidSamplingConfig, InvalidSettings
from chessllm.game.ladder import earlier_games
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import ALL_TOOLS, AnchorSide
from chessllm.llm.models import LLM_MODELS, load_sampling
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog

DEFAULT_ANCHOR_GAMES = 30
DEFAULT_FACEOFF_GAMES = 10
FAILED = "Tools experiment stopped"
CARRY_ON = "Run it again to carry on."


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tools-experiment",
        description="Play an Anchor ladder of an LLM without Tools and with them, then a head to head of the two, "
        "and write the comparison as Markdown.",
    )
    add_configuration_arguments(parser)
    parser.add_argument(
        "--anchor-games",
        type=int,
        default=DEFAULT_ANCHOR_GAMES,
        help=f"the finished Anchor matches each ladder should have, earlier ones included (default "
        f"{DEFAULT_ANCHOR_GAMES})",
    )
    parser.add_argument(
        "--faceoff-games",
        type=int,
        default=DEFAULT_FACEOFF_GAMES,
        help=f"the finished faceoffs of the model with Tools against itself without (default {DEFAULT_FACEOFF_GAMES};"
        " 0 skips them)",
    )
    parser.add_argument("--report-only", action="store_true", help="write the report from the logs, without playing")
    parser.add_argument(
        "--reports-dir", type=Path, default=REPORTS_DIR, help="where the report goes (default: the project's reports/)"
    )
    add_analysis_argument(parser)
    return parser


def main(
    argv: list[str] | None = None,
    player_for: Callable[[Settings, Color], LlmPlayer] = default_player_for,
    anchor_for: Callable[[AnchorSide], Anchor] | None = None,
    sampling_file: Path = SAMPLING_FILE,
    move_model_for: Callable[[], MoveModel | None] = default_move_model,
    evaluator_for: Callable[[], Evaluator | None] = default_evaluator,
    today: Callable[[], date] = date.today,
) -> int:
    """Run the command; returns its exit code. anchor_for, move_model_for and evaluator_for as anchor-batch's;
    today dates the report."""
    args = parser().parse_args(argv)
    if not args.tools:
        args.tools = ALL_TOOLS
    if args.report_only:
        return write_report(args, today())
    for flag, games in (("--anchor-games", args.anchor_games), ("--faceoff-games", args.faceoff_games)):
        if games < 0:
            return fail(FAILED, f"{flag} must be at least 0, not {games}")
    if args.engine == "random":
        return fail(FAILED, "the random mover is the ladder's bottom rung, not its engine: choose dragon or stockfish")
    plain = argparse.Namespace(**vars(args) | {"tools": frozenset(), "tool_call_cap": None, "skill": None})
    tooled = argparse.Namespace(**vars(args) | {"skill": None})
    try:
        configurations = [
            settings_configuration(anchor_match_settings(ladder, "white", first_rung(ladder), sampling_file), "white")
            for ladder in (plain, tooled)
        ]
        if args.faceoff_games:
            faceoff_settings(plain, tooled, "white", sampling_file)
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return fail(FAILED, str(error))
    if anchor_for is None:
        anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
    have = [len(earlier_games(args.games_dir, configuration, args.engine)) for configuration in configurations]
    if any(games < args.anchor_games for games in have):
        refused = check_ladder(tooled, anchor_for, sampling_file)  # its engine, once: the two ladders share it
        if refused is not None:
            return fail(FAILED, refused)
    analyser = Analyser(None, None) if args.no_analysis else Analyser(move_model_for(), evaluator_for())
    try:
        for name, ladder, played in zip(("without Tools", "with Tools"), (plain, tooled), have):
            missing = max(args.anchor_games - played, 0)
            print(f"Anchor ladder {name}: {played} of {args.anchor_games} games, {missing} to play.", flush=True)
            if missing:
                code = play_ladder(
                    argparse.Namespace(**vars(ladder) | {"games": missing}),
                    player_for, anchor_for, sampling_file, analyser, FAILED,
                )
                if code:
                    print(CARRY_ON, file=sys.stderr)
                    return code
        if args.faceoff_games:
            code = play_head_to_head(args, plain, tooled, configurations, player_for, sampling_file, analyser)
            if code:
                return code
    finally:
        analyser.close()
    return write_report(args, today())


def faceoff_settings(
    plain: argparse.Namespace, tooled: argparse.Namespace, tools_color: Color, sampling_file: Path
) -> Settings:
    """The settings of a faceoff of the model with Tools at tools_color against itself without them. Raises
    InvalidSettings when they can't be played, and InvalidSamplingConfig for a broken config."""
    with_tools, without = benchmark_llm_side(tooled), benchmark_llm_side(plain)
    white, black = (with_tools, without) if tools_color == "white" else (without, with_tools)
    settings = Settings(
        "llm_faceoff",
        white,
        black,
        sampling=load_sampling(sampling_file),
        rules=plain.rules,
        max_attempts=plain.max_attempts,
        legal_counterpart=not plain.no_legal_counterpart,
    )
    settings.check(LLM_MODELS)
    return settings


def earlier_faceoffs(games_dir: Path, pair: list[PlayerConfiguration]) -> int:
    """The finished LLM faceoffs in games_dir between the two configurations, either way round."""
    ids = sorted(configuration.id() for configuration in pair)
    count = 0
    for path in sorted(games_dir.glob("*.jsonl")) if games_dir.is_dir() else []:
        events = finished_game(path)
        if events is None or logged_mode(events[0]) != "llm_faceoff":
            continue
        start, end = events[0], events[-1]
        sides, _ = read_sides(start, end)
        count += sorted(llm_configuration(start, color, side).id() for color, side in sides.items()) == ids
    return count


def play_head_to_head(
    args: argparse.Namespace,
    plain: argparse.Namespace,
    tooled: argparse.Namespace,
    configurations: list[PlayerConfiguration],
    player_for: Callable[[Settings, Color], LlmPlayer],
    sampling_file: Path,
    analyser: Analyser,
) -> int:
    """Play the faceoffs still missing, the side with Tools White in the first of all and colours swapped each game;
    returns the exit code."""
    have = earlier_faceoffs(args.games_dir, configurations)
    missing = max(args.faceoff_games - have, 0)
    print(f"Head to head: {have} of {args.faceoff_games} games, {missing} to play.", flush=True)
    log: GameLog | None = None
    try:
        for number in range(have + 1, args.faceoff_games + 1):
            tools_color: Color = "white" if number % 2 else "black"
            settings = faceoff_settings(plain, tooled, tools_color, sampling_file)
            players = {color: player_for(settings, color) for color in COLORS}
            log = GameLog(args.games_dir, *settings.side_names())
            state = play_anchor_match(settings, players, {}, log)
            print(
                f"Game {number}/{args.faceoff_games}: Tools as {tools_color}, without as {opponent(tools_color)}: "
                f"{state.result} by {state.end_reason}",
                flush=True,
            )
            finished, log = log.path, None
            analyser.analyse(finished)
    except KeyboardInterrupt:
        unfinished = f"; the game was left unfinished in {log.path}" if log is not None else ""
        print(f"Interrupted in the head to head{unfinished}. {CARRY_ON}", file=sys.stderr)
        return INTERRUPTED_EXIT_CODE
    return 0


def write_report(args: argparse.Namespace, day: date) -> int:
    path = args.reports_dir / f"tools-comparison-{day.isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown(tools_comparison(args.games_dir), day), encoding="utf-8")
    print(f"Report written to {path}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
