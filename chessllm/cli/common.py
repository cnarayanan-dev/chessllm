"""What the commands share: the LLM's Player configuration arguments, the players, Anchors and engines a game is
played and analysed with, and how a command reports that it failed. The commands import each other's code from here,
never from one another."""

import argparse
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from chessllm.analytics.analysis import analyse_game
from chessllm.analytics.leaderboard import settings_configuration, system1_side_configuration
from chessllm.core.config import (
    CLAUDE_TOKEN_VARIABLE,
    DRAGON_PATH_VARIABLE,
    GAMES_DIR,
    PROMPT_LIBRARY_DIR,
    STOCKFISH_PATH_VARIABLE,
    SYSTEM1_DEFAULT_URL,
    claude_token_from_environment,
)
from chessllm.engines.anchors import (
    Anchor,
    DragonAnchor,
    RandomAnchor,
    StockfishAnchor,
    configured_dragon_path,
    configured_stockfish_path,
)
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.exceptions import (
    AnchorUnavailable,
    InvalidSamplingConfig,
    InvalidSettings,
    Maia2Unavailable,
    StockfishUnavailable,
)
from chessllm.core.types import Color, RulesKey, opponent, score_for
from chessllm.game.ladder import (
    FIRST_SKILL,
    AnchoredGame,
    earlier_games,
    next_color,
    next_rung,
    rung_name,
    rung_side,
)
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.records import GameState
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import (
    AnchorEngine,
    AnchorSide,
    BenchmarkLlmSide,
    LlmConstraints,
    LlmSide,
    PromptTemplate,
    RetryFeedback,
    Side,
    System1Side,
    ALL_TOOLS,
    TOOL_NAMES,
    ToolName,
    TurnMemory,
    side_tool_call_cap,
)
from chessllm.game.llm_turn.prompt import DefaultTemplate, default_template
from chessllm.llm.models import KNOWN_MODELS, load_sampling
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog
from chessllm.system1.port import DecisionModel
from chessllm.system1.prompt import DEFAULT_TEMPLATE, SYSTEM1_TEMPLATES, resolve_system1_template

if TYPE_CHECKING:
    from chessllm.llm.claude_player import ClaudePlayer
    from chessllm.llm.ollama_player import OllamaPlayer

# The default Prompt templates --prompt-template offers: Moves is not one, as it is the Default under chat_moves and
# fits no other Turn memory.
PROMPT_TEMPLATE_CHOICES: tuple[DefaultTemplate, ...] = ("default", "described")


def add_thinking_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=LlmSide().thinking)


def add_prompt_arguments(parser: argparse.ArgumentParser) -> None:
    """The LLM constraints, Retry feedback and Prompt template of the Player configuration."""
    defaults = LlmSide()
    parser.add_argument("--llm-constraints", choices=get_args(LlmConstraints), default=defaults.llm_constraints)
    parser.add_argument("--retry-feedback", choices=get_args(RetryFeedback), default=defaults.retry_feedback)
    parser.add_argument(
        "--prompt-template",
        choices=PROMPT_TEMPLATE_CHOICES,
        default="default",
        help="the default Prompt template: default (the PGN and FEN, or under chat_moves only the opponent's last "
        "move), or described (also the last move, every piece's square and check)",
    )
    parser.add_argument(
        "--turn-memory",
        choices=get_args(TurnMemory),
        default=defaults.turn_memory,
        help="whether the LLM's turns share one conversation: fresh (the default: each turn starts anew), "
        "chat_position (one conversation for the game, each turn adding its message), or chat_moves (one "
        "conversation, each turn adding only the opponent's last move)",
    )


def tool_set(value: str) -> frozenset[ToolName]:
    """A --tools value: tool names joined by commas, e.g. board,legal_moves. An empty one is refused, never taken
    as no Tools or all four."""
    names = [name.strip() for name in value.split(",")]
    if not value.strip():
        raise argparse.ArgumentTypeError(f"no Tools in {value!r}: give them joined by commas, e.g. board,legal_moves")
    if "" in names:
        joined = "give the Tools joined by commas, e.g. board,legal_moves"
        raise argparse.ArgumentTypeError(f"an empty Tool name in {value!r}: {joined}")
    unknown = [name for name in names if name not in TOOL_NAMES]
    if unknown:
        raise argparse.ArgumentTypeError(f"no Tool {', '.join(unknown)}: the Tools are {', '.join(TOOL_NAMES)}")
    return frozenset(name for name in TOOL_NAMES if name in names)


