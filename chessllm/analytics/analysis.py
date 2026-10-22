"""Game analysis: one analysis file per finished game, next to its log, holding each LLM side's Move-quality
estimate from a MoveModel, and its centipawn loss and accuracy from an Evaluator. The game log is only read, never
changed (ADR 0004, ADR 0005).

The analysis file of games/<stem>.jsonl is games/<stem>.analysis.json:

    {
      "analysis_version": 1,
      "game_log": "<stem>.jsonl",
      "game_id": "...",                  # from game_start
      "analysed_at": "2026-10-19T16:00:00+02:00",
      "versions": {"move_model": "maia2 0.11.0, rapid model, ...", "stockfish": "Stockfish 19"},  # what ran
      "move_quality": {                  # null when the move model didn't run
        "scale": "lichess_rapid",
        "ratings": [1000, 1100, ...],      # the grid the estimate is taken over
        "sides": {
          "white": null,                   # not an LLM: a human or an Anchor, whose moves are not scored
          "black": {
            "estimate": 1300,              # the most likely rating, or null when no move was scored
            "interval": [1150, 1480],      # 95% likelihood-ratio interval, or null; clipped to the grid
            "moves": [{"ply": 2, "fen": "...", "move": "e7e5", "log_probabilities": [...]}, ...]
          }
        }
      },
      "centipawn_loss_and_accuracy": {   # null when Stockfish didn't run; diagnostics, never an Elo (ADR 0005)
        "search": {"depth": 16, "threads": 1, "hash_mb": 64},
        "sides": {
          "white": null,
          "black": {
            "average_centipawn_loss": 85.3,   # or null when no move was scored
            "accuracy": 71.2,                 # the mean of the moves' accuracies, or null
            "moves": [{"ply": 2, "fen": "...", "move": "e7e5", "evaluation_before": 30, "evaluation_after": 25,
                       "centipawn_loss": 5, "accuracy": 99.1}, ...]
          }
        }
      }
    }

Each move's log_probabilities go with ratings, one per rating, so a Player configuration's pooled estimate is
estimate() over the moves of all its games together.

Centipawn loss and accuracy follow lichess (https://lichess.org/page/accuracy, and lila's AccuracyPercent.scala):
evaluations are from the mover's point of view, capped at +-1000 centipawns with a mate as 1000; a move's
centipawn loss is how far it drops the evaluation (never below 0), and its accuracy is
103.1668 * exp(-0.04354 * (Win% before - Win% after)) - 3.1669 + 1, clipped to 0-100, with
Win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * centipawns)) - 1). A side's accuracy is the plain mean of its moves'
accuracies, not lichess's game accuracy, which weights moves by how volatile the game was around them and so needs
every position of the game evaluated, the opponent's too.

Only legal moves played are scored, as for the Move-quality estimate, and not even those when the position before
or after isn't valid chess, as a chaos move earlier in the game can leave it (ADR 0006).

Run `uv run analyse-games` (chessllm.cli.analyse) to analyse every finished game without an analysis file, or with
--all to re-analyse every finished game."""

import json
import logging
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import chess
import chess.engine

from chessllm.core.types import COLORS, Color, color_of
from chessllm.engines.evaluator import Evaluator
from chessllm.logs.game_log import now
from chessllm.exceptions import Maia2Unavailable, StockfishUnavailable
from chessllm.engines.move_model import MoveModel

ANALYSIS_VERSION = 1
ANALYSIS_SUFFIX = ".analysis.json"
# Half the 95% quantile of chi-squared with one degree of freedom: the log-likelihood drop at the interval's ends.
LOG_LIKELIHOOD_DROP_95 = 3.8415 / 2
# Evaluations are capped at +-1000 centipawns and a mate counts as 1000, as lichess does (scalachess Eval.Cp.CEILING).
CENTIPAWN_CAP = 1000


def analysis_path(log: Path) -> Path:
    """Where the analysis of a game log goes: next to it, e.g. games/<stem>.analysis.json."""
    return log.with_name(log.stem + ANALYSIS_SUFFIX)


