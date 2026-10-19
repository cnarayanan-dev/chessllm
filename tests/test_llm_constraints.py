import io
import json

import chess
import chess.pgn

from chessllm.game import Settings
from chessllm.players import Message
from chessllm.prompt import LISTED_SYSTEM_PROMPT_FILE, SYSTEM_PROMPT_FILE, system_prompt

E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
BLACK_MOVES_AFTER_E4 = {chess.Board(E4_FEN).san(move) for move in chess.Board(E4_FEN).legal_moves}


def listed_game(scripted, replies, **settings):
    client, player = scripted(replies)
    client.post("/api/games", json={"llm_constraints": "listed", **settings})
    return client, player


def shown_legal_moves(prompt: list[Message]) -> str:
    *_, last_line = prompt[1].content.splitlines()
    assert last_line.startswith("Legal moves: ")
    return last_line.removeprefix("Legal moves: ")


def log_events(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()], log


def test_the_llm_constraints_default_to_free(scripted):
    client, player = scripted([])

    state = client.post("/api/games").json()

    assert state["settings"]["llm_constraints"] == "free"
    assert player.built_for == [Settings()]


def test_listed_is_copied_into_the_game_and_applies_to_the_next_game_only(scripted):
    client, player = listed_game(scripted, ["e5", "e5"])
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    client.post("/api/games")
    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert [settings.llm_constraints for settings in player.built_for] == ["listed", "free"]
    assert state["settings"]["llm_constraints"] == "free"
    assert "Legal moves:" in player.prompts[0][1].content
    assert "Legal moves:" not in player.prompts[1][1].content


def test_unknown_llm_constraints_are_refused(scripted):
    client, _ = scripted([])

    assert client.post("/api/games", json={"llm_constraints": "enforced"}).status_code == 422


def test_listed_sends_the_listed_system_prompt_and_every_legal_move_under_the_pgn_and_fen(scripted):
    client, player = listed_game(scripted, ["e5"])

    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    [prompt] = player.prompts
    assert prompt[0] == Message("system", system_prompt("black", LISTED_SYSTEM_PROMPT_FILE))
    pgn_line, fen_line, _ = prompt[1].content.splitlines()
    assert (pgn_line, fen_line) == ("PGN: 1. e4", f"FEN: {E4_FEN}")
    shown = shown_legal_moves(prompt).split(" ")
    assert len(shown) == len(BLACK_MOVES_AFTER_E4)
    assert set(shown) == BLACK_MOVES_AFTER_E4


def test_the_listed_system_prompt_announces_the_list_and_its_random_order():
    prompt = system_prompt("black", LISTED_SYSTEM_PROMPT_FILE)

    assert "random" in prompt
    assert "Legal moves: " in prompt
    assert "$" not in prompt


def test_the_order_of_the_legal_moves_varies_between_turns(scripted):
    # Both knights go out and back, so the LLM is shown the position after 1. Nf3 on its first and third turns.
    client, player = listed_game(scripted, ["Nf6", "Ng8", "Nf6"])

    for uci in ["g1f3", "f3g1", "g1f3"]:
        client.post("/api/games/current/moves", json={"uci": uci})

    first, _, third = player.prompts
    position = lambda prompt: prompt[1].content.splitlines()[1].split(" ")[:5]  # the FEN without the move counters
    assert position(first) == position(third)
    assert set(shown_legal_moves(first).split(" ")) == set(shown_legal_moves(third).split(" "))
    assert shown_legal_moves(first) != shown_legal_moves(third)


def test_hinted_feedback_in_listed_repeats_the_list_shown_that_turn(scripted):
    client, player = listed_game(scripted, ["Qh4", "e5"], retry_feedback="hinted")

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    shown = shown_legal_moves(player.prompts[0])
    feedback = state["llm_turn"]["attempts"][1]["feedback_sent"]
    assert feedback.splitlines()[-1] == f"Legal moves: {shown}"


def test_the_log_records_the_llm_constraints_the_prompt_file_and_the_list_each_attempt_saw(scripted, tmp_path):
    client, player = listed_game(scripted, ["Qh4", "e5"])

    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    (start, _, attempt_1, attempt_2), _ = log_events(tmp_path / "games")
    assert start["black"]["llm_constraints"] == "listed"
    assert start["prompt_file"] == str(LISTED_SYSTEM_PROMPT_FILE)
    shown = shown_legal_moves(player.prompts[0])
    assert attempt_1["legal_moves"] == attempt_2["legal_moves"] == shown


def test_a_free_game_logs_free_and_no_legal_moves(scripted, tmp_path):
    client, _ = scripted(["e5"])
    client.post("/api/games")

    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    (start, _, attempt), _ = log_events(tmp_path / "games")
    assert start["black"]["llm_constraints"] == "free"
    assert start["prompt_file"] == str(SYSTEM_PROMPT_FILE)
    assert "legal_moves" not in attempt


def test_the_pgn_headers_name_the_llm_constraints(scripted, tmp_path):
    client, _ = listed_game(scripted, ["Qh4"] * 4)

    client.post("/api/games/current/moves", json={"uci": "e2e4"})  # four illegal moves: a forfeit ends the game

    _, log = log_events(tmp_path / "games")
    game = chess.pgn.read_game(io.StringIO(log.with_suffix(".pgn").read_text(encoding="utf-8")))
    assert game.headers["BlackLLMConstraints"] == "listed"