def add_tools_arguments(parser: argparse.ArgumentParser) -> None:
    """The Tools of the Player configuration and their Tool-call cap (ADR 0011)."""
    tools = ", ".join(TOOL_NAMES)
    parser.add_argument(
        "--tools",
        nargs="?",
        type=tool_set,
        const=ALL_TOOLS,
        default=frozenset(),
        metavar="LIST",
        help=f"the Tools the LLM may call before it answers, joined by commas, from {tools}; bare, all four (needs "
        "thinking on, Free or Blind enforced, Standard rules and fresh Turn memory)",
    )
    parser.add_argument(
        "--tool-call-cap",
        type=int,
        metavar="N",
        help=f"the most tool calls per attempt (default {BenchmarkLlmSide.tool_call_cap}; needs --tools)",
    )


def tool_call_cap(tools: frozenset[ToolName], cap: int | None, flag: str) -> int:
    """The Tool-call cap a side with these tools plays with, given by flag, e.g. "--tool-call-cap 5". Raises
    InvalidSettings for a cap without tools, which would mean nothing."""
    if cap is None:
        return BenchmarkLlmSide.tool_call_cap
    if not tools:
        raise InvalidSettings(f"{flag} gives a Tool-call cap without Tools")
    return cap


def add_rules_arguments(parser: argparse.ArgumentParser) -> None:
    """The Rules, part of the Player configuration, and under Chaos rules whether Legal counterparts are asked
    for, which is not."""
    parser.add_argument("--rules", choices=get_args(RulesKey), default=Settings.rules)
    parser.add_argument(
        "--no-legal-counterpart",
        action="store_true",
        help="under Chaos rules, don't ask the LLM for a legal move after each chaos move (one call fewer each)",
    )


def prompt_template(args: argparse.Namespace) -> PromptTemplate | None:
    """The Prompt template --prompt-template asks for: None for the Default, read when each game starts."""
    kind: DefaultTemplate = args.prompt_template
    return None if kind == "default" else default_template(args.llm_constraints, kind)


def add_games_dir_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--games-dir", type=Path, default=GAMES_DIR, help="where logs go (default: the project's games/)")


def add_analysis_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--no-analysis", action="store_true", help="don't analyse each game (with Maia-2 and Stockfish)")


def add_configuration_arguments(parser: argparse.ArgumentParser) -> None:
    """The LLM's Player configuration in an Anchor match, and where Dragon and the logs are: shared by anchor-match
    and anchor-batch."""
    defaults = LlmSide()
    parser.add_argument("--model", default=defaults.model, help=f"the Ollama model (default {defaults.model})")
    add_thinking_argument(parser)
    parser.add_argument(
        "--thinking-level",
        metavar="LEVEL",
        help="think at one of the Thinking levels the model offers, e.g. xhigh for qwen3.8:latest (turns thinking on)",
    )
    parser.add_argument(
        "--thinking-budget",
        type=int,
        metavar="TOKENS",
        help="the most tokens of thinking and answer per attempt before the model is made to answer, e.g. 3072 "
        "(needs thinking on)",
    )
    add_prompt_arguments(parser)
    add_tools_arguments(parser)
    # Chaos rules only with the Stockfish Anchor, which copes with chaos positions.
    add_rules_arguments(parser)
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=Settings.max_attempts,
        help=f"illegal moves per turn before the LLM forfeits (default {Settings.max_attempts})",
    )
    parser.add_argument(
        "--engine",
        choices=get_args(AnchorEngine),
        default="dragon",
        help="the Anchor: Dragon, or Stockfish as a rough stand-in where Dragon can't be had (default dragon); "
        "anchor-match also takes random, the random legal mover, which needs no engine",
    )
    parser.add_argument("--dragon", help=f"the Dragon executable (default: ${DRAGON_PATH_VARIABLE})")
    parser.add_argument(
        "--stockfish", help=f"the Stockfish executable (default: ${STOCKFISH_PATH_VARIABLE}, else on the PATH)"
    )
    add_games_dir_argument(parser)