def estimate(ratings: Sequence[int], moves: Sequence[Sequence[float]]) -> tuple[int | None, list[int] | None]:
    """The maximum-likelihood rating over the grid of ratings, from each move's log-probabilities at those ratings,
    and its 95% interval: the ratings whose log-likelihood is within LOG_LIKELIHOOD_DROP_95 of the best, found by
    linear interpolation between grid points and clipped to the grid. (None, None) without moves."""
    if not moves:
        return None, None
    totals = [sum(move[index] for move in moves) for index in range(len(ratings))]
    best = max(range(len(ratings)), key=lambda index: totals[index])
    threshold = totals[best] - LOG_LIKELIHOOD_DROP_95

    def bound(step: int) -> int:
        index = best
        while 0 <= index + step < len(ratings):
            inside, outside = index, index + step
            if totals[outside] < threshold:
                share = (totals[inside] - threshold) / (totals[inside] - totals[outside])
                return round(ratings[inside] + share * (ratings[outside] - ratings[inside]))
            index = outside
        return ratings[index]

    return ratings[best], [bound(-1), bound(+1)]


def read_events(log: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def llm_colours(start: dict[str, Any]) -> list[Color]:
    """The colours played by an LLM. Version 1 logs have one LLM side, llm_color (ADR 0004)."""
    if "log_version" not in start:
        return [start["llm_color"]]
    return [colour for colour in COLORS if start[colour].get("player") == "llm"]


def scored_moves(events: list[dict[str, Any]]) -> list[tuple[Color, int, str, str]]:
    """The legal moves the LLMs played, as (colour, ply, fen before, UCI). Illegal attempts are skipped, and so are
    chaos moves, which are logged as illegal attempts with a resolution (ADR 0006)."""
    moves = []
    for event in events:
        if event["type"] != "llm_attempt" or event.get("result") != "legal":
            continue
        board = chess.Board(event["fen"])
        # Early version 1 logs have no san; the move as written is legal then, a notation slip at worst.
        move = board.parse_san(event.get("san") or event["move"])
        colour = color_of(board.turn)
        moves.append((colour, event["ply"], event["fen"], move.uci()))
    return moves


def move_quality(log_events: list[dict[str, Any]], move_model: MoveModel) -> dict[str, Any]:
    """The move_quality section: each LLM side's Move-quality estimate from the move model."""
    ratings = list(move_model.ratings)
    sides: dict[Color, dict[str, Any] | None] = dict.fromkeys(COLORS)
    for colour in llm_colours(log_events[0]):
        played = [(ply, fen, uci) for moved, ply, fen, uci in scored_moves(log_events) if moved == colour]
        log_probabilities = [[math.log(p) for p in move_model.probabilities(fen, uci)] for _, fen, uci in played]
        moves = [
            {"ply": ply, "fen": fen, "move": uci, "log_probabilities": move}
            for (ply, fen, uci), move in zip(played, log_probabilities)
        ]
        best, interval = estimate(ratings, log_probabilities)
        sides[colour] = {"estimate": best, "interval": interval, "moves": moves}
    return {"scale": "lichess_rapid", "ratings": ratings, "sides": sides}


def win_percent(centipawns: int) -> float:
    """Lichess's Win%: the chance of winning, 0-100, of a side with this evaluation, capped at +-1000 centipawns
    (https://lichess.org/page/accuracy; scalachess WinPercent.fromCentiPawns)."""
    capped = max(-CENTIPAWN_CAP, min(CENTIPAWN_CAP, centipawns))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * capped)) - 1)


def move_accuracy(before: int, after: int) -> float:
    """Lichess's accuracy of a move, 0-100, from the mover's evaluation before and after it, including lichess's
    +1 "uncertainty bonus" (lila AccuracyPercent.fromWinPercents)."""
    drop = win_percent(before) - win_percent(after)
    if drop <= 0:
        return 100.0
    return max(0.0, min(100.0, 103.1668100711649 * math.exp(-0.04354415386753951 * drop) - 3.166924740191411 + 1))


def centipawns(score: chess.engine.Score) -> int:
    """An evaluation in centipawns, a mate counting as +-CENTIPAWN_CAP, as lichess counts it."""
    mate = score.mate()
    if mate is not None:
        return CENTIPAWN_CAP if mate > 0 else -CENTIPAWN_CAP  # mate 0: the side to move is mated
    return max(-CENTIPAWN_CAP, min(CENTIPAWN_CAP, score.score() or 0))


