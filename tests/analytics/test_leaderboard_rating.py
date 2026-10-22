"""The leaderboard's Rating: a maximum-likelihood Elo on the chess.com scale over one pool of every rated game (Anchor
matches and LLM faceoffs under Standard rules), with the Dragon Anchors held at 125 × (skill + 1) ± 100.

The synthetic configurations below have a planted strength: their scores against each Anchor are what the Elo model
expects of a player that strong."""

import random

from tests.analytics.test_leaderboard import HUMAN, LLAMA, QWEN, by_model, game, leaderboard  # noqa: F401 (the fixture)


def dragon(skill):
    return {"player": "anchor", "engine": "dragon", "skill": skill}


def result_of(outcome, white):
    """The game's result for an outcome ("win", "draw", "loss" or "forfeit") of the side that is white or not."""
    if outcome == "draw":
        return "1/2-1/2"
    return "1-0" if (outcome == "win") == white else "0-1"


def against_anchor(llm, skill, wins=0, draws=0, losses=0, forfeits=0, rules=None):
    """An Anchor match batch: the given results of the LLM against Dragon at a Skill level, colours alternating."""
    results = ["win"] * wins + ["draw"] * draws + ["loss"] * losses + ["forfeit"] * forfeits
    games = []
    for number, outcome in enumerate(results):
        llm_white = number % 2 == 0
        white, black = (llm, dragon(skill)) if llm_white else (dragon(skill), llm)
        reason = {"draw": "move_cap", "forfeit": "forfeit"}.get(outcome, "checkmate")
        games.append(game(white, black, result_of(outcome, llm_white), reason, mode="anchor_match", rules=rules))
    return games


def test_a_planted_score_against_anchors_gives_a_rating_whose_interval_contains_the_true_strength(leaderboard):
    # Rated 400: expected to score 70% against Skill 1 (250) and 36% against Skill 3 (500).
    [llama] = leaderboard(
        *against_anchor(LLAMA, 1, wins=7, losses=3),
        *against_anchor(LLAMA, 3, wins=3, draws=1, losses=6),
    )

    rating = llama["rating"]
    assert rating["low"] < 400 < rating["high"]
    assert rating["low"] < rating["estimate"] < rating["high"]
    assert rating["high"] - rating["low"] < 600
    assert rating["rated_games"] == 20


def test_a_configuration_that_lost_every_anchored_game_gets_an_upper_bound(leaderboard):
    [llama] = leaderboard(*against_anchor(LLAMA, 1, losses=6, forfeits=4))

    rating = llama["rating"]
    assert (rating["estimate"], rating["low"]) == (None, None)
    # Losing 10 of 10 is a 5% chance for a player rated about 70 against Skill 1 (250), and less for anyone stronger.
    assert 40 < rating["high"] < 100
    assert rating["rated_games"] == 10


GEMMA = LLAMA | {"model": "gemma3:12b"}
MISTRAL = LLAMA | {"model": "mistral:7b"}


def test_a_configuration_with_no_path_to_an_anchor_gets_no_rating(leaderboard):
    configurations = by_model(
        leaderboard(
            *against_anchor(QWEN, 3, wins=5, losses=5),
            game(LLAMA, GEMMA, "1-0"),  # a faceoff between two configurations that never met an Anchor
            game(GEMMA, LLAMA, "1/2-1/2", "move_cap"),
            game(HUMAN, MISTRAL, "0-1"),  # Play LLM only
        )
    )

    assert configurations[("qwen3.5:9b", "free")]["rating"] is not None
    assert configurations[("llama3:8b", "free")]["rating"] is None
    assert configurations[("gemma3:12b", "free")]["rating"] is None
    assert configurations[("mistral:7b", "free")]["rating"] is None


def faceoffs(first, second, wins=0, draws=0, losses=0, rules=None):
    """LLM faceoff games with the given results of the first configuration against the second, colours alternating."""
    results = ["win"] * wins + ["draw"] * draws + ["loss"] * losses
    games = []
    for number, outcome in enumerate(results):
        first_white = number % 2 == 0
        white, black = (first, second) if first_white else (second, first)
        reason = "move_cap" if outcome == "draw" else "checkmate"
        games.append(game(white, black, result_of(outcome, first_white), reason, rules=rules))
    return games


