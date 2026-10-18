import pytest
from conftest import Raw

from chessllm.game import Settings
from chessllm.players import LlmTimeout, Message

DEFAULT_SYSTEM_PROMPT = """You are playing chess as Black against a human playing White.
Each turn you get the game so far in PGN and the current position in FEN.
Reply with your next move in SAN (e.g. Nf6, exd5, O-O, e8=Q).
The move must be legal in the current position.

Example:
PGN: 1. e4
FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1
Answer: {"move": "e5"}
"""


def test_each_turn_sends_only_the_system_prompt_and_the_current_pgn_and_fen(scripted):
    client, player = scripted(["e5", "Nc6"])
    client.post("/api/games")
    client.post("/api/games/current/moves", json={"uci": "e2e4"})
    client.post("/api/games/current/moves", json={"uci": "g1f3"})

    assert player.prompts == [
        [
            Message("system", DEFAULT_SYSTEM_PROMPT),
            Message("user", "PGN: 1. e4\nFEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"),
        ],
        [
            Message("system", DEFAULT_SYSTEM_PROMPT),
            Message(
                "user",
                "PGN: 1. e4 e5 2. Nf3\nFEN: rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2",
            ),
        ],
    ]


def test_there_is_no_llm_turn_before_the_llm_has_moved(scripted):
    client, _ = scripted([])

    assert client.post("/api/games").json()["llm_turn"] is None


def test_a_legal_reply_is_applied_and_its_thinking_shown_in_the_state(scripted):
    client, _ = scripted(["e5", "Nc6"], thinking=["Mirror the centre pawn.", "Defend e5."])
    client.post("/api/games")
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    state = client.post("/api/games/current/moves", json={"uci": "g1f3"}).json()

    assert state["pgn"] == "1. e4 e5 2. Nf3 Nc6"
    assert state["last_move"] == "b8c6"
    assert state["llm_turn"] == {
        "attempts": [{"move": "Nc6", "result": "legal", "feedback_sent": None}],
        "thinking": "Defend e5.",
    }


@pytest.mark.parametrize(
    "reply",
    [
        "Qh4",  # blocked by the e7 pawn
        "banana",  # not SAN
        Raw("e5"),  # not JSON
        Raw('{"mv": "e5"}'),  # JSON without a move
    ],
)
def test_a_bad_llm_reply_is_reported_as_an_error_without_changing_the_game(scripted, reply):
    client, _ = scripted([reply])
    before = client.post("/api/games").json()

    response = client.post("/api/games/current/moves", json={"uci": "e2e4"})

    assert response.status_code == 502
    assert "qwen3.5:9b" in response.json()["detail"]
    assert client.get("/api/games/current").json() == before


def test_the_human_can_play_again_after_a_bad_llm_reply(scripted):
    client, _ = scripted(["Qh4", "e5"])
    client.post("/api/games")
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    state = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()

    assert state["pgn"] == "1. e4 e5"


def test_a_turn_over_the_time_limit_is_reported_as_too_long_thinking_without_changing_the_game(scripted):
    client, _ = scripted([LlmTimeout(300)])
    before = client.post("/api/games").json()

    response = client.post("/api/games/current/moves", json={"uci": "e2e4"})

    assert response.status_code == 502
    assert response.json()["detail"] == "Too long thinking: qwen3.5:9b gave no answer within 5 minutes."
    assert client.get("/api/games/current").json() == before


def test_the_default_opponent_is_qwen_with_thinking_on(scripted):
    client, _ = scripted([])

    assert client.post("/api/games").json()["settings"] == {"model": "qwen3.5:9b", "thinking": True}


def test_the_game_reports_the_settings_it_was_started_with(scripted):
    client, _ = scripted([], settings=Settings(model="gemma3:4b"))

    assert client.post("/api/games").json()["settings"] == {"model": "gemma3:4b", "thinking": True}


def test_a_new_game_clears_the_llm_turn(scripted):
    client, _ = scripted(["e5"], thinking=["Mirror the centre pawn."])
    client.post("/api/games")
    client.post("/api/games/current/moves", json={"uci": "e2e4"})

    assert client.post("/api/games").json()["llm_turn"] is None
