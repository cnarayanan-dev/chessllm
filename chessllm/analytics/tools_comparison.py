"""The Tools comparison: for each model that played with Tools, its Player configurations that differ only in their
Tools (and the Prompt template a side with Tools plays by default), one column per tool set, over every finished game
in the game logs (ADR 0011). What `tools-experiment` writes as Markdown.

A configuration with Tools is compared with the same configuration without them: its Tools and Tool-call cap left
out, and the Tools template's System prompt taken as the default one it stands in for. Each column has its record,
its Rating (fitted over every rated game in the logs, as the leaderboard's) and Move-quality estimate (ADR 0005), its
illegal moves and Legal-move streak (not applicable under Enforced decoding, ADR 0003), forfeits and Time used, and
for a tool set its tool use, from each attempt's tool_calls. Head to head is the LLM faceoffs of a tool set against
no Tools, the same model on both sides."""

import statistics
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from chessllm.analytics.analysis import analysis_path
from chessllm.analytics.leaderboard import (
    PlayerConfiguration,
    finished_game,
    forfeited,
    llm_configuration,
    logged_streak,
    rated_game,
    read_sides,
    side_attempts,
    side_outcome,
)
from chessllm.analytics.move_quality import (
    ConfigurationMoves,
    MoveQuality,
    move_quality,
    read_analysed_moves,
    read_validation,
)
from chessllm.analytics.rating import RatedGame, Rating, ratings
from chessllm.core.config import VALIDATION_FILE
from chessllm.core.types import COLORS, Color, score_for
from chessllm.engines.anchors import ANCHOR_RATINGS, AnchorRating
from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES, TOOLS_SYSTEM_PROMPT_FILE
from chessllm.game.records import ILLEGAL_RESULTS
from chessllm.game.sides import ENFORCED, TOOL_NAMES, BenchmarkLlmSide

TOOLS_PROMPT = TOOLS_SYSTEM_PROMPT_FILE.name


@dataclass
class ToolUse:
    """The Tool calls of a configuration's attempts, from each attempt's tool_calls."""

    attempts: int = 0
    tool_calls: int = 0
    attempts_using: Counter[str] = field(default_factory=Counter)  # by tool: the attempts that called it
    attempts_at_cap: int = 0  # the attempts that made as many calls as the Tool-call cap allows
    attempts_without_tool_call: int = 0
    tool_calls_as_text: int = 0  # the attempts whose tool phase ended with a tool call written as text

    def add(self, attempt: dict[str, Any], cap: int | None) -> None:
        calls = [str(call.get("tool")) for call in attempt.get("tool_calls") or []]
        self.attempts += 1
        self.tool_calls += len(calls)
        self.attempts_using.update(set(calls))
        self.attempts_at_cap += cap is not None and len(calls) >= cap
        self.attempts_without_tool_call += not calls
        self.tool_calls_as_text += attempt.get("tool_call_as_text") is True

    @property
    def calls_per_attempt(self) -> float | None:
        return self.tool_calls / self.attempts if self.attempts else None


@dataclass
class ToolSetColumn:
    """One Player configuration's results over its finished games: a column of its model's comparison."""

    configuration: PlayerConfiguration
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    forfeits: int = 0  # losses by Forfeit
    illegal_moves: int = 0  # illegal attempts, invalid and ambiguous ones included
    streaks: list[int] = field(default_factory=list)  # each game's Legal-move streak
    time_used_s: float = 0.0  # over the games that log their Time used
    timed_turns: int = 0  # the turns of those games
    tool_use: ToolUse = field(default_factory=ToolUse)
    analysed_moves: ConfigurationMoves = field(default_factory=ConfigurationMoves)
    rating: Rating | None = None
    move_quality: MoveQuality | None = None

    def add(self, events: list[dict[str, Any]], color: Color, stats: dict[str, Any]) -> None:
        """Add one finished game the configuration played at color, with each side's stats (read_sides)."""
        end = events[-1]
        outcome = side_outcome(end["result"], color)
        self.games += 1
        self.wins += outcome == "win"
        self.draws += outcome == "draw"
        self.losses += outcome == "loss"
        self.forfeits += forfeited(end, color)
        attempts = side_attempts(events, color)
        self.illegal_moves += sum(attempt.get("result") in ILLEGAL_RESULTS for attempt in attempts)
        streak = logged_streak(stats, color)
        if isinstance(streak, int):
            self.streaks.append(streak)
        time_used = (end.get("time_used") or {}).get(color)
        if isinstance(time_used, (int, float)):
            self.time_used_s += time_used
            self.timed_turns += len({attempt.get("ply") for attempt in attempts})
        if self.tools:
            for attempt in attempts:
                self.tool_use.add(attempt, self.tool_call_cap)

    @property
    def tools(self) -> tuple[str, ...]:
        return self.configuration.tools

    @property
    def tool_call_cap(self) -> int | None:
        return self.configuration.tool_call_cap

    @property
    def enforced(self) -> bool:
        return self.configuration.llm_constraints in ENFORCED

    @property
    def illegal_moves_per_game(self) -> float | None:
        """None under Enforced decoding, where no move can be illegal (ADR 0003)."""
        return None if self.enforced or not self.games else self.illegal_moves / self.games

    @property
    def median_legal_move_streak(self) -> float | None:
        """None under Enforced decoding, where the streak would be every move (ADR 0003)."""
        return None if self.enforced or not self.streaks else statistics.median(self.streaks)

    @property
    def time_used_per_move_s(self) -> float | None:
        return self.time_used_s / self.timed_turns if self.timed_turns else None

    def label(self) -> str:
        """The tool set: "no tools", "all four" or the tools joined by "+", with the Tool-call cap if not the
        default."""
        if not self.tools:
            return "no tools"
        tools = "all four" if set(self.tools) == set(TOOL_NAMES) else "+".join(self.tools)
        cap = self.tool_call_cap
        return tools if cap == BenchmarkLlmSide.tool_call_cap else f"{tools}, cap {cap}"


