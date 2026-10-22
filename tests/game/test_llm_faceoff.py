"""LLM faceoff: an LLM plays each side, every turn started with POST /llm-turn, until the game ends."""

import io
import json
import threading

import chess.pgn
import pytest
from fastapi.testclient import TestClient

from tests.conftest import BlockingPlayer, Raw, ScriptedPlayer, llm_faceoff, play_llm

from chessllm.api.app import create_app
from chessllm.llm.players import LlmTimeout

QWEN_THINKING = {"model": "qwen3.5:9b", "thinking": True}


def play_to_the_end(client: TestClient) -> dict:
    """Ask for LLM turns, as the page does, until the game is over."""
    for _ in range(50):
        response = client.post("/api/games/current/llm-turn")
        assert response.status_code == 200, response.text
        state = response.json()
        if state["status"] == "over":
            return state
    raise AssertionError("the faceoff did not end")


def events(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_a_faceoff_starts_with_white_to_move_and_no_human_moves(faceoff):
    _, state, players = faceoff([], [])

    assert (state["turn"], state["status"], state["human_legal_moves"]) == ("white", "playing", [])
    assert state["settings"]["mode"] == "llm_faceoff"
    assert players["white"].prompts == players["black"].prompts == []


def test_a_faceoff_plays_to_checkmate_each_turn_answered_by_the_side_to_moves_own_player(faceoff):
    client, _, players = faceoff(["f3", "g4"], ["e5", "Qh4#"])

    state = play_to_the_end(client)

    assert (state["result"], state["end_reason"]) == ("0-1", "checkmate")
    assert state["pgn"] == "1. f3 e5 2. g4 Qh4#"
    assert (len(players["white"].prompts), len(players["black"].prompts)) == (2, 2)
    assert [turn["color"] for turn in state["llm_turns"]] == ["white", "black", "white", "black"]


def test_a_faceoff_plays_to_a_draw(faceoff):
    client, _, _ = faceoff(["Nf3", "Ng1", "Nf3", "Ng1"], ["Nf6", "Ng8", "Nf6", "Ng8"])

    state = play_to_the_end(client)

    assert (state["result"], state["end_reason"]) == ("1/2-1/2", "threefold_repetition")


def test_a_side_that_gives_no_legal_move_forfeits_and_only_its_own_stats_count_the_illegal_moves(faceoff):
    client, _, _ = faceoff(["Ke3", "e4"], ["Ke7", "Ke6", "Kd5", "e4"])

    state = play_to_the_end(client)

    assert (state["result"], state["end_reason"]) == ("1-0", "forfeit")
    assert state["pgn"] == "1. e4"
    white, black = state["stats"]["white"], state["stats"]["black"]
    assert (white["illegal_moves"]["illegal"], white["recovered_turns"], white["legal_move_streak"]) == (1, 1, 0)
    assert (black["illegal_moves"]["illegal"], black["recovered_turns"], black["legal_move_streak"]) == (4, 0, 0)


@pytest.mark.parametrize(
    ("white", "black", "result"),
    [
        ([LlmTimeout(600)], [], "0-1"),
        (["e4"], [RuntimeError("Ollama is not running")], "1-0"),
    ],
)
def test_a_timeout_or_failed_call_forfeits_the_side_to_move(faceoff, white, black, result):
    client, _, _ = faceoff(white, black)

    state = play_to_the_end(client)

    assert (state["result"], state["end_reason"]) == (result, "forfeit")
    assert state["llm_turn"]["attempts"][-1]["error"]


def test_each_side_is_prompted_with_its_own_colour(faceoff):
    client, _, players = faceoff(["e4"], ["e5"])

    client.post("/api/games/current/llm-turn")
    client.post("/api/games/current/llm-turn")

    [white_prompt], [black_prompt] = players["white"].prompts, players["black"].prompts
    assert "chess as White" in white_prompt[0].content
    assert "chess as Black" in black_prompt[0].content
    assert "PGN: 1. e4" in black_prompt[1].content


def test_each_side_plays_with_its_own_llm_constraints_and_retry_feedback(faceoff):
    client, _, players = faceoff(
        ["e4"],
        ["Ke7", "e5"],
        white_settings={"llm_constraints": "listed", "retry_feedback": "bare"},
        black_settings={"llm_constraints": "free", "retry_feedback": "hinted"},
    )

    client.post("/api/games/current/llm-turn")
    state = client.post("/api/games/current/llm-turn").json()

    assert "Legal moves:" in players["white"].prompts[0][1].content
    assert "Legal moves:" not in players["black"].prompts[0][1].content
    assert "Legal moves:" in state["llm_turn"]["attempts"][1]["feedback_sent"]  # hinted
    assert state["stats"]["black"]["illegal_moves"]["illegal"] == 1
    assert state["stats"]["white"]["illegal_moves"]["illegal"] == 0


def test_the_same_model_can_play_both_sides_with_their_stats_kept_apart(faceoff):
    client, start, players = faceoff([Raw('{"move": "e2e4"}')], ["e5"], QWEN_THINKING, QWEN_THINKING)

    client.post("/api/games/current/llm-turn")
    state = client.post("/api/games/current/llm-turn").json()

    assert start["settings"]["white"] == start["settings"]["black"]
    assert players["white"].colors == ["white"] and players["black"].colors == ["black"]
    assert (state["stats"]["white"]["notation_slips"], state["stats"]["black"]["notation_slips"]) == (1, 0)
    assert (state["stats"]["white"]["legal_move_streak"], state["stats"]["black"]["legal_move_streak"]) == (1, 1)


def test_each_llm_side_gets_its_own_player_built_from_the_games_settings(faceoff):
    _, start, players = faceoff([], [], {"model": "qwen3.5:9b"}, {"model": "llama3:8b"})

    [white_built], [black_built] = players["white"].built_for, players["black"].built_for
    assert white_built is black_built  # the game's settings, from which each side's player takes its own side
    assert (white_built.white.model, white_built.black.model) == ("qwen3.5:9b", "llama3:8b")
    assert start["settings"]["white"] == {
        "player": "llm",
        "model": "qwen3.5:9b",
        "thinking": False,
        "llm_constraints": "free",
        "retry_feedback": "explained",
    }


def test_human_moves_are_refused_in_a_faceoff(faceoff):
    client, before, _ = faceoff([], [])

    response = client.post("/api/games/current/moves", json={"uci": "e2e4"})

    assert response.status_code == 400
    assert client.get("/api/games/current").json() == before


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "llm_faceoff", "white": {"player": "human"}, "black": {"player": "llm"}},
        {"mode": "play_llm", "white": {"player": "llm"}, "black": {"player": "llm"}},
        {"mode": "play_llm", "white": {"player": "human"}, "black": {"player": "human"}},
        llm_faceoff(black={"model": "gemma3:4b"}),
        llm_faceoff(white={"model": "llama3:8b", "thinking": True}, black=QWEN_THINKING),
        play_llm("black", model="gemma3:4b"),
    ],
)
def test_settings_that_dont_fit_are_refused(scripted, body):
    client, player = scripted([])

    response = client.post("/api/games", json=body)

    assert response.status_code == 400, response.text
    assert player.built_for == []


