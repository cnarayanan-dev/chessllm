"""Play a batch of LLM faceoffs from the command line: two models against each other, unattended.

    uv run faceoff-batch --models gemma3:12b llama3:8b --games 9
    uv run faceoff-batch --first-system1-model d3:2b --models llama3:8b --games 10
    uv run faceoff-batch --first-system1-model d3:2b --second-system1-model d3:9b --second-choice-temperature 0.5

Colours alternate game by game, the first model as White in the first game. Either side can be a System 1 model
(ADR 0012) in place of an LLM: --first-system1-model or --second-system1-model names it, with its server
(--first-system1-url, default the local Ollama), Choice temperature (--first-choice-temperature, default 1) and Prompt
template (--first-system1-template, by its ID in the Prompt library, default the System 1 default), and
--models then names only the LLM sides, in order. Before the first game every System 1 side's server is asked whether
it has the model, and each game plays from a fresh seed, logged with it. Both LLM sides share the LLM's settings
(thinking, LLM constraints, Retry feedback, rules, attempts per turn), as a faceoff started in the app does by default;
--thinking-for MODEL turns thinking on for one model only, and --thinking-for MODEL=LEVEL at one of the Thinking levels
it offers, e.g. qwen3.8:latest=xhigh; --thinking-budget-for MODEL=TOKENS gives one model a Thinking budget (ADR 0007),
and --tools-for MODEL[=LIST] and --tool-call-cap-for MODEL=N its Tools and their Tool-call cap (ADR 0011).
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
    add_system1_arguments,
    add_thinking_argument,
    default_evaluator,
    default_move_model,
    fail,
    prompt_template,
    refuse_llm_settings,
    system1_side,
    tool_call_cap,
    tool_set,
)
from chessllm.cli.common import (
    decision_model_for as default_decision_model_for,
    missing_models as default_missing_models,
    player_for as default_player_for,
    system1_missing_models as default_system1_missing_models,
)
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.core.config import SAMPLING_FILE
from chessllm.core.types import Color
from chessllm.exceptions import InvalidSamplingConfig, InvalidSettings
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import ALL_TOOLS, BenchmarkLlmSide, LlmSide, System1Side, ToolName
from chessllm.llm.models import LLM_MODELS, load_sampling
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog
from chessllm.system1.port import DecisionModel

FAILED = "Faceoff batch not played"


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faceoff-batch",
        description="Play a batch of LLM faceoffs between two models, unattended, alternating colours, and log every "
        "game.",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=[],
        metavar="MODEL",
        help="the Ollama models of the sides that are LLMs, in order: two, or one if a side is a System 1 model "
        "(--first-system1-model, --second-system1-model), or none if both are",
    )
    add_system1_arguments(parser, "first")
    add_system1_arguments(parser, "second")
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
    parser.add_argument(
        "--tools-for",
        action="append",
        type=model_tools,
        default=[],
        metavar="MODEL[=LIST]",
        help="give this model Tools it may call before it answers (repeatable), joined by commas after \"=\", e.g. "
        "qwen3.5:9b=board,legal_moves; bare, all four (needs its thinking on, Free or Blind enforced, Standard rules "
        "and fresh Turn memory)",
    )
    parser.add_argument(
        "--tool-call-cap-for",
        action="append",
        type=model_cap,
        default=[],
        metavar="MODEL=N",
        help=f"the most tool calls per attempt for this model (repeatable; default {BenchmarkLlmSide.tool_call_cap}; "
        "needs its --tools-for)",
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


def model_tools(value: str) -> tuple[str, frozenset[ToolName]]:
    """A --tools-for value: the model, and the Tools after "=", all four without "="."""
    model, equals, tools = value.partition("=")
    return model, tool_set(tools) if equals else ALL_TOOLS


def model_cap(value: str) -> tuple[str, int]:
    """A --tool-call-cap-for value: the model, and its Tool-call cap after "="."""
    model, _, cap = value.partition("=")
    if not model or not cap.isdigit():
        raise argparse.ArgumentTypeError(f"not MODEL=N: {value!r}")
    return model, int(cap)


def faceoff_sides(args: argparse.Namespace, library: PromptLibrary | None = None) -> tuple[LlmSide | System1Side, LlmSide | System1Side]:
    """The first and the second side of the batch: a System 1 side where its --…-system1-model is given, else an LLM
    side of the next of --models, with the LLM's settings in args. Raises InvalidSettings if --models doesn't name
    exactly the sides that aren't System 1 sides, if an LLM's setting is given when both are System 1 sides, as
    system1_side does for a System 1 side's Prompt template (found in the library), and when an LLM's settings
    can't be played together. Raises InvalidSamplingConfig for a broken config."""
    system1 = (system1_side(args, "first", library), system1_side(args, "second", library))
    llm_sides = system1.count(None)
    if len(args.models) != llm_sides:
        raise InvalidSettings(
            f"--models must name the {llm_sides} side{'s' * (llm_sides != 1)} that {'are' if llm_sides != 1 else 'is'} "
            f"an LLM (a side without --first-system1-model or --second-system1-model is), not {len(args.models)}"
        )
    if not llm_sides:
        refuse_llm_settings(args, parser().parse_args([]), "both sides are System 1 models")
    llms = iter(args.models)
    first, second = (side or llm_side(args, next(llms)) for side in system1)
    return first, second


