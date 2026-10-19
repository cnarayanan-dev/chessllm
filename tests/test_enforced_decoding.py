import json

import chess
import pytest

from chessllm.players import Message
from chessllm.prompt import LISTED_SYSTEM_PROMPT_FILE, SYSTEM_PROMPT_FILE, system_prompt

E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
BLACK_MOVES_AFTER_E4 = sorted(chess.Board(E4_FEN).san(move) for move in chess.Board(E4_FEN).legal_moves)
NOT_APPLICABLE = {"legal_move_streak": None, "illegal_moves": None, "recovered_turns": None}


def start_game(scripted, llm_constraints, replies):
    client, player = scripted(replies)
    client.post("/api/games", json={"llm_constraints": llm_constraints})
    return client, player


def log_events(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("llm_constraints", ["blind_enforced", "listed_enforced"])
def test_the_enforced_constraints_are_accepted_and_copied_into_the_game(scripted, llm_constraints):
    client, player = start_game(scripted, llm_constraints, [])

    state = client.get("/api/games/current").json()

    assert state["settings"]["llm_constraints"] == llm_constraints
    assert [settings.llm_constraints for settings in player.built_for] == [llm_constraints]


@pytest.mark.parametrize("llm_constraints", ["blind_enforced", "listed_enforced"])
def test_enforced_decoding_allows_exactly_the_legal_moves_each_turn(scripted, llm_constraints):
    client, player = start_game(scripted, llm_constraints, ["e5", "Nc6"])

    client.post("/api/games/current/moves", json={"uci": "e2e4"})
    client.post("/api/games/current/moves", json={"uci": "g1f3"})

    after_nf3 = chess.Board()
    for san in ["e4", "e5", "Nf3"]:
        after_nf3.push_san(san)
    first, second = player.allowed_moves
    assert sorted(first) == BLACK_MOVES_AFTER_E4
    assert sorted(second) == sorted(after_nf3.san(move) for move in after_nf3.legal_moves)


@pytest.mark.parametrize("llm_constraints", ["free", "listed"])
def test_without_enforced_decoding_no_moves_are_allowed_in_particular(scripted, llm_constraints):
    client, player = start_game(scripted, llm_constraints, ["e5"])

    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    assert player.allowed_moves == [None]


def test_blind_enforced_sends_the_free_prompt_with_no_list(scripted, tmp_path):
    client, player = start_game(scripted, "blind_enforced", ["e5"])

    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    [prompt] = player.prompts
    assert prompt == [Message("system", system_prompt("black", SYSTEM_PROMPT_FILE)), Message("user", f"PGN: 1. e4\nFEN: {E4_FEN}")]
    start, _, attempt = log_events(tmp_path / "games")
    assert start["prompt_file"] == str(SYSTEM_PROMPT_FILE)
    assert "legal_moves" not in attempt


def test_listed_enforced_sends_the_listed_prompt_and_list(scripted, tmp_path):
    client, player = start_game(scripted, "listed_enforced", ["e5"])

    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    [prompt] = player.prompts
    assert prompt[0] == Message("system", system_prompt("black", LISTED_SYSTEM_PROMPT_FILE))
    *_, last_line = prompt[1].content.splitlines()
    shown = last_line.removeprefix("Legal moves: ")
    assert sorted(shown.split(" ")) == BLACK_MOVES_AFTER_E4
    start, _, attempt = log_events(tmp_path / "games")
    assert start["prompt_file"] == str(LISTED_SYSTEM_PROMPT_FILE)
    assert attempt["legal_moves"] == shown


@pytest.mark.parametrize("llm_constraints", ["blind_enforced", "listed_enforced"])
def test_the_illegal_move_metrics_are_not_applicable_in_the_state_under_enforced_decoding(scripted, llm_constraints):
    client, _ = start_game(scripted, llm_constraints, ["e5"])

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert state["stats"] == NOT_APPLICABLE | {"notation_slips": 0}


@pytest.mark.parametrize("llm_constraints", ["blind_enforced", "listed_enforced"])
def test_an_illegal_move_that_gets_through_is_retried_and_logged_but_the_totals_stay_null(
    scripted, tmp_path, llm_constraints
):
    client, player = start_game(scripted, llm_constraints, ["Qh4", "e5"])

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert [attempt["result"] for attempt in state["llm_turn"]["attempts"]] == ["illegal", "legal"]
    assert state["llm_turn"]["attempts"][1]["feedback_sent"] is not None
    assert len(player.allowed_moves) == 2 and player.allowed_moves[0] == player.allowed_moves[1]
    assert state["stats"] == NOT_APPLICABLE | {"notation_slips": 0}
    attempts = [event for event in log_events(tmp_path / "games") if event["type"] == "llm_attempt"]
    assert [attempt["result"] for attempt in attempts] == ["illegal", "legal"]


@pytest.mark.parametrize("llm_constraints", ["blind_enforced", "listed_enforced"])
def test_the_game_end_line_records_the_metrics_as_not_applicable(scripted, tmp_path, llm_constraints):
    client, _ = start_game(scripted, llm_constraints, ["Qh4"] * 4)

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()  # four illegal moves: a forfeit

    assert state["end_reason"] == "forfeit"
    *_, end = log_events(tmp_path / "games")
    assert end["type"] == "game_end"
    assert end["stats"] == {"white": None, "black": NOT_APPLICABLE | {"notation_slips": 0}}


@pytest.mark.parametrize("llm_constraints", ["blind_enforced", "listed_enforced"])
def test_a_failed_call_still_forfeits_under_enforced_decoding(scripted, llm_constraints):
    client, _ = start_game(scripted, llm_constraints, [RuntimeError("Ollama is not running")])

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert (state["status"], state["end_reason"]) == ("over", "forfeit")
    assert state["llm_turn"]["attempts"][0]["result"] == "error"


def test_free_and_listed_keep_counting_the_illegal_move_metrics(scripted):
    client, _ = start_game(scripted, "listed", ["Qh4", "e5"])

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert state["stats"] == {
        "legal_move_streak": 0,
        "illegal_moves": {"invalid": 0, "illegal": 1, "ambiguous": 0},
        "recovered_turns": 1,
        "notation_slips": 0,
    }
