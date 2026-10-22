"""A Player configuration's Move-quality estimate: the moves of all its analysed games pooled into one
maximum-likelihood rating (chessllm.analytics.analysis.estimate over every move together, not the mean of the per-game
estimates), converted from Lichess Rapid to chess.com Rapid (chessllm.analytics.rating_scales). ADR 0005.

Only analysis files made with the same move model version and rating grid are pooled: their log-probabilities are
over the same ratings and from the same model. If a configuration's games were analysed with more than one, the
estimate comes from the one covering the most games (then the most moves, then the latest version name), and games
and moves say how many went into it. `analyse-games --all` brings every game onto the current model.

The grid's ends are honest bounds, not estimates. Maia-2's lowest rating, Lichess 1000, stands for every player under
1100, so a likelihood that is still rising at the grid's floor says only "this low or lower". Then:
- the most likely rating at the floor (or ceiling) gives no estimate, only the interval's other end as a bound;
- an interval that reaches the floor (or ceiling) is open on that side (low or high is None).
The ends that remain carry the conversion's own uncertainty, which grows below the conversion table's floor
(chess.com Rapid 815), so an estimate down there has a wider interval than one inside the table.

The estimate is shown as unvalidated until the validation (#48) has passed for the move model and grid it comes from.
The validation writes its outcome to chessllm.core.config.VALIDATION_FILE:

    {"move_model": "maia2 0.11.0, rapid model, ...", "ratings": [1000, 1100, ...], "passed": true,
     "report": "docs/research/..."}

and an estimate is validated only if that file exists, passed, and names the same move model version and grid."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from chessllm.analytics.analysis import estimate
from chessllm.analytics.rating_scales import CHESS_COM_MINIMUM, chess_com_rapid, conversion_margin, is_extrapolated


class LichessRapidEstimate(BaseModel):
    """The pooled estimate on the move model's own scale, before conversion: the most likely rating on the grid and
    its 95% interval, clipped to the grid."""

    estimate: int
    interval: tuple[int, int]
    ratings: list[int]  # the grid


class MoveQuality(BaseModel):
    """A Player configuration's Move-quality estimate on the chess.com Rapid scale. Never blended with the Rating."""

    estimate: int | None  # None at the grid's floor or ceiling: then only low or high is known, a bound
    low: int | None  # the 95% interval's lower end; None when it reaches the grid's floor (open below)
    high: int | None  # its upper end; None when it reaches the grid's ceiling (open above)
    extrapolated: bool  # part of the interval lies outside the conversion table, so the conversion is extrapolated
    validated: bool  # False until the validation has passed for this move model and grid
    games: int  # analysed games pooled
    moves: int  # moves scored in them
    move_model: str  # the move model version the analyses name
    lichess_rapid: LichessRapidEstimate


GridKey = tuple[str, tuple[int, ...]]  # (move model version, rating grid)


@dataclass
class PooledMoves:
    games: int = 0
    moves: list[list[float]] = field(default_factory=list)


@dataclass
class ConfigurationMoves:
    """The scored moves of one Player configuration's analysed games, kept apart per move model and grid."""

    pools: dict[GridKey, PooledMoves] = field(default_factory=dict)

    def add(self, key: GridKey, moves: list[list[float]]) -> None:
        pool = self.pools.setdefault(key, PooledMoves())
        pool.games += 1
        pool.moves.extend(moves)


def read_analysed_moves(path: Path) -> dict[str, tuple[GridKey, list[list[float]]]]:
    """Each LLM side's scored moves in an analysis file, as {colour: ((version, grid), log-probabilities per move)}.
    Empty if there is no analysis file or it can't be read: the game is then left out of the estimate."""
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
        version = analysis["versions"]["move_model"]
        quality = analysis["move_quality"]
        grid = tuple(int(rating) for rating in quality["ratings"])
        sides: dict[str, tuple[GridKey, list[list[float]]]] = {}
        for colour, side in quality["sides"].items():
            if side is None:
                continue
            moves = [[float(value) for value in move["log_probabilities"]] for move in side["moves"]]
            if all(len(move) == len(grid) for move in moves):
                sides[colour] = ((str(version), grid), moves)
        return sides
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def read_validation(path: Path) -> GridKey | None:
    """The move model version and grid the validation passed for, or None if it hasn't passed (or hasn't run)."""
    try:
        record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if record.get("passed") is not True:
            return None
        return str(record["move_model"]), tuple(int(rating) for rating in record["ratings"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def move_quality(configuration: ConfigurationMoves, validated_for: GridKey | None) -> MoveQuality | None:
    """The pooled Move-quality estimate, or None if no analysed game has a scored move."""
    candidates = [(key, pool) for key, pool in configuration.pools.items() if pool.moves]
    if not candidates:
        return None
    (version, grid), pool = max(candidates, key=lambda item: (item[1].games, len(item[1].moves), item[0][0]))
    best, interval = estimate(grid, pool.moves)
    assert best is not None and interval is not None
    low, high = interval
    return MoveQuality(
        estimate=None if best in (grid[0], grid[-1]) else round(chess_com_rapid(best)),
        low=None if low <= grid[0] else round(max(CHESS_COM_MINIMUM, chess_com_rapid(low) - conversion_margin(low))),
        high=None if high >= grid[-1] else round(chess_com_rapid(high) + conversion_margin(high)),
        extrapolated=is_extrapolated(low) or is_extrapolated(high),
        validated=validated_for == (version, grid),
        games=pool.games,
        moves=len(pool.moves),
        move_model=version,
        lichess_rapid=LichessRapidEstimate(estimate=best, interval=(low, high), ratings=list(grid)),
    )
