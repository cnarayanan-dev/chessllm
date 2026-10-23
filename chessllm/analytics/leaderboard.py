"""The leaderboard: every finished game in the game logs, its results grouped by Player configuration.

Read from the logs on every request, so there is no stored state to keep in step with them. Both log versions are
read (ADR 0004); a missing `rules` means Standard rules."""

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from chessllm.analytics.analysis import analysis_path
from chessllm.engines.anchors import ANCHOR_RATINGS, AnchorRating, anchor_name
from chessllm.core.config import VALIDATION_FILE
from chessllm.core.types import COLORS, Color, RulesKey, Sampling, opponent, score_for
from chessllm.game.modes import mode_named
from chessllm.game.rules import rules_named
from chessllm.game.settings import Settings
from chessllm.game.sides import ENFORCED, BenchmarkLlmSide, LlmConstraints, RetryFeedback, Tool, TurnMemory
from chessllm.analytics.move_quality import (
    ConfigurationMoves,
    MoveQuality,
    move_quality,
    read_analysed_moves,
    read_validation,
)
from chessllm.game.llm_turn.prompt import prompt_file, side_template
from chessllm.analytics.rating import RatedGame, Rating, ratings


# How each turn gave the position: fen (the PGN and FEN), described (also where every piece stands) or moves (only
# the opponent's last move, under Turn memory chat_moves, the LLM keeping track of the board itself).
PositionFormat = Literal["fen", "described", "moves"]


def prompt_settings(file_name: str, template_id: str | None) -> tuple[str, PositionFormat | None]:
    """The prompt and position of a Player configuration, which games are still grouped by until they are grouped by
    their Prompt template's text: a default template's System prompt file name, with described for the Described
    default and moves for the Moves default; any other template's ID."""
    if not file_name:
        return template_id or "", None
    positions: tuple[PositionFormat, ...] = ("described", "moves")
    for position in positions:
        if template_id is not None and template_id.startswith(position):
            return file_name, position
    return file_name, None


class PlayerConfiguration(BaseModel):
    """An LLM together with every setting it plays a game with. Games are pooled only if all of these match."""

    model: str
    thinking: bool
    llm_constraints: LlmConstraints
    rules: RulesKey
    retry_feedback: RetryFeedback
    max_retries: int  # per turn, before the LLM forfeits
    sampling: Sampling  # from the config file; empty means the model's defaults
    prompt: str  # the system prompt's file name, e.g. "system.txt", or the ID of a Prompt template that isn't a default
    # How each turn gave the position; None is the default, fen. Left out when it is fen, so the API's configurations
    # and their ids stay as they were before the setting existed.
    position: PositionFormat | None = Field(None, exclude_if=lambda position: position in (None, "fen"))
    # Whether its turns shared one conversation; None is the default, fresh, which it is given as. Left out when it
    # is fresh, like position, so the configurations from before the setting keep their ids.
    turn_memory: TurnMemory | None = Field(None, exclude_if=lambda memory: memory is None)

    @field_validator("turn_memory")
    @classmethod
    def _fresh_is_none(cls, turn_memory: TurnMemory | None) -> TurnMemory | None:
        return None if turn_memory == "fresh" else turn_memory
    # The Thinking level, None for plain thinking on or off. Set only by the benchmark's commands, so it is kept out
    # of the API's schema and output, which stay as they were (#67); it still gives the configuration its own id.
    thinking_level: SkipJsonSchema[str | None] = Field(None, exclude=True)
    # The Thinking budget in tokens, None for none: benchmark only like the level, and kept out of the API the same way.
    thinking_budget: SkipJsonSchema[int | None] = Field(None, exclude=True)
    # The Tools it could call, sorted, and their Tool-call cap; None for none, and then no cap. Benchmark only and
    # kept out of the API like the Thinking level (ADR 0011).
    tools: SkipJsonSchema[tuple[Tool, ...] | None] = Field(None, exclude=True)
    tool_call_cap: SkipJsonSchema[int | None] = Field(None, exclude=True)

    @field_validator("tools")
    @classmethod
    def _sorted_or_none(cls, tools: tuple[Tool, ...] | None) -> tuple[Tool, ...] | None:
        return tuple(sorted(tools)) if tools else None

    @model_validator(mode="after")
    def _no_cap_without_tools(self) -> Self:
        if self.tools is None:
            self.tool_call_cap = None
        return self

    def id(self) -> str:
        """A short fingerprint of the settings, the same for the same settings on every request. The default
        position and Turn memory, no Thinking level, no Thinking budget and no Tools are left out, so configurations
        from before those settings keep their id."""
        settings = self.model_dump()  # without the default position, the Thinking level, budget or Tools
        if self.thinking_level is not None:
            settings["thinking_level"] = self.thinking_level
        if self.thinking_budget is not None:
            settings["thinking_budget"] = self.thinking_budget
        if self.tools is not None:
            settings["tools"], settings["tool_call_cap"] = list(self.tools), self.tool_call_cap
        canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


