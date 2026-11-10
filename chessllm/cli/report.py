"""Filter the game logs and summarise how the LLMs played: record per Player configuration, how games ended, recurring
themes (illegal moves, streaks, forfeits, mates, openings, move quality, tokens) and the games themselves.

Run:
    uv run games-report                                              # every finished game in games/
    uv run games-report --mode anchor_match --model llama3 --since 2026-10-19
    uv run games-report --include-unfinished --json                  # the same report as JSON

A Player configuration is grouped here by model, LLM constraints, thinking and its Thinking level and Thinking budget,
rules, retry feedback, position, Turn memory and Tools with their Tool-call cap (the leaderboard also splits by
sampling, prompt and retries). Each LLM side of a game is counted, so an LLM faceoff counts once for each side. Both
log versions are read (ADR 0004) through chessllm.analytics.leaderboard.read_sides; a file that isn't a readable game
log is skipped and counted.

A System 1 side (ADR 0012) is reported apart, as the report's last section, only when the logs have one: per System 1
Player configuration (model, Choice temperature and Prompt template), its record, its Move-quality estimate and the
share of its moves that were its top option. That share counts the turns that were asked and played a move: a turn with
only one legal move isn't asked and has no choice, and a Forfeit plays no move. A move tied for the top probability
counts as the top option, as it does at Choice temperature 0, which then plays it every time. Illegal moves, retries,
the Legal-move streak, notation slips and Chaos gain cannot happen to a System 1 side: they are null in the JSON and
"not applicable" in the text, never zero (ADR 0003).

Phases: an illegal move at ply 20 or earlier is in the opening; later, it is in the endgame when the queens, rooks,
bishops and knights left on the board are worth at most ENDGAME_MATERIAL together (Q 9, R 5, B/N 3; 62 at the start),
and in the middlegame otherwise."""

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import chess

from chessllm.analytics.analysis import analysis_path
from chessllm.core.config import GAMES_DIR, VALIDATION_FILE
from chessllm.core.types import COLORS, Color, opponent
from chessllm.game.modes import mode_named
from chessllm.game.records import ILLEGAL_RESULTS
from chessllm.analytics.leaderboard import (
    System1Configuration,
    logged_prompt,
    read_sides,
    side_outcome,
    system1_configuration,
)
from chessllm.analytics.move_quality import ConfigurationMoves, move_quality, read_analysed_moves, read_validation
from chessllm.game.sides import ENFORCED, BenchmarkLlmSide

OPENING_PLIES = 20
ENDGAME_MATERIAL = 26
PIECE_VALUES = {chess.QUEEN: 9, chess.ROOK: 5, chess.BISHOP: 3, chess.KNIGHT: 3}
NO_ANSWER = ("timeout", "error")  # an attempt with no move: the LLM forfeits at once
OPENING_LENGTH = 4  # plies
TOP = 5
# The statistics a System 1 side cannot have: it can't propose an illegal move, so there are no retries, no streak, no
# notation slips and no Chaos moves to gain from.
NOT_APPLICABLE_TO_SYSTEM1 = (
    "illegal_turn_rate", "illegal_attempts_per_turn", "illegal_kinds", "illegal_phases", "top_illegal_moves",
    "repeated_rejected_moves", "no_answers", "legal_move_streak_mean", "legal_move_streak_median", "recovered_turns",
    "notation_slips", "chaos_gain",
)


@dataclass
class Game:
    path: Path
    start: dict[str, Any]
    events: list[dict[str, Any]]
    end: dict[str, Any] | None  # None while unfinished
    sides: dict[Color, dict[str, Any]]
    stats: dict[str, Any]
    version: int

    @property
    def mode(self) -> str:
        return str(self.start.get("mode")) if self.version >= 2 else "play_llm"  # a version 1 `mode` is constraints

    @property
    def rules(self) -> str:
        return str(self.start.get("rules", "standard"))

    @property
    def started(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.start["started_at"])
        except (KeyError, TypeError, ValueError):
            return None

    def played_moves(self) -> list[str]:
        """The moves on the board in order, as written: legal moves, chaos moves, human and Anchor moves."""
        moves: dict[int, str] = {}
        for event in self.events:
            kind, ply = event.get("type"), event.get("ply")
            if not isinstance(ply, int):
                continue
            if kind in ("human_move", "anchor_move"):
                moves[ply] = str(event["move"])
            elif kind == "system1_turn" and event.get("san"):
                moves[ply] = str(event["san"])
            elif kind == "llm_attempt" and (
                event.get("result") == "legal" or (event.get("resolution") or {}).get("kind") in ("chaos", "spawn")
            ):
                moves[ply] = str(event.get("san") or event.get("move"))
        return [moves[ply] for ply in sorted(moves)]


