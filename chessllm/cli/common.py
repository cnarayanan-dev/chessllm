"""What the commands share: the LLM's Player configuration arguments, the players, Anchors and engines a game is
played and analysed with, and how a command reports that it failed. The commands import each other's code from here,
never from one another."""

import argparse
import secrets
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast, get_args

from chessllm.analytics.analysis import analyse_game
from chessllm.core.config import DRAGON_PATH_VARIABLE, GAMES_DIR, STOCKFISH_PATH_VARIABLE
from chessllm.engines.anchors import (
    RANDOM_MOVER_SKILL,
    Anchor,
    DragonAnchor,
    RandomAnchor,
    StockfishAnchor,
    configured_dragon_path,
    configured_stockfish_path,
)
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.exceptions import InvalidSettings, Maia2Unavailable, StockfishUnavailable
from chessllm.core.types import Color, RulesKey
from chessllm.game.settings import Settings
from chessllm.game.sides import (
    DEFAULT_TOOL_CALL_CAP,
    TOOLS,
    AnchorSide,
    BenchmarkLlmSide,
    LadderEngine,
    LlmConstraints,
    LlmSide,
    PromptTemplate,
    RetryFeedback,
    Tool,
    TurnMemory,
)
from chessllm.game.llm_turn.prompt import PositionTemplate, default_template
from chessllm.llm.models import CONTEXT_TOKENS, LLM_MODELS, load_sampling

if TYPE_CHECKING:
    from chessllm.llm.ollama_player import OllamaPlayer


def add_thinking_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=LlmSide().thinking)


def add_prompt_arguments(parser: argparse.ArgumentParser) -> None:
    """The LLM constraints, Retry feedback and Prompt template of the Player configuration."""
    defaults = LlmSide()
    parser.add_argument("--llm-constraints", choices=get_args(LlmConstraints), default=defaults.llm_constraints)
    parser.add_argument("--retry-feedback", choices=get_args(RetryFeedback), default=defaults.retry_feedback)
    parser.add_argument(
        "--prompt-template",
        choices=get_args(PositionTemplate),
        default="default",
        help="the default Prompt template: default (the PGN and FEN), or described (also the last move, every "
        "piece's square and check). Under --turn-memory chat_moves leave it at default, which then means the Moves "
        "template (only the opponent's last move); described is refused there, as it shows the position",
    )
    parser.add_argument(
        "--turn-memory",
        choices=get_args(TurnMemory),
        default=defaults.turn_memory,
        help="whether the LLM's turns share one conversation: fresh (the default: each turn starts anew), "
        "chat_position (one conversation for the game, each turn adding its message), or chat_moves (one "
        "conversation, each turn adding only the opponent's last move)",
    )


def warn_of_turn_memory(args: argparse.Namespace) -> None:
    """Warn, before any game, that a conversation isn't trimmed to the model's context yet (#106): a long game can
    outgrow it, and Ollama then cuts it silently. The attempts that may not have fit log context_may_be_cut."""
    if args.turn_memory != "fresh":
        print(
            f"Warning: under Turn memory {args.turn_memory} a conversation is not yet trimmed to the "
            f"{CONTEXT_TOKENS:,}-token context (#106). In a long game Ollama may cut its oldest messages silently; "
            "each attempt that may not have fit logs context_may_be_cut: true.",
            file=sys.stderr,
        )


def tool_set(value: str) -> frozenset[Tool]:
    """A list of Tools as the commands take it, comma-separated, e.g. "board,legal_moves". Only a flag given bare
    means all four: an empty list is refused, like an unknown tool."""
    names = [name.strip() for name in value.split(",")]
    if not any(names):
        raise argparse.ArgumentTypeError(f"no tools in {value!r}: give the flag bare for all four")
    if unknown := sorted(set(names) - set(TOOLS)):
        given = ", ".join(repr(name) for name in unknown)
        raise argparse.ArgumentTypeError(f"no tool {given}: the tools are {', '.join(TOOLS)}")
    return frozenset(cast(list[Tool], names))


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
    """The Prompt template --prompt-template asks for: None for default, the side's default read when each game
    starts, which under chat_moves is Moves (side_template). Described is refused under chat_moves when the game's
    settings are checked, as it shows the position."""
    kind: PositionTemplate = args.prompt_template
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
    parser.add_argument(
        "--tools",
        nargs="?",
        type=tool_set,
        const=frozenset(TOOLS),
        default=frozenset(),
        metavar="LIST",
        help=f"the Tools the LLM may call during an attempt, comma-separated, of {', '.join(TOOLS)}; bare for all "
        "four (needs a model that calls tools, thinking on, Free or Blind enforced, Standard rules)",
    )
    parser.add_argument(
        "--tool-call-cap",
        type=int,
        metavar="N",
        help=f"the most Tool calls per attempt (default {DEFAULT_TOOL_CALL_CAP}; needs --tools)",
    )
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
        choices=get_args(LadderEngine),  # the random mover is Skill 0
        default="dragon",
        help="the Anchor at Skill 1-7: Dragon, or Stockfish as a rough stand-in where Dragon can't be had (default "
        "dragon). Skill 0 is the random legal mover, whatever the engine",
    )
    parser.add_argument("--dragon", help=f"the Dragon executable (default: ${DRAGON_PATH_VARIABLE})")
    parser.add_argument(
        "--stockfish", help=f"the Stockfish executable (default: ${STOCKFISH_PATH_VARIABLE}, else on the PATH)"
    )
    add_games_dir_argument(parser)


