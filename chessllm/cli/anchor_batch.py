"""Play a batch of Anchor matches from the command line: a Player configuration against Dragon, unattended, up and
down the Skill ladder (ADR 0005).

    uv run anchor-batch --model llama3:8b --games 30 --dragon ~/dragon/dragon-osx

The ladder. Colours alternate, game by game. Dragon's Skill is judged after every second game at it, one game as
White and one as Black, so White's advantage cancels out: scoring over 50% in that pair (2 or 1.5 of 2 points)
steps up a Skill level, under 50% steps down, and exactly 50% stays, within Skill 1-7. A pair of games is the
window because it is the smallest one fair to both colours, and it lets a 30-game batch climb from Skill 1 to 7 and
still spend most of its games near the level where the LLM scores 50%, where results say most about its Rating.

Extending. The ladder is a function of the results so far and nothing else, so it reads them from the game logs:
before the first game, the batch reads every finished Anchor match of the same Player configuration in the games
directory, oldest first, and goes on from there, at the Skill and colour that history gives, as if the earlier
games had been the start of this batch. A configuration without earlier games starts at Skill 1 as White. --skill
overrides the first game's Skill only; the ladder goes on from that game. An unfinished game (one interrupted) is
not part of the history, and the new games simply join the pool the Rating is fitted from (order doesn't matter).

After each game, it is analysed into its analysis file (chessllm.analytics.analysis) unless --no-analysis, as the app and
`analyse-games` do: the Move-quality estimate with Maia-2 and centipawn loss and accuracy with
Stockfish. Each engine is started when the first game ends; one that can't start is left out for the rest of the
batch, with a warning, and with neither the games aren't analysed. `analyse-games` can catch up."""

import argparse
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from chessllm.analytics.analysis import analyse_game
from chessllm.engines.evaluator import Evaluator
from chessllm.cli.anchor_match import (
    add_configuration_arguments,
    anchor_match_settings,
    default_anchor,
    default_player_for,
    play_anchor_match,
)
from chessllm.engines.anchors import DRAGON_SKILLS, Anchor, AnchorUnavailable
from chessllm.game.session import COLORS, AnchorSide, Color, Settings
from chessllm.logs.game_log import GameLog
from chessllm.analytics.leaderboard import PlayerConfiguration, finished_game, llm_configuration, settings_configuration
from chessllm.engines.maia2_model import Maia2Unavailable
from chessllm.llm.models import SAMPLING_FILE
from chessllm.engines.move_model import MoveModel
from chessllm.llm.players import LlmPlayer
from chessllm.engines.stockfish_evaluator import StockfishUnavailable

DEFAULT_BUDGET = 30
FIRST_SKILL = DRAGON_SKILLS[0]
INTERRUPTED_EXIT_CODE = 130


@dataclass(frozen=True)
class AnchoredGame:
    """One finished Anchor match, as the ladder sees it: Dragon's Skill, the LLM's colour and its score."""

    skill: int
    llm_color: Color
    score: float  # 1 for a win, 0.5 for a draw, 0 for a loss (a Forfeit included)


def next_skill(history: list[AnchoredGame]) -> int:
    """The Skill of the next game after the games so far, oldest first: judged on the last pair of games at the
    current Skill, once there is a whole pair since the ladder last moved."""
    if not history:
        return FIRST_SKILL
    skill = history[-1].skill
    at_skill = 0
    for game in reversed(history):
        if game.skill != skill:
            break
        at_skill += 1
    if at_skill % 2:
        return skill
    score = sum(game.score for game in history[-2:])
    if score > 1:
        return min(skill + 1, DRAGON_SKILLS[-1])
    if score < 1:
        return max(skill - 1, FIRST_SKILL)
    return skill


def next_color(history: list[AnchoredGame]) -> Color:
    """The LLM's colour in the next game: the other colour from its last game, White to start."""
    return "black" if history and history[-1].llm_color == "white" else "white"


def llm_score(result: str, llm_color: Color) -> float:
    if result == "1/2-1/2":
        return 0.5
    return 1.0 if result == ("1-0" if llm_color == "white" else "0-1") else 0.0