@dataclass(frozen=True)
class Configuration:
    model: str
    llm_constraints: str
    thinking: bool
    rules: str
    retry_feedback: str
    position: str = "fen"
    turn_memory: str = "fresh"
    thinking_level: str | None = None  # None for plain thinking on or off
    thinking_budget: int | None = None  # in tokens; None for no budget
    tools: tuple[str, ...] = ()  # sorted; empty for no Tools
    tool_call_cap: int | None = None  # None for no Tools

    def label(self) -> str:
        thinking = "thinking" if self.thinking else "no thinking"
        if self.thinking_level is not None:
            thinking = f"thinking {self.thinking_level}"
        if self.thinking_budget is not None:
            thinking += f", budget {self.thinking_budget}"
        extra = " / described position" if self.position != "fen" else ""
        extra += f" / {self.turn_memory}" if self.turn_memory != "fresh" else ""
        if self.tools:
            extra += f" / tools {'+'.join(self.tools)}"
            extra += f", cap {self.tool_call_cap}" if self.tool_call_cap != BenchmarkLlmSide.tool_call_cap else ""
        return (
            f"{self.model} / {self.llm_constraints} / {thinking} / {self.rules} / {self.retry_feedback} feedback"
            f"{extra}"
        )


@dataclass
class LlmSide:
    """One LLM side of one game."""

    game: Game
    color: Color
    configuration: Configuration
    opponent: str  # "human", "Dragon skill 3", "Random mover", or the other LLM's model
    outcome: str | None  # win/draw/loss from this side's view; None while unfinished

    @property
    def enforced(self) -> bool:
        return self.configuration.llm_constraints in ENFORCED

    def turns(self) -> list[list[dict[str, Any]]]:
        """Its turns in order, each its attempts in order. A version 1 attempt has no colour: it is the one LLM's."""
        by_ply: dict[int, list[dict[str, Any]]] = defaultdict(list)
        default_color = self.game.start.get("llm_color")
        for event in self.game.events:
            if event.get("type") == "llm_attempt" and event.get("color", default_color) == self.color:
                by_ply[int(event["ply"])].append(event)
        return [sorted(by_ply[ply], key=lambda attempt: int(attempt.get("attempt", 1))) for ply in sorted(by_ply)]


@dataclass
class System1Side:
    """One System 1 side of one game."""

    game: Game
    color: Color
    configuration: System1Configuration
    template: str | None  # the Prompt template's ID when it has one, else None
    opponent: str
    outcome: str | None  # win/draw/loss from this side's view; None while unfinished

    def prompt_text(self) -> str:
        """The Prompt template's text, to tell a template without an ID by."""
        template = self.game.sides[self.color].get("prompt_template") or {}
        return f"{template.get('system_prompt')}\n{template.get('turn_template')}"

    def label(self) -> str:
        """The side's configuration as the report names it: model, Choice temperature and template ID."""
        configuration = self.configuration
        prompt = self.template or "custom prompt"
        return f"{configuration.model} / Choice temperature {configuration.choice_temperature:g} / {prompt}"

    def turns(self) -> list[dict[str, Any]]:
        """Its system1_turn events in order."""
        return [
            event for event in self.game.events if event.get("type") == "system1_turn" and event.get("color") == self.color
        ]


def load_games(games_dir: Path) -> tuple[list[Game], list[tuple[str, str]]]:
    """Every game log in the directory, and the files skipped with why."""
    games, skipped = [], []
    for path in sorted(games_dir.glob("*.jsonl")):
        try:
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            skipped.append((path.name, f"unreadable: {error}"))
            continue
        if not events or not all(isinstance(event, dict) for event in events) or events[0].get("type") != "game_start":
            skipped.append((path.name, "no game_start"))
            continue
        start = events[0]
        end = events[-1] if events[-1].get("type") == "game_end" else None
        try:
            sides, stats = read_sides(start, end or {"stats": {}})
        except (KeyError, TypeError) as error:
            skipped.append((path.name, f"unknown log shape (missing {error})"))
            continue
        version = int(start.get("log_version", 1))
        games.append(Game(path, start, events, end, sides, stats or {}, version))
    return games, skipped


def end_reason(game: Game) -> str:
    """How the game ended, as the report counts it: its end reason, "aborted" for a game a Hosted model's provider
    stopped (ADR 0013), or "unfinished" for any other game without an end."""
    if game.end:
        return str(game.end["reason"])
    return "aborted" if game.events[-1].get("type") == "game_aborted" else "unfinished"


