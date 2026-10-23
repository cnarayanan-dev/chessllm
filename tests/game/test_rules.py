"""The Rules as objects: Standard rules never play an illegal move, Chaos rules play an LLM's rule-breaking or
ambiguous move (ADR 0006), and each says what that changes in the game, its checks and its logs."""

import chess
import pytest

from chessllm.exceptions import InvalidSettings
from chessllm.game.ending import GameEnd
from chessllm.game.rules import CHAOS, RULES, STANDARD, rules_named
from chessllm.game.sides import AnchorSide, LlmSide


def test_each_rules_is_found_by_its_key():
    assert RULES == {"standard": STANDARD, "chaos": CHAOS}
    assert rules_named("chaos") is CHAOS
    assert rules_named("anarchy") is None


def test_chaos_rules_games_are_unrated():
    assert (STANDARD.rated, CHAOS.rated) == (True, False)


def test_only_chaos_rules_play_illegal_moves():
    assert (STANDARD.plays_illegal_moves, CHAOS.plays_illegal_moves) == (False, True)


def test_standard_rules_never_resolve_a_move():
    assert STANDARD.resolve(chess.Board(), "Bd3", "illegal") is None


def test_chaos_rules_resolve_a_rule_breaking_move_but_never_badly_formed_notation():
    resolved = CHAOS.resolve(chess.Board(), "Bd3", "illegal")

    assert resolved is not None and resolved.kind == "chaos"
    assert CHAOS.resolve(chess.Board(), "Bd3", "invalid") is None
    assert CHAOS.resolve(chess.Board(), "Bd3", "cut_off") is None


def test_a_king_capture_and_a_king_left_in_check_end_the_game_only_under_chaos_rules():
    no_black_king = chess.Board("8/8/8/8/8/8/8/K7 w - - 0 1")
    into_check = chess.Board("k7/8/8/8/8/8/8/K6r b - - 0 1")  # White, having just moved, is in check

    assert CHAOS.end(no_black_king) == GameEnd("1-0", "king_capture")
    assert CHAOS.end(into_check) == GameEnd("0-1", "king_left_in_check")
    assert CHAOS.end(chess.Board()) is None
    assert STANDARD.end(into_check) is None


def test_only_chaos_rules_show_in_the_logs_and_the_pgn():
    assert (STANDARD.game_start_fields(), CHAOS.game_start_fields()) == ({}, {"rules": "chaos"})
    assert (STANDARD.pgn_headers(), CHAOS.pgn_headers()) == ({}, {"Rules": "Chaos"})
    assert STANDARD.game_end_fields(plies=40, first_chaos_ply=None) == {}
    assert CHAOS.game_end_fields(plies=40, first_chaos_ply=None) == {"chaos_plies": 0}
    assert CHAOS.game_end_fields(plies=40, first_chaos_ply=31) == {"chaos_plies": 10}


def test_under_chaos_rules_an_attempt_always_logs_its_resolution():
    assert STANDARD.attempt_log_shape({"move": "e4"}) == {"move": "e4"}
    assert CHAOS.attempt_log_shape({"move": "e4"}) == {"move": "e4", "resolution": None}


def test_only_chaos_rules_count_chaos_moves():
    assert STANDARD.chaos_counts(chaos_moves=2, spawns=1) == (None, None)
    assert CHAOS.chaos_counts(chaos_moves=2, spawns=1) == (2, 1)


def test_chaos_rules_need_stockfish_or_the_random_mover_as_the_anchor_and_every_llm_under_free_or_listed():
    CHAOS.check_anchor(AnchorSide(engine="stockfish"))
    CHAOS.check_anchor(AnchorSide.random_mover(seed=1))
    CHAOS.check_llm("black", LlmSide(llm_constraints="listed"))
    STANDARD.check_anchor(AnchorSide(engine="dragon"))
    STANDARD.check_llm("black", LlmSide(llm_constraints="listed_enforced"))

    with pytest.raises(InvalidSettings, match="Only Stockfish or the random mover can be the Anchor under Chaos rules"):
        CHAOS.check_anchor(AnchorSide(engine="dragon"))
    with pytest.raises(InvalidSettings, match=r"not llama3:8b \(black\) under listed_enforced"):
        CHAOS.check_llm("black", LlmSide(llm_constraints="listed_enforced"))