class OpponentResults(BaseModel):
    opponent: str  # the id of the other Player configuration, "human", or an Anchor's name, e.g. "anchor:dragon:3"
    games: int
    wins: int
    draws: int
    losses: int


class LeaderboardEntry(BaseModel):
    """One Player configuration's results over all its finished games. A game it played on both sides of an LLM
    faceoff counts once for each side."""

    id: str
    configuration: PlayerConfiguration
    games: int
    wins: int
    draws: int
    losses: int
    score: float  # (wins + draws / 2) / games, from 0 to 1
    forfeits: int  # games lost by Forfeit, among the losses
    legal_moves: int  # legal moves played
    attempts: int | None  # every attempt, legal or not; None under Enforced decoding (ADR 0003)
    average_legal_move_streak: float | None  # None under Enforced decoding (ADR 0003)
    opponents: list[OpponentResults]  # sorted by opponent
    # Stockfish diagnostics over every analysed legal move, never an Elo (ADR 0005); None without analysed moves.
    average_centipawn_loss: float | None
    average_accuracy: float | None  # lichess's move accuracy, 0-100
    # Fitted only from Anchor matches and LLM faceoffs under Standard rules, a Forfeit a loss; None with no path to an
    # Anchor, so always None under Chaos rules or with Play LLM games only (ADR 0005)
    rating: Rating | None
    # Pooled from the analysis files of all its games, Play LLM included; None without an analysed move (ADR 0005)
    move_quality: MoveQuality | None


class Leaderboard(BaseModel):
    configurations: list[LeaderboardEntry]


# A game's result from one side, in words.
Outcome = Literal["win", "draw", "loss"]


def side_outcome(result: str, color: Color) -> Outcome:
    """The game's result from the side at color: a win, a loss, or, for anything else that ends a game, a draw."""
    score = score_for(result, color)
    return "win" if score == 1 else "loss" if score == 0 else "draw"


@dataclass
class Tally:
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0

    def add(self, outcome: str) -> None:
        self.games += 1
        self.wins += outcome == "win"
        self.draws += outcome == "draw"
        self.losses += outcome == "loss"


@dataclass
class ConfigurationTally:
    configuration: PlayerConfiguration
    results: Tally = field(default_factory=Tally)
    forfeits: int = 0
    legal_moves: int = 0
    attempts: int = 0
    streaks: list[int] = field(default_factory=list)
    opponents: dict[str, Tally] = field(default_factory=lambda: defaultdict(Tally))
    centipawn_losses: list[float] = field(default_factory=list)
    accuracies: list[float] = field(default_factory=list)

    def entry(self, rating: Rating | None, move_quality: MoveQuality | None) -> LeaderboardEntry:
        results = self.results
        enforced = self.configuration.llm_constraints in ENFORCED
        return LeaderboardEntry(
            id=self.configuration.id(),
            configuration=self.configuration,
            games=results.games,
            wins=results.wins,
            draws=results.draws,
            losses=results.losses,
            score=(results.wins + results.draws / 2) / results.games,
            forfeits=self.forfeits,
            legal_moves=self.legal_moves,
            attempts=None if enforced else self.attempts,
            average_legal_move_streak=(
                sum(self.streaks) / len(self.streaks) if self.streaks and not enforced else None
            ),
            opponents=[
                OpponentResults(opponent=opponent, **vars(tally)) for opponent, tally in sorted(self.opponents.items())
            ],
            average_centipawn_loss=mean(self.centipawn_losses),
            average_accuracy=mean(self.accuracies),
            rating=rating,
            move_quality=move_quality,
        )


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def leaderboard(
    games_dir: Path,
    move_quality_validation: Path = VALIDATION_FILE,
    anchors: Mapping[str, AnchorRating] = ANCHOR_RATINGS,
) -> Leaderboard:
    tallies: dict[str, ConfigurationTally] = {}
    analysed: dict[str, ConfigurationMoves] = defaultdict(ConfigurationMoves)
    rated: list[RatedGame] = []
    for path in sorted(games_dir.glob("*.jsonl")):
        events = finished_game(path)
        if events is not None:
            add_game(tallies, events)
            add_analysed_moves(analysed, path, events)
            add_centipawn_loss_and_accuracy(tallies, events, analysis_path(path))
            rated.extend(rated_game(events))
    validated_for = read_validation(move_quality_validation)
    fitted = ratings(rated, anchors)
    entries = [
        tally.entry(fitted.get(key), move_quality(analysed[key], validated_for)) for key, tally in tallies.items()
    ]
    return Leaderboard(configurations=sorted(entries, key=lambda entry: (entry.configuration.model, entry.id)))