# The settings that only an LLM side has, by the name of their argument and their flag, across the commands: refused
# when no side is an LLM (ADR 0012), never silently ignored. A command has some of them (refuse_llm_settings).
LLM_ONLY_FLAGS: dict[str, str] = {
    "model": "--model",
    "thinking": "--thinking",
    "thinking_for": "--thinking-for",
    "thinking_level": "--thinking-level",
    "thinking_budget": "--thinking-budget",
    "thinking_budget_for": "--thinking-budget-for",
    "llm_constraints": "--llm-constraints",
    "retry_feedback": "--retry-feedback",
    "prompt_template": "--prompt-template",
    "turn_memory": "--turn-memory",
    "tools": "--tools",
    "tools_for": "--tools-for",
    "tool_call_cap": "--tool-call-cap",
    "tool_call_cap_for": "--tool-call-cap-for",
    "rules": "--rules",
    "no_legal_counterpart": "--no-legal-counterpart",
    "max_attempts": "--max-attempts",
}


def refuse_llm_settings(args: argparse.Namespace, unchanged: argparse.Namespace, reason: str) -> None:
    """Raises InvalidSettings, naming the flag and giving the reason, if args has any of the LLM_ONLY_FLAGS that
    unchanged, the command's arguments with none given, has and args has changed. A command has only some of them."""
    for dest, flag in LLM_ONLY_FLAGS.items():
        if dest in vars(unchanged) and getattr(args, dest) != getattr(unchanged, dest):
            raise InvalidSettings(f"{flag} sets an LLM, but {reason}")


def _flag(side: str | None, name: str) -> str:
    """The flag of a System 1 side's setting, e.g. "system1-model": --system1-model, or for the named side "first",
    --first-system1-model."""
    return f"--{side}-{name}" if side else f"--{name}"


def _dest(side: str | None, name: str) -> str:
    """The name of the argument _flag(side, name) is parsed into."""
    return _flag(side, name).removeprefix("--").replace("-", "_")


def add_system1_arguments(parser: argparse.ArgumentParser, side: str | None = None) -> None:
    """A System 1 side in place of the LLM side (ADR 0012): --system1-model names it, and the rest set it. For a
    command with two such sides, side names one, e.g. "first" for --first-system1-model. The seed is apart
    (add_system1_seed_argument): a command of many games gives each a fresh one."""
    parser.add_argument(
        _flag(side, "system1-model"),
        metavar="MODEL",
        help="play a System 1 model, e.g. d3:2b, instead of an LLM: its name on the server (the LLM's settings, such "
        "as --model and --thinking, then don't apply and are refused)",
    )
    parser.add_argument(
        _flag(side, "system1-url"),
        metavar="URL",
        default=SYSTEM1_DEFAULT_URL,
        help=f"the base URL of the server that serves the System 1 model's /v1/systemone (default {SYSTEM1_DEFAULT_URL})",
    )
    parser.add_argument(
        _flag(side, "choice-temperature"),
        type=float,
        default=System1Side.choice_temperature,
        metavar="T",
        help="how the System 1 model's probabilities become its move: at 1 (the default) each move is played as "
        "often as its probability, below 1 its favourites more often, at 0 always its top move",
    )
    parser.add_argument(
        _flag(side, "system1-template"),
        metavar="ID",
        help="the System 1 model's Prompt template, by its ID in the Prompt library: "
        + ", ".join(SYSTEM1_TEMPLATES)
        + f" or a saved one that doesn't place the Legal-move list (default {DEFAULT_TEMPLATE.id}; --prompt-template "
        "is the LLM's)",
    )


