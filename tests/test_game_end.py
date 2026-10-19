from typing import Any

import chess
import pytest

# Every game below is played from the start position through the API: the human's moves are posted
# as UCI and the scripted fake replies with Black's moves.

FOOLS_MATE_REVERSED = "1. e4 f6 2. d4 g5 3. Qh5#"
FOOLS_MATE = "1. f3 e5 2. g4 Qh4#"
# Sam Loyd's ten-move stalemate: White's last move leaves Black without a legal move.
STALEMATE = "1. e3 a5 2. Qh5 Ra6 3. Qxa5 h5 4. h4 Rah6 5. Qxc7 f6 6. Qxd7+ Kf7 7. Qxb7 Qd3 8. Qxb8 Qh7 9. Qxc8 Kg6 10. Qe6"
# Black's 4... Ng8 brings back the start position a third time.
THREEFOLD = "1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8"
# Only knights move, never capturing and never repeating a position. Black's 50th move completes
# fifty moves without a pawn move or capture.
FIFTY_MOVES = """
1. Na3 Na6 2. Nb1 Nb4 3. Na3 Nc6 4. Nb1 Na5 5. Na3 Nb3 6. Nb1 Nc5 7. Na3 Na4 8. Nb1 Nb6 9. Na3 Nc4
10. Nb1 Na3 11. Nc3 Nb1 12. Na4 Na3 13. Nb6 Nb1 14. Nc4 Na3 15. Na5 Nb1 16. Nb3 Na3 17. Nc5 Nb1
18. Na6 Na3 19. Nb4 Nb1 20. Nc6 Na3 21. Nb8 Nb1 22. Nf3 Na3 23. Na6 Nb1 24. Nb4 Na3 25. Nc6 Nb1
26. Na5 Na3 27. Nb3 Nb1 28. Nc5 Na3 29. Na4 Nb1 30. Nb6 Na3 31. Nc4 Nb1 32. Na3 Nc3 33. Nb1 Na4
34. Na3 Nb6 35. Nb1 Nc4 36. Na3 Na5 37. Nb1 Nb3 38. Na3 Nc5 39. Nb1 Na6 40. Na3 Nb4 41. Nb1 Nc6
42. Na3 Nb8 43. Nb1 Nf6 44. Na3 Na6 45. Nb1 Nb4 46. Na3 Nc6 47. Nb1 Na5 48. Na3 Nb3 49. Nb1 Nc5
50. Na3 Nh5
"""
# Everything is traded off until Black's last capture leaves king and knight against a bare king.
INSUFFICIENT_MATERIAL = """
1. g4 e5 2. h4 Qxh4 3. Bg2 Qxg4 4. Bxb7 Qxg1+ 5. Rxg1 c5 6. Bxc8 c4 7. Bxd7+ Kxd7 8. Rxg7 Bxg7
9. d4 exd4 10. Qxd4+ Bxd4 11. Be3 Bxb2 12. Bxa7 Bxa1 13. Bxb8 Rxa2 14. Kf1 Rxc2 15. e4 Rxf2+
16. Kxf2 Be5 17. Bxe5 Ke7 18. Bxh8 h6 19. Bb2 Kd7 20. Bc1 Ke8 21. Bxh6 Nxh6 22. e5 f6 23. exf6 Ng8
24. Nd2 Nxf6 25. Nxc4 Nd5 26. Ne3 Nxe3
"""


def play(scripted, movetext: str) -> tuple[Any, Any, dict[str, Any]]:
    """Start a game and play the movetext: White's moves are posted, Black's are the fake's replies."""
    sans = [token for token in movetext.split() if not token.endswith(".")]
    board = chess.Board()
    human_moves = []
    for san in sans:
        if board.turn == chess.WHITE:
            human_moves.append(board.parse_san(san).uci())
        board.push_san(san)
    client, player = scripted(sans[1::2])
    state = client.post("/api/games").json()
    for uci in human_moves:
        response = client.post("/api/games/current/moves", json={"uci": uci})
        assert response.status_code == 200, response.json()
        state = response.json()
        if state["status"] == "playing":
            response = client.post("/api/games/current/llm-turn")
            assert response.status_code == 200, response.json()
            state = response.json()
    return client, player, state


def test_a_new_game_is_playing_without_a_result(scripted):
    client, _ = scripted([])

    state = client.post("/api/games").json()

    assert state["status"] == "playing"
    assert state["result"] is None
    assert state["end_reason"] is None


def test_the_game_stays_playing_while_no_ending_is_reached(scripted):
    _, _, state = play(scripted, "1. e4 e5 2. Nf3 Nc6")

    assert state["status"] == "playing"
    assert state["result"] is None
    assert state["end_reason"] is None


@pytest.mark.parametrize(
    ("movetext", "result", "end_reason", "turn"),
    [
        pytest.param(FOOLS_MATE_REVERSED, "1-0", "checkmate", "black", id="human-checkmates"),
        pytest.param(FOOLS_MATE, "0-1", "checkmate", "white", id="llm-checkmates"),
        pytest.param(STALEMATE, "1/2-1/2", "stalemate", "black", id="stalemate"),
        pytest.param(THREEFOLD, "1/2-1/2", "threefold_repetition", "white", id="threefold-repetition"),
        pytest.param(FIFTY_MOVES, "1/2-1/2", "fifty_moves", "white", id="fifty-moves"),
        pytest.param(INSUFFICIENT_MATERIAL, "1/2-1/2", "insufficient_material", "white", id="insufficient-material"),
    ],
)
def test_each_ending_is_reported_with_its_result_and_reason(scripted, movetext, result, end_reason, turn):
    client, player, state = play(scripted, movetext)

    assert state["status"] == "over"
    assert state["result"] == result
    assert state["end_reason"] == end_reason
    assert state["turn"] == turn
    assert state["human_legal_moves"] == []
    assert player.replies == []  # the fake played every scripted move and was not asked for more
    assert client.get("/api/games/current").json() == state


def test_the_llm_is_not_asked_to_move_after_the_game_ends_on_the_humans_move(scripted):
    _, player, state = play(scripted, STALEMATE)

    assert state["pgn"].endswith("10. Qe6")
    assert len(player.prompts) == 9


def test_a_draw_black_could_claim_on_its_next_move_does_not_end_the_game_early(scripted):
    # Black could claim threefold repetition with Ng8, but plays on with e5 instead.
    _, player, state = play(scripted, "1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 e5")

    assert state["status"] == "playing"
    assert len(player.prompts) == 4


def test_the_fifty_move_draw_comes_after_fifty_moves_without_a_pawn_move_or_capture(scripted):
    _, _, state = play(scripted, FIFTY_MOVES)

    assert state["fen"].split()[4:] == ["100", "51"]  # halfmove clock and move number


def test_a_human_move_after_the_game_ends_is_rejected_without_asking_the_llm(scripted):
    client, player, before = play(scripted, INSUFFICIENT_MATERIAL)
    assert before["turn"] == "white"
    prompts = len(player.prompts)

    response = client.post("/api/games/current/moves", json={"uci": "f2f3"})  # a legal king move

    assert response.status_code == 400
    assert client.get("/api/games/current").json() == before
    assert len(player.prompts) == prompts


def test_a_new_game_after_the_end_is_playing_again(scripted):
    client, _, _ = play(scripted, FOOLS_MATE)

    state = client.post("/api/games").json()

    assert state["status"] == "playing"
    assert state["result"] is None
    assert state["end_reason"] is None
    assert len(state["human_legal_moves"]) == 20