def test_faceoffs_place_configurations_relative_to_each_other_in_the_pool(leaderboard):
    configurations = by_model(
        leaderboard(
            *against_anchor(QWEN, 3, wins=5, losses=5),  # about 500
            *faceoffs(LLAMA, QWEN, wins=7, losses=3),  # LLAMA never met an Anchor but beat QWEN
            *faceoffs(GEMMA, QWEN, losses=8),  # GEMMA lost every game to QWEN
        )
    )

    qwen = configurations[("qwen3.5:9b", "free")]["rating"]
    llama = configurations[("llama3:8b", "free")]["rating"]
    gemma = configurations[("gemma3:12b", "free")]["rating"]
    assert qwen["low"] < 500 < qwen["high"]
    assert llama["estimate"] > qwen["estimate"]
    assert llama["high"] - llama["low"] > qwen["high"] - qwen["low"]  # its place is only as sure as QWEN's
    assert (gemma["estimate"], gemma["low"]) == (None, None)
    assert gemma["high"] < qwen["estimate"]


def test_a_configuration_that_won_every_anchored_game_gets_a_lower_bound(leaderboard):
    [llama] = leaderboard(*against_anchor(LLAMA, 7, wins=6))

    rating = llama["rating"]
    assert (rating["estimate"], rating["high"]) == (None, None)
    assert 1000 < rating["low"] < 1200  # Skill 7 is 1000


def test_play_llm_and_chaos_rules_games_do_not_affect_any_rating(leaderboard):
    rated = [*against_anchor(QWEN, 3, wins=5, losses=5), *faceoffs(LLAMA, QWEN, wins=7, losses=3)]
    unrated = [
        *[game(HUMAN, LLAMA, "0-1") for _ in range(5)],  # Play LLM: LLAMA beat the human
        *[game(QWEN, HUMAN, "0-1") for _ in range(5)],
        *against_anchor(LLAMA, 7, wins=6, rules="chaos"),
        *faceoffs(QWEN, LLAMA, wins=6, rules="chaos"),
    ]

    alone = {c["id"]: c["rating"] for c in leaderboard(*rated)}
    pooled = leaderboard(*rated, *unrated)

    assert {c["id"]: c["rating"] for c in pooled if c["id"] in alone} == alone
    chaos = [c for c in pooled if c["configuration"]["rules"] == "chaos"]
    assert len(chaos) == 2
    assert [c["rating"] for c in chaos] == [None, None]


def test_the_ratings_are_the_same_whatever_order_the_games_are_in(leaderboard, tmp_path):
    games = [
        *against_anchor(QWEN, 1, wins=6, draws=1, losses=3),
        *against_anchor(QWEN, 3, wins=2, losses=6, forfeits=2),
        *faceoffs(LLAMA, QWEN, wins=4, draws=2, losses=4),
        *against_anchor(LLAMA, 2, wins=3, losses=3),
        *faceoffs(GEMMA, QWEN, losses=5),  # GEMMA and MISTRAL lost to QWEN and drew each other: both "< X"
        *faceoffs(MISTRAL, LLAMA, losses=3),
        *faceoffs(GEMMA, MISTRAL, wins=2, draws=2, losses=1),
        *against_anchor(LLAMA | {"thinking": True}, 7, wins=4),
    ]

    in_order = sorted(leaderboard(*games), key=lambda c: c["id"])
    for seed in range(3):
        shuffled = games[:]
        random.Random(seed).shuffle(shuffled)
        for path in (tmp_path / "games").iterdir():
            path.unlink()
        assert sorted(leaderboard(*shuffled), key=lambda c: c["id"]) == in_order

    ratings = {c["configuration"]["model"] + str(c["configuration"]["thinking"]): c["rating"] for c in in_order}
    assert ratings["gemma3:12bFalse"]["high"] is not None and ratings["gemma3:12bFalse"]["estimate"] is None
    assert ratings["mistral:7bFalse"]["high"] is not None and ratings["mistral:7bFalse"]["estimate"] is None
    assert ratings["llama3:8bTrue"]["low"] is not None and ratings["llama3:8bTrue"]["estimate"] is None
    assert ratings["llama3:8bFalse"]["estimate"] is not None
