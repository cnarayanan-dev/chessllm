import io
import json

import chess
import chess.pgn

from conftest import Raw, play_llm, play_move

from chessllm.players import LlmTimeout

START_FEN = chess.STARTING_FEN
E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def logs(games_dir, suffix):
    return sorted(games_dir.glob(f"*{suffix}"))


def events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def without(event, *keys):
    return {key: value for key, value in event.items() if key not in keys}


QWEN_THINKING = {
    "player": "llm",
    "model": "qwen3.5:9b",
    "thinking": True,
    "llm_constraints": "free",
    "retry_feedback": "explained",
}


def play(client, *ucis):
    client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True))
    for uci in ucis:
        state = play_move(client, uci).json()
    return state


def test_a_game_log_records_the_start_every_move_and_every_attempt(scripted, tmp_path):
    client, _ = scripted(["Qh4", "e5"], thinking=["Attack f2.", "Take the centre."])

    play(client, "e2e4")

    [log] = logs(tmp_path / "games", ".jsonl")
    assert log.name.endswith("_human_vs_qwen3.5-9b.jsonl")
    start, human, attempt_1, attempt_2 = events(log)
    assert without(start, "game_id", "started_at", "prompt_file") == {
        "type": "game_start",
        "log_version": 2,
        "mode": "play_llm",
        "white": {"player": "human"},
        "black": QWEN_THINKING,
        "sampling": "model_default",
        "max_retries": 4,
    }
    assert start["prompt_file"].endswith("system.txt")
    assert human == {"type": "human_move", "color": "white", "ply": 1, "move": "e4", "fen_after": E4_FEN}
    assert without(attempt_1, "latency_s") == {
        "type": "llm_attempt",
        "color": "black",
        "ply": 2,
        "attempt": 1,
        "pgn": "1. e4",
        "fen": E4_FEN,
        "feedback_sent": None,
        "thinking": "Attack f2.",
        "raw_reply": '{"move": "Qh4"}',
        "move": "Qh4",
        "san": None,
        "notation_slip": False,
        "result": "illegal",
        "error": None,
    }
    assert attempt_2["attempt"] == 2
    assert attempt_2["feedback_sent"].startswith('Your move "Qh4" is illegal')
    assert (attempt_2["move"], attempt_2["result"]) == ("e5", "legal")
    assert attempt_2["latency_s"] == 0.0


def test_with_thinking_off_the_log_keeps_the_reasoning_as_the_attempts_thinking(scripted, tmp_path):
    client, _ = scripted([Raw('{"reasoning": "Mirror the centre pawn.", "move": "e5"}')])
    client.post("/api/games", json=play_llm(thinking=False))

    play_move(client, "e2e4")

    *_, attempt = events(logs(tmp_path / "games", ".jsonl")[0])
    assert attempt["thinking"] == "Mirror the centre pawn."
    assert "reasoning" not in attempt


def test_a_finished_game_ends_its_log_with_the_summary_and_writes_a_pgn(scripted, tmp_path):
    client, _ = scripted(["e5", "Nc6", "Nf6"])

    play(client, "e2e4", "f1c4", "d1h5", "h5f7")  # Scholar's mate

    [log] = logs(tmp_path / "games", ".jsonl")
    end = events(log)[-1]
    assert without(end, "ended_at") == {
        "type": "game_end",
        "result": "1-0",
        "reason": "checkmate",
        "plies": 7,
        "stats": {
            "white": None,
            "black": {
                "legal_move_streak": 3,
                "illegal_moves": {"invalid": 0, "illegal": 0, "ambiguous": 0},
                "recovered_turns": 0,
                "notation_slips": 0,
            },
        },
    }
    [pgn_file] = logs(tmp_path / "games", ".pgn")
    assert pgn_file.stem == log.stem
    game = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
    assert game.headers["White"] == "Human"
    assert game.headers["Black"] == "qwen3.5:9b (thinking)"
    assert game.headers["Result"] == "1-0"
    assert game.headers["Termination"] == "checkmate"
    assert game.headers["Mode"] == "Play LLM"
    assert game.headers["BlackLLMConstraints"] == "free"
    assert "WhiteLLMConstraints" not in game.headers
    assert game.board().variation_san(game.mainline_moves()) == "1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7#"


