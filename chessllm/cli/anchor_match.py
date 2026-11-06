"""Play one Anchor match from the command line: a Model player against Dragon at a Skill and colour. The Model player
is an LLM with a Player configuration, or a System 1 model (ADR 0012).

    uv run anchor-match --model llama3:8b --skill 1 --color white --dragon ~/dragon/dragon-osx
    uv run anchor-match --model llama3:8b --engine random
    uv run anchor-match --system1-model d3:2b --system1-url http://localhost:11434 --choice-temperature 1
    uv run anchor-match --system1-model d3:2b --system1-template system1-position-only@299e4459

The game runs unattended through the same game session as the app's Modes, and writes its log and PGN to the
games directory. The Dragon executable comes from --dragon, else the CHESSLLM_DRAGON environment variable. The random
legal mover (--engine random) needs no engine; it plays from a fresh seed, logged with its side, and --seed with a
logged seed replays its moves. A System 1 model's server is the one at --system1-url, which must have the model before
the game starts; its own seed, --system1-seed, replays the order of its options and its draws."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from chessllm.cli.common import (
    add_configuration_arguments,
    add_system1_arguments,
    add_system1_seed_argument,
    anchor_match_settings,
    default_anchor,
    fail,
    model_under_test,
    side_anchor_match_settings,
    system1_side,
)
from chessllm.cli.common import (
    decision_model_for as default_decision_model_for,
    missing_models as default_missing_models,
    player_for as default_player_for,
    system1_missing_models as default_system1_missing_models,
)
from chessllm.engines.anchors import Anchor, new_seed
from chessllm.core.config import SAMPLING_FILE
from chessllm.core.types import COLORS, Color, opponent
from chessllm.exceptions import AnchorUnavailable, InvalidSamplingConfig, InvalidSettings
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.sides import AnchorSide, System1Side
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog
from chessllm.system1.port import DecisionModel

FAILED = "Anchor match not played"


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anchor-match",
        description="Play one game of an LLM, or a System 1 model, against an Anchor, Komodo Dragon 1 by default, "
        "unattended, and log it.",
    )
    add_configuration_arguments(parser)
    add_system1_arguments(parser)
    add_system1_seed_argument(parser)
    parser.add_argument("--skill", type=int, default=1, help="Dragon's Skill level, 1-7 (default 1)")
    parser.add_argument("--color", choices=COLORS, default="white", help="the model's colour (default white)")
    parser.add_argument("--seed", type=int, help="the random mover's seed, e.g. a logged one to replay (default: fresh)")
    return parser


def main(
    argv: list[str] | None = None,
    player_for: Callable[[Settings, Color], LlmPlayer] = default_player_for,
    anchor_for: Callable[[AnchorSide], Anchor] | None = None,
    sampling_file: Path = SAMPLING_FILE,
    missing_models: Callable[[list[str]], list[str]] = default_missing_models,
    system1_missing_models: Callable[[str, list[str]], list[str]] = default_system1_missing_models,
    decision_model_for: Callable[[System1Side], DecisionModel] = default_decision_model_for,
    prompt_library: PromptLibrary | None = None,
) -> int:
    """Run the command; returns its exit code. anchor_for builds the Anchor, by default Dragon from --dragon;
    missing_models says which models Ollama doesn't have, by default Ollama itself; system1_missing_models(base_url,
    models) says which models a System 1 server doesn't have, by default the server itself, and decision_model_for
    builds the decision model of a System 1 side, by default over HTTP; prompt_library holds the Prompt templates
    --system1-template picks from, by default the project's."""
    args = parser().parse_args(argv)
    llm_color: Color = args.color
    if args.engine == "random":
        anchor_side = AnchorSide.random_mover(args.seed if args.seed is not None else new_seed())
    else:
        anchor_side = AnchorSide(engine=args.engine, skill=args.skill)
    try:
        system1 = system1_side(args, library=prompt_library)
        if system1 is None:
            settings = anchor_match_settings(args, llm_color, anchor_side, sampling_file)
        else:
            settings = side_anchor_match_settings(system1, args, llm_color, anchor_side, sampling_file)
        settings.check_installed(missing_models)
        settings.check_served(system1_missing_models)
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return fail(FAILED, str(error))
    if anchor_for is None:
        anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
    try:
        anchor = anchor_for(anchor_side)  # started before the game, so a missing Dragon leaves no log behind
    except AnchorUnavailable as error:
        return fail(FAILED, str(error))
    anchor_color = opponent(llm_color)
    try:
        players, decision_models = model_under_test(settings, llm_color, system1, player_for, decision_model_for)
        log = GameLog(args.games_dir, *settings.side_names())
        state = play_anchor_match(
            settings, players, {anchor_color: anchor}, log, decision_models=decision_models, seed=args.system1_seed
        )
    except AnchorUnavailable as error:
        return fail(FAILED, f"{error}. The game was left unfinished in {log.path}")
    finally:
        anchor.close()
    print(f"{state.result} by {state.end_reason}: {log.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
