"""Move cap: an unattended game (LLM faceoff) not ended by the rules after 150 moves per side is a draw."""

import io
import json
import random

import chess
import chess.pgn

from tests.conftest import play_llm, play_move

MOVE_CAP_PLIES = 300  # 150 moves per side


def ended(board: chess.Board) -> bool:
    """Whether the game would be over by the rules after the last move (claimable draws included)."""
    return board.is_game_over(claim_draw=False) or board.is_repetition(3) or board.halfmove_clock >= 100


KNIGHTS_HOME = (chess.G1, chess.G8, chess.F3, chess.F6)


def long_game(plies: int, seed: int = 0, knights_home: bool = False) -> list[chess.Move]:
    """A seeded random game of the given number of plies that the rules haven't ended by its last ply.
    Captures and pawn moves are preferred so the fifty-move rule never comes into play. With knights_home,
    the g-file knights never move and f3 and f6 stay empty, so the knights can shuffle at the end."""
    rng = random.Random(seed)
    for _ in range(100):
        board = chess.Board()
        while len(board.move_stack) < plies:
            moves = list(board.legal_moves)
            if knights_home:
                moves = [move for move in moves if not {move.from_square, move.to_square} & set(KNIGHTS_HOME)]
            rng.shuffle(moves)
            if board.halfmove_clock > 80:
                moves.sort(key=lambda move: not (board.is_capture(move) or board.piece_type_at(move.from_square) == chess.PAWN))
            for move in moves:
                board.push(move)
                if not ended(board):
                    break
                board.pop()
            else:
                break  # every move ends the game: start again
        if len(board.move_stack) == plies:
            return board.move_stack
    raise AssertionError("no long game found")


def sans(moves: list[chess.Move]) -> dict[str, list[str]]:
    """The SAN moves of each side, as their scripted replies."""
    board, replies = chess.Board(), {"white": [], "black": []}
    for move in moves:
        replies["white" if board.turn == chess.WHITE else "black"].append(board.san(move))
        board.push(move)
    return replies


def play_to_the_end(client) -> dict:
    for _ in range(MOVE_CAP_PLIES + 10):
        state = client.post("/api/games/current/llm-turn").json()
        if state["status"] == "over":
            return state
    raise AssertionError("the faceoff did not end")


def log_events(games_dir) -> list[dict]:
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_a_faceoff_not_ended_after_150_moves_per_side_is_a_draw_at_the_move_cap(faceoff, tmp_path):
    replies = sans(long_game(MOVE_CAP_PLIES + 2))
    client, _, players = faceoff(replies["white"], replies["black"])

    state = play_to_the_end(client)

    assert (state["result"], state["end_reason"]) == ("1/2-1/2", "move_cap")
    assert len(state["llm_turns"]) == MOVE_CAP_PLIES
    assert state["pgn"].split()[-3:-1] == ["150.", replies["white"][149]]
    assert (len(players["white"].replies), len(players["black"].replies)) == (1, 1)  # the 151st moves never asked for
    end = log_events(tmp_path / "games")[-1]
    assert (end["type"], end["result"], end["reason"], end["plies"]) == ("game_end", "1/2-1/2", "move_cap", 300)
    [pgn_file] = sorted((tmp_path / "games").glob("*.pgn"))
    pgn = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
    assert (pgn.headers["Result"], pgn.headers["Termination"]) == ("1/2-1/2", "move_cap")
    assert len(list(pgn.mainline_moves())) == MOVE_CAP_PLIES


def game_ending_in_repetition(plies: int) -> list[chess.Move]:
    """A random game whose last ply repeats a position for the third time, after two knight shuffles."""
    for seed in range(100):
        board = chess.Board()
        for move in long_game(plies - 8, seed, knights_home=True):
            board.push(move)
        try:
            for san in ["Nf3", "Nf6", "Ng1", "Ng8"] * 2:
                assert not ended(board)
                board.push_san(san)
        except (AssertionError, ValueError):
            continue
        if board.is_repetition(3):
            return board.move_stack
    raise AssertionError("no game ending in repetition found")


def test_a_faceoff_ended_by_the_rules_on_the_150th_move_keeps_the_rules_result(faceoff):
    replies = sans(game_ending_in_repetition(MOVE_CAP_PLIES))
    client, _, _ = faceoff(replies["white"], replies["black"])

    state = play_to_the_end(client)

    assert len(state["llm_turns"]) == MOVE_CAP_PLIES
    assert (state["result"], state["end_reason"]) == ("1/2-1/2", "threefold_repetition")


def test_a_faceoff_forfeited_on_the_150th_move_is_a_forfeit(faceoff):
    replies = sans(long_game(MOVE_CAP_PLIES - 1))
    client, _, _ = faceoff(replies["white"], replies["black"] + ["Ke9"] * 4)

    state = play_to_the_end(client)

    assert (state["result"], state["end_reason"]) == ("1-0", "forfeit")


def test_a_play_llm_game_goes_on_past_150_moves_per_side(scripted):
    moves = long_game(MOVE_CAP_PLIES + 2)
    replies = sans(moves)
    client, _ = scripted(replies["black"])
    client.post("/api/games", json=play_llm("white"))

    for move in moves[::2]:
        state = play_move(client, move.uci()).json()

    assert state["status"] == "playing"
    assert len(state["pgn"].split()) == 151 * 3