def test_settings_in_the_old_flat_shape_are_refused(scripted):
    client, _ = scripted([])

    assert client.post("/api/games", json={"model": "llama3:8b", "human_color": "black"}).status_code == 422


def test_an_unknown_mode_is_refused(scripted):
    client, _ = scripted([])

    assert client.post("/api/games", json={"mode": "tournament"}).status_code == 422


def test_a_new_game_starts_while_an_abandoned_faceoffs_turn_runs_and_that_turn_is_logged_to_its_own_game(tmp_path):
    blocking, scripted = BlockingPlayer(["e4"]), ScriptedPlayer(["d4"])
    games = iter([blocking, scripted])
    built = {}

    def player_for(settings, color):
        if color not in built.setdefault(id(settings), {}):
            built[id(settings)][color] = next(games) if color == "white" else ScriptedPlayer([])
        return built[id(settings)][color]

    games_dir = tmp_path / "games"
    client = TestClient(create_app(player_for, games_dir=games_dir, sampling_file=tmp_path / "no-sampling.toml"))
    client.post("/api/games", json=llm_faceoff())
    responses = []
    running = threading.Thread(target=lambda: responses.append(client.post("/api/games/current/llm-turn")))
    running.start()
    assert blocking.asked.wait(timeout=5)

    new_game = client.post("/api/games", json=llm_faceoff({"model": "qwen3.5:9b"}))
    new_turn = client.post("/api/games/current/llm-turn")
    blocking.release.set()
    running.join(timeout=5)

    assert new_game.status_code == 200 and new_turn.status_code == 200
    assert new_turn.json()["pgn"] == "1. d4"
    [abandoned] = responses
    assert abandoned.json()["pgn"] == "1. e4"
    assert abandoned.json()["game_id"] != new_game.json()["game_id"]
    assert client.get("/api/games/current").json()["pgn"] == "1. d4"
    old_log, new_log = sorted(games_dir.glob("*.jsonl"), key=lambda path: "qwen" in path.name)
    assert [event["move"] for event in map(json.loads, old_log.read_text().splitlines()) if event["type"] == "llm_attempt"] == ["e4"]
    assert [event["move"] for event in map(json.loads, new_log.read_text().splitlines()) if event["type"] == "llm_attempt"] == ["d4"]


