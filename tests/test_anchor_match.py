"""Anchor match: one game of an LLM against an Anchor, played unattended from the command line."""

import io
import json

import chess.pgn
import pytest

from fastapi.testclient import TestClient

from conftest import ScriptedAnchor, ScriptedPlayer
from test_analysis import PeakedMoveModel
from test_move_cap import MOVE_CAP_PLIES, long_game, sans

from chessllm.analysis import analyse_game
from chessllm.anchor_match import main
from chessllm.anchors import ANCHOR_RATINGS, anchor_name
from chessllm.app import create_app


def events(games_dir) -> list[dict]:
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def pgn_game(games_dir) -> chess.pgn.Game:
    [pgn_file] = sorted(games_dir.glob("*.pgn"))
    game = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
    assert game is not None
    return game


@pytest.fixture
def anchor_match(tmp_path):
    """Runs the command with a ScriptedPlayer for the LLM and a ScriptedAnchor, logging to tmp_path / "games".
    Returns the exit code, the player, the anchor and the Anchor sides the anchor was built for."""

    def run(llm: list, anchor_moves: list[str], *args: str):
        player, anchor, built_for = ScriptedPlayer(llm), ScriptedAnchor(anchor_moves), []

        def anchor_for(side):
            built_for.append(side)
            return anchor

        code = main(
            ["--games-dir", str(tmp_path / "games"), *args],
            player_for=player.for_settings,
            anchor_for=anchor_for,
            sampling_file=tmp_path / "no-sampling.toml",
        )
        return code, player, anchor, built_for

    return run


def test_the_command_plays_one_game_against_dragon_and_logs_the_anchor_side(anchor_match, tmp_path):
    code, _, anchor, _ = anchor_match(
        ["e5", "Qh4#"], ["f3", "g4"], "--model", "llama3:8b", "--skill", "3", "--color", "black"
    )

    assert code == 0
    games_dir = tmp_path / "games"
    [log] = games_dir.glob("*.jsonl")
    assert log.name.endswith("_dragon-skill3_vs_llama3-8b.jsonl")
    start, *_, end = events(games_dir)
    assert start["type"] == "game_start"
    assert (start["log_version"], start["mode"]) == (2, "anchor_match")
    assert start["white"] == {"player": "anchor", "engine": "dragon", "skill": 3}
    assert start["black"] == {
        "player": "llm", "model": "llama3:8b", "thinking": False, "llm_constraints": "free", "retry_feedback": "explained",
    }
    assert "rules" not in start and start["prompt_file"].endswith("system.txt")
    assert (end["type"], end["result"], end["reason"], end["plies"]) == ("game_end", "0-1", "checkmate", 4)
    assert end["stats"]["white"] is None and end["stats"]["black"]["legal_move_streak"] == 2
    game = pgn_game(games_dir)
    assert (game.headers["White"], game.headers["Black"]) == ("Dragon (Skill 3)", "llama3:8b (no thinking)")
    assert (game.headers["Mode"], game.headers["Result"]) == ("Anchor match", "0-1")
    assert [move.uci() for move in game.mainline_moves()] == ["f2f3", "e7e5", "g2g4", "d8h4"]
    assert anchor.closed


