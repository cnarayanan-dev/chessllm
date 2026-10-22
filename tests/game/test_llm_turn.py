from tests.conftest import Raw, play_llm, play_move

from chessllm.game.session import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.players import Message

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
    play_move(client, "e2e4")
    play_move(client, "g1f3")

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


def test_each_attempt_in_the_state_carries_the_prompt_exactly_as_sent(scripted):
    client, _ = scripted(["e5"])
    client.post("/api/games")

    state = play_move(client, "e2e4").json()

    assert state["llm_turn"]["attempts"][0]["prompt"] == [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": "PGN: 1. e4\nFEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"},
    ]


def test_there_is_no_llm_turn_before_the_llm_has_moved(scripted):
    client, _ = scripted([])

    assert client.post("/api/games").json()["llm_turn"] is None


def test_a_legal_reply_is_applied_and_its_thinking_shown_in_the_state(scripted):
    client, _ = scripted(["e5", "Nc6"], thinking=["Mirror the centre pawn.", "Defend e5."])
    client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True))
    play_move(client, "e2e4")

    state = play_move(client, "g1f3").json()

    assert state["pgn"] == "1. e4 e5 2. Nf3 Nc6"
    assert state["last_move"] == "b8c6"
    del state["llm_turn"]["attempts"][0]["prompt"]  # the prompt has its own test
    assert state["llm_turn"] == {
        "ply": 4,
        "color": "black",
        "attempts": [
            {
                "move": "Nc6",
                "san": "Nc6",
                "notation_slip": False,
                "result": "legal",
                "feedback_sent": None,
                "raw_reply": '{"move": "Nc6"}',
                "thinking": "Defend e5.",
                "reasoning": None,
                "error": None,
                "latency_s": 0.0,
            }
        ],
        "thinking": "Defend e5.",
        "reasoning": None,
    }


def test_the_default_opponent_is_llama_with_thinking_off(scripted):
    client, _ = scripted([])

    assert client.post("/api/games").json()["settings"] == {
        "mode": "play_llm",
        "white": {"player": "human"},
        "black": {
            "player": "llm",
            "model": "llama3:8b",
            "thinking": False,
            "llm_constraints": "free",
            "retry_feedback": "explained",
        },
        "sampling": {},
        "max_attempts": 5,
    }


def test_the_game_reports_the_settings_it_was_started_with(scripted):
    client, _ = scripted([])

    state = client.post("/api/games", json=play_llm(model="llama3:8b", thinking=False, retry_feedback="bare")).json()

    assert state["settings"] == {
        "mode": "play_llm",
        "white": {"player": "human"},
        "black": {
            "player": "llm",
            "model": "llama3:8b",
            "thinking": False,
            "llm_constraints": "free",
            "retry_feedback": "bare",
        },
        "sampling": {},
        "max_attempts": 5,
    }


def test_the_player_for_a_game_is_built_once_from_that_games_settings(scripted):
    client, player = scripted(["e5", "Nc6", "d5"])
    client.post("/api/games", json=play_llm(model="llama3:8b", thinking=False))
    play_move(client, "e2e4")

    state = play_move(client, "g1f3").json()

    assert player.built_for == [Settings(black=LlmSide(model="llama3:8b", thinking=False))]
    assert (state["settings"]["black"]["model"], state["settings"]["black"]["thinking"]) == ("llama3:8b", False)


def test_settings_sent_for_a_new_game_apply_only_to_that_game(scripted):
    client, player = scripted(["Qh4", "e5", "d5"])
    client.post("/api/games", json=play_llm(model="llama3:8b", thinking=False, retry_feedback="bare"))
    playing = play_move(client, "e2e4").json()

    state = client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True)).json()
    play_move(client, "d2d4")

    assert playing["llm_turn"]["attempts"][1]["feedback_sent"].endswith("Try again.")  # bare
    assert player.built_for == [
        Settings(black=LlmSide(model="llama3:8b", thinking=False, retry_feedback="bare")),
        Settings(black=LlmSide(model="qwen3.5:9b", thinking=True)),
    ]
    assert state["settings"] == {
        "mode": "play_llm",
        "white": {"player": "human"},
        "black": {
            "player": "llm",
            "model": "qwen3.5:9b",
            "thinking": True,
            "llm_constraints": "free",
            "retry_feedback": "explained",
        },
        "sampling": {},
        "max_attempts": 5,
    }


def test_with_thinking_off_a_legal_reply_is_applied_and_its_reasoning_shown_with_no_thinking(scripted):
    reply = '{"reasoning": "Mirror the centre pawn.", "move": "e5"}'
    client, _ = scripted([Raw(reply)])
    client.post("/api/games", json=play_llm(thinking=False))

    state = play_move(client, "e2e4").json()

    assert state["pgn"] == "1. e4 e5"
    [attempt] = state["llm_turn"]["attempts"]
    assert attempt["result"] == "legal"
    assert attempt["move"] == "e5"
    assert (attempt["reasoning"], attempt["thinking"]) == ("Mirror the centre pawn.", None)
    assert (state["llm_turn"]["reasoning"], state["llm_turn"]["thinking"]) == ("Mirror the centre pawn.", None)


def test_a_new_game_clears_the_llm_turn(scripted):
    client, _ = scripted(["e5"], thinking=["Mirror the centre pawn."])
    client.post("/api/games")
    play_move(client, "e2e4")

    assert client.post("/api/games").json()["llm_turn"] is None
