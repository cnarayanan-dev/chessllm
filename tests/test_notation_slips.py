import io
import json

import chess.pgn
import pytest


def start(scripted, replies, **settings):
    client, player = scripted(replies)
    client.post("/api/games", json=settings)
    return client, player


def attempts(state):
    return [(a["move"], a["result"], a["notation_slip"], a["san"]) for a in state["llm_turn"]["attempts"]]


def log_events(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize(
    "written",
    [
        "g8f6",  # UCI
        "Ng8f6",  # long-form SAN
        "Nf6+",  # a false check sign
    ],
)
def test_a_legal_move_not_in_standard_san_is_played_and_flagged_as_a_notation_slip(scripted, written):
    client, _ = start(scripted, [written])

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert attempts(state) == [(written, "legal", True, "Nf6")]
    assert state["pgn"] == "1. e4 Nf6"
    assert state["stats"]["notation_slips"] == 1


def test_exact_standard_san_is_not_a_notation_slip(scripted):
    client, _ = start(scripted, ["Nf6"])

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert attempts(state) == [("Nf6", "legal", False, "Nf6")]
    assert state["stats"]["notation_slips"] == 0


def test_a_missing_check_sign_is_a_notation_slip(scripted):
    client, _ = start(scripted, ["e4", "Bc4", "Bxf7"], human_color="black")
    for uci in ["e7e5", "d7d6"]:
        client.post("/api/games/current/moves", json={"uci": uci})

    state = client.get("/api/games/current").json()

    assert attempts(state) == [("Bxf7", "legal", True, "Bxf7+")]
    assert state["pgn"] == "1. e4 e5 2. Bc4 d6 3. Bxf7+"


def test_a_missing_mate_sign_is_a_notation_slip_and_the_pgn_file_has_standard_san(scripted, tmp_path):
    client, _ = start(scripted, ["e4", "Bc4", "Qh5", "Qxf7"], human_color="black")
    for uci in ["e7e5", "b8c6", "g8f6"]:
        state = client.post("/api/games/current/moves", json={"uci": uci}).json()

    assert attempts(state) == [("Qxf7", "legal", True, "Qxf7#")]
    assert (state["status"], state["end_reason"]) == ("over", "checkmate")
    [pgn_file] = sorted((tmp_path / "games").glob("*.pgn"))
    game = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
    assert game.board().variation_san(game.mainline_moves()) == "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#"


def test_a_notation_slip_keeps_the_legal_move_streak_and_uses_no_retry(scripted):
    client, player = start(scripted, ["e7e5", "Nc6"])
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    state = client.post("/api/games/current/moves", json={"uci": "g1f3"}).json()

    assert len(player.prompts) == 2  # one attempt per turn
    assert state["stats"]["legal_move_streak"] == 2
    assert state["stats"]["illegal_moves"] == {"invalid": 0, "illegal": 0, "ambiguous": 0}
    assert state["stats"]["recovered_turns"] == 0
    assert state["stats"]["notation_slips"] == 1


def test_an_illegal_move_has_no_standard_san_and_is_not_a_notation_slip(scripted):
    client, _ = start(scripted, ["Qh4", "e7e5"])

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert attempts(state) == [("Qh4", "illegal", False, None), ("e7e5", "legal", True, "e5")]


def test_the_log_records_each_slip_and_the_game_end_counts_them(scripted, tmp_path):
    client, _ = start(scripted, ["e4", "f1c4", "Qh5", "Qxf7"], human_color="black")
    for uci in ["e7e5", "b8c6", "g8f6"]:
        client.post("/api/games/current/moves", json={"uci": uci})

    events = log_events(tmp_path / "games")
    llm_attempts = [event for event in events if event["type"] == "llm_attempt"]
    assert [(a["move"], a["notation_slip"], a["san"]) for a in llm_attempts] == [
        ("e4", False, "e4"),
        ("f1c4", True, "Bc4"),
        ("Qh5", False, "Qh5"),
        ("Qxf7", True, "Qxf7#"),
    ]
    assert events[-1]["type"] == "game_end"
    assert events[-1]["stats"]["white"]["notation_slips"] == 2
