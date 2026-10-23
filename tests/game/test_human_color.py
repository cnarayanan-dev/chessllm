import io
import json

import chess
import chess.pgn

from tests.conftest import play_llm, play_move

from chessllm.game.settings import Settings
from chessllm.game.sides import HumanSide, LlmSide
from chessllm.llm.players import Message
from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILE, system_prompt

START_FEN = chess.STARTING_FEN
E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"

SYSTEM_PROMPT_AS_WHITE = """You are playing chess as White against a human playing Black.
Each turn you get the game so far in PGN and the current position in FEN.
Reply with your next move in SAN (e.g. Nf6, exd5, O-O, e8=Q).
The move must be legal in the current position.

Example:
PGN: (no moves yet)
FEN: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
Answer: {"move": "e4"}
"""


def events(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_the_human_plays_white_by_default(scripted):
    client, player = scripted([])

    state = client.post("/api/games").json()

    assert (state["settings"]["mode"], state["settings"]["white"]) == ("play_llm", {"player": "human"})
    assert state["turn"] == "white"
    assert len(state["human_legal_moves"]) == 20
    assert player.prompts == []


def test_when_the_human_plays_black_the_llm_opens_the_game(scripted):
    client, player = scripted(["e4"])

    client.post("/api/games", json=play_llm("black"))

    state = client.post("/api/games/current/llm-turn").json()

    assert player.built_for == [Settings(white=LlmSide(), black=HumanSide())]
    assert state["pgn"] == "1. e4"
    assert state["fen"] == E4_FEN
    assert state["turn"] == "black"
    assert state["last_move"] == "e2e4"
    assert "e7e5" in state["human_legal_moves"]
    assert state["llm_turn"]["attempts"][0]["move"] == "e4"


def test_the_llm_playing_white_is_told_its_colour_and_shown_a_white_example(scripted):
    client, player = scripted(["e4", "Nf3"])
    client.post("/api/games", json=play_llm("black"))
    client.post("/api/games/current/llm-turn")
    play_move(client, "e7e5")

    assert player.prompts == [
        [Message("system", SYSTEM_PROMPT_AS_WHITE), Message("user", f"PGN: (no moves yet)\nFEN: {START_FEN}")],
        [
            Message("system", SYSTEM_PROMPT_AS_WHITE),
            Message("user", "PGN: 1. e4 e5\nFEN: rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"),
        ],
    ]


def test_the_human_playing_black_cannot_move_white_pieces(scripted):
    client, _ = scripted(["e4"])
    client.post("/api/games", json=play_llm("black"))
    client.post("/api/games/current/llm-turn")

    response = play_move(client, "d2d4")

    assert response.status_code == 400


def test_the_human_playing_black_can_checkmate_the_llm(scripted, tmp_path):
    client, _ = scripted(["f3", "g4"])
    client.post("/api/games", json=play_llm("black", model="qwen3.5:9b", thinking=True))
    client.post("/api/games/current/llm-turn")
    play_move(client, "e7e5")

    state = play_move(client, "d8h4").json()

    assert (state["status"], state["result"], state["end_reason"]) == ("over", "0-1", "checkmate")
    assert state["human_legal_moves"] == []
    [pgn_file] = sorted((tmp_path / "games").glob("*.pgn"))
    game = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
    assert (game.headers["White"], game.headers["Black"]) == ("qwen3.5:9b (thinking)", "Human")
    assert game.headers["Result"] == "0-1"


def test_an_llm_playing_white_that_forfeits_its_first_move_loses_as_white(scripted, tmp_path):
    client, _ = scripted(["e5", "Ke2", "banana", "Nf6"])

    client.post("/api/games", json=play_llm("black"))

    state = client.post("/api/games/current/llm-turn").json()

    assert (state["status"], state["result"], state["end_reason"]) == ("over", "0-1", "forfeit")
    start, *_, end = events(tmp_path / "games")
    assert (start["white"]["player"], start["black"]) == ("llm", {"player": "human"})
    assert (end["type"], end["result"], end["plies"]) == ("game_end", "0-1", 0)


def test_the_log_records_the_llm_as_black_when_the_human_plays_white(scripted, tmp_path):
    client, _ = scripted([])

    client.post("/api/games", json=play_llm("white"))

    [start] = events(tmp_path / "games")
    assert (start["white"], start["black"]["player"]) == ({"player": "human"}, "llm")


def test_a_side_other_than_white_or_black_is_refused(scripted):
    client, player = scripted([])

    response = client.post("/api/games", json=play_llm("red"))

    assert response.status_code == 422
    assert player.built_for == []


def test_every_prompt_file_fills_in_for_either_colour():
    for prompt_file in SYSTEM_PROMPT_FILE.parent.glob("*.txt"):
        for color, opponent in [("white", "Black"), ("black", "White")]:
            prompt = system_prompt(color, prompt_file)
            assert "$" not in prompt
            # The Tools prompt, played only in the benchmark's commands, never says the opponent is human (#119).
            against = opponent if prompt_file.name == "system_tools.txt" else f"a human playing {opponent}"
            assert f"as {color.capitalize()} against {against}" in prompt
