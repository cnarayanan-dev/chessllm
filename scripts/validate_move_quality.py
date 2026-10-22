"""Validate the Move-quality estimate on human games of known rating, and record whether it passed (#48, ADR 0005).

The sample is rated Rapid games from the Lichess open database (https://database.lichess.org), taken from the start
of one month's file, January 2025 (after the games Maia-2 was trained on, which end in 2023). Only the start of the
file is read, streamed and decompressed on the fly, until every rating band has its quota; the selected games are
written without their clock comments to SAMPLE_FILE, which is committed, with where they came from in SAMPLE_SOURCE.
So a run needs no network, and the same sample gives the same report.

For each player of each sampled game, the estimator (chessllm.analytics.analysis.estimate over the move model's grid, as for an
LLM side) is run on every move they played, and its most likely rating compared with the rating they had at the
start of the game. Both are converted from Lichess Rapid to chess.com Rapid (chessllm.analytics.rating_scales), the scale of
the pass mark, so an error is in chess.com points. The pass mark (ADR 0005), in every band:

- per game: the root-mean-square error of one player's estimate is at most PER_GAME_TOLERANCE (±250);
- pooled: the root-mean-square error of POOL_SIZE (20) player-games' moves pooled into one estimate, against their
  mean rating, is at most POOLED_TOLERANCE (±100);
- bias: in a band at or below chess.com 600 (its centre converted), the mean error is at most BIAS_TOLERANCE (100).

The outcome goes to chessllm/analytics/move_quality_validation.json (chessllm.core.config.VALIDATION_FILE), which marks the
leaderboard's estimates validated only when it passed for the same move model and grid; the report goes to REPORT_FILE.

Run:
    uv run python -m scripts.validate_move_quality fetch   # (re)build the sample from the network
    uv run python -m scripts.validate_move_quality         # run Maia-2 over the sample, write report and outcome
"""

import argparse
import hashlib
import io
import json
import math
import re
import sys
from collections.abc import Generator, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, cast

import chess
import chess.pgn

from chessllm.analytics.analysis import estimate
from chessllm.engines.move_model import MoveModel
from chessllm.core.config import VALIDATION_FILE
from chessllm.analytics.rating_scales import chess_com_rapid, lichess_floor

ROOT = Path(__file__).resolve().parent.parent
MONTH = "2025-01"
DATABASE_URL = f"https://database.lichess.org/standard/lichess_db_standard_rated_{MONTH}.pgn.zst"
SAMPLE_FILE = ROOT / "docs" / "research" / "move-quality-validation-sample.pgn"
SAMPLE_SOURCE = SAMPLE_FILE.with_suffix(".json")
REPORT_FILE = ROOT / "docs" / "research" / "move-quality-validation.md"

GAMES_PER_BAND = 50
POOL_SIZE = 20
PER_GAME_TOLERANCE = 250.0
POOLED_TOLERANCE = 100.0
BIAS_TOLERANCE = 100.0
LOW_BAND_CEILING = 600  # chess.com Rapid: bands centred at or below it must show no systematic bias
MIN_MOVES_PER_SIDE = 10
TERMINATIONS = ("Normal", "Time forfeit")  # not "Abandoned" or "Rules infraction"


@dataclass(frozen=True)
class Band:
    """A rating band on the Lichess Rapid scale, the database's: low ≤ rating < high."""

    low: int
    high: int

    def __contains__(self, rating: int) -> bool:
        return self.low <= rating < self.high

    @property
    def centre(self) -> float:
        return (self.low + self.high) / 2

    def chess_com(self) -> tuple[int, int]:
        """The band's ends converted to chess.com Rapid."""
        return round(chess_com_rapid(self.low)), round(chess_com_rapid(self.high))

    def is_low(self) -> bool:
        """At or below chess.com 600, by its centre: where the pass mark asks for no systematic bias."""
        return chess_com_rapid(self.centre) <= LOW_BAND_CEILING

    def __str__(self) -> str:
        return f"{self.low}-{self.high}"