def llm_sides(game: Game) -> list[LlmSide]:
    result: list[LlmSide] = []
    for color in COLORS:
        side = game.sides[color]
        if side.get("player") != "llm":
            continue
        configuration = Configuration(
            model=str(side["model"]),
            llm_constraints=str(side["llm_constraints"]),
            thinking=bool(side["thinking"]),
            rules=game.rules,
            retry_feedback=str(side["retry_feedback"]),
            position=logged_prompt(game.start, color, side)[1] or "fen",
            turn_memory=str(side.get("turn_memory") or "fresh"),
            thinking_level=side.get("thinking_level"),
            thinking_budget=side.get("thinking_budget"),
            tools=tuple(sorted(side.get("tools", ()))),
            tool_call_cap=side.get("tool_call_cap"),
        )
        other = game.sides[opponent(color)]
        outcome = None if game.end is None else side_outcome(str(game.end.get("result")), color)
        result.append(LlmSide(game, color, configuration, opponent_label(other), outcome))
    return result


def system1_sides(game: Game) -> list[System1Side]:
    result: list[System1Side] = []
    for color in COLORS:
        side = game.sides[color]
        if side.get("player") != "system1":
            continue
        outcome = None if game.end is None else side_outcome(str(game.end.get("result")), color)
        template = (side.get("prompt_template") or {}).get("id")
        result.append(
            System1Side(
                game,
                color,
                system1_configuration(game.start, side),
                template,
                opponent_label(game.sides[opponent(color)]),
                outcome,
            )
        )
    return result


def opponent_label(side: dict[str, Any]) -> str:
    if side.get("player") == "anchor" and side.get("engine") == "random":
        return "Random mover"
    if side.get("player") == "anchor":
        return f"{str(side.get('engine', 'anchor')).capitalize()} skill {side.get('skill', '?')}"
    if side.get("player") == "llm":
        return str(side.get("model"))
    if side.get("player") == "system1":
        return f"{side.get('model')} (Choice temperature {float(side.get('choice_temperature', 1)):g})"
    return str(side.get("player", "?"))


@dataclass
class Filters:
    mode: str | None = None
    model: str | None = None  # a substring of the model name, e.g. "llama3"
    constraints: str | None = None
    rules: str | None = None
    finished_only: bool = True
    since: datetime | None = None  # in the logs' own local time

    def side_matches(self, side: LlmSide) -> bool:
        configuration = side.configuration
        return (self.model is None or self.model.lower() in configuration.model.lower()) and (
            self.constraints is None or configuration.llm_constraints == self.constraints
        )

    def system1_side_matches(self, side: System1Side) -> bool:
        """A System 1 side has no LLM constraints, so a filter on them leaves it out."""
        return self.constraints is None and (self.model is None or self.model.lower() in side.configuration.model.lower())

    def game_matches(self, game: Game) -> bool:
        if self.finished_only and game.end is None:
            return False
        if self.mode is not None and game.mode != self.mode:
            return False
        if self.rules is not None and game.rules != self.rules:
            return False
        if self.since is not None:
            started = game.started
            if started is None or started.replace(tzinfo=None) < self.since:
                return False
        return any(self.side_matches(side) for side in llm_sides(game)) or any(
            self.system1_side_matches(side) for side in system1_sides(game)
        )


# --- the analysis -------------------------------------------------------------------------------------------------


def mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def p90(values: Sequence[float]) -> float | None:
    """The 90th percentile, interpolated between the values."""
    if len(values) < 2:
        return values[0] if values else None
    return statistics.quantiles(values, n=10, method="inclusive")[-1]


def ratio(part: float, whole: float) -> float | None:
    return part / whole if whole else None


def record(sides: Iterable[LlmSide | System1Side]) -> dict[str, Any]:
    outcomes = Counter(side.outcome for side in sides)
    finished = outcomes["win"] + outcomes["draw"] + outcomes["loss"]
    return {
        "games": finished + outcomes[None],
        "wins": outcomes["win"],
        "draws": outcomes["draw"],
        "losses": outcomes["loss"],
        "unfinished": outcomes[None],
        "score": ratio(outcomes["win"] + outcomes["draw"] / 2, finished),
    }


def phase(ply: int, fen: str) -> str:
    if ply <= OPENING_PLIES:
        return "opening"
    board = chess.Board(fen)
    material = sum(PIECE_VALUES.get(piece.piece_type, 0) for piece in board.piece_map().values())
    return "endgame" if material <= ENDGAME_MATERIAL else "middlegame"


def mates_in_one(board: chess.Board) -> list[chess.Move]:
    """The moves that mate at once in the position, if it has both kings (a Chaos rules game can lose one)."""
    if board.king(chess.WHITE) is None or board.king(chess.BLACK) is None:
        return []
    mates = []
    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            mates.append(move)
        board.pop()
    return mates


