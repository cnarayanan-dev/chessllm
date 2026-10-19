import pytest
from conftest import Raw, play_llm, play_move

from chessllm.players import LlmTimeout, Message

E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def explained(move: str, kind: str, attempt: int) -> str:
    return (
        f'Your move "{move}" is illegal in this position (kind: {kind} move). '
        f"Attempt {attempt} of 5. Reply with a different legal move."
    )


def start(scripted, replies, **kwargs):
    client, player = scripted(replies, **kwargs)
    client.post("/api/games", json=play_llm(model="qwen3.5:9b", thinking=True))
    return client, player


def attempts(state):
    return [(attempt["move"], attempt["result"]) for attempt in state["llm_turn"]["attempts"]]


@pytest.mark.parametrize(
    ("reply", "move", "kind"),
    [
        ("Qh4", "Qh4", "illegal"),  # blocked by the e7 pawn
        ("O-O", "O-O", "illegal"),  # pieces in the way
        ("banana", "banana", "invalid"),  # not SAN
        ("--", "--", "invalid"),  # a null move would let Black pass
        (Raw("e5"), "e5", "invalid"),  # not JSON: the raw reply stands in for the move
        (Raw(""), "", "invalid"),  # an empty answer
        (Raw('{"mv": "e5"}'), '{"mv": "e5"}', "invalid"),  # JSON without a move
    ],
)
def test_each_illegal_move_is_recorded_with_its_kind_and_the_board_stays_unchanged(scripted, reply, move, kind):
    client, _ = start(scripted, [reply, "e5"])

    state = play_move(client, "e2e4").json()

    assert attempts(state) == [(move, kind), ("e5", "legal")]
    assert state["pgn"] == "1. e4 e5"


def test_an_ambiguous_move_is_its_own_kind(scripted):
    # Both knights can reach d7, so "Nd7" doesn't say which one.
    client, _ = start(scripted, ["Nf6", "d6", "Nd7", "Nbd7"])
    for uci in ["e2e4", "g1f3"]:
        play_move(client, uci)

    state = play_move(client, "b1c3").json()

    assert attempts(state) == [("Nd7", "ambiguous"), ("Nbd7", "legal")]


def test_a_retry_adds_the_rejected_answer_and_the_explained_feedback(scripted):
    client, player = start(scripted, ["Qh4", "banana", "e5"])

    state = play_move(client, "e2e4").json()

    first_prompt = player.prompts[0]
    feedback_1 = explained("Qh4", "illegal", 1)
    feedback_2 = explained("banana", "invalid", 2)
    assert player.prompts[1] == first_prompt + [
        Message("assistant", '{"move": "Qh4"}'),
        Message("user", feedback_1),
    ]
    assert player.prompts[2] == player.prompts[1] + [
        Message("assistant", '{"move": "banana"}'),
        Message("user", feedback_2),
    ]
    assert [attempt["feedback_sent"] for attempt in state["llm_turn"]["attempts"]] == [None, feedback_1, feedback_2]


def test_each_attempt_records_the_raw_reply_and_its_thinking(scripted):
    client, _ = start(scripted, ["Qh4", "e5"], thinking=["The queen attacks f2.", "Take the centre."])

    state = play_move(client, "e2e4").json()

    assert [(a["raw_reply"], a["thinking"]) for a in state["llm_turn"]["attempts"]] == [
        ('{"move": "Qh4"}', "The queen attacks f2."),
        ('{"move": "e5"}', "Take the centre."),
    ]
    assert state["llm_turn"]["thinking"] == "Take the centre."


def test_a_turn_recovered_by_a_retry_is_counted(scripted):
    client, _ = start(scripted, ["Qh4", "e5"])

    state = play_move(client, "e2e4").json()

    assert state["status"] == "playing"
    assert state["stats"]["black"]["recovered_turns"] == 1
    assert state["stats"]["black"]["illegal_moves"] == {"invalid": 0, "illegal": 1, "ambiguous": 0}


def test_the_fifth_failed_attempt_forfeits_the_game(scripted):
    client, player = start(scripted, ["Qh4", "banana", "O-O", "Ke7", "Kd6"])

    state = play_move(client, "e2e4").json()

    assert len(player.prompts) == 5
    assert attempts(state) == [
        ("Qh4", "illegal"), ("banana", "invalid"), ("O-O", "illegal"), ("Ke7", "illegal"), ("Kd6", "illegal"),
    ]
    assert (state["status"], state["result"], state["end_reason"]) == ("over", "1-0", "forfeit")
    assert state["pgn"] == "1. e4"  # the human's move stays
    assert state["human_legal_moves"] == []
    assert state["stats"]["black"]["illegal_moves"] == {"invalid": 1, "illegal": 4, "ambiguous": 0}
    assert state["stats"]["black"]["recovered_turns"] == 0