# Lichess Rapid 800-2000 in steps of 200: about chess.com Rapid 150-1790, which spans the pass mark's 400-1600 and
# goes a band lower, towards where our LLMs play.
BANDS = [Band(low, low + 200) for low in range(800, 2000, 200)]


# --- Selecting the sample -------------------------------------------------------------------------------------------


@dataclass
class Sample:
    pgn: str  # the selected games, without comments, in the order they were read
    games_read: int  # games read from the database to fill every band


def raw_games(lines: Iterable[str]) -> Iterator[str]:
    """The games in PGN text, one string each; a game starts at its [Event] tag."""
    game: list[str] = []
    for line in lines:
        if line.startswith("[Event ") and game:
            yield "".join(game)
            game = []
        game.append(line)
    if game:
        yield "".join(game)


TAG = re.compile(r'^\[(\w+) "(.*)"\]\s*$', re.MULTILINE)


def band_of(headers: dict[str, str], bands: Sequence[Band]) -> Band | None:
    """The band both players are in, if the game is a rated Rapid game between two humans that ended normally."""
    if not headers.get("Event", "").startswith("Rated Rapid "):
        return None
    if headers.get("Termination") not in TERMINATIONS or "BOT" in (headers.get("WhiteTitle"), headers.get("BlackTitle")):
        return None
    try:
        white, black = int(headers["WhiteElo"]), int(headers["BlackElo"])
    except (KeyError, ValueError):
        return None
    return next((band for band in bands if white in band and black in band), None)


def select_sample(lines: Iterable[str], bands: Sequence[Band] = BANDS, per_band: int = GAMES_PER_BAND) -> Sample:
    """The first per_band games of each band, read from lines of a Lichess database file; reading stops as soon as
    every band is full."""
    taken: dict[Band, int] = dict.fromkeys(bands, 0)
    selected: list[str] = []
    games_read = 0
    for text in raw_games(lines):
        games_read += 1
        band = band_of(dict(TAG.findall(text.split("\n\n", 1)[0])), bands)
        if band is None or taken[band] >= per_band:
            continue
        game = chess.pgn.read_game(io.StringIO(text))
        if game is None or game.errors or len(list(game.mainline_moves())) < 2 * MIN_MOVES_PER_SIDE:
            continue
        selected.append(game.accept(chess.pgn.StringExporter(columns=None, comments=False)) + "\n\n")
        taken[band] += 1
        if all(count >= per_band for count in taken.values()):
            break
    return Sample("".join(selected), games_read)


class _Chunks(io.RawIOBase):
    """A readable stream over an iterator of byte chunks, for zstandard's stream reader."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._buffer = b""

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        while not self._buffer:
            chunk = next(self._chunks, None)
            if chunk is None:
                return b""
            self._buffer = chunk
        size = len(self._buffer) if size < 0 else size
        data, self._buffer = self._buffer[:size], self._buffer[size:]
        return data


def database_lines(url: str = DATABASE_URL) -> Generator[str]:
    """The lines of a Lichess database file, streamed and decompressed as they are read; closing the generator
    closes the download, so only as much of the file is fetched as is read."""
    import httpx
    import zstandard

    with httpx.stream("GET", url, timeout=60, follow_redirects=True) as response:
        response.raise_for_status()
        reader = zstandard.ZstdDecompressor().stream_reader(
            cast(IO[bytes], _Chunks(response.iter_raw())), read_across_frames=True
        )
        yield from io.TextIOWrapper(reader, encoding="utf-8", newline="")


# --- Validating -----------------------------------------------------------------------------------------------------


@dataclass
class PlayerGame:
    """One player's side of a sampled game: their rating and the log-probabilities of their moves."""

    game: str
    rating: int
    moves: list[list[float]]