def test_a_forfeit_is_logged_with_its_illegal_moves_and_pgn(scripted, tmp_path):
    client, _ = scripted(["Qh4", "banana", "O-O", "Nd7"])

    play(client, "e2e4")

    end = events(logs(tmp_path / "games", ".jsonl")[0])[-1]
    assert (end["result"], end["reason"], end["plies"]) == ("1-0", "forfeit", 1)
    assert end["stats"]["black"]["illegal_moves"] == {"invalid": 1, "illegal": 3, "ambiguous": 0}
    pgn = logs(tmp_path / "games", ".pgn")[0].read_text(encoding="utf-8")
    assert '[Termination "forfeit"]' in pgn
    assert "1. e4 1-0" in pgn


def test_a_timeout_is_logged_as_an_attempt_without_a_reply(scripted, tmp_path):
    client, _ = scripted([LlmTimeout(300)])

    play(client, "e2e4")

    *_, attempt, end = events(logs(tmp_path / "games", ".jsonl")[0])
    assert (attempt["result"], attempt["raw_reply"], attempt["move"]) == ("timeout", None, None)
    assert attempt["error"] == "Too long thinking: qwen3.5:9b gave no answer within 5 minutes."
    assert end["reason"] == "forfeit"


def test_a_game_abandoned_with_new_game_keeps_its_log_so_far(scripted, tmp_path):
    client, _ = scripted(["e5"])
    play(client, "e2e4")

    client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True))

    first, second = logs(tmp_path / "games", ".jsonl")
    assert [event["type"] for event in events(first)] == ["game_start", "human_move", "llm_attempt"]
    assert [event["type"] for event in events(second)] == ["game_start"]
    assert logs(tmp_path / "games", ".pgn") == []


def test_each_game_gets_its_own_files_and_id(scripted, tmp_path):
    client, _ = scripted([])

    for _ in range(3):
        client.post("/api/games")

    starts = [events(log)[0] for log in logs(tmp_path / "games", ".jsonl")]
    assert len({start["game_id"] for start in starts}) == 3


def test_the_log_records_the_retry_feedback_and_the_sampling_from_the_config(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("temperature = 0.2\n")
    client, _ = scripted([], sampling_file=config)

    client.post("/api/games", json=play_llm(retry_feedback="hinted"))

    [log] = logs(tmp_path / "games", ".jsonl")
    [start] = events(log)
    assert (start["black"]["retry_feedback"], start["sampling"]) == ("hinted", {"temperature": 0.2})


def test_with_the_human_as_black_the_llm_is_white_in_the_log_and_the_file_names(scripted, tmp_path):
    client, _ = scripted(["e4", "Qh5", "Bc4", "Qxf7#"])
    client.post("/api/games", json=play_llm("black", model="qwen3.5:9b", thinking=True, llm_constraints="listed"))
    client.post("/api/games/current/llm-turn")
    for uci in ["e7e5", "b8c6", "g8f6"]:
        play_move(client, uci)

    [log] = logs(tmp_path / "games", ".jsonl")
    assert log.name.endswith("_qwen3.5-9b_vs_human.jsonl")
    start, *moves, end = events(log)
    assert (start["white"], start["black"]) == (QWEN_THINKING | {"llm_constraints": "listed"}, {"player": "human"})
    assert [(event["type"], event["color"]) for event in moves] == [
        ("llm_attempt", "white"),
        ("human_move", "black"),
        ("llm_attempt", "white"),
        ("human_move", "black"),
        ("llm_attempt", "white"),
        ("human_move", "black"),
        ("llm_attempt", "white"),
    ]
    assert (end["result"], end["stats"]["black"], end["stats"]["white"]["legal_move_streak"]) == ("1-0", None, 4)
    [pgn_file] = logs(tmp_path / "games", ".pgn")
    assert pgn_file.stem == log.stem
    game = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
    assert (game.headers["White"], game.headers["Black"]) == ("qwen3.5:9b (thinking)", "Human")
    assert (game.headers["Mode"], game.headers["WhiteLLMConstraints"]) == ("Play LLM", "listed")
    assert "BlackLLMConstraints" not in game.headers