def anchor_match_settings(
    args: argparse.Namespace, llm_color: Color, skill: int, sampling_file: Path, seed: int | None = None
) -> Settings:
    """The settings of an Anchor match of the LLM in args at llm_color against the engine at skill, or at Skill 0
    against the random mover with the seed, a new one each game when None. Raises InvalidSettings with the reason
    when they can't be played, and InvalidSamplingConfig for a broken config."""
    llm = BenchmarkLlmSide(
        model=args.model,
        thinking=args.thinking or args.thinking_level is not None,
        thinking_level=args.thinking_level,
        thinking_budget=args.thinking_budget,
        llm_constraints=args.llm_constraints,
        retry_feedback=args.retry_feedback,
        prompt_template=prompt_template(args),
        turn_memory=args.turn_memory,
        tools=args.tools,
        tool_call_cap=DEFAULT_TOOL_CALL_CAP if args.tool_call_cap is None else args.tool_call_cap,
    )
    if args.tool_call_cap is not None and not args.tools:
        raise InvalidSettings(f"--tool-call-cap {args.tool_call_cap} needs --tools: there are no tools to cap")
    anchor_side = anchor_side_at(args.engine, skill, seed)
    white, black = (llm, anchor_side) if llm_color == "white" else (anchor_side, llm)
    settings = Settings(
        "anchor_match",
        white,
        black,
        sampling=load_sampling(sampling_file),
        rules=args.rules,
        max_attempts=args.max_attempts,
        legal_counterpart=not args.no_legal_counterpart,
    )
    settings.check(LLM_MODELS)
    return settings


def anchor_side_at(engine: LadderEngine, skill: int, seed: int | None = None) -> AnchorSide:
    """The Anchor at a Skill of the engine's ladder: the engine at Skill 1-7, and the random mover at Skill 0
    (RANDOM_MOVER_SKILL), with the seed, or a new one drawn for the game, which game_start logs so the game can be
    replayed, and the engine's ladder it is the bottom rung of."""
    if skill != RANDOM_MOVER_SKILL:
        return AnchorSide(engine=engine, skill=skill)
    seed = secrets.randbits(32) if seed is None else seed
    return AnchorSide(engine="random", skill=RANDOM_MOVER_SKILL, seed=seed, ladder=engine)


def player_for(settings: Settings, color: Color) -> "OllamaPlayer":
    """The LLM player of one LLM side of a game, built when the game starts. A benchmark side's Thinking budget
    sets its time limit, from its model's speed (ADR 0007)."""
    # Imported late, so the tests never load the Ollama client.
    from chessllm.llm.ollama_player import OllamaPlayer, time_limit_s

    side = settings.side(color)
    assert isinstance(side, LlmSide)
    budget = side.thinking_budget if isinstance(side, BenchmarkLlmSide) else None
    speed = next((model.tokens_per_s for model in LLM_MODELS if model.name == side.model), None)
    timeout_s = time_limit_s(budget, speed)
    return OllamaPlayer(side.model, side.think(), timeout_s=timeout_s, sampling=settings.sampling, budget=budget)


def default_anchor(args: argparse.Namespace, side: AnchorSide) -> Anchor:
    """The Anchor of the side: the random mover from its seed, or the engine from --dragon or --stockfish."""
    if side.engine == "random":
        assert side.seed is not None, "the random mover plays from a seed"
        return RandomAnchor(side.seed)
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