@dataclass
class Themes:
    """The recurring patterns of a set of LLM sides, accumulated side by side."""

    turns: int = 0
    turns_with_illegal: int = 0
    illegal_attempts: int = 0
    illegal_kinds: Counter[str] = field(default_factory=Counter)
    illegal_moves: Counter[str] = field(default_factory=Counter)
    illegal_phases: Counter[str] = field(default_factory=Counter)
    repeated_rejected: int = 0  # retries that proposed a move already rejected in the same turn
    no_answers: int = 0  # timeouts and failed calls
    chaos_moves: int = 0
    streaks: list[int] = field(default_factory=list)
    recovered_turns: int = 0
    notation_slips: int = 0
    finished: int = 0
    forfeits: int = 0
    forfeits_without_answer: int = 0
    losses_by: Counter[str] = field(default_factory=Counter)
    plies: list[int] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    thinking_tokens: list[int] = field(default_factory=list)  # per attempt with an answer; logs before them have none
    prompt_tokens: list[int] = field(default_factory=list)
    length_stops: int = 0  # attempts whose generation was cut at the token limit
    budgeted_answers: int = 0  # attempts with an answer by a side with a Thinking budget
    forced_answers: int = 0  # of those, the ones the budget forced, cut-offs included
    cut_offs: int = 0  # forced answers cut off too, so without a move: neither illegal nor a forfeit at once
    allowed_mate_in_one: int = 0  # legal moves after which the opponent could mate at once
    missed_mate_in_one: int = 0  # turns with a mate in one that the LLM didn't play
    mate_turns_checked: int = 0
    centipawn_losses: list[float] = field(default_factory=list)
    accuracies: list[float] = field(default_factory=list)
    analysed_moves: ConfigurationMoves = field(default_factory=ConfigurationMoves)

    def add(self, side: LlmSide) -> None:
        streak, streak_broken = 0, False
        turns = side.turns()
        for turn in turns:
            self.turns += 1
            rejected: set[str] = set()
            illegal_in_turn = False
            for attempt in turn:
                result = attempt.get("result")
                if isinstance(attempt.get("latency_s"), (int, float)):
                    self.latencies.append(float(attempt["latency_s"]))
                self.add_tokens(attempt)
                if result not in NO_ANSWER and side.configuration.thinking_budget is not None:
                    self.budgeted_answers += 1
                    self.forced_answers += attempt.get("forced") is True
                if result in NO_ANSWER:
                    self.no_answers += 1
                elif result == "cut_off":
                    self.cut_offs += 1
                elif result in ILLEGAL_RESULTS:
                    illegal_in_turn = streak_broken = True  # even if a retry recovers the turn
                    move = str(attempt.get("move"))
                    self.illegal_attempts += 1
                    self.illegal_kinds[str(result)] += 1
                    self.illegal_moves[move] += 1
                    self.illegal_phases[phase(int(attempt["ply"]), str(attempt["fen"]))] += 1
                    self.repeated_rejected += move in rejected
                    rejected.add(move)
                    if (attempt.get("resolution") or {}).get("kind") in ("chaos", "spawn"):
                        self.chaos_moves += 1
                elif result == "legal":
                    self.notation_slips += bool(attempt.get("notation_slip"))
                    self.recovered_turns += illegal_in_turn  # recovered from an illegal move, not from a cut-off
                    if not streak_broken:
                        streak += 1
                    self.add_mates(attempt)
            self.turns_with_illegal += illegal_in_turn
        if not side.enforced:
            logged = (side.game.stats.get(side.color) or {}).get("legal_move_streak")
            self.streaks.append(logged if isinstance(logged, int) else streak)
        end = side.game.end
        if end is not None:
            self.finished += 1
            self.plies.append(int(end.get("plies", 0)))
            if side.outcome == "loss":
                self.losses_by[str(end.get("reason"))] += 1
                if end.get("reason") == "forfeit":
                    self.forfeits += 1
                    last = turns[-1][-1] if turns and turns[-1] else {}
                    self.forfeits_without_answer += last.get("result") in NO_ANSWER
        self.add_analysis(side)

    def add_tokens(self, attempt: dict[str, Any]) -> None:
        if isinstance(attempt.get("thinking_tokens"), int):
            self.thinking_tokens.append(attempt["thinking_tokens"])
        if isinstance(attempt.get("prompt_tokens"), int):
            self.prompt_tokens.append(attempt["prompt_tokens"])
        self.length_stops += attempt.get("stop_reason") == "length"

    def add_mates(self, attempt: dict[str, Any]) -> None:
        try:
            board = chess.Board(attempt["fen"])
            move = board.parse_san(str(attempt.get("san") or attempt["move"]))
        except (KeyError, ValueError):
            return
        self.mate_turns_checked += 1
        mates = mates_in_one(board)
        self.missed_mate_in_one += bool(mates) and move not in mates
        board.push(move)
        self.allowed_mate_in_one += bool(mates_in_one(board))

    def add_analysis(self, side: LlmSide) -> None:
        add_analysis(self, side.game, side.color)

    def as_dict(self, validated_for: Any) -> dict[str, Any]:
        quality = move_quality(self.analysed_moves, validated_for)
        return {
            "turns": self.turns,
            "illegal_turn_rate": ratio(self.turns_with_illegal, self.turns),
            "illegal_attempts_per_turn": ratio(self.illegal_attempts, self.turns),
            "illegal_kinds": dict(self.illegal_kinds),
            "illegal_phases": dict(self.illegal_phases),
            "top_illegal_moves": self.illegal_moves.most_common(TOP),
            "repeated_rejected_moves": self.repeated_rejected,
            "no_answers": self.no_answers,
            "chaos_moves": self.chaos_moves,
            "legal_move_streak_mean": mean(self.streaks),
            "legal_move_streak_median": median(self.streaks),
            "recovered_turns": self.recovered_turns,
            "notation_slips": self.notation_slips,
            "forfeit_rate": ratio(self.forfeits, self.finished),
            "forfeits_without_answer": self.forfeits_without_answer,
            "losses_by": dict(self.losses_by),
            "plies_mean": mean(self.plies),
            "plies_median": median(self.plies),
            "latency_mean_s": mean(self.latencies),
            "thinking_tokens_median": median(self.thinking_tokens),
            "thinking_tokens_p90": p90(self.thinking_tokens),
            "prompt_tokens_median": median(self.prompt_tokens),
            "length_stops": self.length_stops,
            "budgeted_answers": self.budgeted_answers,
            "forced_answers": self.forced_answers,
            "forced_share": ratio(self.forced_answers, self.budgeted_answers),
            "cut_offs": self.cut_offs,
            "allowed_mate_in_one": self.allowed_mate_in_one,
            "missed_mate_in_one": self.missed_mate_in_one,
            "mate_turns_checked": self.mate_turns_checked,
            "average_centipawn_loss": mean(self.centipawn_losses),
            "average_accuracy": mean(self.accuracies),
            "analysed_moves": len(self.centipawn_losses),
            "move_quality": quality.model_dump() if quality is not None else None,
        }


