"""The leaderboard's Move-quality estimate: each Player configuration's moves from all its analysed games pooled into
one maximum-likelihood rating, converted from Lichess Rapid to chess.com Rapid.

The analysis files are written as a fake MoveModel would score them: every move's log-probability peaks at a chosen
Lichess rating and falls off around it."""

import json
import math

import pytest

from tests.analytics.test_leaderboard import HUMAN, LLAMA, QWEN, by_model, configurations, game, write_log


GRID = list(range(1000, 2001, 100))  # Maia-2's grid: 1000 stands for "under 1100"
MODEL_VERSION = "fake-move-model 1"


def peaked(peak: int, ratings=GRID, width: float = 400) -> list[float]:
    """One move's log-probabilities from the fake MoveModel: most likely for a player rated peak."""
    return [math.log(0.4) - ((rating - peak) / width) ** 2 for rating in ratings]


def analysis(sides, version=MODEL_VERSION, ratings=GRID):
    """An analysis file whose sides are {colour: [peak of each move, ...]}; a colour left out is not an LLM."""
    return {
        "analysis_version": 1,
        "game_log": "x.jsonl",
        "game_id": "x",
        "analysed_at": "2026-10-19T16:00:00+02:00",
        "versions": {"move_model": version},
        "move_quality": {
            "scale": "lichess_rapid",
            "ratings": ratings,
            "sides": {
                colour: (
                    {
                        "estimate": None,  # the leaderboard pools the moves and never reads the per-game numbers
                        "interval": None,
                        "moves": [
                            {"ply": ply, "fen": "", "move": "e2e4", "log_probabilities": peaked(peak, ratings)}
                            for ply, peak in enumerate(sides[colour])
                        ],
                    }
                    if colour in sides
                    else None
                )
                for colour in ("white", "black")
            },
        },
    }


@pytest.fixture
def leaderboard(tmp_path):
    """Writes (game log, analysis file or None) pairs into a temporary games directory and returns the leaderboard."""

    def make(*games, validation=None) -> list[dict]:
        games_dir = tmp_path / "games"
        for number, (events, analysed) in enumerate(games):
            name = f"2026-10-19T10-00-{number:02d}_game"
            write_log(games_dir, name, events)
            if analysed is not None:
                text = analysed if isinstance(analysed, str) else json.dumps(analysed)
                (games_dir / f"{name}.analysis.json").write_text(text, encoding="utf-8")
        validation_file = tmp_path / "move_quality_validation.json"
        if validation is not None:
            validation_file.write_text(json.dumps(validation), encoding="utf-8")
        return configurations(games_dir, move_quality_validation=validation_file)

    return make


def test_a_configuration_with_analysed_games_has_a_move_quality_estimate_on_the_chess_com_scale(leaderboard):
    [llama] = leaderboard((game(HUMAN, LLAMA, "1-0"), analysis({"black": [1400] * 10})))

    quality = llama["move_quality"]
    # Lichess Rapid 1400 lies between ChessGoals' 1290 (chess.com Rapid 815) and 1490 (1085): 815 + 110 × 1.35.
    assert quality["estimate"] == 964
    assert quality["lichess_rapid"]["estimate"] == 1400
    assert quality["low"] < 964 < quality["high"]
    assert (quality["games"], quality["moves"]) == (1, 10)
    assert quality["move_model"] == MODEL_VERSION


def test_the_estimate_pools_the_moves_of_all_games_rather_than_averaging_the_games(leaderboard):
    # Alone, the games' estimates are 1300 and 1900 (mean 1600). Together the log-likelihood
    # -9((r - 1300)/400)² - ((r - 1900)/400)² peaks at 1360, nearest the grid's 1400.
    [llama] = leaderboard(
        (game(HUMAN, LLAMA, "1-0"), analysis({"black": [1300] * 9})),
        (game(LLAMA, HUMAN, "1-0"), analysis({"white": [1900]})),
    )

    quality = llama["move_quality"]
    assert quality["lichess_rapid"]["estimate"] == 1400
    assert quality["estimate"] == 964
    assert (quality["games"], quality["moves"]) == (2, 10)


def test_an_estimate_below_the_conversion_floor_has_a_wider_interval_than_one_above_it(leaderboard):
    # The same likelihood around Lichess 1200, below ChessGoals' floor of 1290, and around 1600, inside the table.
    configurations = by_model(
        leaderboard(
            (game(HUMAN, LLAMA, "1-0"), analysis({"black": [1200] * 30})),
            (game(HUMAN, QWEN, "1-0"), analysis({"black": [1600] * 30})),
        )
    )

    below = configurations[("llama3:8b", "free")]["move_quality"]
    inside = configurations[("qwen3.5:9b", "free")]["move_quality"]
    assert below["lichess_rapid"]["estimate"] == 1200 and inside["lichess_rapid"]["estimate"] == 1600
    assert below["low"] < below["estimate"] < 815 < below["high"]
    assert below["high"] - below["low"] > inside["high"] - inside["low"]
    assert below["extrapolated"] and not inside["extrapolated"]