@dataclass
class BandResult:
    band: Band
    ratings: list[int]  # the move model's grid
    player_games: int = 0
    errors: list[float] = field(default_factory=list)  # chess.com: estimate less rating, per player-game
    lichess_errors: list[float] = field(default_factory=list)  # the same on the Lichess scale
    pooled_errors: list[float] = field(default_factory=list)  # chess.com, per pool of pool_size player-games
    floor_clipped: int = 0  # estimates at the grid's lowest rating, which stands for every rating under it
    ceiling_clipped: int = 0

    @property
    def bias(self) -> float:
        return mean(self.errors)

    @property
    def rmse(self) -> float:
        return root_mean_square(self.errors)

    @property
    def pooled_rmse(self) -> float:
        return root_mean_square(self.pooled_errors)

    def failures(self) -> list[str]:
        """Why the band misses the pass mark; empty if it meets it."""
        if not self.errors:
            return [f"Lichess {self.band}: no games in the sample"]
        reasons = []
        if self.rmse > PER_GAME_TOLERANCE:
            reasons.append(f"Lichess {self.band}: per-game error ±{self.rmse:.0f} exceeds ±{PER_GAME_TOLERANCE:.0f}")
        if not self.pooled_errors:
            reasons.append(f"Lichess {self.band}: too few player-games for one pool")
        elif self.pooled_rmse > POOLED_TOLERANCE:
            reasons.append(
                f"Lichess {self.band}: pooled error ±{self.pooled_rmse:.0f} exceeds ±{POOLED_TOLERANCE:.0f}"
            )
        if self.band.is_low() and abs(self.bias) > BIAS_TOLERANCE:
            reasons.append(
                f"Lichess {self.band} (chess.com ≤ {LOW_BAND_CEILING}): bias {self.bias:+.0f} exceeds "
                f"±{BIAS_TOLERANCE:.0f}"
            )
        return reasons


@dataclass
class Validation:
    move_model: str
    ratings: list[int]
    pool_size: int
    bands: list[BandResult]

    @property
    def reasons(self) -> list[str]:
        return [reason for band in self.bands for reason in band.failures()]

    @property
    def passed(self) -> bool:
        return not self.reasons


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def root_mean_square(values: Sequence[float]) -> float:
    return math.sqrt(mean([value * value for value in values])) if values else math.nan


def player_games(pgn: str, move_model: MoveModel) -> Iterator[PlayerGame]:
    """Each player of each game in pgn, White then Black, with every move they played scored by the move model."""
    stream = io.StringIO(pgn)
    while (game := chess.pgn.read_game(stream)) is not None:
        moves: dict[chess.Color, list[list[float]]] = {chess.WHITE: [], chess.BLACK: []}
        board = game.board()
        for move in game.mainline_moves():
            probabilities = move_model.probabilities(board.fen(), move.uci())
            moves[board.turn].append([math.log(p) for p in probabilities])
            board.push(move)
        site = game.headers.get("Site", "")
        yield PlayerGame(site, int(game.headers["WhiteElo"]), moves[chess.WHITE])
        yield PlayerGame(site, int(game.headers["BlackElo"]), moves[chess.BLACK])


def validate(
    pgn: str, move_model: MoveModel, bands: Sequence[Band] = BANDS, pool_size: int = POOL_SIZE
) -> Validation:
    ratings = list(move_model.ratings)
    results = {band: BandResult(band, ratings) for band in bands}
    in_band: dict[Band, list[PlayerGame]] = {band: [] for band in bands}
    for player in player_games(pgn, move_model):
        band = next((band for band in bands if player.rating in band), None)
        if band is None or not player.moves:
            continue
        in_band[band].append(player)
        result = results[band]
        best, _ = estimate(ratings, player.moves)
        assert best is not None
        result.player_games += 1
        result.errors.append(chess_com_rapid(best) - chess_com_rapid(player.rating))
        result.lichess_errors.append(best - player.rating)
        result.floor_clipped += best == ratings[0]
        result.ceiling_clipped += best == ratings[-1]
    for band, players in in_band.items():
        for start in range(0, len(players) - pool_size + 1, pool_size):
            pool = players[start : start + pool_size]
            best, _ = estimate(ratings, [move for player in pool for move in player.moves])
            assert best is not None
            truth = mean([chess_com_rapid(player.rating) for player in pool])
            results[band].pooled_errors.append(chess_com_rapid(best) - truth)
    return Validation(move_model.version, ratings, pool_size, [results[band] for band in bands])


