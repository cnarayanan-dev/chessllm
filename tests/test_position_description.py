"""Position description: an LLM side can be told, next to the PGN and FEN, the last move, where every piece stands
and whether it is in check, so that it needn't decode the FEN to know its own pieces."""

import json

import chess

from conftest import ScriptedPlayer

from chessllm.faceoff_batch import main
from chessllm.leaderboard import llm_configuration
from chessllm.prompt import describe_position, turn_messages


def test_the_description_lists_the_last_move_both_sides_pieces_and_check():
    board = chess.Board()
    for san in ["f3", "e5", "g4", "Qh4+"]:
        board.push_san(san)

    description = describe_position(board, last_move="Qh4+")

    assert description.splitlines() == [
        "Last move: Qh4+",
        "Your pieces (White): King e1; Queen d1; Rooks a1, h1; Bishops c1, f1; Knights b1, g1; "
        "Pawns a2, b2, c2, d2, e2, f3, g4, h2",
        "Opponent's pieces (Black): King e8; Queen h4; Rooks a8, h8; Bishops c8, f8; Knights b8, g8; "
        "Pawns a7, b7, c7, d7, e5, f7, g7, h7",
        "You are in check.",
    ]


def test_without_a_last_move_or_check_those_lines_are_left_out():
    description = describe_position(chess.Board(), last_move=None)

    assert description.splitlines()[0].startswith("Your pieces (White): King e1;")
    assert "check" not in description and "Last move" not in description


def test_the_description_goes_under_the_fen_in_the_turns_message():
    board = chess.Board()
    [_, user] = turn_messages("", board.fen(), "white", description=describe_position(board, None))

    assert user.content.splitlines()[1].startswith("FEN: ")
    assert user.content.splitlines()[2].startswith("Your pieces (White):")


def test_a_described_faceoff_logs_the_setting_and_is_its_own_player_configuration(tmp_path):
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])

    code = main(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "1", "--position", "described", "--games-dir",
         str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    [log] = tmp_path.glob("*.jsonl")
    start = json.loads(log.read_text().splitlines()[0])
    assert start["white"]["position"] == "described" and start["black"]["position"] == "described"
    # Black's prompt at ply 4 described the position after 2. g4.
    last_prompt = player.prompts[-1][-1].content
    assert "Last move: g4" in last_prompt and "Your pieces (Black):" in last_prompt
    described = llm_configuration(start, "white", start["white"])
    plain = llm_configuration(start, "white", {k: v for k, v in start["white"].items() if k != "position"})
    assert described.position == "described" and plain.position is None
    assert described.id() != plain.id()


def test_the_default_isnt_logged_so_older_games_keep_their_configuration(tmp_path):
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])

    main(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "1", "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    [log] = tmp_path.glob("*.jsonl")
    start = json.loads(log.read_text().splitlines()[0])
    assert "position" not in start["white"]
    assert "Your pieces" not in player.prompts[-1][-1].content


def test_a_described_attempt_logs_its_prompt_with_the_description(tmp_path):
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])

    main(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "1", "--position", "described", "--games-dir",
         str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    [log] = tmp_path.glob("*.jsonl")
    attempts = [event for event in map(json.loads, log.read_text().splitlines()) if event["type"] == "llm_attempt"]
    position = attempts[-1]["prompt"][-1]["content"]
    assert "Last move: g4" in position and "Your pieces (Black):" in position