def add_analysis(themes: "Themes | System1Themes", game: Game, color: Color) -> None:
    """Add a side's Move-quality estimate moves and its Stockfish centipawn losses and accuracies, from the game's
    analysis file, if it has one."""
    path = analysis_path(game.path)
    moves = read_analysed_moves(path).get(color)
    if moves is not None:
        themes.analysed_moves.add(*moves)
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
        analysed = analysis["centipawn_loss_and_accuracy"]["sides"][color]
        for move in analysed["moves"]:
            themes.centipawn_losses.append(float(move["centipawn_loss"]))
            themes.accuracies.append(float(move["accuracy"]))
    except (OSError, ValueError, KeyError, TypeError):
        return


@dataclass
class System1Themes:
    """The patterns of a set of System 1 sides. Only what can happen to one: its choices, forfeits and move quality."""

    turns: int = 0
    top_option_moves: int = 0  # asked turns that played the top option
    top_option_turns: int = 0  # asked turns that played a move
    finished: int = 0
    forfeits: int = 0
    losses_by: Counter[str] = field(default_factory=Counter)
    plies: list[int] = field(default_factory=list)
    times: list[float] = field(default_factory=list)  # each turn's Time used
    centipawn_losses: list[float] = field(default_factory=list)
    accuracies: list[float] = field(default_factory=list)
    analysed_moves: ConfigurationMoves = field(default_factory=ConfigurationMoves)

    def add(self, side: System1Side) -> None:
        for turn in side.turns():
            self.turns += 1
            if isinstance(turn.get("time_s"), (int, float)):
                self.times.append(float(turn["time_s"]))
            if turn.get("asked") and turn.get("move") is not None:
                self.top_option_turns += 1
                self.top_option_moves += played_a_top_option(turn)
        end = side.game.end
        if end is not None:
            self.finished += 1
            self.plies.append(int(end.get("plies", 0)))
            if side.outcome == "loss":
                self.losses_by[str(end.get("reason"))] += 1
                self.forfeits += end.get("reason") == "forfeit"
        add_analysis(self, side.game, side.color)

    def as_dict(self, validated_for: Any) -> dict[str, Any]:
        quality = move_quality(self.analysed_moves, validated_for)
        return {
            "turns": self.turns,
            "top_option_moves": self.top_option_moves,
            "top_option_turns": self.top_option_turns,
            "top_option_share": ratio(self.top_option_moves, self.top_option_turns),
            # Not applicable to a System 1 side, which offers only legal moves in one attempt (ADR 0003): null, not 0.
            **dict.fromkeys(NOT_APPLICABLE_TO_SYSTEM1),
            "forfeit_rate": ratio(self.forfeits, self.finished),
            "losses_by": dict(self.losses_by),
            "plies_mean": mean(self.plies),
            "time_mean_s": mean(self.times),
            "average_centipawn_loss": mean(self.centipawn_losses),
            "average_accuracy": mean(self.accuracies),
            "analysed_moves": len(self.centipawn_losses),
            "move_quality": quality.model_dump() if quality is not None else None,
        }