def add_system1_seed_argument(parser: argparse.ArgumentParser) -> None:
    """--system1-seed, for a command of a single game with one System 1 side."""
    parser.add_argument(
        "--system1-seed",
        type=int,
        metavar="SEED",
        help="the System 1 side's seed, for the order of its options and its draws, e.g. a logged one to replay "
        "(default: fresh)",
    )


def system1_side(
    args: argparse.Namespace, side: str | None = None, library: PromptLibrary | None = None
) -> System1Side | None:
    """The System 1 side --system1-model asks for (add_system1_arguments, or its --{side}- flags for a named side),
    or None if it isn't given. Its Prompt template is --system1-template's, found in the Prompt library (by default
    the project's), else the default one. Raises InvalidSettings, naming the flag, if --system1-template is given
    without a System 1 model, or if the library has no such template or the side can't play it; without a side name,
    also if an LLM's setting (add_configuration_arguments) is given."""
    model = getattr(args, _dest(side, "system1-model"))
    template_id = getattr(args, _dest(side, "system1-template"))
    if model is None:
        if template_id is not None:
            raise InvalidSettings(
                f"{_flag(side, 'system1-template')} {template_id} needs {_flag(side, 'system1-model')}"
            )
        return None
    if side is None:
        defaults = argparse.ArgumentParser()
        add_configuration_arguments(defaults)
        refuse_llm_settings(args, defaults.parse_args([]), f"--system1-model {model} is a System 1 model")
    template = None
    if template_id is not None:
        template = resolve_system1_template(template_id, library or PromptLibrary(PROMPT_LIBRARY_DIR))
    return System1Side(
        model=model,
        base_url=getattr(args, _dest(side, "system1-url")),
        choice_temperature=getattr(args, _dest(side, "choice-temperature")),
        prompt_template=template,
    )


def anchor_match_settings(
    args: argparse.Namespace, llm_color: Color, anchor_side: AnchorSide, sampling_file: Path
) -> Settings:
    """The settings of an Anchor match of the LLM in args at llm_color against the Anchor side. Raises
    InvalidSettings with the reason when they can't be played, and InvalidSamplingConfig for a broken config."""
    return side_anchor_match_settings(benchmark_llm_side(args), args, llm_color, anchor_side, sampling_file)


def side_anchor_match_settings(
    model_side: Side, args: argparse.Namespace, color: Color, anchor_side: AnchorSide, sampling_file: Path
) -> Settings:
    """The settings of an Anchor match of the Model player's side at color against the Anchor side, with the
    sampling and Rules in args. Raises InvalidSettings and InvalidSamplingConfig as anchor_match_settings does."""
    white, black = (model_side, anchor_side) if color == "white" else (anchor_side, model_side)
    settings = Settings(
        "anchor_match",
        white,
        black,
        sampling=load_sampling(sampling_file),
        rules=args.rules,
        max_attempts=args.max_attempts,
        legal_counterpart=not args.no_legal_counterpart,
    )
    settings.check(KNOWN_MODELS)
    return settings


def benchmark_llm_side(args: argparse.Namespace) -> BenchmarkLlmSide:
    """The LLM side of the Player configuration in args (add_configuration_arguments). Raises InvalidSettings for a
    Tool-call cap without Tools."""
    return BenchmarkLlmSide(
        model=args.model,
        thinking=args.thinking or args.thinking_level is not None,
        thinking_level=args.thinking_level,
        thinking_budget=args.thinking_budget,
        llm_constraints=args.llm_constraints,
        retry_feedback=args.retry_feedback,
        prompt_template=prompt_template(args),
        turn_memory=args.turn_memory,
        tools=args.tools,
        tool_call_cap=tool_call_cap(args.tools, args.tool_call_cap, f"--tool-call-cap {args.tool_call_cap}"),
    )


def has_claude_token() -> bool:
    """Whether the app has access to the Hosted model's provider: a token is set, in the environment or in .env.
    Read when asked, and not checked with the provider: a wrong one surfaces as an Aborted game (ADR 0013)."""
    return claude_token_from_environment() is not None


