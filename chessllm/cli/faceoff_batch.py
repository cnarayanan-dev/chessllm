"""Play a batch of LLM faceoffs from the command line: two models against each other, unattended.

    uv run faceoff-batch --models gemma3:12b llama3:8b --games 9

Colours alternate game by game, the first model as White in the first game. Both sides share the LLM's settings
(thinking, LLM constraints, Retry feedback, rules, attempts per turn), as a faceoff started in the app does by default;
--thinking-for MODEL turns thinking on for one model only, and --thinking-for MODEL=LEVEL at one of the Thinking levels
it offers, e.g. qwen3.8:latest=xhigh; --thinking-budget-for MODEL=TOKENS gives one model a Thinking budget (ADR 0007).
Each game is analysed as it ends, with Maia-2 and Stockfish (--no-analysis to skip). Ctrl-C stops it, leaving every
finished game's log complete."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from chessllm.cli.common import (
    Analyser,
    add_analysis_argument,
    add_games_dir_argument,
    add_prompt_arguments,
    add_rules_arguments,
    add_thinking_argument,
    default_evaluator,
    default_move_model,
    fail,
    prompt_template,
    warn_of_turn_memory,
)
from chessllm.cli.common import player_for as default_player_for
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.core.config import SAMPLING_FILE
from chessllm.core.types import COLORS, Color
from chessllm.exceptions import InvalidSamplingConfig, InvalidSettings
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import BenchmarkLlmSide, LlmSide
from chessllm.llm.models import LLM_MODELS, load_sampling
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog

FAILED = "Faceoff batch not played"


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faceoff-batch",
        description="Play a batch of LLM faceoffs between two models, unattended, alternating colours, and log every "
        "game.",
    )
    parser.add_argument("--models", nargs=2, required=True, metavar="MODEL", help="the two Ollama models")
    parser.add_argument("--games", type=int, default=2, help="how many games (default 2)")
    add_thinking_argument(parser)
    parser.add_argument(
        "--thinking-for",
        action="append",
        type=model_thinking,
        default=[],
        metavar="MODEL[=LEVEL]",
        help="turn thinking on for this model only (repeatable), e.g. a thinking model against one that can't think; "
        "=LEVEL thinks at one of the Thinking levels the model offers, e.g. qwen3.8:latest=xhigh",
    )
    parser.add_argument(
        "--thinking-budget-for",
        action="append",
        type=model_budget,
        default=[],
        metavar="MODEL=TOKENS",
        help="give this model a Thinking budget of TOKENS per attempt (repeatable; needs its thinking on), e.g. "
        "qwen3.8:latest=3072",
    )
    add_prompt_arguments(parser)
    add_rules_arguments(parser)
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=Settings.max_attempts,
        help=f"illegal moves per turn before an LLM forfeits (default {Settings.max_attempts})",
    )
    add_games_dir_argument(parser)
    add_analysis_argument(parser)
    return parser


def model_thinking(value: str) -> tuple[str, str | None]:
    """A --thinking-for value: the model, and the Thinking level after "=", if any."""
    model, _, level = value.partition("=")
    return model, level or None


def model_budget(value: str) -> tuple[str, int]:
    """A --thinking-budget-for value: the model, and the Thinking budget in tokens after "="."""
    model, _, tokens = value.partition("=")
    if not model or not tokens.isdigit():
        raise argparse.ArgumentTypeError(f"not MODEL=TOKENS: {value!r}")
    return model, int(tokens)


def faceoff_settings(args: argparse.Namespace, white: str, black: str, sampling_file: Path) -> Settings:
    """The settings of a faceoff of model white against model black. Raises InvalidSettings when they can't be
    played, and InvalidSamplingConfig for a broken config."""

    levels: dict[str, str | None] = {}
    for model, level in args.thinking_for:
        if levels.get(model, level) != level:
            raise InvalidSettings(f"--thinking-for gives {model} two Thinking levels, {levels[model]} and {level}")
        levels[model] = level
    budgets: dict[str, int] = {}
    for model, budget in args.thinking_budget_for:
        if budgets.get(model, budget) != budget:
            two = f"two Thinking budgets, {budgets[model]} and {budget}"
            raise InvalidSettings(f"--thinking-budget-for gives {model} {two}")
        budgets[model] = budget

    def side(model: str) -> LlmSide:
        return BenchmarkLlmSide(
            model=model,
            thinking=args.thinking or model in levels,
            thinking_level=levels.get(model),
            thinking_budget=budgets.get(model),
            llm_constraints=args.llm_constraints,
            retry_feedback=args.retry_feedback,
            prompt_template=prompt_template(args),
            turn_memory=args.turn_memory,
        )

    settings = Settings(
        "llm_faceoff",
        side(white),
        side(black),
        sampling=load_sampling(sampling_file),
        rules=args.rules,
        legal_counterpart=not args.no_legal_counterpart,
        max_attempts=args.max_attempts,
    )
    settings.check(LLM_MODELS)
    return settings


def main(
    argv: list[str] | None = None,
    player_for: Callable[[Settings, Color], LlmPlayer] = default_player_for,
    sampling_file: Path = SAMPLING_FILE,
    move_model_for: Callable[[], MoveModel | None] = default_move_model,
    evaluator_for: Callable[[], Evaluator | None] = default_evaluator,
) -> int:
    """Run the command; returns its exit code."""
    args = parser().parse_args(argv)
    if args.games < 1:
        return fail(FAILED, f"the budget must be at least one game, not {args.games}")
    first, second = args.models
    try:
        faceoff_settings(args, first, second, sampling_file)
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return fail(FAILED, str(error))
    warn_of_turn_memory(args)
    analyser = Analyser(None, None) if args.no_analysis else Analyser(move_model_for(), evaluator_for())
    scores = {first: 0.0, second: 0.0}
    log: GameLog | None = None
    try:
        for number in range(1, args.games + 1):
            white, black = (first, second) if number % 2 else (second, first)
            settings = faceoff_settings(args, white, black, sampling_file)
            players = {color: player_for(settings, color) for color in COLORS}
            log = GameLog(args.games_dir, *settings.side_names())
            state = play_anchor_match(settings, players, {}, log)
            result = state.result
            assert result is not None  # played to its end
            white_score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
            scores[white] += white_score
            scores[black] += 1 - white_score
            print(f"Game {number}/{args.games}: {white} (White) vs {black} (Black): {result} by {state.end_reason}")
            finished, log = log.path, None
            analyser.analyse(finished)
    except KeyboardInterrupt:
        print(f"Stopped{f'; the last game was left unfinished in {log.path}' if log is not None else ''}.")
    finally:
        analyser.close()
    print(f"Batch: {first} {scores[first]:g} - {scores[second]:g} {second}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