def test_the_log_and_pgn_record_both_llm_sides(faceoff, tmp_path):
    client, _, _ = faceoff(["f3", "g4"], ["e5", "Qh4#"], QWEN_THINKING, {"llm_constraints": "listed_enforced"})

    play_to_the_end(client)

    games_dir = tmp_path / "games"
    [log] = sorted(games_dir.glob("*.jsonl"))
    assert log.name.endswith("_qwen3.5-9b_vs_llama3-8b.jsonl")
    start, *attempts, end = events(games_dir)
    assert (start["mode"], start["white"]["model"], start["black"]["model"]) == ("llm_faceoff", "qwen3.5:9b", "llama3:8b")
    assert (start["white"]["thinking"], start["black"]["llm_constraints"]) == (True, "listed_enforced")
    assert start["prompt_files"]["white"].endswith("system.txt")
    assert start["prompt_files"]["black"].endswith("system_listed.txt")
    assert [attempt["color"] for attempt in attempts] == ["white", "black", "white", "black"]
    assert end["stats"]["white"]["legal_move_streak"] == 2
    assert end["stats"]["black"] == {
        "legal_move_streak": None, "illegal_moves": None, "recovered_turns": None, "notation_slips": 0,
    }
    pgn = chess.pgn.read_game(io.StringIO(log.with_suffix(".pgn").read_text(encoding="utf-8")))
    assert pgn.headers["White"] == "qwen3.5:9b (thinking)"
    assert pgn.headers["Black"] == "llama3:8b (no thinking)"
    assert pgn.headers["Mode"] == "LLM faceoff"
    assert (pgn.headers["WhiteLLMConstraints"], pgn.headers["BlackLLMConstraints"]) == ("free", "listed_enforced")
    assert pgn.headers["Result"] == "0-1"


def test_a_faceoff_logs_each_sides_prompt_file_even_when_shared(faceoff, tmp_path):
    faceoff([], [])

    [start] = events(tmp_path / "games")
    assert start["prompt_files"]["white"] == start["prompt_files"]["black"]
    assert start["prompt_files"]["white"].endswith("system.txt")
    assert "prompt_file" not in start
