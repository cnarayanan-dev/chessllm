"""The validation of the Move-quality estimate on human games of known rating (scripts/validate_move_quality.py).

The sample is a tiny PGN written here, in the Lichess database's form, and the move model a fake whose probabilities
peak at a chosen Lichess rating. Its grid is ChessGoals' table rows, so estimates convert to chess.com exactly:
Lichess Rapid 1290 → chess.com Rapid 815, 1490 → 1085, 1615 → 1255, 1740 → 1420."""

import json
import math

import pytest

from scripts.validate_move_quality import Band, select_sample, validate, run

# Twenty plies of a quiet game: ten moves a side, the least a sampled game may have.
MOVES = "1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O O-O 7. Re1 a6 8. a4 h6 9. h3 Re8 10. Nbd2 Be6"
TABLE_GRID = [1290, 1490, 1615, 1740]


def pgn_game(
    white: int,
    black: int,
    event: str = "Rated Rapid game",
    site: str = "x",
    moves: str = MOVES,
    white_title: str | None = None,
    termination: str = "Normal",
) -> str:
    """One game as the Lichess database writes it, with clock comments."""
    headers = [
        f'[Event "{event}"]',
        f'[Site "https://lichess.org/{site}"]',
        '[White "a"]',
        '[Black "b"]',
        '[Result "1-0"]',
        f'[WhiteElo "{white}"]',
        f'[BlackElo "{black}"]',
        *([f'[WhiteTitle "{white_title}"]'] if white_title else []),
        '[TimeControl "600+0"]',
        f'[Termination "{termination}"]',
    ]
    commented = " ".join(f"{token} {{ [%clk 0:10:00] }}" if "." not in token else token for token in moves.split())
    return "\n".join(headers) + "\n\n" + commented + " 1-0\n\n"


def sites(pgn: str) -> list[str]:
    return [line.split("/")[-1].rstrip('"]') for line in pgn.splitlines() if line.startswith("[Site ")]


class FakeMoveModel:
    """Every move most likely for a player rated peak (White's peak, then Black's), falling off around it."""

    version = "fake-move-model 1"

    def __init__(self, white_peak: int, black_peak: int | None = None, ratings: list[int] = TABLE_GRID) -> None:
        self.ratings = ratings
        self.peaks = {"w": white_peak, "b": black_peak if black_peak is not None else white_peak}

    def probabilities(self, fen: str, move: str) -> list[float]:
        peak = self.peaks[fen.split(" ")[1]]
        return [0.4 * math.exp(-(((rating - peak) / 100) ** 2)) for rating in self.ratings]


def test_the_sample_holds_rated_rapid_games_whose_players_are_both_in_one_band():
    bands = [Band(1000, 1200), Band(1400, 1600)]
    database = "".join(
        [
            pgn_game(1450, 1500, site="rapid1"),
            pgn_game(1450, 1500, event="Rated Blitz game", site="blitz"),
            pgn_game(1450, 1500, event="Casual Rapid game", site="casual"),
            pgn_game(1450, 1650, site="twobands"),
            pgn_game(1450, 1500, white_title="BOT", site="bot"),
            pgn_game(1450, 1500, moves="1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7#", site="short"),
            pgn_game(1450, 1500, termination="Abandoned", site="abandoned"),
            pgn_game(300, 350, site="below"),
            pgn_game(1100, 1050, event="Rated Rapid tournament https://lichess.org/tournament/x", site="rapid2"),
        ]
    )

    sample = select_sample(database.splitlines(keepends=True), bands, per_band=5)

    assert sites(sample.pgn) == ["rapid1", "rapid2"]
    assert sample.games_read == 9
    assert "%clk" not in sample.pgn


def test_reading_stops_once_every_band_has_its_quota():
    bands = [Band(1000, 1200), Band(1400, 1600)]
    filled = pgn_game(1450, 1500, site="a") + pgn_game(1100, 1100, site="b") + pgn_game(1500, 1500, site="c")

    def database():
        yield from filled.splitlines(keepends=True)
        raise AssertionError("read past the point where every band was full")

    sample = select_sample(database(), bands, per_band=1)

    assert sites(sample.pgn) == ["a", "b"]