@dataclass
class HeadToHead:
    """The LLM faceoffs of a tool set against no Tools, from the tool set's side."""

    column: ToolSetColumn
    wins: int = 0
    draws: int = 0
    losses: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def points(self) -> float:
        return self.wins + self.draws / 2


@dataclass
class ModelComparison:
    """The tool sets one model played with under otherwise the same Player configuration, no Tools first."""

    model: str
    without_tools: PlayerConfiguration
    columns: list[ToolSetColumn] = field(default_factory=list)
    head_to_head: list[HeadToHead] = field(default_factory=list)  # one for each tool set, in the columns' order


def without_tools(configuration: PlayerConfiguration) -> PlayerConfiguration:
    """The configuration without its Tools: what a configuration with Tools is compared with."""
    prompt = configuration.prompt
    if configuration.tools and prompt == TOOLS_PROMPT:
        prompt = SYSTEM_PROMPT_FILES[configuration.llm_constraints].name
    return configuration.model_copy(update={"tools": (), "tool_call_cap": None, "prompt": prompt})


def tools_comparison(
    games_dir: Path,
    move_quality_validation: Path = VALIDATION_FILE,
    anchors: Mapping[str, AnchorRating] = ANCHOR_RATINGS,
) -> list[ModelComparison]:
    """A comparison for each configuration played with some Tools, over every finished game in games_dir; by
    model."""
    columns: dict[str, ToolSetColumn] = {}
    faceoffs: list[tuple[str, str, float]] = []  # (white's id, black's id, white's score)
    rated: list[RatedGame] = []
    for path in sorted(games_dir.glob("*.jsonl")) if games_dir.is_dir() else []:
        events = finished_game(path)
        if events is None:
            continue
        start, end = events[0], events[-1]
        sides, stats = read_sides(start, end)
        analysed = read_analysed_moves(analysis_path(path))
        ids: dict[Color, str] = {}
        for color in COLORS:
            side = sides[color]
            if side["player"] != "llm":
                continue
            configuration = llm_configuration(start, color, side)
            ids[color] = configuration.id()
            column = columns.setdefault(ids[color], ToolSetColumn(configuration))
            column.add(events, color, stats)
            if color in analysed:
                column.analysed_moves.add(*analysed[color])
        if len(ids) == 2:
            faceoffs.append((ids["white"], ids["black"], score_for(end["result"], "white")))
        rated.extend(rated_game(events))
    fitted = ratings(rated, anchors)
    validated_for = read_validation(move_quality_validation)
    for key, column in columns.items():
        column.rating = fitted.get(key)
        column.move_quality = move_quality(column.analysed_moves, validated_for)

    families: dict[str, list[ToolSetColumn]] = {}
    for column in columns.values():
        families.setdefault(without_tools(column.configuration).id(), []).append(column)
    comparisons = []
    for base_id, family in families.items():
        if not any(column.tools for column in family):
            continue
        family.sort(key=lambda column: (len(column.tools) != 0, -len(column.tools), column.tools, column.tool_call_cap))
        comparison = ModelComparison(family[0].configuration.model, without_tools(family[0].configuration), family)
        for column in family:
            if column.tools:
                comparison.head_to_head.append(head_to_head(column, base_id, faceoffs))
        comparisons.append(comparison)
    return sorted(comparisons, key=lambda comparison: (comparison.model, comparison.without_tools.id()))


def head_to_head(column: ToolSetColumn, base_id: str, faceoffs: list[tuple[str, str, float]]) -> HeadToHead:
    result = HeadToHead(column)
    key = column.configuration.id()
    for white, black, white_score in faceoffs:
        if {white, black} != {key, base_id}:
            continue
        score = white_score if white == key else 1 - white_score
        result.wins += score == 1
        result.draws += score == 0.5
        result.losses += score == 0
    return result


# --- the Markdown -------------------------------------------------------------------------------------------------


