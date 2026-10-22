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
from typing import get_args

from chessllm.cli.anchor_batch import Analyser, default_evaluator, default_move_model
from chessllm.cli.anchor_match import default_player_for, play_anchor_match
from chessllm.engines.evaluator import Evaluator
from chessllm.game.session import COLORS, BenchmarkLlmSide, Color, LlmSide, Rules, Settings
from chessllm.logs.game_log import GAMES_DIR, GameLog
from chessllm.llm.models import LLM_MODELS, SAMPLING_FILE, load_sampling
from chessllm.engines.move_model import MoveModel
from chessllm.llm.players import LlmPlayer
from chessllm.game.prompt import LlmConstraints, PositionFormat, RetryFeedback


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faceoff-batch",
        description="Play a batch of LLM faceoffs between two models, unattended, alternating colours, and log every "
        "game.",
    )
    defaults = LlmSide()
    parser.add_argument("--models", nargs=2, required=True, metavar="MODEL", help="the two Ollama models")
    parser.add_argument("--games", type=int, default=2, help="how many games (default 2)")
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=defaults.thinking)
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
    parser.add_argument("--llm-constraints", choices=get_args(LlmConstraints), default=defaults.llm_constraints)
    parser.add_argument("--retry-feedback", choices=get_args(RetryFeedback), default=defaults.retry_feedback)
    parser.add_argument(
        "--position",
        choices=get_args(PositionFormat),
        default=defaults.position,
        help="how each turn gives the position: fen, or described (also the pieces, last move and check)",
    )
    parser.add_argument("--rules", choices=get_args(Rules), default=Settings.rules)
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=Settings.max_attempts,
        help=f"illegal moves per turn before an LLM forfeits (default {Settings.max_attempts})",
    )
    parser.add_argument("--games-dir", type=Path, default=GAMES_DIR, help=f"where logs go (default {GAMES_DIR})")
    parser.add_argument("--no-analysis", action="store_true", help="don't analyse each game (with Maia-2 and Stockfish)")
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
    """The settings of a faceoff of model white against model black. Raises ValueError when they can't be played."""

    levels: dict[str, str | None] = {}
    for model, level in args.thinking_for:
        if levels.get(model, level) != level:
            raise ValueError(f"--thinking-for gives {model} two Thinking levels, {levels[model]} and {level}")
        levels[model] = level
    budgets: dict[str, int] = {}
    for model, budget in args.thinking_budget_for:
        if budgets.get(model, budget) != budget:
            raise ValueError(f"--thinking-budget-for gives {model} two Thinking budgets, {budgets[model]} and {budget}")
        budgets[model] = budget

    def side(model: str) -> LlmSide:
        return BenchmarkLlmSide(
            model=model,
            thinking=args.thinking or model in levels,
            thinking_level=levels.get(model),
            thinking_budget=budgets.get(model),
            llm_constraints=args.llm_constraints,
            retry_feedback=args.retry_feedback,
            position=args.position,
        )

    settings = Settings(
        "llm_faceoff",
        side(white),
        side(black),
        sampling=load_sampling(sampling_file),
        rules=args.rules,
        max_attempts=args.max_attempts,
    )
    problem = settings.problem(LLM_MODELS)
    if problem is not None:
        raise ValueError(problem)
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
        return fail(f"the budget must be at least one game, not {args.games}")
    first, second = args.models
    try:
        faceoff_settings(args, first, second, sampling_file)
    except ValueError as error:
        return fail(str(error))
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
            result = state["result"]
            white_score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
            scores[white] += white_score
            scores[black] += 1 - white_score
            print(f"Game {number}/{args.games}: {white} (White) vs {black} (Black): {result} by {state['end_reason']}")
            finished, log = log.path, None
            analyser.analyse(finished)
    except KeyboardInterrupt:
        print(f"Stopped{f'; the last game was left unfinished in {log.path}' if log is not None else ''}.")
    finally:
        analyser.close()
    print(f"Batch: {first} {scores[first]:g} - {scores[second]:g} {second}")
    return 0


def fail(message: str) -> int:
    print(f"Faceoff batch not played: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