def test_the_attempts_per_turn_can_be_chosen_for_the_game(scripted):
    client, player = scripted(["Qh4", "banana", "e5"])
    client.post("/api/games", json=play_llm(model="qwen3.5:9b") | {"max_attempts": 2})

    state = play_move(client, "e2e4").json()

    assert state["settings"]["max_attempts"] == 2
    assert attempts(state) == [("Qh4", "illegal"), ("banana", "invalid")]
    assert player.prompts[1][-1].content.endswith("Attempt 1 of 2. Reply with a different legal move.")
    assert (state["status"], state["result"], state["end_reason"]) == ("over", "1-0", "forfeit")


@pytest.mark.parametrize("max_attempts", [0, 26])
def test_attempts_per_turn_outside_1_to_25_are_refused(scripted, max_attempts):
    client, _ = scripted(["e5"])

    response = client.post("/api/games", json=play_llm() | {"max_attempts": max_attempts})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("failure", "result", "error"),
    [
        (LlmTimeout(300), "timeout", "Too long thinking: qwen3.5:9b gave no answer within 5 minutes."),
        (ConnectionError("Ollama is not running"), "error", "qwen3.5:9b did not reply: Ollama is not running"),
    ],
)
def test_a_timeout_or_a_failed_call_forfeits_at_once(scripted, failure, result, error):
    client, player = start(scripted, [failure, "e5"])

    state = play_move(client, "e2e4").json()

    assert len(player.prompts) == 1
    [attempt] = state["llm_turn"]["attempts"]
    assert (attempt["move"], attempt["result"], attempt["error"]) == (None, result, error)
    assert (state["status"], state["result"], state["end_reason"]) == ("over", "1-0", "forfeit")
    assert state["pgn"] == "1. e4"


def test_a_timeout_after_an_illegal_move_still_forfeits_at_once(scripted):
    client, player = start(scripted, ["Qh4", LlmTimeout(300), "e5"])

    state = play_move(client, "e2e4").json()

    assert len(player.prompts) == 2
    assert attempts(state) == [("Qh4", "illegal"), (None, "timeout")]
    assert state["end_reason"] == "forfeit"


def test_the_legal_move_streak_stops_at_the_first_illegal_move(scripted):
    client, _ = start(scripted, ["e5", "Nc6", "Qxf2", "Nf6", "d6"])
    play_move(client, "e2e4")
    state = play_move(client, "g1f3").json()
    assert state["stats"]["black"]["legal_move_streak"] == 2

    state = play_move(client, "b1c3").json()  # Qxf2 fails, Nf6 recovers
    assert state["stats"]["black"]["legal_move_streak"] == 2

    state = play_move(client, "d2d4").json()
    assert state["stats"]["black"]["legal_move_streak"] == 2
    assert state["stats"]["black"]["recovered_turns"] == 1


def test_a_new_game_starts_with_clean_stats(scripted):
    client, _ = start(scripted, ["Qh4", "e5"])
    play_move(client, "e2e4")

    state = client.post("/api/games").json()

    assert state["stats"]["black"] == {
        "legal_move_streak": 0,
        "illegal_moves": {"invalid": 0, "illegal": 0, "ambiguous": 0},
        "recovered_turns": 0,
        "notation_slips": 0,
    }
    assert state["llm_turn"] is None


def test_bare_feedback_says_only_that_the_move_was_illegal(scripted):
    client, player = scripted(["Qh4", "banana", "e5"])
    client.post("/api/games", json=play_llm(retry_feedback="bare"))

    state = play_move(client, "e2e4").json()

    assert [prompt[-1].content for prompt in player.prompts[1:]] == [
        'Your move "Qh4" is illegal. Attempt 1 of 5. Try again.',
        'Your move "banana" is illegal. Attempt 2 of 5. Try again.',
    ]
    assert state["settings"]["black"]["retry_feedback"] == "bare"


def test_hinted_feedback_adds_the_legal_moves_in_san(scripted):
    client, player = scripted(["Qh4", "e5"])
    client.post("/api/games", json=play_llm(retry_feedback="hinted"))

    play_move(client, "e2e4")

    legal_after_e4 = (
        "Nh6 Nf6 Nc6 Na6 h6 g6 f6 e6 d6 c6 b6 a6 h5 g5 f5 e5 d5 c5 b5 a5"
    )
    assert player.prompts[1][-1].content == explained("Qh4", "illegal", 1) + f"\nLegal moves: {legal_after_e4}"


def test_an_unknown_retry_feedback_level_is_refused(scripted):
    client, _ = scripted([])

    assert client.post("/api/games", json=play_llm(retry_feedback="loud")).status_code == 422