def test_an_estimate_at_the_move_models_lowest_rating_is_only_an_upper_bound(leaderboard):
    # The moves are likeliest for a player below the grid's lowest rating, which stands for everyone under 1100.
    [llama] = leaderboard((game(HUMAN, LLAMA, "1-0"), analysis({"black": [700] * 20})))

    quality = llama["move_quality"]
    assert quality["lichess_rapid"]["estimate"] == 1000
    assert quality["estimate"] is None
    assert quality["low"] is None
    assert quality["high"] is not None and quality["high"] < 815
    assert quality["extrapolated"]


def test_the_estimate_is_unvalidated_until_the_validation_has_run(leaderboard):
    [llama] = leaderboard((game(HUMAN, LLAMA, "1-0"), analysis({"black": [1400] * 10})))

    assert llama["move_quality"]["validated"] is False


@pytest.mark.parametrize(
    ("validation", "validated"),
    [
        ({"move_model": MODEL_VERSION, "ratings": GRID, "passed": True}, True),
        ({"move_model": MODEL_VERSION, "ratings": GRID, "passed": False}, False),
        ({"move_model": "fake-move-model 0", "ratings": GRID, "passed": True}, False),
        ({"move_model": MODEL_VERSION, "ratings": GRID[1:], "passed": True}, False),
    ],
    ids=["passed", "failed", "another model version", "another grid"],
)
def test_the_estimate_is_validated_only_by_a_passed_validation_of_its_move_model_and_grid(
    leaderboard, validation, validated
):
    [llama] = leaderboard((game(HUMAN, LLAMA, "1-0"), analysis({"black": [1400] * 10})), validation=validation)

    assert llama["move_quality"]["validated"] is validated


def test_games_without_a_readable_analysis_file_are_left_out_of_the_estimate(leaderboard):
    configurations = by_model(
        leaderboard(
            (game(HUMAN, LLAMA, "1-0"), analysis({"black": [1400] * 10})),
            (game(HUMAN, LLAMA, "0-1"), None),
            (game(HUMAN, LLAMA, "0-1"), "not json"),
            (game(HUMAN, LLAMA, "0-1"), {"analysis_version": 1}),
            (game(HUMAN, QWEN, "1-0"), None),
            (game(HUMAN, QWEN | {"llm_constraints": "listed"}, "1-0"), analysis({"black": []})),
        )
    )

    llama = configurations[("llama3:8b", "free")]
    assert llama["games"] == 4
    assert (llama["move_quality"]["games"], llama["move_quality"]["estimate"]) == (1, 964)
    assert configurations[("qwen3.5:9b", "free")]["move_quality"] is None
    assert configurations[("qwen3.5:9b", "listed")]["move_quality"] is None  # analysed, but no legal move played


def test_analyses_by_different_move_models_or_grids_are_not_pooled(leaderboard):
    # The current model's analyses cover more games, so they make the estimate; the older one's moves are left out.
    [llama] = leaderboard(
        (game(HUMAN, LLAMA, "1-0"), analysis({"black": [1900] * 50}, version="fake-move-model 0")),
        (game(HUMAN, LLAMA, "1-0"), analysis({"black": [1400] * 5})),
        (game(HUMAN, LLAMA, "1-0"), analysis({"black": [1400] * 5})),
        (game(HUMAN, LLAMA, "1-0"), analysis({"black": [1400] * 5}, ratings=list(range(1000, 2001, 50)))),
    )

    quality = llama["move_quality"]
    assert (quality["move_model"], quality["games"], quality["moves"]) == (MODEL_VERSION, 2, 10)
    assert quality["lichess_rapid"]["ratings"] == GRID
    assert quality["lichess_rapid"]["estimate"] == 1400


def test_each_llm_side_of_a_faceoff_counts_towards_its_own_configurations_estimate(leaderboard):
    configurations = by_model(
        leaderboard((game(LLAMA, QWEN, "1-0"), analysis({"white": [1700] * 10, "black": [1400] * 10})))
    )

    assert configurations[("llama3:8b", "free")]["move_quality"]["lichess_rapid"]["estimate"] == 1700
    assert configurations[("qwen3.5:9b", "free")]["move_quality"]["lichess_rapid"]["estimate"] == 1400