def test_the_llms_retries_and_forfeit_are_logged_as_in_a_faceoff_and_the_anchor_wins(anchor_match, tmp_path):
    code, player, anchor, _ = anchor_match(
        ["Nf3", "Ke3", "Ke2", "Ke4", "Ke5"],
        ["e5"],
        "--model", "qwen3.5:9b", "--thinking", "--llm-constraints", "listed", "--retry-feedback", "bare",
        "--max-attempts", "4", "--color", "white", "--skill", "1",
    )

    assert code == 0
    start, *moves, end = events(tmp_path / "games")
    assert start["white"] == {
        "player": "llm", "model": "qwen3.5:9b", "thinking": True, "llm_constraints": "listed", "retry_feedback": "bare",
    }
    assert start["black"] == {"player": "anchor", "engine": "dragon", "skill": 1}
    assert [(event["type"], event.get("attempt"), event["move"]) for event in moves] == [
        ("llm_attempt", 1, "Nf3"),
        ("anchor_move", None, "e5"),
        ("llm_attempt", 1, "Ke3"),
        ("llm_attempt", 2, "Ke2"),
        ("llm_attempt", 3, "Ke4"),
        ("llm_attempt", 4, "Ke5"),
    ]
    assert moves[1] == {
        "type": "anchor_move", "color": "black", "ply": 2, "move": "e5",
        "fen_after": "rnbqkbnr/pppp1ppp/8/4p3/8/5N2/PPPPPPPP/RNBQKB1R w KQkq - 0 2",
    }
    assert moves[3]["feedback_sent"] is not None and "legal_moves" in moves[3]
    assert (end["result"], end["reason"], end["plies"]) == ("0-1", "forfeit", 2)
    assert end["stats"]["white"]["illegal_moves"]["illegal"] == 4 and end["stats"]["black"] is None
    assert anchor.positions == ["rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 1"]
    assert player.colors == ["white"] and player.built_for[0].mode == "anchor_match"
    assert pgn_game(tmp_path / "games").headers["White"] == "qwen3.5:9b (thinking)"


def test_the_leaderboard_counts_an_anchor_match_against_the_anchor_and_only_the_llms_attempts(anchor_match, tmp_path):
    # 1. Nf3 e5 2. Ke3 (illegal) Nd4 Qg5, then the LLM forfeits its third turn: with no reply left, the call fails.
    anchor_match(["Nf3", "Ke3", "Nd4"], ["e5", "Qg5"], "--color", "white", "--skill", "3")
    client = TestClient(create_app(lambda settings, color: None, games_dir=tmp_path / "games"))

    [entry] = client.get("/api/leaderboard").json()["configurations"]

    assert entry["configuration"]["model"] == "llama3:8b"
    assert (entry["games"], entry["wins"], entry["losses"], entry["forfeits"]) == (1, 0, 1, 1)
    assert (entry["legal_moves"], entry["attempts"]) == (2, 4)
    assert entry["opponents"] == [
        {"opponent": "anchor:dragon:3", "games": 1, "wins": 0, "draws": 0, "losses": 1}
    ]


def test_analysis_scores_only_the_llms_moves_and_leaves_the_anchor_side_null(anchor_match, tmp_path):
    anchor_match(["e5", "Qh4#"], ["f3", "g4"], "--color", "black")
    [log] = (tmp_path / "games").glob("*.jsonl")

    analysis = json.loads(analyse_game(log, PeakedMoveModel(black_peak=1200)).read_text(encoding="utf-8"))

    sides = analysis["move_quality"]["sides"]
    assert sides["white"] is None
    assert sides["black"]["estimate"] == 1200
    assert [move["move"] for move in sides["black"]["moves"]] == ["e7e5", "d8h4"]


def test_an_anchor_match_not_ended_after_150_moves_per_side_is_a_draw_at_the_move_cap(anchor_match, tmp_path):
    replies = sans(long_game(MOVE_CAP_PLIES + 2))

    code, player, anchor, _ = anchor_match(replies["black"], replies["white"], "--color", "black")

    assert code == 0
    end = events(tmp_path / "games")[-1]
    assert (end["type"], end["result"], end["reason"], end["plies"]) == ("game_end", "1/2-1/2", "move_cap", 300)
    assert (len(anchor.moves), len(player.replies)) == (1, 1)  # the 151st moves never asked for


@pytest.mark.parametrize(
    ("args", "error"),
    [
        (["--rules", "chaos"], "Only Stockfish can be the Anchor under Chaos rules"),
        (["--skill", "8"], "Dragon (black) plays at Skill 1-7, not 8"),
        (["--model", "nonesuch:1b"], "nonesuch:1b (white) is not in the model list"),
        (["--model", "llama3:8b", "--thinking"], "llama3:8b (white) cannot think"),
    ],
)
def test_settings_that_cant_be_played_are_refused_before_the_game_starts(anchor_match, tmp_path, capsys, args, error):
    code, player, _, built_for = anchor_match([], [], *args)

    assert code == 1
    assert error in capsys.readouterr().err
    assert built_for == [] and player.built_for == []
    assert not (tmp_path / "games").exists()


