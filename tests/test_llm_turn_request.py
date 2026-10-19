"""The human's move and the LLM's turn are separate requests: POST /moves never waits for the LLM."""

import threading

import chess
from fastapi.testclient import TestClient

from chessllm.app import create_app
from chessllm.players import LlmReply, Message

START_FEN = chess.STARTING_FEN


def test_a_human_move_returns_at_once_with_the_llm_to_move(scripted):
    client, player = scripted([])
    client.post("/api/games")

    response = client.post("/api/games/current/moves", json={"uci": "e2e4"})

    assert response.status_code == 200
    state = response.json()
    assert state["pgn"] == "1. e4"
    assert (state["turn"], state["status"], state["last_move"]) == ("black", "playing", "e2e4")
    assert state["human_legal_moves"] == []
    assert player.prompts == []


def test_castling_shows_the_rook_moved_before_the_llm_replies(scripted):
    client, player = scripted(["e5", "Nc6", "Nf6"])
    client.post("/api/games")
    for uci in ["e2e4", "g1f3", "f1c4"]:
        client.post("/api/games/current/moves", json={"uci": uci})
        client.post("/api/games/current/llm-turn")

    state = client.post("/api/games/current/moves", json={"uci": "e1g1"}).json()

    assert state["fen"].startswith("r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQ1RK1 b")
    assert len(player.prompts) == 3


def test_a_new_game_as_black_starts_with_the_llm_to_move_and_no_llm_turn_played(scripted):
    client, player = scripted([])

    state = client.post("/api/games", json={"human_color": "black"}).json()

    assert (state["fen"], state["turn"], state["status"]) == (START_FEN, "white", "playing")
    assert state["human_legal_moves"] == []
    assert state["llm_turn"] is None
    assert player.prompts == []


def test_the_llm_turn_plays_the_llms_move_and_returns_the_state(scripted):
    client, _ = scripted(["e5"])
    client.post("/api/games")
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    response = client.post("/api/games/current/llm-turn")

    assert response.status_code == 200
    state = response.json()
    assert (state["pgn"], state["turn"], state["last_move"]) == ("1. e4 e5", "white", "e7e5")
    assert "g1f3" in state["human_legal_moves"]
    assert client.get("/api/games/current").json() == state


def test_the_llm_turn_opens_a_game_the_llm_plays_as_white(scripted):
    client, _ = scripted(["e4"])
    client.post("/api/games", json={"human_color": "black"})

    state = client.post("/api/games/current/llm-turn").json()

    assert (state["pgn"], state["turn"]) == ("1. e4", "black")
    assert "e7e5" in state["human_legal_moves"]


def test_the_llm_turn_is_refused_on_the_humans_turn(scripted):
    client, player = scripted(["e5"])
    before = client.post("/api/games").json()

    response = client.post("/api/games/current/llm-turn")

    assert response.status_code == 409
    assert client.get("/api/games/current").json() == before
    assert player.prompts == []


def test_the_llm_turn_is_refused_once_the_game_is_over(scripted):
    client, player = scripted(["f6", "g5"])
    client.post("/api/games")
    for uci in ["e2e4", "d2d4"]:
        client.post("/api/games/current/moves", json={"uci": uci})
        client.post("/api/games/current/llm-turn")
    over = client.post("/api/games/current/moves", json={"uci": "d1h5"}).json()
    assert (over["status"], over["turn"]) == ("over", "black")  # mated on the LLM's turn

    response = client.post("/api/games/current/llm-turn")

    assert response.status_code == 409
    assert client.get("/api/games/current").json() == over
    assert len(player.prompts) == 2


def test_there_is_no_llm_turn_without_a_game(scripted):
    client, _ = scripted([])

    assert client.post("/api/games/current/llm-turn").status_code == 404


class BlockingPlayer:
    """Test fake for the LLM player port: answers e5, but only once released, so a turn can be kept running."""

    def __init__(self) -> None:
        self.asked = threading.Event()
        self.release = threading.Event()
        self.prompts: list[list[Message]] = []

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        self.prompts.append(messages)
        self.asked.set()
        assert self.release.wait(timeout=5)
        return LlmReply(raw='{"move": "e5"}', thinking=None, latency_s=0.0)


def test_a_second_llm_turn_is_refused_while_one_is_running(tmp_path):
    player = BlockingPlayer()
    client = TestClient(
        create_app(lambda settings: player, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml")
    )
    client.post("/api/games")
    client.post("/api/games/current/moves", json={"uci": "e2e4"})
    responses = []
    running = threading.Thread(target=lambda: responses.append(client.post("/api/games/current/llm-turn")))
    running.start()
    assert player.asked.wait(timeout=5)

    second = client.post("/api/games/current/llm-turn")
    waiting = client.get("/api/games/current").json()
    player.release.set()
    running.join(timeout=5)

    assert second.status_code == 409
    assert (waiting["pgn"], waiting["turn"]) == ("1. e4", "black")
    [first] = responses
    assert first.status_code == 200
    assert first.json()["pgn"] == "1. e4 e5"
    assert len(player.prompts) == 1
