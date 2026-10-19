import pytest
from conftest import play_move

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def test_starting_a_game_returns_the_start_position(scripted):
    client, _ = scripted([])

    response = client.post("/api/games")

    assert response.status_code == 200
    state = response.json()
    assert state["fen"] == START_FEN
    assert state["pgn"] == ""
    assert state["turn"] == "white"
    assert state["last_move"] is None
    assert len(state["human_legal_moves"]) == 20
    assert {"e2e4", "g1f3", "b1c3"} <= set(state["human_legal_moves"])


def test_a_legal_human_move_is_answered_by_the_llms_turn(scripted):
    client, _ = scripted(["e5"])
    client.post("/api/games")

    response = play_move(client, "e2e4")

    assert response.status_code == 200
    state = response.json()
    assert state["pgn"] == "1. e4 e5"
    assert state["fen"] == "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    assert state["turn"] == "white"
    assert state["last_move"] == "e7e5"
    assert "g1f3" in state["human_legal_moves"]


@pytest.mark.parametrize(
    "uci",
    [
        "e2e5",  # illegal pawn move
        "e7e5",  # Black's piece on White's turn
        "banana",  # not UCI at all
        "e1g1",  # castling through pieces
    ],
)
def test_an_illegal_human_move_is_rejected_without_changing_the_state(scripted, uci):
    client, player = scripted([])
    before = client.post("/api/games").json()

    response = play_move(client, uci)

    assert response.status_code == 400
    assert client.get("/api/games/current").json() == before
    assert player.prompts == []


def test_a_new_game_resets_to_the_start_position(scripted):
    client, _ = scripted(["e5"])
    client.post("/api/games")
    play_move(client, "e2e4")

    state = client.post("/api/games").json()

    assert state["fen"] == START_FEN
    assert state["pgn"] == ""
    assert client.get("/api/games/current").json() == state


def test_there_is_no_current_game_before_one_is_started(scripted):
    client, _ = scripted([])

    assert client.get("/api/games/current").status_code == 404
    assert play_move(client, "e2e4").status_code == 404


def test_the_llm_is_not_asked_to_move_after_the_human_mates(scripted):
    client, player = scripted(["f6", "g5"])
    client.post("/api/games")
    play_move(client, "e2e4")
    play_move(client, "d2d4")

    response = play_move(client, "d1h5")

    assert response.status_code == 200
    assert response.json()["pgn"] == "1. e4 f6 2. d4 g5 3. Qh5#"
    assert len(player.prompts) == 2


def test_a_human_move_on_blacks_turn_is_rejected(scripted):
    client, _ = scripted(["f6", "g5"])
    client.post("/api/games")
    for uci in ["e2e4", "d2d4", "d1h5"]:
        play_move(client, uci)
    before = client.get("/api/games/current").json()
    assert before["turn"] == "black"

    response = play_move(client, "a7a6")

    assert response.status_code == 400
    assert client.get("/api/games/current").json() == before


def test_the_state_says_whether_the_side_to_move_is_in_check(scripted):
    client, _ = scripted(["e5", "Qh4"])
    assert client.post("/api/games").json()["check"] is False

    assert play_move(client, "e2e4").json()["check"] is False
    response = play_move(client, "f2f3")  # 1. e4 e5 2. f3 Qh4+

    assert response.json()["pgn"] == "1. e4 e5 2. f3 Qh4+"
    assert response.json()["check"] is True
