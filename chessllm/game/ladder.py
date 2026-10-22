"""The Skill ladder of an Anchor match batch (ADR 0005): the Skill and colour of the next game, from the results so
far, and those results read back from the game logs (how chessllm.cli.anchor_batch describes it)."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from chessllm.analytics.leaderboard import PlayerConfiguration, finished_game, llm_configuration
from chessllm.engines.anchors import DRAGON_SKILLS
from chessllm.core.types import COLORS, Color, opponent, score_for

FIRST_SKILL = DRAGON_SKILLS[0]


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
    return opponent(history[-1].llm_color) if history else "white"


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
            llm, anchor = start[llm_color], start[opponent(llm_color)]
            if (
                llm["player"] == "llm"
                and anchor.get("engine") == engine
                and llm_configuration(start, llm_color, llm) == configuration
            ):
                history.append(AnchoredGame(anchor["skill"], llm_color, score_for(end["result"], llm_color)))
    return history