def player_for(settings: Settings, color: Color) -> "OllamaPlayer | ClaudePlayer":
    """The LLM player of one LLM side of a game, built when the game starts: Claude for a Hosted model, with the
    token CLAUDE_TOKEN gives, else an Ollama model's. A benchmark side's Thinking budget sets its time limit, from its
    model's speed (ADR 0007), and its Tool-call cap the player's (ADR 0011)."""
    side = settings.side(color)
    assert isinstance(side, LlmSide)
    if any(model.hosted and model.name == side.model for model in KNOWN_MODELS):
        # Imported late, so the tests never load the Anthropic client.
        from chessllm.llm.claude_player import ClaudePlayer

        return ClaudePlayer(side.model, side.think() is True, token=claude_token_from_environment())
    # Imported late, so the tests never load the Ollama client.
    from chessllm.llm.ollama_player import OllamaPlayer, time_limit_s

    budget = side.thinking_budget if isinstance(side, BenchmarkLlmSide) else None
    speed = next((model.tokens_per_s for model in KNOWN_MODELS if model.name == side.model), None)
    timeout_s = time_limit_s(budget, speed)
    cap = side_tool_call_cap(side)
    return OllamaPlayer(
        side.model, side.think(), timeout_s=timeout_s, sampling=settings.sampling, budget=budget, tool_call_cap=cap
    )


def system1_missing_models(base_url: str, models: list[str]) -> list[str]:
    """The models the System 1 server at base_url doesn't have, from the server itself; raises System1Unavailable if
    it can't say. Checked before the first game (Settings.check_served), as missing_models is for Ollama."""
    # Imported late, so the tests never load the HTTP client.
    from chessllm.system1 import http_model

    return http_model.missing_models(base_url, models)


def decision_model_for(side: System1Side) -> DecisionModel:
    """The decision model of a System 1 side, asking its server over HTTP; built when the game starts."""
    from chessllm.system1.http_model import SystemOneModel

    return SystemOneModel(side.base_url, side.model)


def missing_models(models: list[str]) -> list[str]:
    """The models Ollama doesn't have, from Ollama itself; raises OllamaUnavailable if it can't say. Every command
    checks its games' settings with it before the first game (Settings.check_installed), so a missing model stops
    the command rather than forfeiting every game."""
    # Imported late, so the tests never load the Ollama client.
    from chessllm.llm import ollama_models

    return ollama_models.missing_models(models)


def default_anchor(args: argparse.Namespace, side: AnchorSide) -> Anchor:
    """The Anchor of the side, from --dragon or --stockfish; the random mover from its seed."""
    if side.engine == "random":
        assert side.seed is not None, "Settings.check gives the random mover a seed"
        return RandomAnchor(side.seed)
    assert side.skill is not None, "Settings.check gives an engine Anchor a Skill"
    if side.engine == "stockfish":
        return StockfishAnchor(configured_stockfish_path(args.stockfish), side.skill)
    return DragonAnchor(configured_dragon_path(args.dragon), side.skill)


def default_move_model() -> MoveModel:
    from chessllm.engines.maia2_model import Maia2MoveModel

    return Maia2MoveModel()


def default_evaluator() -> Evaluator:
    from chessllm.engines.stockfish_evaluator import StockfishEvaluator

    return StockfishEvaluator()


class Analyser:
    """Analyses each finished game with whichever engines can start. Both are started (and checked) when the first
    game ends; an engine that can't start is warned about once and left out from then on."""

    def __init__(self, move_model: MoveModel | None, evaluator: Evaluator | None) -> None:
        self._move_model = move_model
        self._evaluator = evaluator
        self._checked = False

    def analyse(self, log: Path) -> None:
        if not self._checked:
            self._check_engines()
        if self._move_model is None and self._evaluator is None:
            return
        try:
            analyse_game(log, self._move_model, self._evaluator)
        except Exception as error:
            warn(f"{log.name} was not analysed: {error}.")

    def _check_engines(self) -> None:
        self._checked = True
        if self._move_model is not None:
            try:
                self._move_model.version
            except Maia2Unavailable as error:
                warn(f"No Move-quality estimate in this batch: Maia-2 can't start ({error}).")
                close(self._move_model)
                self._move_model = None
        if self._evaluator is not None:
            try:
                self._evaluator.version
            except StockfishUnavailable as error:
                warn(f"No centipawn loss or accuracy in this batch: Stockfish can't start ({error}).")
                close(self._evaluator)
                self._evaluator = None

    def close(self) -> None:
        close(self._move_model)
        close(self._evaluator)
        self._move_model = self._evaluator = None


