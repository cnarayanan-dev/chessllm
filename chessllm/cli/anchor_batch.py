"""Play a batch of Anchor matches from the command line: a Player configuration against the Anchors, unattended, up
and down the ladder (ADR 0005, ADR 0011).

    uv run anchor-batch --model llama3:8b --games 30 --dragon ~/dragon/dragon-osx

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
--skill overrides the first game's rung only (0 for the random mover); the ladder goes on from that game. An unfinished game (one interrupted) is
not part of the history, and the new games simply join the pool the Rating is fitted from (order doesn't matter).

After each game, it is analysed into its analysis file (chessllm.analytics.analysis) unless --no-analysis, as the app and
`analyse-games` do: the Move-quality estimate with Maia-2 and centipawn loss and accuracy with
Stockfish. Each engine is started when the first game ends; one that can't start is left out for the rest of the
batch, with a warning, and with neither the games aren't analysed. `analyse-games` can catch up."""

import argparse
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from chessllm.analytics.leaderboard import settings_configuration
from chessllm.cli.common import (
    Analyser,
    add_analysis_argument,
    add_configuration_arguments,
    anchor_match_settings,
    default_anchor,
    default_evaluator,
    default_move_model,
    fail,
    warn_of_turn_memory,
)
from chessllm.cli.common import player_for as default_player_for
from chessllm.engines.anchors import Anchor
from chessllm.engines.evaluator import Evaluator
from chessllm.core.config import SAMPLING_FILE
from chessllm.core.types import Color, opponent, score_for
from chessllm.engines.move_model import MoveModel
from chessllm.exceptions import AnchorUnavailable, InvalidSamplingConfig, InvalidSettings
from chessllm.game.ladder import (
    FIRST_SKILL,
    AnchoredGame,
    earlier_games,
    next_color,
    next_rung,
    rung_name,
    rung_side,
)
from chessllm.game.records import GameState
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import AnchorSide
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog

DEFAULT_BUDGET = 30
INTERRUPTED_EXIT_CODE = 130
FAILED = "Anchor match batch stopped"


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anchor-batch",
        description="Play a batch of Anchor matches of an LLM, unattended, up and down a ladder from the random legal "
        "mover to Komodo Dragon 1 at Skill 7, stepping up after scoring over 50% and down after under 50%, and log "
        "every game.",
    )
    add_configuration_arguments(parser)
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
) -> int:
    """Run the command; returns its exit code. anchor_for builds each game's Anchor, by default the random mover or
    Dragon from --dragon, and Dragon once more before the first game, to check that it starts;
    move_model_for and evaluator_for the engines the games are analysed with, by default Maia-2 and Stockfish
    (None leaves one out)."""
    args = parser().parse_args(argv)
    if args.games < 1:
        return fail(FAILED, f"the budget must be at least one game, not {args.games}")
    if args.engine == "random":
        return fail(FAILED, "the random mover is the ladder's bottom rung, not its engine: choose dragon or stockfish")
    engine_side = AnchorSide(engine=args.engine, skill=args.skill or FIRST_SKILL)
    try:
        settings = anchor_match_settings(args, "white", engine_side, sampling_file)
    except (InvalidSettings, InvalidSamplingConfig) as error:
        return fail(FAILED, str(error))
    warn_of_turn_memory(args)
    if anchor_for is None:
        anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
    try:
        anchor_for(engine_side).close()  # a missing engine stops the batch now, not once the ladder reaches it
    except AnchorUnavailable as error:
        return fail(FAILED, str(error))
    history = earlier_games(args.games_dir, settings_configuration(settings, "white"), args.engine)
    if history:
        print(f"Going on from {len(history)} earlier Anchor matches of this Player configuration.")
    analyser = Analyser(None, None) if args.no_analysis else Analyser(move_model_for(), evaluator_for())
    played: list[AnchoredGame] = []
    log: GameLog | None = None
    try:
        for number in range(1, args.games + 1):
            rung = args.skill if number == 1 and args.skill is not None else next_rung(history)
            llm_color = next_color(history)
            anchor_side = rung_side(rung, args.engine)
            settings = anchor_match_settings(args, llm_color, anchor_side, sampling_file)
            try:
                anchor = anchor_for(anchor_side)
            except AnchorUnavailable as error:
                summary(played, history)
                return fail(FAILED, str(error))
            anchor_color = opponent(llm_color)
            try:
                players = {llm_color: player_for(settings, llm_color)}
                log = GameLog(args.games_dir, *settings.side_names())
                state = play_anchor_match(settings, players, {anchor_color: anchor}, log)
            except AnchorUnavailable as error:
                summary(played, history)
                return fail(FAILED, f"{error}. Game {number} was left unfinished in {log and log.path}")
            finally:
                anchor.close()
            assert state.result is not None  # played to its end
            game = AnchoredGame(rung, llm_color, score_for(state.result, llm_color))
            history.append(game)
            played.append(game)
            print(f"Game {number}/{args.games}: {rung_name(rung)}, LLM as {llm_color}: {outcome(game, state)}", flush=True)
            finished, log = log.path, None
            analyser.analyse(finished)
    except KeyboardInterrupt:
        unfinished = f"; game {len(played) + 1} was left unfinished in {log.path}" if log is not None else ""
        print(f"Interrupted after {len(played)} of {args.games} games{unfinished}.", file=sys.stderr)
        summary(played, history)
        return INTERRUPTED_EXIT_CODE
    finally:
        analyser.close()
    summary(played, history)
    return 0


def outcome(game: AnchoredGame, state: GameState) -> str:
    word = {1.0: "win", 0.5: "draw", 0.0: "loss"}[game.score]
    return f"{word} ({state.result}, {state.end_reason})"


def summary(played: list[AnchoredGame], history: list[AnchoredGame]) -> None:
    """Print the batch's results, per rung, and where the ladder stands."""
    counts = Counter(game.score for game in played)
    print(f"Batch: {len(played)} games, {counts[1.0]} wins, {counts[0.5]} draws, {counts[0.0]} losses.")
    for rung in sorted({game.rung for game in played}):
        at_rung = Counter(game.score for game in played if game.rung == rung)
        print(f"  {rung_name(rung)}: {at_rung[1.0]} W · {at_rung[0.5]} D · {at_rung[0.0]} L")
    print(f"Next game: {rung_name(next_rung(history))}, LLM as {next_color(history)}.")


if __name__ == "__main__":
    sys.exit(main())