def test_each_players_error_is_their_estimate_less_their_rating_on_the_chess_com_scale():
    # Every move is likeliest at Lichess 1490 (chess.com 1085). White is rated 1290 (815), Black 1615 (1255).
    sample = pgn_game(1290, 1615)

    [band] = validate(sample, FakeMoveModel(1490), bands=[Band(1200, 1700)], pool_size=2).bands

    assert band.player_games == 2
    assert band.errors == [270, -170]
    assert band.bias == 50
    assert band.rmse == pytest.approx(225.6, abs=0.1)  # √((270² + 170²) / 2)
    # The one pool of both players: its pooled estimate is 1085 against their mean rating (815 + 1255) / 2 = 1035.
    assert band.pooled_errors == [50]


def test_the_pooled_estimate_comes_from_the_pools_moves_together():
    # White's moves peak at 1290 and Black's at 1740; pooled, ten moves each, the likelihood peaks between them,
    # at 1490 on this grid (1085), whatever each player's own estimate.
    sample = pgn_game(1490, 1490)

    [band] = validate(sample, FakeMoveModel(1290, 1740), bands=[Band(1400, 1600)], pool_size=2).bands

    assert band.errors == [815 - 1085, 1420 - 1085]
    assert band.pooled_errors == [0]


def test_estimates_at_the_grids_floor_are_counted_as_clipped():
    sample = pgn_game(1490, 1490)

    [band] = validate(sample, FakeMoveModel(1290, 1490), bands=[Band(1400, 1600)], pool_size=2).bands

    assert band.floor_clipped == 1


def test_a_move_model_within_the_pass_mark_passes(tmp_path):
    sample = tmp_path / "sample.pgn"
    sample.write_text("".join(pgn_game(1490, 1615, site=f"g{n}") for n in range(2)), encoding="utf-8")
    report, outcome = tmp_path / "report.md", tmp_path / "move_quality_validation.json"

    validation = run(sample, FakeMoveModel(1490, 1615), report, outcome, bands=[Band(1400, 1700)], pool_size=2)

    assert validation.passed
    assert json.loads(outcome.read_text(encoding="utf-8")) == {
        "move_model": "fake-move-model 1",
        "ratings": TABLE_GRID,
        "passed": True,
        "report": str(report),
    }
    assert "**Passed**" in report.read_text(encoding="utf-8")


def test_a_move_model_off_the_mark_fails_and_the_report_says_why(tmp_path):
    # Everyone is estimated at 1740 (1420), while White is rated 1290 (815) and Black 1490 (1085).
    sample = tmp_path / "sample.pgn"
    sample.write_text(pgn_game(1290, 1490), encoding="utf-8")
    report, outcome = tmp_path / "report.md", tmp_path / "move_quality_validation.json"

    validation = run(sample, FakeMoveModel(1740), report, outcome, bands=[Band(1200, 1500)], pool_size=2)

    assert not validation.passed
    assert json.loads(outcome.read_text(encoding="utf-8"))["passed"] is False
    text = report.read_text(encoding="utf-8")
    assert "**Failed**" in text
    assert "per-game error" in text and "pooled error" in text


def test_a_low_band_with_a_systematic_bias_fails():
    # Lichess 1000-1200 is about chess.com 424-694, a band at or below 600. Everyone is estimated one grid step high.
    sample = pgn_game(1100, 1100)
    model = FakeMoveModel(1200, ratings=[1000, 1100, 1200, 1300])

    validation = validate(sample, model, bands=[Band(1000, 1200)], pool_size=2)

    assert not validation.passed
    assert any("bias" in reason for reason in validation.reasons)


def test_rerunning_with_the_same_sample_gives_the_same_report(tmp_path):
    sample = tmp_path / "sample.pgn"
    sample.write_text(pgn_game(1290, 1615) + pgn_game(1490, 1490, site="y"), encoding="utf-8")
    report, outcome = tmp_path / "report.md", tmp_path / "outcome.json"

    run(sample, FakeMoveModel(1490), report, outcome, bands=[Band(1200, 1700)], pool_size=2)
    first = report.read_text(encoding="utf-8")
    run(sample, FakeMoveModel(1490), report, outcome, bands=[Band(1200, 1700)], pool_size=2)

    assert report.read_text(encoding="utf-8") == first