def finished_game(path: Path) -> list[dict[str, Any]] | None:
    """The events of a finished game's log, or None for anything else in the games directory: a game still being
    played or abandoned (no game_end), or a file that isn't a game log."""
    try:
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not events or not all(isinstance(event, dict) for event in events):
        return None
    if events[0].get("type") != "game_start" or events[-1].get("type") != "game_end":
        return None
    return events


def add_game(tallies: dict[str, ConfigurationTally], events: list[dict[str, Any]]) -> None:
    start, end = events[0], events[-1]
    sides, stats = read_sides(start, end)
    configurations = {
        color: llm_configuration(start, color, side) for color, side in sides.items() if side["player"] == "llm"
    }
    for color, configuration in configurations.items():
        other = opponent(color)
        outcome = side_outcome(end["result"], color)
        tally = tallies.setdefault(configuration.id(), ConfigurationTally(configuration))
        tally.results.add(outcome)
        tally.opponents[opponent_name(sides[other], configurations.get(other))].add(outcome)
        tally.forfeits += outcome == "loss" and end["reason"] == "forfeit"
        # A version 1 attempt has no colour: it is the one LLM's, at llm_color.
        attempts = [
            event
            for event in events
            if event["type"] == "llm_attempt" and event.get("color", start.get("llm_color")) == color
        ]
        tally.attempts += len(attempts)
        tally.legal_moves += sum(event["result"] == "legal" for event in attempts)
        streak = (stats.get(color) or {}).get("legal_move_streak")
        if streak is not None:
            tally.streaks.append(streak)


def rated_game(events: list[dict[str, Any]]) -> list[RatedGame]:
    """The game as the Rating counts it, if it does: a game whose Mode and Rules are rated, an Anchor match or LLM
    faceoff under Standard rules (version 1 logs are all Play LLM). A Forfeit is a loss like any other."""
    start, end = events[0], events[-1]
    mode, rules = mode_named(start.get("mode")), rules_named(start.get("rules", "standard"))
    if "log_version" not in start or mode is None or not mode.rated or rules is None or not rules.rated:
        return []
    sides, _ = read_sides(start, end)
    players = []
    for color, side in sides.items():
        if side["player"] == "llm":
            players.append(llm_configuration(start, color, side).id())
        elif side["player"] == "anchor":
            players.append(anchor_name(side))
        else:
            return []
    white, black = players
    return [RatedGame(white=white, black=black, white_score=score_for(end["result"], "white"))]


def add_analysed_moves(analysed: dict[str, ConfigurationMoves], log: Path, events: list[dict[str, Any]]) -> None:
    """Pool each LLM side's scored moves from the game's analysis file, if it has one, into its configuration's."""
    start, end = events[0], events[-1]
    sides, _ = read_sides(start, end)
    analysed_sides = read_analysed_moves(analysis_path(log))
    for colour in COLORS:
        side = sides[colour]
        if colour in analysed_sides and side["player"] == "llm":
            key, moves = analysed_sides[colour]
            analysed[llm_configuration(start, colour, side).id()].add(key, moves)


