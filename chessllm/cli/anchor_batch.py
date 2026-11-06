"""Play a batch of Anchor matches from the command line: a Player configuration against the Anchors, unattended, up
and down the ladder (ADR 0005, ADR 0011).

    uv run anchor-batch --model llama3:8b --games 30 --dragon ~/dragon/dragon-osx
    uv run anchor-batch --system1-model d3:2b --system1-url http://localhost:11434 --games 20

The ladder. Its bottom rung is the random legal mover, which plays each game from a fresh seed, logged with its side;
above it are Dragon's Skill levels 1-7. Colours alternate, game by game. A rung is judged after every second game at
it, one game as White and one as Black, so White's advantage cancels out: scoring over 50% in that pair (2 or 1.5 of
2 points) steps up a rung, under 50% steps down, and exactly 50% stays, from the random mover to Skill 7. A pair of
games is the window because it is the smallest one fair to both colours, and it lets a 30-game batch climb from the
random mover to Skill 7 and still spend most of its games near the level where the LLM scores 50%, where results say
most about its Rating. The engine is started once before the first game, so a missing Dragon stops the batch before
it starts, not when the ladder first reaches it.

Extending. The ladder is a function of the results so far and nothing else, so it reads them from the game logs:
before the first game, the batch reads every finished Anchor match of the same Player configuration in the games
directory, oldest first, and goes on from there, at the rung and colour that history gives, as if the earlier
games had been the start of this batch. A configuration without earlier games starts at the random mover as White.

A System 1 model (ADR 0012) plays the same ladder: --system1-model, --system1-url, --choice-temperature and
--system1-template give the Player configuration under test in place of the LLM's, whose own settings are then
refused. Its earlier games are those of the same model, Choice temperature and Prompt template (by text), so a change
to either starts a ladder of its own. Before the first game the batch checks that the server answers and has the
model. Each game draws a fresh seed for the order of the model's options and its draws, logged in the game; the
batch has no seed of its own to fix (--system1-seed is for the single game of anchor-match).
--skill overrides the first game's rung only (0 for the random mover); the ladder goes on from that game. An unfinished game (one interrupted) is
not part of the history, and the new games simply join the pool the Rating is fitted from (order doesn't matter).

After each game, it is analysed into its analysis file (chessllm.analytics.analysis) unless --no-analysis, as the app and
`analyse-games` do: the Move-quality estimate with Maia-2 and centipawn loss and accuracy with
Stockfish. Each engine is started when the first game ends; one that can't start is left out for the rest of the
batch, with a warning, and with neither the games aren't analysed. `analyse-games` can catch up."""

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from chessllm.cli.common import (
    Analyser,
    add_analysis_argument,
    add_configuration_arguments,
    add_system1_arguments,
    check_ladder,
    default_anchor,
    default_evaluator,
    default_move_model,
    fail,
    play_ladder,
    system1_side,
)
from chessllm.cli.common import (
    decision_model_for as default_decision_model_for,
    missing_models as default_missing_models,
    player_for as default_player_for,
    system1_missing_models as default_system1_missing_models,
)
from chessllm.engines.anchors import Anchor
from chessllm.engines.evaluator import Evaluator
from chessllm.core.config import SAMPLING_FILE
from chessllm.core.types import Color
from chessllm.exceptions import InvalidSamplingConfig, InvalidSettings
from chessllm.engines.move_model import MoveModel
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.settings import Settings
from chessllm.game.sides import AnchorSide, System1Side
from chessllm.llm.players import LlmPlayer
from chessllm.system1.port import DecisionModel

DEFAULT_BUDGET = 30
FAILED = "Anchor match batch stopped"


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anchor-batch",
        description="Play a batch of Anchor matches of an LLM, or a System 1 model, unattended, up and down a ladder from "
        "the random legal mover to Komodo Dragon 1 at Skill 7, stepping up after scoring over 50% and down after under 50%, and log "
        "every game.",
    )
    add_configuration_arguments(parser)
    add_system1_arguments(parser)
    parser.add_argument("--games", type=int, default=DEFAULT_BUDGET, help=f"the budget (default {DEFAULT_BUDGET})")
    parser.add_argument(
        "--skill",
        type=int,
        help="the first game's rung: 0 for the random mover, else a Skill, 1-7 (default: where the configuration's "
        "earlier games left the ladder, else the random mover)",
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
    missing_models: Callable[[list[str]], list[str]] = default_missing_models,
    system1_missing_models: Callable[[str, list[str]], list[str]] = default_system1_missing_models,
    decision_model_for: Callable[[System1Side], DecisionModel] = default_decision_model_for,
    prompt_library: PromptLibrary | None = None,
) -> int:
    """Run the command; returns its exit code. anchor_for builds each game's Anchor, by default the random mover or
    Dragon from --dragon, and Dragon once more before the first game, to check that it starts;
    move_model_for and evaluator_for the engines the games are analysed with, by default Maia-2 and Stockfish
    (None leaves one out); missing_models which models Ollama doesn't have, by default Ollama itself;
    system1_missing_models(base_url, models) which models a System 1 server doesn't have, and decision_model_for the
    decision model of a System 1 side, each game's, by default over HTTP; prompt_library the Prompt templates
    --system1-template picks from, by default the project's."""
    args = parser().parse_args(argv)
    if args.games < 1:
        return fail(FAILED, f"the budget must be at least one game, not {args.games}")
    if args.engine == "random":
        return fail(FAILED, "the random mover is the ladder's bottom rung, not its engine: choose dragon or stockfish")
    if anchor_for is None:
        anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
    try:
        system1 = system1_side(args, library=prompt_library)
    except (InvalidSettings, InvalidSamplingConfig) as refused:
        return fail(FAILED, str(refused))
    error = check_ladder(args, anchor_for, sampling_file, missing_models, system1, system1_missing_models)
    if error is not None:
        return fail(FAILED, error)
    analyser = Analyser(None, None) if args.no_analysis else Analyser(move_model_for(), evaluator_for())
    try:
        return play_ladder(args, player_for, anchor_for, sampling_file, analyser, FAILED, system1, decision_model_for)
    finally:
        analyser.close()


if __name__ == "__main__":
    sys.exit(main())
