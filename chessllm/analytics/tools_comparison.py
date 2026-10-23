"""The tools comparison (ADR 0011): a model's Player configurations that differ only in their Tools, side by side,
over every finished game of each in the game logs, not only one run's.

Each configuration's games, W/D/L, Forfeits, Rating and Move-quality estimate are its leaderboard entry's, the Rating
fitted over every configuration jointly (chessllm.analytics.leaderboard). The rest is read from its games here: its
illegal moves and Legal-move streaks as game_end's stats have them, None under Enforced decoding (ADR 0003), its Time
used per legal move, its tool use over the attempts game_end's tool_use counts (an attempt at the Tool-call cap made
as many tool calls as its game's cap allowed), and, for a configuration with tools, its LLM faceoffs against the one
without, when there is one."""

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from chessllm.analytics.leaderboard import (
    LeaderboardEntry,
    PlayerConfiguration,
    Tally,
    finished_game,
    leaderboard,
    llm_configuration,
    read_sides,
    side_outcome,
)
from chessllm.core.config import VALIDATION_FILE
from chessllm.core.types import Color, opponent
from chessllm.engines.anchors import ANCHOR_RATINGS, AnchorRating
from chessllm.game.sides import ENFORCED


@dataclass
class ToolUseTally:
    """How a configuration with Tools used them, over its attempts that could use them."""

    attempts: int = 0
    tool_calls: int = 0
    attempts_calling: Counter[str] = field(default_factory=Counter)  # by tool: attempts that called it at least once
    attempts_at_cap: int = 0
    attempts_without_tool_calls: int = 0
    tool_calls_as_text: int = 0  # attempts whose tool phase ended in a tool call written as text

    def add(self, attempt: dict[str, Any], cap: int | None) -> None:
        """Count the attempt as game_end's tool_use does (SideStats.count_tool_use): one that answered, or that failed
        after a tool call or one written as text; one that failed before either couldn't use the tools."""
        calls = attempt.get("tool_calls") or []
        if attempt.get("raw_reply") is None and not calls and attempt.get("tool_call_as_text") is not True:
            return
        self.attempts += 1
        self.tool_calls += len(calls)
        self.attempts_calling.update({str(call.get("tool")) for call in calls})
        self.attempts_at_cap += cap is not None and len(calls) >= cap
        self.attempts_without_tool_calls += not calls
        self.tool_calls_as_text += attempt.get("tool_call_as_text") is True


@dataclass
class Column:
    """One configuration of the comparison: its leaderboard entry and what its games add to it."""

    entry: LeaderboardEntry
    illegal_moves: int = 0
    streaks: list[int] = field(default_factory=list)
    time_used_s: float = 0.0
    timed_moves: int = 0  # legal moves of the games that log their Time used
    tool_use: ToolUseTally = field(default_factory=ToolUseTally)
    head_to_head: Tally = field(default_factory=Tally)  # its faceoffs against the configuration without tools

    @property
    def configuration(self) -> PlayerConfiguration:
        return self.entry.configuration

    @property
    def enforced(self) -> bool:
        return self.configuration.llm_constraints in ENFORCED

    def add(self, events: list[dict[str, Any]], color: Color, stats: dict[str, Any]) -> None:
        """Add the side at color of a finished game, its events and its stats as game_end logs them."""
        start, end = events[0], events[-1]
        illegal = stats.get("illegal_moves")
        if isinstance(illegal, dict):
            self.illegal_moves += sum(illegal.values())
        if isinstance(streak := stats.get("legal_move_streak"), int):
            self.streaks.append(streak)
        # A version 1 attempt has no colour: it is the one LLM's, at llm_color.
        attempts = [
            event
            for event in events
            if event["type"] == "llm_attempt" and event.get("color", start.get("llm_color")) == color
        ]
        time_used = (end.get("time_used") or {}).get(color)
        if isinstance(time_used, (int, float)):
            self.time_used_s += time_used
            self.timed_moves += sum(attempt.get("result") == "legal" for attempt in attempts)
        if self.configuration.tools is not None:
            cap = start[color].get("tool_call_cap")
            for attempt in attempts:
                self.tool_use.add(attempt, cap)


def comparison(
    games_dir: Path,
    belongs: Callable[[PlayerConfiguration], bool],
    move_quality_validation: Path = VALIDATION_FILE,
    anchors: Mapping[str, AnchorRating] = ANCHOR_RATINGS,
) -> list[Column]:
    """The columns of the configurations that belong to the comparison, among every one with a finished game in
    games_dir: the one without tools first, then those with the most tools."""
    board = leaderboard(games_dir, move_quality_validation, anchors)
    columns = {entry.id: Column(entry) for entry in board.configurations if belongs(entry.configuration)}
    no_tools = next((key for key, column in columns.items() if column.configuration.tools is None), None)
    for path in sorted(games_dir.glob("*.jsonl")):
        events = finished_game(path)
        if events is None:
            continue
        start, end = events[0], events[-1]
        sides, stats = read_sides(start, end)
        llms = {color: side for color, side in sides.items() if side["player"] == "llm"}
        ids = {color: llm_configuration(start, color, side).id() for color, side in llms.items()}
        for color, key in ids.items():
            if key in columns:
                columns[key].add(events, color, stats.get(color) or {})
        if no_tools is None:
            continue  # no configuration without tools: no head to head
        for color, key in ids.items():
            if key in columns and key != no_tools and ids.get(opponent(color)) == no_tools:
                columns[key].head_to_head.add(side_outcome(end["result"], color))
    return sorted(columns.values(), key=column_order)


def column_order(column: Column) -> tuple[bool, int, tuple[str, ...], int]:
    tools = column.configuration.tools or ()
    return bool(tools), -len(tools), tools, column.configuration.tool_call_cap or 0