def test_the_app_doesnt_start_an_anchor_match(scripted):
    client, _ = scripted([])
    anchor = {"player": "anchor", "engine": "dragon", "skill": 1}

    for body in (
        {"mode": "anchor_match", "white": {"player": "llm"}, "black": anchor},
        {"mode": "llm_faceoff", "white": {"player": "llm"}, "black": anchor},
    ):
        assert client.post("/api/games", json=body).status_code == 422


def not_an_engine(tmp_path):
    script = tmp_path / "not-dragon"
    script.write_text("#!/bin/sh\necho 'not an engine'\nexit 1\n")
    script.chmod(0o755)
    return script


@pytest.mark.parametrize(
    ("dragon", "error"),
    [
        (None, "Dragon isn't configured: pass --dragon or set CHESSLLM_DRAGON"),
        ("missing/dragon-osx", "Dragon isn't installed at"),
        (not_an_engine, "won't start"),
    ],
)
def test_a_missing_or_failing_dragon_is_a_clear_error_before_the_game_starts(
    tmp_path, capsys, monkeypatch, dragon, error
):
    monkeypatch.delenv("CHESSLLM_DRAGON", raising=False)
    player = ScriptedPlayer([])
    path = dragon(tmp_path) if callable(dragon) else dragon and str(tmp_path / dragon)

    code = main(
        ["--games-dir", str(tmp_path / "games"), *(["--dragon", str(path)] if path else [])],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 1
    assert error in capsys.readouterr().err
    assert player.built_for == [] and not (tmp_path / "games").exists()


def test_the_dragon_path_can_come_from_the_environment(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("CHESSLLM_DRAGON", str(tmp_path / "from-env" / "dragon-osx"))

    code = main(["--games-dir", str(tmp_path / "games")], sampling_file=tmp_path / "no-sampling.toml")

    assert code == 1
    assert f"Dragon isn't installed at {tmp_path / 'from-env' / 'dragon-osx'}" in capsys.readouterr().err


def test_stockfish_can_stand_in_for_dragon_and_is_logged_and_rated_as_its_own_anchor(anchor_match, tmp_path):
    code, _, _, built_for = anchor_match(["e5", "Qh4#"], ["f3", "g4"], "--engine", "stockfish", "--color", "black")

    assert code == 0
    assert [(side.engine, side.skill) for side in built_for] == [("stockfish", 1)]
    [log] = (tmp_path / "games").glob("*.jsonl")
    assert log.name.endswith("_stockfish-skill1_vs_llama3-8b.jsonl")
    start = events(tmp_path / "games")[0]
    assert start["white"] == {"player": "anchor", "engine": "stockfish", "skill": 1}
    assert pgn_game(tmp_path / "games").headers["White"] == "Stockfish (Skill 1)"
    assert anchor_name(start["white"]) in ANCHOR_RATINGS


def test_under_chaos_rules_the_llms_illegal_move_is_played_against_the_stockfish_anchor(anchor_match, tmp_path):
    # Qxe8 isn't legal (the queen can't get there), but under Chaos rules it is played, and takes the king.
    code, _, _, built_for = anchor_match(
        ["e4", "Qxe8"], ["e5"], "--engine", "stockfish", "--rules", "chaos", "--color", "white"
    )

    assert code == 0
    assert [side.engine for side in built_for] == ["stockfish"]
    start, *_, end = events(tmp_path / "games")
    assert start["rules"] == "chaos"
    assert (end["result"], end["reason"]) == ("1-0", "king_capture")
    assert end["stats"]["white"]["chaos_moves"] == 1