def earlier_games(
    games_dir: Path, configuration: PlayerConfiguration, engine: str = "dragon"
) -> list[AnchoredGame]:
    """The finished Anchor matches against the engine (Dragon by default) of the configuration in games_dir, oldest first: by game_start's
    started_at, which is to the microsecond (older logs have whole seconds, and their ties go by file name)."""
    logs = []
    for path in sorted(games_dir.glob("*.jsonl")) if games_dir.is_dir() else []:
        events = finished_game(path)
        if events is not None and events[0].get("mode") == "anchor_match":
            logs.append((datetime.fromisoformat(events[0]["started_at"]), path.name, events))
    history = []
    for *_, events in sorted(logs, key=lambda log: log[:2]):
        start, end = events[0], events[-1]
        llm_color: Color
        for llm_color in COLORS:
            llm, anchor = start[llm_color], start["black" if llm_color == "white" else "white"]
            if (
                llm["player"] == "llm"
                and anchor.get("engine") == engine
                and llm_configuration(start, llm_color, llm) == configuration
            ):
                history.append(AnchoredGame(anchor["skill"], llm_color, llm_score(end["result"], llm_color)))
    return history


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anchor-batch",
        description="Play a batch of Anchor matches of an LLM against Komodo Dragon 1, unattended, stepping Dragon's "
        "Skill up after scoring over 50% against it and down after under 50%, and log every game.",
    )
    add_configuration_arguments(parser)
    parser.add_argument("--games", type=int, default=DEFAULT_BUDGET, help=f"the budget (default {DEFAULT_BUDGET})")
    parser.add_argument(
        "--skill",
        type=int,
        help="the first game's Skill, 1-7 (default: where the configuration's earlier games left the ladder, else 1)",
    )
    parser.add_argument(
        "--no-analysis", action="store_true", help="don't analyse each game (with Maia-2 and Stockfish)"
    )
    return parser


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


def main(
    argv: list[str] | None = None,
    player_for: Callable[[Settings, Color], LlmPlayer] = default_player_for,
    anchor_for: Callable[[AnchorSide], Anchor] | None = None,
    sampling_file: Path = SAMPLING_FILE,
    move_model_for: Callable[[], MoveModel | None] = default_move_model,
    evaluator_for: Callable[[], Evaluator | None] = default_evaluator,
) -> int:
    """Run the command; returns its exit code. anchor_for builds each game's Anchor, by default Dragon from --dragon;
    move_model_for and evaluator_for the engines the games are analysed with, by default Maia-2 and Stockfish
    (None leaves one out)."""
    args = parser().parse_args(argv)
    if args.games < 1:
        return fail(f"the budget must be at least one game, not {args.games}")
    try:
        settings = anchor_match_settings(args, "white", args.skill or FIRST_SKILL, sampling_file)
    except ValueError as error:
        return fail(str(error))
    if anchor_for is None:
        anchor_for = lambda side: default_anchor(args, side)  # noqa: E731
    history = earlier_games(args.games_dir, settings_configuration(settings, "white"), args.engine)
    if history:
        print(f"Going on from {len(history)} earlier Anchor matches of this Player configuration.")
    analyser = Analyser(None, None) if args.no_analysis else Analyser(move_model_for(), evaluator_for())
    played: list[AnchoredGame] = []
    log: GameLog | None = None
    try:
        for number in range(1, args.games + 1):
            skill = args.skill if number == 1 and args.skill is not None else next_skill(history)
            llm_color = next_color(history)
            settings = anchor_match_settings(args, llm_color, skill, sampling_file)
            try:
                anchor = anchor_for(AnchorSide(engine=args.engine, skill=skill))
            except AnchorUnavailable as error:
                summary(played, history)
                return fail(str(error))
            anchor_color: Color = "black" if llm_color == "white" else "white"
            try:
                players = {llm_color: player_for(settings, llm_color)}
                log = GameLog(args.games_dir, *settings.side_names())
                state = play_anchor_match(settings, players, {anchor_color: anchor}, log)
            except AnchorUnavailable as error:
                summary(played, history)
                return fail(f"{error}. Game {number} was left unfinished in {log and log.path}")
            finally:
                anchor.close()
            game = AnchoredGame(skill, llm_color, llm_score(state["result"], llm_color))
            history.append(game)
            played.append(game)
            print(f"Game {number}/{args.games}: Skill {skill}, LLM as {llm_color}: {outcome(game, state)}", flush=True)
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


def outcome(game: AnchoredGame, state: dict[str, Any]) -> str:
    word = {1.0: "win", 0.5: "draw", 0.0: "loss"}[game.score]
    return f"{word} ({state['result']}, {state['end_reason']})"


def summary(played: list[AnchoredGame], history: list[AnchoredGame]) -> None:
    """Print the batch's results, per Skill, and where the ladder stands."""
    counts = Counter(game.score for game in played)
    print(f"Batch: {len(played)} games, {counts[1.0]} wins, {counts[0.5]} draws, {counts[0.0]} losses.")
    for skill in sorted({game.skill for game in played}):
        at_skill = Counter(game.score for game in played if game.skill == skill)
        print(f"  Skill {skill}: {at_skill[1.0]} W · {at_skill[0.5]} D · {at_skill[0.0]} L")
    print(f"Next game: Skill {next_skill(history)}, LLM as {next_color(history)}.")


def fail(message: str) -> int:
    print(f"Anchor match batch stopped: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