def played_a_top_option(turn: dict[str, Any]) -> bool:
    """Whether the move a System 1 turn played had the highest probability of its options, or the highest with others:
    a tie for the top counts, as at Choice temperature 0, which plays the first of them."""
    probabilities = {option["san"]: option.get("probability") for option in turn["options"]}
    played = probabilities.get(turn.get("san"))
    return played is not None and played >= max(value for value in probabilities.values() if value is not None)


def opening(game: Game) -> str | None:
    moves = game.played_moves()[:OPENING_LENGTH]
    if len(moves) < OPENING_LENGTH:
        return None
    return " ".join(f"{index // 2 + 1}. {move}" if index % 2 == 0 else move for index, move in enumerate(moves))


def analyse(games: list[Game], filters: Filters, validation_file: Path = VALIDATION_FILE) -> dict[str, Any]:
    selected = [game for game in games if filters.game_matches(game)]
    sides = [side for game in selected for side in llm_sides(game) if filters.side_matches(side)]
    by_configuration: dict[Configuration, list[LlmSide]] = defaultdict(list)
    for side in sides:
        by_configuration[side.configuration].append(side)
    validated_for = read_validation(validation_file)
    configurations = []
    for configuration in sorted(by_configuration, key=Configuration.label):
        its_sides = by_configuration[configuration]
        anchors = sorted({side.opponent for side in its_sides if (mode := mode_named(side.game.mode)) is not None and mode.against_an_anchor})
        themes = Themes()
        for side in its_sides:
            themes.add(side)
        configurations.append(
            {
                "configuration": configuration.__dict__ | {"label": configuration.label()},
                "record": record(its_sides),
                "by_anchor": {
                    anchor: record(side for side in its_sides if side.opponent == anchor) for anchor in anchors
                },
                "themes": themes.as_dict(validated_for),
            }
        )
    overall = Themes()
    for side in sides:
        overall.add(side)
    openings = Counter(name for game in selected if (name := opening(game)) is not None)
    report = {
        "games": len(selected),
        "llm_sides": len(sides),
        "configurations": configurations,
        "end_reasons": dict(Counter(end_reason(game) for game in selected)),
        "overall_themes": overall.as_dict(validated_for),
        "openings": openings.most_common(TOP),
        "game_list": [game_summary(game, filters) for game in selected],
    }
    system1 = [side for game in selected for side in system1_sides(game) if filters.system1_side_matches(side)]
    if system1:  # reports over logs without System 1 sides have neither key
        report |= {
            "system1_sides": len(system1),
            "system1_configurations": system1_configurations(system1, validated_for),
        }
    return report


def system1_configurations(sides: list[System1Side], validated_for: Any) -> list[dict[str, Any]]:
    by_configuration: dict[str, list[System1Side]] = defaultdict(list)  # by Player configuration id
    for side in sides:
        by_configuration[side.configuration.id()].append(side)
    configurations = []
    for its_sides in sorted(by_configuration.values(), key=lambda its_sides: its_sides[0].label()):
        configuration = its_sides[0].configuration
        anchors = sorted({side.opponent for side in its_sides if (mode := mode_named(side.game.mode)) is not None and mode.against_an_anchor})
        themes = System1Themes()
        for side in its_sides:
            themes.add(side)
        configurations.append(
            {
                "configuration": {
                    "model": configuration.model,
                    "choice_temperature": configuration.choice_temperature,
                    "prompt_template": its_sides[0].template or its_sides[0].prompt_text(),
                    "label": its_sides[0].label(),
                },
                "record": record(its_sides),
                "by_anchor": {
                    anchor: record(side for side in its_sides if side.opponent == anchor) for anchor in anchors
                },
                "themes": themes.as_dict(validated_for),
            }
        )
    return configurations