def markdown(comparisons: list[ModelComparison], day: date) -> str:
    """The comparison as the Markdown file tools-experiment writes."""
    out = [
        f"# Tools comparison, {day.isoformat()}",
        "",
        "Every finished game in the game logs of each Player configuration, one column per tool set; the "
        "configurations of a model differ only in their Tools and the Prompt template a side with Tools plays. "
        "Rating and Move-quality estimate on the chess.com scale, with their 95% intervals (ADR 0005); n/a: not "
        "applicable under Enforced decoding (ADR 0003).",
    ]
    if not comparisons:
        out += ["", "No games with Tools yet."]
    for comparison in comparisons:
        out += ["", f"## {comparison.model}", "", configuration_label(comparison.without_tools), ""]
        out += comparison_table(comparison)
        out += ["", "Head to head (LLM faceoffs, the model against itself, from the tool set's side):", ""]
        for match in comparison.head_to_head:
            if match.games:
                record = f"{match.wins} W · {match.draws} D · {match.losses} L"
                out.append(f"- {match.column.label()} vs no tools: {record}, {match.points:g} - "
                           f"{match.games - match.points:g} in {match.games} games")
            else:
                out.append(f"- {match.column.label()} vs no tools: no games")
    return "\n".join(out) + "\n"


def comparison_table(comparison: ModelComparison) -> list[str]:
    columns = comparison.columns

    def row(name: str, cell: Any) -> str:
        return "| " + " | ".join([name, *(cell(column) for column in columns)]) + " |"

    def tool_cell(cell: Any) -> Any:
        return lambda column: cell(column) if column.tools else "-"

    def share(count: Any, tool: str | None = None) -> Any:
        """The attempts count picks out, of the column's; "-" without Tools, or without the tool if given."""

        def cell(column: ToolSetColumn) -> str:
            if not column.tools or (tool is not None and tool not in column.tools):
                return "-"
            return counted(count(column.tool_use), column.tool_use.attempts)

        return cell

    rows = [
        "| | " + " | ".join(column.label() for column in columns) + " |",
        "|---" * (len(columns) + 1) + "|",
        row("games", lambda column: str(column.games)),
        row("W · D · L", lambda column: f"{column.wins} · {column.draws} · {column.losses}"),
        row("Rating", lambda column: rating_text(column.rating)),
        row("Move-quality estimate", lambda column: quality_text(column.move_quality)),
        row("illegal moves per game", lambda column: number(column.illegal_moves_per_game, column)),
        row("median Legal-move streak", lambda column: number(column.median_legal_move_streak, column)),
        row("forfeits", lambda column: counted(column.forfeits, column.games)),
        row("Time used per move", lambda column: seconds(column.time_used_per_move_s)),
        row("tool calls per attempt", tool_cell(lambda column: number(column.tool_use.calls_per_attempt))),
    ]
    for tool in TOOL_NAMES:
        rows.append(row(f"attempts using {tool}", share(lambda use, tool=tool: use.attempts_using[tool], tool)))
    rows += [
        row("attempts at the Tool-call cap", share(lambda use: use.attempts_at_cap)),
        row("attempts with no tool call", share(lambda use: use.attempts_without_tool_call)),
        row("tool calls written as text", share(lambda use: use.tool_calls_as_text)),
    ]
    return rows


def configuration_label(configuration: PlayerConfiguration) -> str:
    """The settings a model's columns share, apart from the model."""
    thinking = "thinking" if configuration.thinking else "no thinking"
    if configuration.thinking_level is not None:
        thinking = f"thinking {configuration.thinking_level}"
    if configuration.thinking_budget is not None:
        thinking += f", budget {configuration.thinking_budget}"
    parts = [
        configuration.llm_constraints, thinking, configuration.rules, f"{configuration.retry_feedback} feedback",
        f"{configuration.max_retries + 1} attempts per turn",
    ]
    if configuration.turn_memory is not None:
        parts.append(configuration.turn_memory)
    if configuration.position is not None:
        parts.append(f"{configuration.position} position")
    if configuration.prompt != SYSTEM_PROMPT_FILES[configuration.llm_constraints].name:
        parts.append(f"prompt {configuration.prompt}")
    if configuration.sampling:
        parts.append(", ".join(f"{name} {value}" for name, value in sorted(configuration.sampling.items())))
    return " / ".join(parts)


def rating_text(rating: Rating | None) -> str:
    if rating is None:
        return "-"
    if rating.estimate is None:
        return f"< {rating.high}" if rating.high is not None else f"> {rating.low}"
    return f"{rating.estimate} [{rating.low}, {rating.high}]"


def quality_text(quality: MoveQuality | None) -> str:
    if quality is None:
        return "-"
    low = quality.low if quality.low is not None else "open"
    high = quality.high if quality.high is not None else "open"
    estimate = quality.estimate if quality.estimate is not None else "at the grid's edge"
    return f"{estimate} [{low}, {high}]"


def number(value: float | None, column: ToolSetColumn | None = None) -> str:
    if column is not None and column.enforced:
        return "n/a"
    return "-" if value is None else f"{value:.2f}".rstrip("0").rstrip(".")


def counted(part: int, whole: int) -> str:
    return f"{part} ({100 * part / whole:.0f}%)" if whole else str(part)


def seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f} s"