INTERRUPTED_EXIT_CODE = 130


def first_rung(args: argparse.Namespace) -> AnchorSide:
    """The engine Anchor of the ladder in args at its first Skill, or at --skill."""
    return AnchorSide(engine=args.engine, skill=args.skill or FIRST_SKILL)


def model_under_test(
    settings: Settings,
    color: Color,
    system1: System1Side | None,
    player_for: Callable[[Settings, Color], LlmPlayer],
    decision_model_for: Callable[[System1Side], DecisionModel],
) -> tuple[dict[Color, LlmPlayer], dict[Color, DecisionModel]]:
    """The players and decision models (play_anchor_match's) of the Model player at color: the System 1 side's
    decision model (system1), else the LLM's player, built for these settings."""
    if system1 is None:
        return {color: player_for(settings, color)}, {}
    return {}, {color: decision_model_for(system1)}


def ladder_settings(
    args: argparse.Namespace, color: Color, anchor_side: AnchorSide, sampling_file: Path, system1: System1Side | None
) -> Settings:
    """The settings of a game of the ladder in args: the System 1 model's (system1) or else the LLM's, at color."""
    if system1 is None:
        return anchor_match_settings(args, color, anchor_side, sampling_file)
    return side_anchor_match_settings(system1, args, color, anchor_side, sampling_file)


def check_ladder(
    args: argparse.Namespace,
    anchor_for: Callable[[AnchorSide], Anchor],
    sampling_file: Path,
    missing_models: Callable[[list[str]], list[str]],
    system1: System1Side | None = None,
    system1_missing_models: Callable[[str, list[str]], list[str]] = system1_missing_models,
) -> str | None:
    """Why the ladder in args can't be played, or None: its settings, whether Ollama has its model (missing_models),
    or for a System 1 model (system1) whether its server answers and has it (system1_missing_models), then its
    engine, which is started once now, so a missing engine stops a batch before it starts, not once the ladder
    reaches it. A Hosted model needs the provider's token, not checked with the provider. Done before the analysis engines
    are built."""
    try:
        settings = ladder_settings(args, "white", first_rung(args), sampling_file, system1)
        settings.check_installed(missing_models)
        settings.check_hosted_access(has_claude_token())
        settings.check_served(system1_missing_models)
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return str(error)
    try:
        anchor_for(first_rung(args)).close()
    except AnchorUnavailable as error:
        return str(error)
    return None