def add_centipawn_loss_and_accuracy(
    tallies: dict[str, ConfigurationTally], events: list[dict[str, Any]], analysis_file: Path
) -> None:
    """Add each LLM side's moves analysed by Stockfish, if the game's analysis file has any (chessllm.analytics.analysis)."""
    try:
        analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
        sides = analysis["centipawn_loss_and_accuracy"]["sides"]
    except (OSError, ValueError, TypeError, KeyError):  # not analysed, not by Stockfish, or not an analysis file
        return
    start = events[0]
    for color, side in read_sides(start, events[-1])[0].items():
        analysed = sides.get(color) if isinstance(sides, dict) else None
        if side["player"] != "llm" or not isinstance(analysed, dict):
            continue
        tally = tallies[llm_configuration(start, color, side).id()]
        for move in analysed.get("moves", []):
            tally.centipawn_losses.append(move["centipawn_loss"])
            tally.accuracies.append(move["accuracy"])


def read_sides(start: dict[str, Any], end: dict[str, Any]) -> tuple[dict[Color, dict[str, Any]], dict[str, Any]]:
    """Each side as version 2 describes it, and each side's stats.

    Version 1 (no log_version) had one LLM, at llm_color, with its settings and its stats at the top level, and the
    human on the other side. Its `mode` is the LLM constraints, which later version 1 logs call llm_constraints."""
    if "log_version" in start:
        return {color: start[color] for color in COLORS}, end["stats"]
    llm_color: Color = start["llm_color"]
    llm = {
        "player": "llm",
        "model": start["model"],
        "thinking": start["thinking"],
        "llm_constraints": start.get("llm_constraints", start.get("mode")),
        "retry_feedback": start["retry_feedback"],
    }
    sides: dict[Color, dict[str, Any]] = {color: llm if color == llm_color else {"player": "human"} for color in COLORS}
    return sides, {llm_color: end}


def llm_configuration(start: dict[str, Any], color: Color, side: dict[str, Any]) -> PlayerConfiguration:
    prompt, position = logged_prompt(start, color, side)
    sampling = start.get("sampling")
    return PlayerConfiguration(
        model=side["model"],
        thinking=side["thinking"],
        llm_constraints=side["llm_constraints"],
        rules=start.get("rules", "standard"),
        retry_feedback=side["retry_feedback"],
        max_retries=start["max_retries"],
        sampling=sampling if isinstance(sampling, dict) else {},
        prompt=prompt,
        position=position,
        turn_memory=side.get("turn_memory"),
        thinking_level=side.get("thinking_level"),
        thinking_budget=side.get("thinking_budget"),
        tools=side.get("tools"),
        tool_call_cap=side.get("tool_call_cap"),
    )


def logged_prompt(start: dict[str, Any], color: Color, side: dict[str, Any]) -> tuple[str, PositionFormat | None]:
    """The prompt and position of the LLM side at color as game_start logs it (prompt_settings). Logs from before
    Prompt templates have no template, and position: described for a described position."""
    file = start.get("prompt_files", {}).get(color) or start.get("prompt_file") or ""
    prompt, position = prompt_settings(PurePath(file).name, side.get("prompt_template", {}).get("id"))
    return prompt, side.get("position", position)


def settings_configuration(settings: Settings, color: Color) -> PlayerConfiguration:
    """The Player configuration the LLM at color plays a game with these settings in, as its log will record it."""
    side = settings.llm_sides()[color]
    template = side_template(side)
    file = prompt_file(template, side.llm_constraints)
    prompt, position = prompt_settings(file.name if file is not None else "", template.id)
    return PlayerConfiguration(
        model=side.model,
        thinking=side.thinking,
        llm_constraints=side.llm_constraints,
        rules=settings.rules,
        retry_feedback=side.retry_feedback,
        max_retries=settings.max_attempts - 1,
        sampling=dict(settings.sampling),
        prompt=prompt,
        position=position,
        turn_memory=side.turn_memory,
        thinking_level=side.thinking_level if isinstance(side, BenchmarkLlmSide) else None,
        thinking_budget=side.thinking_budget if isinstance(side, BenchmarkLlmSide) else None,
        tools=tuple(side.tools) if isinstance(side, BenchmarkLlmSide) else None,
        tool_call_cap=side.tool_call_cap if isinstance(side, BenchmarkLlmSide) else None,
    )


def opponent_name(side: dict[str, Any], configuration: PlayerConfiguration | None) -> str:
    """The other configuration's id for an LLM, the Anchor's name for an Anchor, e.g. "anchor:dragon:3", and the
    side's description for anything else: "human" for a human."""
    if configuration is not None:
        return configuration.id()
    if side["player"] == "anchor":
        return anchor_name(side)
    return ":".join(str(value) for value in side.values())
