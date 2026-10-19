"""Game analysis: one analysis file per finished game, next to its log, holding each LLM side's Move-quality
estimate from a MoveModel. The game log is only read, never changed (ADR 0004, ADR 0005).

The analysis file of games/<stem>.jsonl is games/<stem>.analysis.json:

    {
      "analysis_version": 1,
      "game_log": "<stem>.jsonl",
      "game_id": "...",                  # from game_start
      "analysed_at": "2026-10-19T16:00:00+02:00",
      "versions": {"move_model": "maia2 0.11.0, rapid model, ..."},   # later analyses add theirs, e.g. Stockfish
      "move_quality": {
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
      }
    }

Each move's log_probabilities go with ratings, one per rating, so a Player configuration's pooled estimate is
estimate() over the moves of all its games together.

Run `uv run python -m chessllm.analysis` to analyse every finished game without an analysis file, or with
--all to re-analyse every finished game."""

import argparse
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import chess

from chessllm.game_log import GAMES_DIR, now
from chessllm.move_model import MoveModel

ANALYSIS_VERSION = 1
ANALYSIS_SUFFIX = ".analysis.json"
# Half the 95% quantile of chi-squared with one degree of freedom: the log-likelihood drop at the interval's ends.
LOG_LIKELIHOOD_DROP_95 = 3.8415 / 2

Colour = str  # "white" or "black"


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


def llm_colours(start: dict[str, Any]) -> list[Colour]:
    """The colours played by an LLM. Version 1 logs have one LLM side, llm_color (ADR 0004)."""
    if "log_version" not in start:
        return [start["llm_color"]]
    return [colour for colour in ("white", "black") if start[colour].get("player") == "llm"]


def scored_moves(events: list[dict[str, Any]]) -> list[tuple[Colour, int, str, str]]:
    """The legal moves the LLMs played, as (colour, ply, fen before, UCI). Illegal attempts are skipped, and so are
    chaos moves, which are logged as illegal attempts with a resolution (ADR 0006)."""
    moves = []
    for event in events:
        if event["type"] != "llm_attempt" or event.get("result") != "legal":
            continue
        board = chess.Board(event["fen"])
        # Early version 1 logs have no san; the move as written is legal then, a notation slip at worst.
        move = board.parse_san(event.get("san") or event["move"])
        colour = "white" if board.turn == chess.WHITE else "black"
        moves.append((colour, event["ply"], event["fen"], move.uci()))
    return moves


def analyse_game(log: Path, move_model: MoveModel) -> Path:
    """Analyse a game log into its analysis file, replacing any earlier one, and return the file's path."""
    events = read_events(log)
    start = events[0]
    ratings = list(move_model.ratings)
    sides: dict[Colour, dict[str, Any] | None] = dict.fromkeys(("white", "black"))
    for colour in llm_colours(start):
        played = [(ply, fen, uci) for moved, ply, fen, uci in scored_moves(events) if moved == colour]
        log_probabilities = [[math.log(p) for p in move_model.probabilities(fen, uci)] for _, fen, uci in played]
        moves = [
            {"ply": ply, "fen": fen, "move": uci, "log_probabilities": move}
            for (ply, fen, uci), move in zip(played, log_probabilities)
        ]
        best, interval = estimate(ratings, log_probabilities)
        sides[colour] = {"estimate": best, "interval": interval, "moves": moves}
    analysis = {
        "analysis_version": ANALYSIS_VERSION,
        "game_log": log.name,
        "game_id": start.get("game_id"),
        "analysed_at": now(),
        "versions": {"move_model": move_model.version},
        "move_quality": {"scale": "lichess_rapid", "ratings": ratings, "sides": sides},
    }
    path = analysis_path(log)
    partial = path.with_name(path.name + ".partial")  # renamed into place, so a reader never sees half a file
    partial.write_text(json.dumps(analysis, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    partial.replace(path)
    return path


def is_finished(log: Path) -> bool:
    return any(event["type"] == "game_end" for event in read_events(log))


def analyse_games(games_dir: Path, move_model: MoveModel, reanalyse: bool = False) -> list[Path]:
    """Analyse every finished game in games_dir that has no analysis file yet, or every finished game if reanalyse,
    oldest first. Returns the analysis files written."""
    logs = sorted(games_dir.glob("*.jsonl"))
    return [
        analyse_game(log, move_model)
        for log in logs
        if (reanalyse or not analysis_path(log).exists()) and is_finished(log)
    ]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m chessllm.analysis",
        description="Analyse every finished game without an analysis file: its Move-quality estimate (Maia-2).",
    )
    parser.add_argument("--games-dir", type=Path, default=GAMES_DIR, help="where the game logs are (default: games)")
    parser.add_argument("--all", action="store_true", help="re-analyse every finished game, replacing its analysis")
    args = parser.parse_args(argv)
    from chessllm.maia2_model import Maia2MoveModel

    with Maia2MoveModel() as move_model:
        for path in analyse_games(args.games_dir, move_model, reanalyse=args.all):
            print(f"analysed {path}")


if __name__ == "__main__":
    main()