def game_summary(game: Game, filters: Filters) -> dict[str, Any]:
    def describe(color: Color) -> str:
        side = game.sides[color]
        if side.get("player") == "llm":
            return f"{side['model']} ({side['llm_constraints']}{', thinking' if side['thinking'] else ''})"
        return opponent_label(side)

    started = game.started
    return {
        "file": game.path.name,
        "date": started.strftime("%Y-%m-%d %H:%M") if started else None,
        "mode": game.mode,
        "rules": game.rules,
        "white": describe("white"),
        "black": describe("black"),
        "result": game.end.get("result") if game.end else None,
        "reason": game.end.get("reason") if game.end else None,
        "plies": game.end.get("plies") if game.end else len(game.played_moves()),
        "log_version": game.version,
    }


# --- the text report ----------------------------------------------------------------------------------------------


def table(headers: list[str], rows: list[list[Any]]) -> str:
    cells = [headers, *[[cell_text(cell) for cell in row] for row in rows]]
    widths = [max(len(row[index]) for row in cells) for index in range(len(headers))]
    lines = ["  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in cells]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(lines)


def cell_text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def count_text(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def percent(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.0f}%"


def counts(counter: dict[str, int] | list[tuple[str, int]]) -> str:
    items = counter.items() if isinstance(counter, dict) else counter
    return ", ".join(f"{key} ({value})" for key, value in items) or "-"


def render(report: dict[str, Any], skipped: list[tuple[str, str]], total: int) -> str:
    out = [
        f"{report['games']} games selected of {total} logs ({len(skipped)} skipped), {report['llm_sides']} LLM sides",
    ]
    for name, why in skipped:
        out.append(f"  skipped {name}: {why}")

    out += ["", "1. Record per Player configuration (LLM's view; a faceoff counts once per side)", ""]
    rows: list[list[Any]] = []
    for entry in report["configurations"]:
        result = entry["record"]
        rows.append([entry["configuration"]["label"], result["games"], result["wins"], result["draws"],
                     result["losses"], percent(result["score"]), result["unfinished"]])
        for anchor, by_anchor in entry["by_anchor"].items():
            rows.append([f"    vs {anchor}", by_anchor["games"], by_anchor["wins"], by_anchor["draws"],
                         by_anchor["losses"], percent(by_anchor["score"]), by_anchor["unfinished"]])
    out.append(table(["configuration", "games", "W", "D", "L", "score", "unfinished"], rows))

    out += ["", "2. How games ended", ""]
    reasons = sorted(report["end_reasons"].items(), key=lambda item: -item[1])
    out.append(table(["reason", "games"], [[reason, number] for reason, number in reasons]))

    out += ["", "3. Themes", ""]
    rows = []
    for entry in report["configurations"]:
        themes = entry["themes"]
        rows.append([
            entry["configuration"]["label"], themes["turns"], percent(themes["illegal_turn_rate"]),
            themes["illegal_attempts_per_turn"], themes["legal_move_streak_mean"], themes["legal_move_streak_median"],
            themes["recovered_turns"], themes["notation_slips"], percent(themes["forfeit_rate"]), themes["plies_mean"],
            themes["latency_mean_s"],
        ])
    out.append(table(
        ["configuration", "turns", "illegal turns", "illegal/turn", "streak mean", "streak median", "recovered",
         "slips", "forfeit rate", "plies mean", "latency s"],
        rows,
    ))
    for entry in report["configurations"]:
        out += ["", entry["configuration"]["label"]]
        out += [f"  {line}" for line in theme_lines(entry["themes"])]
    out += ["", "All selected LLM sides together"]
    out += [f"  {line}" for line in theme_lines(report["overall_themes"])]
    out.append(f"  most common openings (first {OPENING_LENGTH} plies): {counts(report['openings'])}")

    out += ["", "4. Games", ""]
    out.append(table(
        ["file", "date", "mode", "rules", "white", "black", "result", "reason", "plies"],
        [[game["file"], game["date"], game["mode"], game["rules"], game["white"], game["black"], game["result"],
          game["reason"], game["plies"]] for game in report["game_list"]],
    ))
    if "system1_configurations" in report:
        out += system1_section(report)
    return "\n".join(out)


def system1_section(report: dict[str, Any]) -> list[str]:
    out = ["", f"5. System 1 sides ({report['system1_sides']}; a faceoff counts once per side)", ""]
    rows: list[list[Any]] = []
    for entry in report["system1_configurations"]:
        result, themes = entry["record"], entry["themes"]
        rows.append([entry["configuration"]["label"], result["games"], result["wins"], result["draws"],
                     result["losses"], percent(result["score"]), result["unfinished"],
                     percent(themes["top_option_share"]), percent(themes["forfeit_rate"]), themes["plies_mean"],
                     themes["time_mean_s"]])
        for anchor, by_anchor in entry["by_anchor"].items():
            rows.append([f"    vs {anchor}", by_anchor["games"], by_anchor["wins"], by_anchor["draws"],
                         by_anchor["losses"], percent(by_anchor["score"]), by_anchor["unfinished"], "", "", "", ""])
    out.append(table(["configuration", "games", "W", "D", "L", "score", "unfinished", "top option", "forfeit rate",
                      "plies mean", "time s"], rows))
    for entry in report["system1_configurations"]:
        themes = entry["themes"]
        out += ["", entry["configuration"]["label"]]
        out.append(
            f"  top option {themes['top_option_moves']} of {themes['top_option_turns']} moves "
            f"({percent(themes['top_option_share'])}); turns with only one legal move are not counted"
        )
        out += [f"  {line}" for line in analysis_lines(themes)]
        out.append("  not applicable: illegal moves, retries, Legal-move streak, notation slips, Chaos gain")
    return out


def theme_lines(themes: dict[str, Any]) -> list[str]:
    lines = [
        f"illegal kinds: {counts(themes['illegal_kinds'])}; by phase: {counts(themes['illegal_phases'])}",
        f"most common illegal moves: {counts(themes['top_illegal_moves'])}; "
        f"a rejected move proposed again in the same turn: {themes['repeated_rejected_moves']}",
        f"losses by: {counts(themes['losses_by'])}; forfeits with no answer (timeout/error): "
        f"{themes['forfeits_without_answer']}; no-answer attempts: {themes['no_answers']}",
        f"mate in one allowed after {themes['allowed_mate_in_one']} and missed on {themes['missed_mate_in_one']} "
        f"of {themes['mate_turns_checked']} legal moves",
    ]
    if themes["thinking_tokens_median"] is not None or themes["prompt_tokens_median"] is not None:
        lines.append(
            f"thinking tokens median {count_text(themes['thinking_tokens_median'])}, "
            f"p90 {count_text(themes['thinking_tokens_p90'])}; "
            f"prompt tokens median {count_text(themes['prompt_tokens_median'])}; "
            f"stopped for length: {themes['length_stops']}"
        )
    if themes["budgeted_answers"]:
        lines.append(
            f"forced answers: {themes['forced_answers']} of {themes['budgeted_answers']} attempts with a budget "
            f"({percent(themes['forced_share'])}); cut off without an answer: {themes['cut_offs']}"
        )
    if themes["chaos_moves"]:
        lines.append(f"chaos moves: {themes['chaos_moves']}")
    return lines + analysis_lines(themes)


def analysis_lines(themes: dict[str, Any]) -> list[str]:
    """The Stockfish and Move-quality lines of a side's themes, from its analysis files."""
    lines = []
    if themes["analysed_moves"]:
        lines.append(
            f"Stockfish over {themes['analysed_moves']} moves: average centipawn loss "
            f"{themes['average_centipawn_loss']:.0f}, accuracy {themes['average_accuracy']:.1f}"
        )
    quality = themes["move_quality"]
    if quality is not None:
        estimate = quality["estimate"] if quality["estimate"] is not None else "at the grid's edge"
        low = quality["low"] if quality["low"] is not None else "open"
        high = quality["high"] if quality["high"] is not None else "open"
        validated = "validated" if quality["validated"] else "unvalidated"
        lines.append(
            f"Move-quality estimate (chess.com): {estimate}, 95% [{low}, {high}], {quality['games']} games, "
            f"{quality['moves']} moves, {validated}"
        )
    return lines


# --- the command --------------------------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="games-report", description=__doc__.split("\n\n")[0])
    parser.add_argument("--games-dir", type=Path, default=GAMES_DIR, help="where the logs are (default: the project's games/)")
    parser.add_argument("--mode", choices=["play_llm", "llm_faceoff", "anchor_match"])
    parser.add_argument("--model", help="only LLM sides whose model contains this, e.g. llama3")
    parser.add_argument("--constraints", choices=["free", "listed", "blind_enforced", "listed_enforced"])
    parser.add_argument("--rules", choices=["standard", "chaos"])
    finished = parser.add_mutually_exclusive_group()
    finished.add_argument("--finished-only", dest="finished_only", action="store_true", default=True,
                          help="only games with a game_end (the default)")
    finished.add_argument("--include-unfinished", dest="finished_only", action="store_false",
                          help="also games still being played or abandoned")
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        help="only games started at or after this date or time (YYYY-MM-DD or YYYY-MM-DDTHH:MM)",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    filters = Filters(args.mode, args.model, args.constraints, args.rules, args.finished_only, args.since)
    games, skipped = load_games(args.games_dir)
    report = analyse(games, filters)
    if args.json:
        print(json.dumps(report | {"skipped": skipped}, indent=2))
    else:
        print(render(report, skipped, len(games) + len(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