def mover_evaluations(fen: str, uci: str, evaluator: Evaluator) -> tuple[int, int] | None:
    """The mover's evaluation in centipawns before and after its move, or None when a position isn't valid chess,
    as after a chaos move can happen (ADR 0006), so an engine can't judge it. A position the move ends the game in
    isn't searched: checkmate is the mover's best result, and any other end a draw."""
    board = chess.Board(fen)
    before_valid = board.is_valid()
    board.push_uci(uci)
    if not (before_valid and board.is_valid()):
        return None
    before = centipawns(evaluator.evaluate(fen))
    if board.is_checkmate():
        return before, CENTIPAWN_CAP
    if board.is_stalemate() or board.is_insufficient_material():
        return before, 0
    return before, -centipawns(evaluator.evaluate(board.fen()))


def centipawn_loss_and_accuracy(log_events: list[dict[str, Any]], evaluator: Evaluator) -> dict[str, Any]:
    """The centipawn_loss_and_accuracy section: each LLM side's legal moves judged by the engine."""
    sides: dict[Color, dict[str, Any] | None] = dict.fromkeys(COLORS)
    for colour in llm_colours(log_events[0]):
        moves: list[dict[str, Any]] = []
        losses: list[float] = []
        accuracies: list[float] = []
        for moved, ply, fen, uci in scored_moves(log_events):
            evaluations = mover_evaluations(fen, uci, evaluator) if moved == colour else None
            if evaluations is None:
                continue
            before, after = evaluations
            losses.append(max(0, before - after))
            accuracies.append(move_accuracy(before, after))
            moves.append(
                {
                    "ply": ply,
                    "fen": fen,
                    "move": uci,
                    "evaluation_before": before,
                    "evaluation_after": after,
                    "centipawn_loss": losses[-1],
                    "accuracy": accuracies[-1],
                }
            )
        sides[colour] = {"average_centipawn_loss": mean(losses), "accuracy": mean(accuracies), "moves": moves}
    return {"search": dict(evaluator.search), "sides": sides}


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def analyse_game(log: Path, move_model: MoveModel | None, evaluator: Evaluator | None = None) -> Path:
    """Analyse a game log into its analysis file, replacing any earlier one, and return the file's path.

    Each analysis needs its engine: without the move model (or when Maia-2 can't start), move_quality is null,
    and without the evaluator (or when Stockfish can't start), centipawn_loss_and_accuracy is null. versions
    names only the engines that ran."""
    events = read_events(log)
    versions: dict[str, str] = {}
    quality = diagnostics = None
    if move_model is not None:
        try:
            quality = move_quality(events, move_model)
            versions["move_model"] = move_model.version
        except Maia2Unavailable as error:
            logging.getLogger(__name__).warning("no Move-quality estimate for %s: %s", log, error)
    if evaluator is not None:
        try:
            diagnostics = centipawn_loss_and_accuracy(events, evaluator)
            versions["stockfish"] = evaluator.version
        except StockfishUnavailable as error:
            logging.getLogger(__name__).warning("no centipawn loss or accuracy for %s: %s", log, error)
    analysis = {
        "analysis_version": ANALYSIS_VERSION,
        "game_log": log.name,
        "game_id": events[0].get("game_id"),
        "analysed_at": now(),
        "versions": versions,
        "move_quality": quality,
        "centipawn_loss_and_accuracy": diagnostics,
    }
    path = analysis_path(log)
    partial = path.with_name(path.name + ".partial")  # renamed into place, so a reader never sees half a file
    partial.write_text(json.dumps(analysis, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    partial.replace(path)
    return path


def is_finished(log: Path) -> bool:
    return any(event["type"] == "game_end" for event in read_events(log))


def analyse_games(
    games_dir: Path, move_model: MoveModel | None, evaluator: Evaluator | None = None, reanalyse: bool = False
) -> list[Path]:
    """Analyse every finished game in games_dir that has no analysis file yet, or every finished game if reanalyse,
    oldest first. Returns the analysis files written."""
    logs = sorted(games_dir.glob("*.jsonl"))
    return [
        analyse_game(log, move_model, evaluator)
        for log in logs
        if (reanalyse or not analysis_path(log).exists()) and is_finished(log)
    ]