# --- Report and outcome ---------------------------------------------------------------------------------------------


def shown(path: Path) -> str:
    """A path as the outcome and report name it: relative to the repository when it's inside it."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def render_report(validation: Validation, sample: Path, source: dict[str, Any]) -> str:
    grid = validation.ratings
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    lines = [
        "# Validation of the Move-quality estimate on Lichess Rapid games",
        "",
        "Written by `uv run python -m scripts.validate_move_quality` (#48); rerunning it on the same sample gives "
        "this report again. Method and pass mark are in ADR 0005 and the script's docstring.",
        "",
        f"**{'Passed' if validation.passed else 'Failed'}**: the leaderboard shows the Move-quality estimate as "
        f"{'validated' if validation.passed else 'unvalidated'} for this move model and grid.",
        "",
    ]
    if not validation.passed:
        lines += ["Why it failed:", "", *(f"- {reason}" for reason in validation.reasons), ""]
    lines += [
        "## Sample",
        "",
        f"- Source: {source.get('url', 'unknown')} (the start of the file only)",
        f"- Games read from its start until every band had {source.get('per_band', '?')} games: "
        f"{source.get('games_read', '?')}",
        f"- Sample: `{shown(sample)}`, SHA-256 `{digest}`",
        f"- Selection: rated Rapid games (Event \"Rated Rapid ...\", tournaments included) between two humans "
        f"(no BOT title), ended normally or on time, at least {MIN_MOVES_PER_SIDE} moves a side, both players in the "
        "same band; the first games of each band in file order. Each player is a player-game, rated at their "
        "rating at the start of the game.",
        f"- Move model: {validation.move_model}; grid (Lichess Rapid) {grid[0]}-{grid[-1]}: "
        + ", ".join(str(rating) for rating in grid),
        "",
        "## Bands",
        "",
        "Bands are on the Lichess Rapid scale, the database's. Errors are on the chess.com Rapid scale, the pass "
        "mark's: estimate and rating each converted with `chessllm.analytics.rating_scales` (ChessGoals' table, extended along "
        f"its lowest segment below Lichess {lichess_floor()}, chess.com 815, where the conversion is an "
        "extrapolation).",
        "",
        "| Lichess Rapid | chess.com Rapid | Bias held to ≤ 600 |",
        "| --- | --- | --- |",
    ]
    for result in validation.bands:
        low, high = result.band.chess_com()
        lines.append(f"| {result.band} | {low}-{high} | {'yes' if result.band.is_low() else 'no'} |")
    lines += [
        "",
        "## Results",
        "",
        f"Pass mark: per-game error ±{PER_GAME_TOLERANCE:.0f}, pooled error over {validation.pool_size} "
        f"player-games ±{POOLED_TOLERANCE:.0f} (root mean square, chess.com), and a bias within "
        f"±{BIAS_TOLERANCE:.0f} in the bands at or below chess.com {LOW_BAND_CEILING}. Bias is the mean error "
        "(estimate less rating); pooled errors pool the moves of consecutive player-games of a band into one "
        "estimate, against their mean rating. At the grid's floor or ceiling the grid point is taken as the estimate "
        "(the leaderboard shows only a bound there).",
        "",
        "| Lichess Rapid | Player-games | Bias | Per-game error | Pooled error (pools) | Bias, Lichess | "
        "Per-game error, Lichess | At grid floor | At grid ceiling | Meets the pass mark |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in validation.bands:
        if not result.errors:
            lines.append(f"| {result.band} | 0 | | | | | | | | no |")
            continue
        pooled = f"±{result.pooled_rmse:.0f} ({len(result.pooled_errors)})" if result.pooled_errors else "—"
        lines.append(
            f"| {result.band} | {result.player_games} | {result.bias:+.0f} | ±{result.rmse:.0f} | {pooled} | "
            f"{mean(result.lichess_errors):+.0f} | ±{root_mean_square(result.lichess_errors):.0f} | "
            f"{share(result.floor_clipped, result.player_games)} | "
            f"{share(result.ceiling_clipped, result.player_games)} | "
            f"{'no' if result.failures() else 'yes'} |"
        )
    lines += [
        "",
        "## Reading it",
        "",
        f"- The grid's lowest rating, Lichess {grid[0]}, stands for every player below the next one, so the estimator "
        f"cannot say a player is weaker than about chess.com {chess_com_rapid(grid[0]):.0f}. Players below it are "
        "estimated at the floor at best, which shows as a positive bias in the bands under it; the share at the grid "
        "floor says how often that happened.",
        "- Below Lichess 1290 both the estimate and the rating go through the extrapolated conversion, so the "
        "chess.com errors there are 1.35 times the Lichess ones and only as good as the extrapolation.",
        "- Bias by band, lowest to highest: "
        + ", ".join(f"{result.bias:+.0f}" for result in validation.bands if result.errors)
        + ". Falling from positive to negative, it means the estimates are pulled towards the middle of the grid: "
        "weak players come out too strong and strong players too weak.",
        "",
    ]
    return "\n".join(lines)


def share(count: int, total: int) -> str:
    return f"{100 * count / total:.0f}%"


def write_outcome(path: Path, validation: Validation, report: Path) -> None:
    outcome = {
        "move_model": validation.move_model,
        "ratings": validation.ratings,
        "passed": validation.passed,
        "report": shown(report),
    }
    path.write_text(json.dumps(outcome, indent=1) + "\n", encoding="utf-8")


def run(
    sample: Path,
    move_model: MoveModel,
    report: Path = REPORT_FILE,
    outcome: Path = VALIDATION_FILE,
    bands: Sequence[Band] = BANDS,
    pool_size: int = POOL_SIZE,
) -> Validation:
    """Validate the move model on the sample and write the report and the outcome the leaderboard reads."""
    validation = validate(sample.read_text(encoding="utf-8"), move_model, bands, pool_size)
    source_file = sample.with_suffix(".json")
    source = json.loads(source_file.read_text(encoding="utf-8")) if source_file.exists() else {}
    report.write_text(render_report(validation, sample, source), encoding="utf-8")
    write_outcome(outcome, validation, report)
    return validation


def fetch(per_band: int = GAMES_PER_BAND) -> Sample:
    """Build the sample from the start of the month's database file and write it and its source."""
    lines = database_lines()
    try:
        sample = select_sample(lines, BANDS, per_band)
    finally:
        lines.close()
    SAMPLE_FILE.write_text(sample.pgn, encoding="utf-8")
    source = {"url": DATABASE_URL, "games_read": sample.games_read, "per_band": per_band}
    SAMPLE_SOURCE.write_text(json.dumps(source, indent=1) + "\n", encoding="utf-8")
    return sample


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m scripts.validate_move_quality", description=__doc__.split("\n")[0])
    parser.add_argument("command", nargs="?", choices=("fetch", "run"), default="run")
    parser.add_argument("--games-per-band", type=int, default=GAMES_PER_BAND)
    args = parser.parse_args(argv)
    if args.command == "fetch":
        sample = fetch(args.games_per_band)
        print(f"read {sample.games_read} games; sample written to {shown(SAMPLE_FILE)}")
        return
    from chessllm.engines.maia2_model import Maia2MoveModel

    with Maia2MoveModel() as move_model:
        validation = run(SAMPLE_FILE, move_model)
    print(f"{'passed' if validation.passed else 'failed'}; report written to {shown(REPORT_FILE)}", file=sys.stderr)


if __name__ == "__main__":
    main()
