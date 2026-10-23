"""Chaos rules: an LLM's rule-breaking or ambiguous move is played on the board at its first attempt (ADR 0006)."""

import json

import pytest

from tests.conftest import llm_faceoff, play_llm, play_move

# Without Legal counterparts, so that every scripted reply is a turn's; the counterparts are tested on their own
# (test_legal_counterpart.py).
CHAOS = {"rules": "chaos", "legal_counterpart": False}


def events(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_a_game_can_start_under_chaos_rules_and_reports_them_in_its_settings_and_log(scripted, tmp_path):
    client, _ = scripted([])

    state = client.post("/api/games", json=play_llm() | CHAOS).json()

    assert state["settings"]["rules"] == "chaos"
    [start] = events(tmp_path / "games")
    assert start["rules"] == "chaos"


@pytest.mark.parametrize("llm_constraints", ["free", "listed"])
def test_chaos_rules_are_allowed_under_free_and_listed(scripted, llm_constraints):
    client, _ = scripted([])

    response = client.post("/api/games", json=play_llm(llm_constraints=llm_constraints) | CHAOS)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize("llm_constraints", ["blind_enforced", "listed_enforced"])
def test_chaos_rules_are_refused_when_the_llm_is_under_enforced_decoding(scripted, llm_constraints):
    client, player = scripted([])

    response = client.post("/api/games", json=play_llm(llm_constraints=llm_constraints) | CHAOS)

    assert response.status_code == 400
    assert "Chaos rules" in response.json()["detail"]
    assert player.built_for == []


def test_chaos_rules_are_refused_when_either_side_of_a_customized_faceoff_is_enforced(scripted):
    client, player = scripted([])

    response = client.post("/api/games", json=llm_faceoff(None, {"llm_constraints": "listed_enforced"}) | CHAOS)

    assert response.status_code == 400
    assert "black" in response.json()["detail"]
    assert player.built_for == []


def test_a_new_game_is_under_standard_rules_unless_chaos_rules_are_asked_for(scripted, tmp_path):
    client, _ = scripted([])

    state = client.post("/api/games", json=play_llm()).json()

    assert "rules" not in state["settings"]  # Standard rules are reported and logged as before Chaos rules existed
    assert "rules" not in events(tmp_path / "games")[0]


def chaos_game(scripted, replies, *ucis, **llm):
    """Start a Play LLM game under Chaos rules with the human as White, and play the human's moves, each followed
    by the LLM's turn. Returns the client, the player and the last state."""
    client, player = scripted(replies)
    state = client.post("/api/games", json=play_llm(**llm) | CHAOS).json()
    for uci in ucis:
        response = play_move(client, uci)
        assert response.status_code == 200, response.text
        state = response.json()
    return client, player, state


def attempts(state):
    """The attempts of the last LLM turn as (move, result, resolution kind)."""
    return [
        (attempt["move"], attempt["result"], attempt["resolution"] and attempt["resolution"]["kind"])
        for attempt in state["llm_turn"]["attempts"]
    ]


def test_a_rule_breaking_move_is_played_at_its_first_attempt(scripted):
    _, player, state = chaos_game(scripted, ["Bc5"], "e2e4")  # the bishop goes through its own e7 pawn

    assert attempts(state) == [("Bc5", "illegal", "chaos")]
    assert len(player.prompts) == 1
    assert state["fen"] == "rnbqk1nr/pppppppp/8/2b5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 1 2"
    assert state["last_move"] == "f8c5"
    assert state["pgn"] == "1. e4 Bc5"
    assert (state["turn"], state["status"]) == ("white", "playing")
    assert "g1f3" in state["human_legal_moves"]


def test_the_resolution_is_kept_with_the_attempt(scripted):
    _, _, state = chaos_game(scripted, ["Bc5"], "e2e4")

    assert state["llm_turn"]["attempts"][0]["resolution"] == {
        "kind": "chaos",
        "from": "f8",
        "to": "c5",
        "piece": "b",
        "rook": None,
        "reason": "the bishop on f8 moves",
    }


def test_an_ambiguous_move_is_played_at_its_first_attempt(scripted):
    _, _, state = chaos_game(scripted, ["e5", "Nc6", "Ne7"], "e2e4", "g1f3", "f1c4")  # both knights can reach e7

    assert attempts(state) == [("Ne7", "ambiguous", "chaos")]
    assert state["last_move"] == "c6e7"  # both are as near; the tie goes to the first in a1→h8 order
    assert state["pgn"] == "1. e4 e5 2. Nf3 Nc6 3. Bc4 Ne7"


@pytest.mark.parametrize("unreadable", ["banana", "e3e5"], ids=["invalid", "uci-from-an-empty-square"])
def test_a_move_the_resolver_cannot_read_gets_a_retry(scripted, unreadable):
    _, player, state = chaos_game(scripted, [unreadable, "Bc5"], "e2e4")

    [first, second] = state["llm_turn"]["attempts"]
    assert (first["move"], second["move"], second["resolution"]["kind"]) == (unreadable, "Bc5", "chaos")
    assert second["feedback_sent"].startswith(f'Your move "{unreadable}" is illegal')
    assert len(player.prompts) == 2


def test_five_unreadable_moves_still_forfeit(scripted):
    _, _, state = chaos_game(scripted, ["banana", "e3e5", "O-O-O-O", "Qz9", "Kk1"], "e2e4")

    assert (state["result"], state["end_reason"]) == ("1-0", "forfeit")


def test_a_legal_move_is_played_as_under_standard_rules(scripted):
    _, _, state = chaos_game(scripted, ["e5"], "e2e4")

    assert attempts(state) == [("e5", "legal", "legal")]
    assert state["pgn"] == "1. e4 e5"


def test_a_piece_the_llm_no_longer_has_spawns_on_its_target(scripted):
    # The queen jumps out to h4 by a chaos move, is taken, and comes back from nowhere.
    _, _, state = chaos_game(scripted, ["Qh4", "a6", "Qd5"], "e2e4", "g1f3", "f3h4")

    assert attempts(state) == [("Qd5", "illegal", "spawn")]
    assert state["fen"].startswith("rnb1kbnr/1ppppppp/p7/3q4/4P2N/")
    assert state["last_move"] == "Q@d5"
    assert state["pgn"] == "1. e4 Qh4 2. Nf3 a6 3. Nxh4 Qd5"


def test_the_plies_of_a_chaos_game_carry_the_resolution_of_each_chaos_move_and_spawn(scripted):
    _, _, state = chaos_game(scripted, ["Qh4", "a6", "Qd5"], "e2e4", "g1f3", "f3h4")

    plies = state["plies"]
    assert [(ply["move"], ply["written"]) for ply in plies] == [
        ("e2e4", "e4"), ("d8h4", "Qh4"), ("g1f3", "Nf3"), ("a7a6", "a6"), ("f3h4", "Nxh4"), ("Q@d5", "Qd5"),
    ]
    # Each position follows on from the one before, chaos moves included.
    assert all(ply["fen_before"] == before["fen_after"] for before, ply in zip(plies, plies[1:]))
    assert plies[-1]["fen_after"] == state["fen"]
    # A chaos move or spawn carries its resolution, the same as its attempt's, for the replay; other plies none.
    assert plies[1]["resolution"] == state["llm_turns"][0]["attempts"][0]["resolution"]
    assert plies[1]["resolution"]["kind"] == "chaos"
    assert plies[5]["resolution"] == {
        "kind": "spawn", "from": None, "to": "d5", "piece": "q", "rook": None,
        "reason": "no queen on the board; one appears on d5",
    }
    assert [("resolution" in ply) for ply in plies] == [False, True, False, False, False, True]


def test_the_llm_taking_the_humans_king_wins_by_king_capture(scripted):
    _, _, state = chaos_game(scripted, ["Qe1"], "e2e4")

    assert (state["status"], state["result"], state["end_reason"]) == ("over", "0-1", "king_capture")
    assert state["human_legal_moves"] == []


def test_a_chaos_move_that_walks_the_king_into_check_loses_at_once(scripted):
    _, _, state = chaos_game(scripted, ["Ke3"], "e2e4")  # the king walks into both white pawns' reach

    assert (state["status"], state["result"], state["end_reason"]) == ("over", "1-0", "king_left_in_check")
    assert state["human_legal_moves"] == []


def test_a_chaos_move_that_ignores_a_check_loses_at_once(scripted):
    _, _, state = chaos_game(scripted, ["f6", "a5"], "e2e4", "d1h5")  # Qh5+, and a5 leaves the king in check

    assert attempts(state) == [("a5", "illegal", "chaos")]
    assert (state["status"], state["result"], state["end_reason"]) == ("over", "1-0", "king_left_in_check")


def test_a_chaos_move_that_blocks_a_check_plays_on(scripted):
    _, _, state = chaos_game(scripted, ["f6", "Bg6"], "e2e4", "d1h5")  # Qh5+, and the f8 bishop jumps in the way

    assert attempts(state) == [("Bg6", "illegal", "chaos")]
    assert state["status"] == "playing"


def test_checkmate_still_ends_a_game_after_a_chaos_move(scripted):
    _, _, state = chaos_game(scripted, ["e5", "Nd6", "Qh4#"], "f2f3", "g2g4", "a2a3")

    assert [turn["attempts"][0]["resolution"]["kind"] for turn in state["llm_turns"]] == ["legal", "chaos", "legal"]
    assert (state["result"], state["end_reason"]) == ("0-1", "checkmate")


def test_stalemate_still_ends_a_game_under_chaos_rules(scripted):
    # Sam Loyd's ten-move stalemate, played legally by both sides.
    whites = ["e2e3", "d1h5", "h5a5", "h2h4", "a5c7", "c7d7", "d7b7", "b7b8", "b8c8", "c8e6"]
    blacks = ["a5", "Ra6", "h5", "Rah6", "f6", "Kf7", "Qd3", "Qh7", "Kg6"]

    _, _, state = chaos_game(scripted, blacks, *whites)

    assert (state["result"], state["end_reason"]) == ("1/2-1/2", "stalemate")


def test_threefold_repetition_is_found_across_chaos_moves(scripted):
    # The black knight hops b8-d6-b8, which no knight can, bringing back the start position a third time.
    _, _, state = chaos_game(scripted, ["Nd6", "Nb8", "Nd6", "Nb8"], "g1f3", "f3g1", "g1f3", "f3g1")

    assert state["pgn"] == "1. Nf3 Nd6 2. Ng1 Nb8 3. Nf3 Nd6 4. Ng1 Nb8"
    assert (state["result"], state["end_reason"]) == ("1/2-1/2", "threefold_repetition")


def test_after_a_chaos_move_the_llm_is_shown_the_move_record_with_its_own_spelling(scripted):
    _, player, _ = chaos_game(scripted, ["Bc5", "Nf6"], "e2e4", "g1f3")

    pgn, fen = player.prompts[1][1].content.splitlines()
    assert pgn == "PGN: 1. e4 Bc5 2. Nf3"
    assert fen == "FEN: rnbqk1nr/pppppppp/8/2b5/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 2 2"


def test_a_chaos_game_logs_the_resolutions_the_chaos_counts_and_a_pgn_up_to_the_first_chaos_move(scripted, tmp_path):
    # Qh4 is a chaos move and Qd5 a spawn; then five unreadable moves forfeit.
    replies = ["Qh4", "a6", "Qd5", "x", "y", "z", "w", "v"]

    chaos_game(scripted, replies, "e2e4", "g1f3", "f3h4", "b1c3")

    start, *moves, end = events(tmp_path / "games")
    assert start["rules"] == "chaos"
    llm_attempts = [event for event in moves if event["type"] == "llm_attempt"]
    assert [attempt["resolution"] and attempt["resolution"]["kind"] for attempt in llm_attempts] == [
        "chaos", "legal", "spawn", None, None, None, None, None,
    ]
    assert llm_attempts[2]["resolution"] == {
        "kind": "spawn", "from": None, "to": "d5", "piece": "q", "rook": None,
        "reason": "no queen on the board; one appears on d5",
    }
    assert (end["result"], end["reason"], end["plies"], end["chaos_plies"]) == ("1-0", "forfeit", 7, 6)
    assert end["stats"]["black"] == {
        "legal_move_streak": 0,
        "illegal_moves": {"invalid": 5, "illegal": 2, "ambiguous": 0},
        "recovered_turns": 0,
        "notation_slips": 0,
        "chaos_moves": 2,
        "spawns": 1,
    }
    [pgn] = sorted((tmp_path / "games").glob("*.pgn"))
    text = pgn.read_text(encoding="utf-8")
    assert '[Rules "Chaos"]' in text
    assert text.rstrip().endswith("1. e4 1-0")


def test_a_chaos_game_without_a_chaos_move_logs_no_chaos_plies(scripted, tmp_path):
    chaos_game(scripted, ["e5", "Nc6", "Nf6"], "e2e4", "f1c4", "d1h5", "h5f7")  # Scholar's mate

    end = events(tmp_path / "games")[-1]
    assert (end["reason"], end["chaos_plies"], end["stats"]["black"]["chaos_moves"]) == ("checkmate", 0, 0)


def test_an_llm_faceoff_under_chaos_rules_applies_them_to_both_sides(scripted):
    client, _ = scripted(["Bc4", "Bc5"])  # each bishop goes through its own king's pawn
    client.post("/api/games", json=llm_faceoff() | CHAOS)

    client.post("/api/games/current/llm-turn")
    state = client.post("/api/games/current/llm-turn").json()

    assert state["pgn"] == "1. Bc4 Bc5"
    assert (state["stats"]["white"]["chaos_moves"], state["stats"]["black"]["chaos_moves"]) == (1, 1)
