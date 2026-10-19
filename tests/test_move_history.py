from conftest import play_move


def turns(state):
    """Each LLM turn of the game as (ply, [(move, result), ...])."""
    return [
        (turn["ply"], [(attempt["move"], attempt["result"]) for attempt in turn["attempts"]])
        for turn in state["llm_turns"]
    ]


def test_the_state_keeps_the_attempts_of_every_llm_turn_with_its_ply(scripted):
    client, _ = scripted(["Qh4", "e5", "Nc6"])
    client.post("/api/games")
    play_move(client, "e2e4")

    state = play_move(client, "g1f3").json()

    assert turns(state) == [(2, [("Qh4", "illegal"), ("e5", "legal")]), (4, [("Nc6", "legal")])]
    assert state["llm_turn"] == state["llm_turns"][-1]


def test_a_forfeited_turn_is_kept_at_the_ply_the_llm_failed_to_play(scripted):
    client, _ = scripted(["e5", "Ke6", "banana", "O-O", "Qa1"])
    client.post("/api/games")
    play_move(client, "e2e4")

    state = play_move(client, "g1f3").json()

    assert turns(state) == [
        (2, [("e5", "legal")]),
        (4, [("Ke6", "illegal"), ("banana", "invalid"), ("O-O", "illegal"), ("Qa1", "illegal")]),
    ]


def test_the_llm_playing_white_has_its_turns_at_odd_plies(scripted):
    client, _ = scripted(["Kd3", "e4", "Nf3"])
    client.post("/api/games", json={"human_color": "black"})
    client.post("/api/games/current/llm-turn")

    state = play_move(client, "e7e5").json()

    assert turns(state) == [(1, [("Kd3", "illegal"), ("e4", "legal")]), (3, [("Nf3", "legal")])]


def test_a_new_game_starts_with_no_llm_turns(scripted):
    client, _ = scripted(["Qh4", "e5"])
    client.post("/api/games")
    play_move(client, "e2e4")

    state = client.post("/api/games").json()

    assert state["llm_turns"] == []
    assert state["llm_turn"] is None
