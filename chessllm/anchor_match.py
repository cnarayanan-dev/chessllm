"""Play one Anchor match from the command line: a Player configuration against Dragon at a Skill and colour.

    uv run python -m chessllm.anchor_match --model llama3:8b --skill 1 --color white --dragon ~/dragon/dragon-osx

The game runs unattended through the same game session as the app's Modes, and writes its log and PGN to the
games directory. The Dragon executable comes from --dragon, else the CHESSLLM_DRAGON environment variable."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_args

from chessllm.anchors import (
    DRAGON_PATH_VARIABLE,
    STOCKFISH_PATH_VARIABLE,
    Anchor,
    AnchorUnavailable,
    DragonAnchor,
    StockfishAnchor,
    configured_dragon_path,
    configured_stockfish_path,
)
from chessllm.game import (
    COLORS,
    AnchorEngine,
    AnchorSide,
    BenchmarkLlmSide,
    Color,
    GameSession,
    LlmSide,
    Rules,
    Settings,
)
from chessllm.game_log import GAMES_DIR, GameLog
from chessllm.models import LLM_MODELS, SAMPLING_FILE, load_sampling
from chessllm.players import LlmPlayer
from chessllm.prompt import LlmConstraints, PositionFormat, RetryFeedback


def add_configuration_arguments(parser: argparse.ArgumentParser) -> None:
    """The LLM's Player configuration, and where Dragon and the logs are: shared with chessllm.anchor_batch."""
    defaults = LlmSide()
    parser.add_argument("--model", default=defaults.model, help=f"the Ollama model (default {defaults.model})")
    parser.add_argument("--thinking", action=argparse.BooleanOptionalAction, default=defaults.thinking)
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
    parser.add_argument("--llm-constraints", choices=get_args(LlmConstraints), default=defaults.llm_constraints)
    parser.add_argument("--retry-feedback", choices=get_args(RetryFeedback), default=defaults.retry_feedback)
    parser.add_argument(
        "--position",
        choices=get_args(PositionFormat),
        default=defaults.position,
        help="how each turn gives the position: fen, or described (also the pieces, last move and check)",
    )
    # Part of the Player configuration. Chaos rules only with the Stockfish Anchor, which copes with chaos positions.
    parser.add_argument("--rules", choices=get_args(Rules), default=Settings.rules)
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
        help="the Anchor: Dragon, or Stockfish as a rough stand-in where Dragon can't be had (default dragon)",
    )
    parser.add_argument("--dragon", help=f"the Dragon executable (default: ${DRAGON_PATH_VARIABLE})")
    parser.add_argument(
        "--stockfish", help=f"the Stockfish executable (default: ${STOCKFISH_PATH_VARIABLE}, else on the PATH)"
    )
    parser.add_argument("--games-dir", type=Path, default=GAMES_DIR, help=f"where logs go (default {GAMES_DIR})")


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m chessllm.anchor_match",
        description="Play one game of an LLM against Komodo Dragon 1, unattended, and log it.",
    )
    add_configuration_arguments(parser)
    parser.add_argument("--skill", type=int, default=1, help="Dragon's Skill level, 1-7 (default 1)")
    parser.add_argument("--color", choices=COLORS, default="white", help="the LLM's colour (default white)")
    return parser


def anchor_match_settings(args: argparse.Namespace, llm_color: Color, skill: int, sampling_file: Path) -> Settings:
    """The settings of an Anchor match of the LLM in args at llm_color against Dragon at skill. Raises ValueError
    with the reason when they can't be played."""
    llm = BenchmarkLlmSide(
        model=args.model,
        thinking=args.thinking or args.thinking_level is not None,
        thinking_level=args.thinking_level,
        thinking_budget=args.thinking_budget,
        llm_constraints=args.llm_constraints,
        retry_feedback=args.retry_feedback,
        position=args.position,
    )
    anchor_side = AnchorSide(engine=args.engine, skill=skill)
    white, black = (llm, anchor_side) if llm_color == "white" else (anchor_side, llm)
    settings = Settings(
        "anchor_match",
        white,
        black,
        sampling=load_sampling(sampling_file),
        rules=args.rules,
        max_attempts=args.max_attempts,
    )
    problem = settings.problem(LLM_MODELS)
    if problem is not None:
        raise ValueError(problem)
    return settings


def default_anchor(args: argparse.Namespace, side: AnchorSide) -> Anchor:
    """The Anchor of the side, from --dragon or --stockfish."""
    if side.engine == "stockfish":
        return StockfishAnchor(configured_stockfish_path(args.stockfish), side.skill)
    return DragonAnchor(configured_dragon_path(args.dragon), side.skill)


def default_player_for(settings: Settings, color: Color) -> LlmPlayer:
    from chessllm.__main__ import player_for  # imported late, so the tests never load the Ollama client

    return player_for(settings, color)


def play_anchor_match(
    settings: Settings, players: dict[Color, LlmPlayer], anchors: dict[Color, Anchor], log: GameLog
) -> dict[str, Any]:
    """Play the game to its end, each turn by the side to move: the LLM's turn or the Anchor's. Returns its last
    state."""
    game = GameSession(players, settings, log, anchors)
    while (state := game.state())["status"] == "playing":
        if state["turn"] in anchors:
            game.play_anchor_turn()
        else:
            game.play_llm_turn()
    return state


def main(
    argv: list[str] | None = None,
    player_for: Callable[[Settings, Color], LlmPlayer] = default_player_for,
    anchor_for: Callable[[AnchorSide], Anchor] | None = None,
    sampling_file: Path = SAMPLING_FILE,
) -> int:
    """Run the command; returns its exit code. anchor_for builds the Anchor, by default Dragon from --dragon."""
    args = parser().parse_args(argv)
    llm_color: Color = args.color
    try:
        settings = anchor_match_settings(args, llm_color, args.skill, sampling_file)
    except ValueError as error:
        return fail(str(error))
    anchor_side = AnchorSide(engine=args.engine, skill=args.skill)
    if anchor_for is None:
        anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
    try:
        anchor = anchor_for(anchor_side)  # started before the game, so a missing Dragon leaves no log behind
    except AnchorUnavailable as error:
        return fail(str(error))
    anchor_color: Color = "black" if llm_color == "white" else "white"
    try:
        players = {llm_color: player_for(settings, llm_color)}
        log = GameLog(args.games_dir, *settings.side_names())
        state = play_anchor_match(settings, players, {anchor_color: anchor}, log)
    except AnchorUnavailable as error:
        return fail(f"{error}. The game was left unfinished in {log.path}")
    finally:
        anchor.close()
    print(f"{state['result']} by {state['end_reason']}: {log.path}")
    return 0


def fail(message: str) -> int:
    print(f"Anchor match not played: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