def faceoff_settings(args: argparse.Namespace, white: LlmSide | System1Side, black: LlmSide | System1Side, sampling_file: Path) -> Settings:
    """The settings of a faceoff of side white against side black. Raises InvalidSettings when they can't be
    played, and InvalidSamplingConfig for a broken config."""
    settings = Settings(
        "llm_faceoff",
        white,
        black,
        sampling=load_sampling(sampling_file),
        rules=args.rules,
        legal_counterpart=not args.no_legal_counterpart,
        max_attempts=args.max_attempts,
    )
    settings.check(LLM_MODELS)
    return settings


def llm_side(args: argparse.Namespace, model: str) -> LlmSide:
    """The LLM side of the model, with the LLM's settings in args and the per-model ones given for it. Raises
    InvalidSettings if a per-model flag gives it two values, or a Tool-call cap without Tools."""
    levels: dict[str, str | None] = {}
    for named, level in args.thinking_for:
        if levels.get(named, level) != level:
            raise InvalidSettings(f"--thinking-for gives {named} two Thinking levels, {levels[named]} and {level}")
        levels[named] = level
    budgets: dict[str, int] = {}
    for named, budget in args.thinking_budget_for:
        if budgets.get(named, budget) != budget:
            two = f"two Thinking budgets, {budgets[named]} and {budget}"
            raise InvalidSettings(f"--thinking-budget-for gives {named} {two}")
        budgets[named] = budget
    tools: dict[str, frozenset[ToolName]] = {}
    for named, its_tools in args.tools_for:
        if tools.get(named, its_tools) != its_tools:
            two = f"two sets of Tools, {'+'.join(sorted(tools[named]))} and {'+'.join(sorted(its_tools))}"
            raise InvalidSettings(f"--tools-for gives {named} {two}")
        tools[named] = its_tools
    caps: dict[str, int] = {}
    for named, cap in args.tool_call_cap_for:
        if caps.get(named, cap) != cap:
            raise InvalidSettings(f"--tool-call-cap-for gives {named} two Tool-call caps, {caps[named]} and {cap}")
        caps[named] = cap
    its_tools = tools.get(model, frozenset())
    cap_flag = f"--tool-call-cap-for {model}={caps[model]}" if model in caps else "--tool-call-cap-for"
    return BenchmarkLlmSide(
        model=model,
        thinking=args.thinking or model in levels,
        thinking_level=levels.get(model),
        thinking_budget=budgets.get(model),
        llm_constraints=args.llm_constraints,
        retry_feedback=args.retry_feedback,
        prompt_template=prompt_template(args),
        turn_memory=args.turn_memory,
        tools=its_tools,
        tool_call_cap=tool_call_cap(its_tools, caps.get(model), cap_flag),
    )


def side_label(side: LlmSide | System1Side) -> str:
    """A side as the batch names it: an LLM by its model, a System 1 side by its model and Choice temperature."""
    return side.name() if isinstance(side, System1Side) else side.model


def main(
    argv: list[str] | None = None,
    player_for: Callable[[Settings, Color], LlmPlayer] = default_player_for,
    sampling_file: Path = SAMPLING_FILE,
    move_model_for: Callable[[], MoveModel | None] = default_move_model,
    evaluator_for: Callable[[], Evaluator | None] = default_evaluator,
    missing_models: Callable[[list[str]], list[str]] = default_missing_models,
    system1_missing_models: Callable[[str, list[str]], list[str]] = default_system1_missing_models,
    decision_model_for: Callable[[System1Side], DecisionModel] = default_decision_model_for,
    prompt_library: PromptLibrary | None = None,
) -> int:
    """Run the command; returns its exit code. missing_models says which models Ollama doesn't have, by default
    Ollama itself; system1_missing_models(base_url, models) says which models a System 1 server doesn't have, by
    default the server itself, and decision_model_for builds the decision model of a System 1 side, by default over
    HTTP. Each System 1 side of each game is given a model of its own. prompt_library holds the Prompt templates
    --first-system1-template and --second-system1-template pick from, by default the project's."""
    args = parser().parse_args(argv)
    if args.games < 1:
        return fail(FAILED, f"the budget must be at least one game, not {args.games}")
    try:
        first, second = faceoff_sides(args, prompt_library)
        settings = faceoff_settings(args, first, second, sampling_file)
        settings.check_installed(missing_models)
        settings.check_served(system1_missing_models)
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return fail(FAILED, str(error))
    analyser = Analyser(None, None) if args.no_analysis else Analyser(move_model_for(), evaluator_for())
    scores = {"first": 0.0, "second": 0.0}
    log: GameLog | None = None
    try:
        for number in range(1, args.games + 1):
            white, black = ("first", "second") if number % 2 else ("second", "first")
            sides = {"first": first, "second": second}
            settings = faceoff_settings(args, sides[white], sides[black], sampling_file)
            players = {color: player_for(settings, color) for color in settings.llm_sides()}
            decision_models = {color: decision_model_for(side) for color, side in settings.system1_sides().items()}
            log = GameLog(args.games_dir, *settings.side_names())
            state = play_anchor_match(settings, players, {}, log, decision_models=decision_models)
            result = state.result
            assert result is not None  # played to its end
            white_score = {"1-0": 1.0, "0-1": 0.0}.get(result, 0.5)
            scores[white] += white_score
            scores[black] += 1 - white_score
            versus = f"{side_label(sides[white])} (White) vs {side_label(sides[black])} (Black)"
            print(f"Game {number}/{args.games}: {versus}: {result} by {state.end_reason}")
            finished, log = log.path, None
            analyser.analyse(finished)
    except KeyboardInterrupt:
        print(f"Stopped{f'; the last game was left unfinished in {log.path}' if log is not None else ''}.")
    finally:
        analyser.close()
    print(f"Batch: {side_label(first)} {scores['first']:g} - {scores['second']:g} {side_label(second)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
