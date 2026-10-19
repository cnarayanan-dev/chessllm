from conftest import play_llm, play_move


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
    client.post("/api/games", json=play_llm("black"))
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


START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
AFTER_E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


def test_a_new_game_has_no_plies(scripted):
    client, _ = scripted([])

    assert client.post("/api/games").json()["plies"] == []


def test_each_ply_has_its_move_and_the_positions_before_and_after_it(scripted):
    client, _ = scripted(["e5"])
    client.post("/api/games")

    state = play_move(client, "e2e4").json()

    e4 = {"ply": 1, "color": "white", "move": "e2e4", "written": "e4", "fen_before": START, "fen_after": AFTER_E4}
    e5 = {"ply": 2, "color": "black", "move": "e7e5", "written": "e5", "fen_before": AFTER_E4, "fen_after": AFTER_E5}
    assert state["plies"] == [e4 | {"check": False}, e5 | {"check": False}]
    assert state["plies"][-1]["fen_after"] == state["fen"]


def test_a_ply_says_whether_it_gave_check(scripted):
    client, _ = scripted(["f5", "g6"])
    client.post("/api/games")
    play_move(client, "e2e4")

    state = play_move(client, "d1h5").json()  # 2. Qh5+

    assert [(ply["written"], ply["check"]) for ply in state["plies"]] == [
        ("e4", False), ("f5", False), ("Qh5+", True), ("g6", False),
    ]


def test_a_ply_is_written_as_in_the_move_record_and_a_promotion_keeps_its_piece_in_uci(scripted):
    client, _ = scripted(["h5", "h4", "h3", "hxg2", "gxh1=Q"])
    client.post("/api/games")
    for uci in ("a2a4", "a4a5", "a5a6", "a6b7"):
        play_move(client, uci)

    state = play_move(client, "b7a8n").json()

    assert [(ply["move"], ply["written"]) for ply in state["plies"][-2:]] == [("b7a8n", "bxa8=N"), ("g2h1q", "gxh1=Q")]
    assert [ply["written"] for ply in state["plies"]] == [token for token in state["pgn"].split() if "." not in token]


def test_a_forfeited_turn_adds_no_ply(scripted):
    client, _ = scripted(["Ke6", "banana", "O-O", "Qa1"])
    client.post("/api/games")

    state = play_move(client, "e2e4").json()

    assert [ply["written"] for ply in state["plies"]] == ["e4"]
    assert state["llm_turn"]["ply"] == 2  # the turn that failed to play ply 2