def play_ladder(
    args: argparse.Namespace,
    player_for: Callable[[Settings, Color], LlmPlayer],
    anchor_for: Callable[[AnchorSide], Anchor],
    sampling_file: Path,
    analyser: Analyser,
    failed: str = "Anchor match batch stopped",
    system1: System1Side | None = None,
    decision_model_for: Callable[[System1Side], DecisionModel] = decision_model_for,
) -> int:
    """Play args.games Anchor matches of the Player configuration in args up and down the ladder, going on from its
    earlier games in args.games_dir, as chessllm.cli.anchor_batch describes; returns the exit code, after failed,
    e.g. "Anchor match batch stopped", when it stops. Its settings and engine are checked first, by check_ladder;
    each finished game is analysed by analyser, which the caller closes. For a System 1 model (system1) the ladder is
    its Player configuration's, and its games each get a fresh seed, logged, by decision_model_for(system1) built
    for each game."""
    settings = ladder_settings(args, "white", first_rung(args), sampling_file, system1)
    configuration = (
        system1_side_configuration(system1, settings.rules) if system1 else settings_configuration(settings, "white")
    )
    history = earlier_games(args.games_dir, configuration, args.engine)
    if history:
        print(f"Going on from {len(history)} earlier Anchor matches of this Player configuration.")
    model = "System 1 model" if system1 else "LLM"
    played: list[AnchoredGame] = []
    log: GameLog | None = None
    try:
        for number in range(1, args.games + 1):
            rung = args.skill if number == 1 and args.skill is not None else next_rung(history)
            llm_color = next_color(history)
            anchor_side = rung_side(rung, args.engine)
            settings = ladder_settings(args, llm_color, anchor_side, sampling_file, system1)
            try:
                anchor = anchor_for(anchor_side)
            except AnchorUnavailable as error:
                ladder_summary(played, history, model)
                return fail(failed, str(error))
            anchor_color = opponent(llm_color)
            try:
                players, decision_models = model_under_test(settings, llm_color, system1, player_for, decision_model_for)
                log = GameLog(args.games_dir, *settings.side_names())
                state = play_anchor_match(settings, players, {anchor_color: anchor}, log, decision_models=decision_models)
            except AnchorUnavailable as error:
                ladder_summary(played, history, model)
                return fail(failed, f"{error}. Game {number} was left unfinished in {log and log.path}")
            finally:
                anchor.close()
            if state.status == "aborted":
                ladder_summary(played, history, model)
                return fail(failed, aborted_message(number, state, log))
            assert state.result is not None  # played to its end
            game = AnchoredGame(rung, llm_color, score_for(state.result, llm_color))
            history.append(game)
            played.append(game)
            print(f"Game {number}/{args.games}: {rung_name(rung)}, {model} as {llm_color}: {outcome(game, state)}", flush=True)
            finished, log = log.path, None
            analyser.analyse(finished)
    except KeyboardInterrupt:
        unfinished = f"; game {len(played) + 1} was left unfinished in {log.path}" if log is not None else ""
        print(f"Interrupted after {len(played)} of {args.games} games{unfinished}.", file=sys.stderr)
        ladder_summary(played, history, model)
        return INTERRUPTED_EXIT_CODE
    ladder_summary(played, history, model)
    return 0


def aborted_message(number: int, state: GameState, log: GameLog) -> str:
    """Why a batch stops at its game number, which was aborted (ADR 0013): what the provider failed with, and that the
    game, kept in its log, counts for no Rating, Move-quality estimate or record."""
    return (
        f"game {number} was aborted: {state.abort_reason}. It counts for no Rating, Move-quality estimate or "
        f"record, and is kept in {log.path}; run the command again to go on"
    )


def outcome(game: AnchoredGame, state: GameState) -> str:
    word = {1.0: "win", 0.5: "draw", 0.0: "loss"}[game.score]
    return f"{word} ({state.result}, {state.end_reason})"


def ladder_summary(played: list[AnchoredGame], history: list[AnchoredGame], model: str = "LLM") -> None:
    """Print the batch's results, per rung, and where the ladder stands; model is the kind of the Model player."""
    counts = Counter(game.score for game in played)
    print(f"Batch: {len(played)} games, {counts[1.0]} wins, {counts[0.5]} draws, {counts[0.0]} losses.")
    for rung in sorted({game.rung for game in played}):
        at_rung = Counter(game.score for game in played if game.rung == rung)
        print(f"  {rung_name(rung)}: {at_rung[1.0]} W · {at_rung[0.5]} D · {at_rung[0.0]} L")
    print(f"Next game: {rung_name(next_rung(history))}, {model} as {next_color(history)}.")


def close(engine: object) -> None:
    """Stop an engine's process, if it has one and it started."""
    stop = getattr(engine, "close", None)
    if stop is not None:
        try:
            stop()
        except Exception:
            pass  # it never started


def warn(message: str) -> None:
    print(f"{message} `analyse-games` can analyse the games later.", file=sys.stderr)


def fail(command: str, message: str) -> int:
    """Report on stderr why the command stopped, after what it is, e.g. "Anchor match not played"; returns the exit
    code."""
    print(f"{command}: {message}", file=sys.stderr)
    return 1
