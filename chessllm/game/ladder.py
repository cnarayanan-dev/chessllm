"""The ladder of an Anchor match batch (ADR 0005, ADR 0011): the rung and colour of the next game, from the results so
far, and those results read back from the game logs (how chessllm.cli.anchor_batch describes it).

A rung is an Anchor: rung 0 is the random legal mover, the bottom of the ladder, and rung s from 1 up is the batch's
engine (Dragon, or Stockfish standing in for it) at Skill s."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from chessllm.analytics.leaderboard import PlayerConfiguration, finished_game, llm_configuration
from chessllm.engines.anchors import DRAGON_SKILLS, new_seed
from chessllm.core.types import COLORS, Color, opponent, score_for
from chessllm.game.modes import mode_named
from chessllm.game.sides import AnchorEngine, AnchorSide

RANDOM_MOVER_RUNG = 0
FIRST_SKILL = DRAGON_SKILLS[0]
TOP_RUNG = DRAGON_SKILLS[-1]


@dataclass(frozen=True)
class AnchoredGame:
    """One finished Anchor match, as the ladder sees it: the Anchor's rung, the LLM's colour and its score."""

    rung: int  # 0 for the random mover, else the engine's Skill
    llm_color: Color
    score: float  # 1 for a win, 0.5 for a draw, 0 for a loss (a Forfeit included)


def rung_side(rung: int, engine: AnchorEngine, seed_for: Callable[[], int] = new_seed) -> AnchorSide:
    """The Anchor side of a game at the rung: the random mover, from a fresh seed, or the engine at that Skill."""
    return AnchorSide.random_mover(seed_for()) if rung == RANDOM_MOVER_RUNG else AnchorSide(engine=engine, skill=rung)


def rung_name(rung: int) -> str:
    """The rung as the batch prints it: "Random mover" or e.g. "Skill 3"."""
    return "Random mover" if rung == RANDOM_MOVER_RUNG else f"Skill {rung}"


def next_rung(history: list[AnchoredGame]) -> int:
    """The rung of the next game after the games so far, oldest first: judged on the last pair of games at the
    current rung, once there is a whole pair since the ladder last moved. A first game is against the random mover."""
    if not history:
        return RANDOM_MOVER_RUNG
    rung = history[-1].rung
    at_rung = 0
    for game in reversed(history):
        if game.rung != rung:
            break
        at_rung += 1
    if at_rung % 2:
        return rung
    score = sum(game.score for game in history[-2:])
    if score > 1:
        return min(rung + 1, TOP_RUNG)
    if score < 1:
        return max(rung - 1, RANDOM_MOVER_RUNG)
    return rung


def next_color(history: list[AnchoredGame]) -> Color:
    """The LLM's colour in the next game: the other colour from its last game, White to start."""
    return opponent(history[-1].llm_color) if history else "white"


def logged_rung(anchor: dict[str, Any], engine: str) -> int | None:
    """The rung of an Anchor side as game_start logs it, on the ladder of the engine; None for another engine's."""
    if anchor.get("engine") == "random":
        return RANDOM_MOVER_RUNG
    return anchor["skill"] if anchor.get("engine") == engine else None


def earlier_games(
    games_dir: Path, configuration: PlayerConfiguration, engine: str = "dragon"
) -> list[AnchoredGame]:
    """The finished Anchor matches of the configuration in games_dir on the engine's ladder (Dragon by default), the
    random mover's included, oldest first: by game_start's started_at, which is to the microsecond (older logs have
    whole seconds, and their ties go by file name)."""
    logs = []
    for path in sorted(games_dir.glob("*.jsonl")) if games_dir.is_dir() else []:
        events = finished_game(path)
        if events is not None and (mode := mode_named(events[0].get("mode"))) is not None and mode.against_an_anchor:
            logs.append((datetime.fromisoformat(events[0]["started_at"]), path.name, events))
    history = []
    for *_, events in sorted(logs, key=lambda log: log[:2]):
        start, end = events[0], events[-1]
        llm_color: Color
        for llm_color in COLORS:
            llm, anchor = start[llm_color], start[opponent(llm_color)]
            if (
                llm["player"] == "llm"
                and (rung := logged_rung(anchor, engine)) is not None
                and llm_configuration(start, llm_color, llm) == configuration
            ):
                history.append(AnchoredGame(rung, llm_color, score_for(end["result"], llm_color)))
    return history
