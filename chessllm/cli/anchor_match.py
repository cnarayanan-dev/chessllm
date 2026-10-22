"""Play one Anchor match from the command line: a Player configuration against Dragon at a Skill and colour.

    uv run anchor-match --model llama3:8b --skill 1 --color white --dragon ~/dragon/dragon-osx

The game runs unattended through the same game session as the app's Modes, and writes its log and PGN to the
games directory. The Dragon executable comes from --dragon, else the CHESSLLM_DRAGON environment variable."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from chessllm.cli.common import add_configuration_arguments, anchor_match_settings, default_anchor, fail
from chessllm.cli.common import player_for as default_player_for
from chessllm.engines.anchors import Anchor
from chessllm.core.config import SAMPLING_FILE
from chessllm.core.types import COLORS, Color, opponent
from chessllm.exceptions import AnchorUnavailable, InvalidSamplingConfig, InvalidSettings
from chessllm.game.runner import play_anchor_match
from chessllm.game.session import Settings
from chessllm.game.sides import AnchorSide
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog

FAILED = "Anchor match not played"


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anchor-match",
        description="Play one game of an LLM against Komodo Dragon 1, unattended, and log it.",
    )
    add_configuration_arguments(parser)
    parser.add_argument("--skill", type=int, default=1, help="Dragon's Skill level, 1-7 (default 1)")
    parser.add_argument("--color", choices=COLORS, default="white", help="the LLM's colour (default white)")
    return parser


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
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return fail(FAILED, str(error))
    anchor_side = AnchorSide(engine=args.engine, skill=args.skill)
    if anchor_for is None:
        anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
    try:
        anchor = anchor_for(anchor_side)  # started before the game, so a missing Dragon leaves no log behind
    except AnchorUnavailable as error:
        return fail(FAILED, str(error))
    anchor_color = opponent(llm_color)
    try:
        players = {llm_color: player_for(settings, llm_color)}
        log = GameLog(args.games_dir, *settings.side_names())
        state = play_anchor_match(settings, players, {anchor_color: anchor}, log)
    except AnchorUnavailable as error:
        return fail(FAILED, f"{error}. The game was left unfinished in {log.path}")
    finally:
        anchor.close()
    print(f"{state.result} by {state.end_reason}: {log.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
