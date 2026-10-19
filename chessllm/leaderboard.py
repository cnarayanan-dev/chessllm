"""The leaderboard: every finished game in the game logs, its results grouped by Player configuration.

Read from the logs on every request, so there is no stored state to keep in step with them. Both log versions are
read (ADR 0004); a missing `rules` means Standard rules."""

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any

from pydantic import BaseModel

from chessllm.game import COLORS, Color, Rules
from chessllm.prompt import ENFORCED, LlmConstraints, RetryFeedback


class PlayerConfiguration(BaseModel):
    """An LLM together with every setting it plays a game with. Games are pooled only if all of these match."""

    model: str
    thinking: bool
    llm_constraints: LlmConstraints
    rules: Rules
    retry_feedback: RetryFeedback
    sampling: dict[str, int | float]  # from the config file; empty means the model's defaults
    prompt: str  # the system prompt's file name, e.g. "system.txt"

    def id(self) -> str:
        """A short fingerprint of the settings, the same for the same settings on every request."""
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


class OpponentResults(BaseModel):
    opponent: str  # the id of the other Player configuration, or "human"
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


class Leaderboard(BaseModel):
    configurations: list[LeaderboardEntry]


SCORES = {"1-0": {"white": "win", "black": "loss"}, "0-1": {"white": "loss", "black": "win"}}


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

    def entry(self) -> LeaderboardEntry:
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
        )


def leaderboard(games_dir: Path) -> Leaderboard:
    tallies: dict[str, ConfigurationTally] = {}
    for path in sorted(games_dir.glob("*.jsonl")):
        events = finished_game(path)
        if events is not None:
            add_game(tallies, events)
    entries = [tally.entry() for tally in tallies.values()]
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
        other: Color = "black" if color == "white" else "white"
        outcome = SCORES.get(end["result"], {}).get(color, "draw")
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
    prompt_file = start.get("prompt_files", {}).get(color) or start.get("prompt_file") or ""
    sampling = start.get("sampling")
    return PlayerConfiguration(
        model=side["model"],
        thinking=side["thinking"],
        llm_constraints=side["llm_constraints"],
        rules=start.get("rules", "standard"),
        retry_feedback=side["retry_feedback"],
        sampling=sampling if isinstance(sampling, dict) else {},
        prompt=PurePath(prompt_file).name,
    )


def opponent_name(side: dict[str, Any], configuration: PlayerConfiguration | None) -> str:
    """The other configuration's id for an LLM, "human" for a human, and the side's description for anything else
    (such as a later Anchor), e.g. "anchor:dragon:3"."""
    if configuration is not None:
        return configuration.id()
    return ":".join(str(value) for value in side.values())
