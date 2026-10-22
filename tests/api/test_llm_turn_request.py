"""The human's move and the LLM's turn are separate requests: POST /moves never waits for the LLM."""

from tests.conftest import BlockingPlayer, Raw, ScriptedPlayer, play_llm, play_move

import json
import threading

import chess
import pytest
from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.logs.game_log import GameLog
from chessllm.exceptions import LlmTimeout

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

    state = client.post("/api/games", json=play_llm("black")).json()

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
    client.post("/api/games", json=play_llm("black"))

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


def test_a_second_llm_turn_is_refused_while_one_is_running(tmp_path):
    player = BlockingPlayer(["e5"])
    client = TestClient(
        create_app(lambda settings, color: player, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml")
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


def test_the_state_shows_a_running_llm_turn_only_once_it_has_landed(tmp_path):
    player = BlockingPlayer(["e5", "Qxf7", "d5"])
    client = TestClient(
        create_app(player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml")
    )
    client.post("/api/games")
    player.release.set()
    previous = play_move(client, "e2e4").json()["llm_turn"]
    player.release.clear()  # the second turn is held
    player.asked.clear()
    client.post("/api/games/current/moves", json={"uci": "d2d4"})
    responses = []
    running = threading.Thread(target=lambda: responses.append(client.post("/api/games/current/llm-turn")))
    running.start()
    assert player.asked.wait(timeout=5)

    waiting = client.get("/api/games/current").json()
    player.release.set()
    running.join(timeout=5)

    assert waiting["llm_turns"] == [previous]
    assert waiting["llm_turn"] == previous
    assert waiting["pgn"] == "1. e4 e5 2. d4"
    [landed] = responses
    assert [turn["ply"] for turn in landed.json()["llm_turns"]] == [2, 4]
    assert [attempt["result"] for attempt in landed.json()["llm_turn"]["attempts"]] == ["illegal", "legal"]


@pytest.mark.parametrize(
    ("replies", "usage", "rules", "results"),
    [
        (["e5"], [], "standard", ["legal"]),
        (["Qxf7"] * 5, [], "standard", ["illegal"] * 5),  # forfeits after max_attempts
        ([LlmTimeout(300)], [], "standard", ["timeout"]),
        ([RuntimeError("connection refused")], [], "standard", ["error"]),
        ([Raw(' {"mo'), "e5"], [{"forced": True, "stop_reason": "length"}, {}], "standard", ["cut_off", "legal"]),
        (["Qh4"], [], "chaos", ["illegal"]),  # a chaos move, played at once
    ],
)
def test_every_llm_turn_lands_in_the_state_exactly_once(tmp_path, replies, usage, rules, results):
    player = ScriptedPlayer(replies)
    player.usage = usage
    log = GameLog(tmp_path, "human", "llama3:8b")
    game = GameSession({"black": player}, Settings(rules=rules), log)
    game.play_human_move("e2e4")

    game.play_llm_turn()

    state = game.state()
    [turn] = state.llm_turns
    assert state.llm_turn == turn
    assert [attempt.result for attempt in turn.attempts] == results
    logged = [event for event in map(json.loads, log.path.read_text().splitlines()) if event["type"] == "llm_attempt"]
    assert [event["result"] for event in logged] == results


def test_a_cut_off_answer_reaches_the_page_as_a_cut_off(scripted):
    """A forced answer cut off at its token cap is not an illegal move (ADR 0007), and the API says so."""
    client, player = scripted([Raw(' {"mo'), "e5"])
    player.usage = [{"forced": True, "stop_reason": "length"}, {}]
    client.post("/api/games")

    response = play_move(client, "e2e4")

    assert response.status_code == 200, response.text
    assert [attempt["result"] for attempt in response.json()["llm_turn"]["attempts"]] == ["cut_off", "legal"]
