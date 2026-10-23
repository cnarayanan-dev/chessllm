"""A new game abandons the old one: the old game's running LLM turn stops and never ends the game."""

import json
import threading

from tests.conftest import BlockingPlayer, Raw, ScriptedPlayer, play_llm
from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import HumanSide, LlmSide
from chessllm.logs.game_log import GameLog


def abandon_during_llm_turn(tmp_path, replies: list[str | BaseException]) -> tuple[TestClient, BlockingPlayer, dict, list]:
    """Start a game with the LLM as White, hold its first turn, start a new game, then release the turn.
    Returns the client, the player, the old game's start state and its LLM turn's response."""
    player = BlockingPlayer(replies)
    client = TestClient(
        create_app(player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml")
    )
    old = client.post("/api/games", json=play_llm("black")).json()
    responses: list = []
    running = threading.Thread(target=lambda: responses.append(client.post("/api/games/current/llm-turn")))
    running.start()
    assert player.asked.wait(timeout=5)

    assert client.post("/api/games", json=play_llm("white")).status_code == 200
    player.release.set()
    running.join(timeout=5)
    return client, player, old, responses


def log_events(tmp_path, game_id: str) -> list[dict]:
    for path in (tmp_path / "games").glob("*.jsonl"):
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if events[0]["game_id"] == game_id:
            return events
    raise AssertionError(f"no log for {game_id}")


def test_an_abandoned_games_failed_turn_does_not_end_it_or_count_on_the_leaderboard(tmp_path):
    client, _, old, responses = abandon_during_llm_turn(tmp_path, [RuntimeError("connection refused")])

    events = log_events(tmp_path, old["game_id"])
    assert [event["type"] for event in events] == ["game_start", "llm_attempt"]
    assert events[-1]["result"] == "error"
    assert client.get("/api/ranking").json()["models"] == []
    [response] = responses
    assert response.status_code == 200
    assert response.json()["status"] == "playing"


def test_an_abandoned_games_turn_makes_no_further_attempts(tmp_path):
    _, player, old, responses = abandon_during_llm_turn(tmp_path, ["e5", "e4"])  # e5 is illegal for White

    events = log_events(tmp_path, old["game_id"])
    assert [event["type"] for event in events] == ["game_start", "llm_attempt"]
    assert events[-1]["result"] == "illegal"
    assert len(player.prompts) == 1
    [response] = responses
    assert response.json()["status"] == "playing"
    assert response.json()["llm_turns"] == []  # stopped before it landed, so never published


def test_an_abandoned_games_turn_returns_its_own_state(tmp_path):
    client, _, old, responses = abandon_during_llm_turn(tmp_path, ["e4"])

    [response] = responses
    assert response.status_code == 200
    assert response.json()["game_id"] == old["game_id"]
    assert response.json()["pgn"] == "1. e4"
    assert client.get("/api/games/current").json()["pgn"] == ""


def test_an_llm_turn_asked_for_after_the_game_was_abandoned_is_never_played(tmp_path):
    """The request found the game before a new one replaced it, and asks for its turn only after."""
    player = ScriptedPlayer([Raw("{}")])
    settings = Settings(white=LlmSide(), black=HumanSide())
    game = GameSession({"white": player}, settings, GameLog(tmp_path, *settings.side_names()))

    game.abandon()
    game.play_llm_turn()

    state = game.state()
    assert (state.llm_turn, state.llm_turns, state.status) == (None, [], "playing")
    assert player.prompts == []
