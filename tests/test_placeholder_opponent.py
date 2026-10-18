from fastapi.testclient import TestClient

from chessllm.app import create_app
from chessllm.players import FirstLegalMovePlayer


def test_the_placeholder_opponent_replies_with_the_first_legal_move():
    client = TestClient(create_app(FirstLegalMovePlayer()))
    client.post("/api/games")

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert state["pgn"] == "1. e4 Nh6"
    assert state["last_move"] == "g8h6"
