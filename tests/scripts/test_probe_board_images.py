"""The pure parts of the board-image probe (scripts/probe_board_images.py): reading and sampling positions from the
logs, rendering the board, the prompts per condition, and the scoring of moves and piece lists."""

import json

import chess
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from chessllm.llm.players import Message
from chessllm.game.prompt import turn_messages
from scripts.probe_board_images import (
    Position,
    ask_move,
    classify_illegal,
    move_messages,
    png_size,
    read_positions,
    render_png,
    sample_positions,
    score_pieces,
)

FREE = {"player": "llm", "model": "gemma3:12b", "thinking": False, "llm_constraints": "free", "retry_feedback": "explained"}
LISTED = FREE | {"llm_constraints": "listed"}
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


def write_game(games_dir, name, white, black, attempts, rules=None):
    start = {"type": "game_start", "game_id": name, "log_version": 2, "mode": "llm_faceoff", "white": white,
             "black": black, "sampling": "model_default", "max_retries": 4, "started_at": "2026-10-19T10:00:00+02:00"}
    if rules:
        start["rules"] = rules
    events = [start] + [{"type": "llm_attempt", "result": "legal", **attempt} for attempt in attempts]
    games_dir.mkdir(exist_ok=True)
    (games_dir / f"{name}.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def position(fen=AFTER_E4, pgn="1. e4", color="black", ply=2, phase="opening", in_check=False):
    return Position(fen, pgn, color, ply, phase, in_check, "game.jsonl")


def test_positions_are_the_first_attempts_of_free_sides_under_standard_rules_each_once(tmp_path):
    start = chess.STARTING_FEN
    first = {"color": "white", "ply": 1, "attempt": 1, "pgn": "", "fen": start}
    reply = {"color": "black", "ply": 2, "attempt": 1, "pgn": "1. e4", "fen": AFTER_E4}
    write_game(tmp_path, "a", FREE, LISTED, [first, first | {"attempt": 2}, reply])
    write_game(tmp_path, "b", FREE, FREE, [first])  # the same start position again
    write_game(tmp_path, "c", FREE, FREE, [reply], rules="chaos")

    positions = read_positions(tmp_path)

    assert positions == [Position(start, "", "white", 1, "opening", False, "a.jsonl")]


def test_the_sample_takes_its_in_check_positions_and_spreads_the_rest_over_the_stages():
    pool = [position(fen=f"{n}", ply=n, phase=phase) for n, phase in
            enumerate(["opening"] * 10 + ["middlegame"] * 10 + ["late"] * 2)]
    checks = [position(fen=f"check{n}", in_check=True) for n in range(5)]

    sample = sample_positions(pool + checks, 12, in_check=3, seed=1)

    assert len(sample) == 12 == len({p.fen for p in sample})
    assert sum(p.in_check for p in sample) == 3
    stages = [p.phase for p in sample if not p.in_check]
    assert stages.count("late") == 2  # all there are; the others make up the rest
    assert stages.count("opening") + stages.count("middlegame") == 7
    assert sample == sample_positions(pool + checks, 12, in_check=3, seed=1)
    assert [p.in_check for p in sample[:4]] == [True, False, False, False]  # interleaved, so a prefix is spread


def test_the_board_renders_as_a_png_of_the_asked_size():
    png = render_png(AFTER_E4, "black", size=256)

    assert png_size(png) == (256, 256)
    assert render_png(AFTER_E4, "black") != render_png(AFTER_E4, "white")  # seen from the mover's side


def test_text_is_the_games_prompt_text_plus_image_adds_one_line_and_image_has_no_fen_or_pgn():
    p = position()

    text = move_messages(p, "text")
    with_image = move_messages(p, "text+image")
    image_only = move_messages(p, "image")

    assert text == turn_messages("1. e4", AFTER_E4, "black")
    assert with_image[0] == text[0]
    assert with_image[1] == Message(
        "user", f"{text[1].content}\nBoard image: the current position, seen from your side (Black at the bottom)."
    )
    assert "Black" in image_only[0].content
    assert not any(word in m.content for m in image_only for word in ("FEN", "PGN", AFTER_E4, "1. e4"))


def test_a_move_is_asked_like_the_game_does_with_the_image_on_the_last_message_and_judged_by_the_game():
    calls = []

    def chat(**request):
        calls.append(request)
        return ChatResponse(message=OllamaMessage(role="assistant", content='{"reasoning": "x", "move": "Nf3"}'))

    after_nf3 = chess.Board()
    for san in ["e4", "e5", "Nf3", "Nc6"]:
        after_nf3.push_san(san)
    p = position(fen=after_nf3.fen(), pgn="1. e4 e5 2. Nf3 Nc6", color="white", ply=5)

    row = ask_move(chat, "gemma3:12b", p, "text+image", {})

    [request] = calls
    assert request["think"] is False and request["options"] is None
    assert list(request["format"]["properties"]) == ["reasoning", "move"]
    assert "images" not in request["messages"][0]
    assert png_size(request["messages"][-1]["images"][0]) == (512, 512)
    assert (row["result"], row["move"], row["san"], row["error_kind"]) == ("illegal", "Nf3", None, "own_piece_on_target")
    assert row["condition"] == "text+image" and row["fen"] == p.fen and row["latency_s"] >= 0


def test_illegal_moves_get_an_error_kind():
    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")  # White to move

    assert classify_illegal(board, "Nd2") == "own_piece_on_target"
    assert classify_illegal(board, "Nd5-f6") == "no_such_piece"
    assert classify_illegal(board, "Ng5") == "unreachable"
    assert classify_illegal(board, "e5") == "unreachable"
    assert classify_illegal(board, "O-O") == "castling"
    pinned = chess.Board("4k3/4r3/8/8/8/8/4N3/4K3 w - - 0 1")
    assert classify_illegal(pinned, "Nc3") == "king_in_check"


def test_a_piece_list_is_scored_against_the_side_to_moves_pieces():
    board = chess.Board("4k3/8/8/8/8/8/4P3/4K1N1 w - - 0 1")

    perfect = score_pieces(board, ["Ke1", "e2", "N-g1"])
    wrong = score_pieces(board, ["Ke1", "Pd2", "Qd1"])

    assert perfect == {"precision": 1.0, "recall": 1.0, "exact": True, "phantoms": [], "missed": []}
    assert wrong["recall"] == 1 / 3 and wrong["precision"] == 1 / 3
    assert wrong["phantoms"] == ["Pd2", "Qd1"] and wrong["missed"] == ["Ng1", "Pe2"]
