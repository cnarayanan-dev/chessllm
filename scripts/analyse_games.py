"""Filter the game logs and summarise how the LLMs played: record per Player configuration, how games ended, recurring
themes (illegal moves, streaks, forfeits, mates, openings, move quality, tokens) and the games themselves.

Run:
    uv run python -m scripts.analyse_games                              # every finished game in games/
    uv run python -m scripts.analyse_games --mode anchor_match --model llama3 --since 2026-10-19
    uv run python -m scripts.analyse_games --include-unfinished --json  # the same report as JSON

A Player configuration is grouped here by model, LLM constraints, thinking, rules, retry feedback and position (the leaderboard
also splits by sampling, prompt and retries). Each LLM side of a game is counted, so an LLM faceoff counts once for
each side. Both log versions are read (ADR 0004) through chessllm.leaderboard.read_sides; a file that isn't a
readable game log is skipped and counted.

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

from chessllm.analysis import analysis_path
from chessllm.game import COLORS, ILLEGAL_KINDS, Color
from chessllm.game_log import GAMES_DIR
from chessllm.leaderboard import SCORES, read_sides
from chessllm.move_quality import VALIDATION_FILE, ConfigurationMoves, move_quality, read_analysed_moves, read_validation
from chessllm.prompt import ENFORCED

OPENING_PLIES = 20
ENDGAME_MATERIAL = 26
PIECE_VALUES = {chess.QUEEN: 9, chess.ROOK: 5, chess.BISHOP: 3, chess.KNIGHT: 3}
NO_ANSWER = ("timeout", "error")  # an attempt with no move: the LLM forfeits at once
OPENING_LENGTH = 4  # plies
TOP = 5


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

    def label(self) -> str:
        thinking = "thinking" if self.thinking else "no thinking"
        described = " / described position" if self.position != "fen" else ""
        return (
            f"{self.model} / {self.llm_constraints} / {thinking} / {self.rules} / {self.retry_feedback} feedback"
            f"{described}"
        )


@dataclass
class LlmSide:
    """One LLM side of one game."""

    game: Game
    color: Color
    configuration: Configuration
    opponent: str  # "human", "Dragon skill 3", or the other LLM's model
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
            position=str(side.get("position") or "fen"),
        )
        other = game.sides["black" if color == "white" else "white"]
        outcome = None if game.end is None else SCORES.get(str(game.end.get("result")), {}).get(color, "draw")
        result.append(LlmSide(game, color, configuration, opponent_label(other), outcome))
    return result


def opponent_label(side: dict[str, Any]) -> str:
    if side.get("player") == "anchor":
        return f"{str(side.get('engine', 'anchor')).capitalize()} skill {side.get('skill', '?')}"
    if side.get("player") == "llm":
        return str(side.get("model"))
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
        return any(self.side_matches(side) for side in llm_sides(game))


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


def record(sides: Iterable[LlmSide]) -> dict[str, Any]:
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
                if result in NO_ANSWER:
                    self.no_answers += 1
                elif result in ILLEGAL_KINDS:
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
                    self.recovered_turns += int(attempt.get("attempt", 1)) > 1
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
        path = analysis_path(side.game.path)
        moves = read_analysed_moves(path).get(side.color)
        if moves is not None:
            self.analysed_moves.add(*moves)
        try:
            analysis = json.loads(path.read_text(encoding="utf-8"))
            analysed = analysis["centipawn_loss_and_accuracy"]["sides"][side.color]
            for move in analysed["moves"]:
                self.centipawn_losses.append(float(move["centipawn_loss"]))
                self.accuracies.append(float(move["accuracy"]))
        except (OSError, ValueError, KeyError, TypeError):
            return

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
            "allowed_mate_in_one": self.allowed_mate_in_one,
            "missed_mate_in_one": self.missed_mate_in_one,
            "mate_turns_checked": self.mate_turns_checked,
            "average_centipawn_loss": mean(self.centipawn_losses),
            "average_accuracy": mean(self.accuracies),
            "analysed_moves": len(self.centipawn_losses),
            "move_quality": quality.model_dump() if quality is not None else None,
        }


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
        anchors = sorted({side.opponent for side in its_sides if side.game.mode == "anchor_match"})
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
    return {
        "games": len(selected),
        "llm_sides": len(sides),
        "configurations": configurations,
        "end_reasons": dict(Counter(str(game.end["reason"]) if game.end else "unfinished" for game in selected)),
        "overall_themes": overall.as_dict(validated_for),
        "openings": openings.most_common(TOP),
        "game_list": [game_summary(game, filters) for game in selected],
    }


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
    return "\n".join(out)


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
    if themes["chaos_moves"]:
        lines.append(f"chaos moves: {themes['chaos_moves']}")
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
    parser = argparse.ArgumentParser(prog="python -m scripts.analyse_games", description=__doc__.split("\n\n")[0])
    parser.add_argument("--games-dir", type=Path, default=GAMES_DIR, help=f"where the logs are (default {GAMES_DIR})")
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
