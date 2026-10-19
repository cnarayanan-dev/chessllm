"""Centipawn loss and accuracy: Stockfish diagnostics of each LLM side's legal moves, in the game's analysis file
and pooled per Player configuration on the leaderboard. Never an Elo (ADR 0005).

A fake Evaluator gives fixed evaluations, so the expected values are worked out by hand from the lichess formulas
(https://lichess.org/page/accuracy): with Win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1), a move from
0 to -100 (Win% 50 to 40.90) has accuracy 103.1668 * exp(-0.04354 * 9.10) - 3.1669 + 1 = 67.24, and a move from 0
into a mate (capped at -1000, Win% 2.46) has accuracy 10.85."""

import json

import chess
import pytest
from chess.engine import Cp, Mate, Score

from conftest import ScriptedAnchor, ScriptedPlayer, play_llm, play_move

from chessllm.analysis import analyse_game, analyse_games
from chessllm.anchor_match import main as anchor_match
from chessllm.maia2_model import Maia2Unavailable
from chessllm.stockfish_evaluator import StockfishUnavailable


def fen_after(*sans: str) -> str:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board.fen()


class FixedEvaluator:
    """Test fake for the Evaluator port: each position's evaluation, relative to the side to move, from a table,
    and 0 for any other position. Records every position it is asked about."""

    version = "fake-engine 1"
    search = {"depth": 1}

    def __init__(self, scores: dict[str, Score] | None = None) -> None:
        self.scores = scores or {}
        self.asked: list[str] = []

    def evaluate(self, fen: str) -> Score:
        self.asked.append(fen)
        return self.scores.get(fen, Cp(0))


# After 2...Nc6 White is a pawn up in the fake's eyes, and 3...Nf6 allows mate in one.
SCHOLARS_MATE_SCORES = {
    fen_after("e4", "e5", "Bc4", "Nc6"): Cp(100),
    fen_after("e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6"): Mate(1),
}


def scholars_mate(scripted, replies=("e5", "Nc6", "Nf6"), **options):
    """A Play LLM game in which the human (White) mates the LLM in four moves. Returns its log."""
    client, _ = scripted(list(replies), **options)
    client.post("/api/games", json=play_llm(model="qwen3.5:9b"))
    for uci in ("e2e4", "f1c4", "d1h5", "h5f7"):
        state = play_move(client, uci).json()
    assert state["status"] == "over"
    return client


def game_files(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return log, log.with_name(f"{log.stem}.analysis.json")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_analysis_file_holds_each_llm_sides_centipawn_loss_and_accuracy(scripted, tmp_path):
    scholars_mate(scripted)
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, None, FixedEvaluator(SCHOLARS_MATE_SCORES))

    analysis = read(analysis_file)
    assert analysis["versions"] == {"stockfish": "fake-engine 1"}
    diagnostics = analysis["centipawn_loss_and_accuracy"]
    assert diagnostics["search"] == {"depth": 1}
    assert diagnostics["sides"]["white"] is None
    black = diagnostics["sides"]["black"]
    assert [(move["ply"], move["move"], move["centipawn_loss"]) for move in black["moves"]] == [
        (2, "e7e5", 0),
        (4, "b8c6", 100),
        (6, "g8f6", 1000),
    ]
    assert [move["accuracy"] for move in black["moves"]] == pytest.approx([100, 67.24, 10.85], abs=0.01)
    assert black["average_centipawn_loss"] == pytest.approx(1100 / 3)
    assert black["accuracy"] == pytest.approx((100 + 67.24 + 10.85) / 3, abs=0.01)


class FlatMoveModel:
    """Test fake for the MoveModel port: every move equally likely at every rating."""

    version = "fake-move-model 1"
    ratings = (1000, 1500)

    def probabilities(self, fen: str, move: str) -> list[float]:
        return [0.5, 0.5]


def test_with_both_engines_the_analysis_file_names_both_versions(scripted, tmp_path):
    scholars_mate(scripted)
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, FlatMoveModel(), FixedEvaluator())

    analysis = read(analysis_file)
    assert analysis["versions"] == {"move_model": "fake-move-model 1", "stockfish": "fake-engine 1"}
    assert analysis["move_quality"]["sides"]["black"]["estimate"] is not None
    assert analysis["centipawn_loss_and_accuracy"]["sides"]["black"]["average_centipawn_loss"] == 0


def test_illegal_attempts_and_human_moves_are_not_scored(scripted, tmp_path):
    evaluator = FixedEvaluator()
    scholars_mate(scripted, replies=["Qh4", "banana", "e5", "Nc6", "Nf6"])
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, None, evaluator)

    black = read(analysis_file)["centipawn_loss_and_accuracy"]["sides"]["black"]
    assert [move["move"] for move in black["moves"]] == ["e7e5", "b8c6", "g8f6"]
    # Each move's position before and after it; the last one is mate in one, not mate, so it is searched too.
    assert len(evaluator.asked) == 6


def test_chaos_moves_are_not_scored(scripted, tmp_path):
    client, _ = scripted(["Bc5", "Nf6", "Nc6"])  # Bc5 goes through the bishop's own e7 pawn: a chaos move
    client.post("/api/games", json=play_llm() | {"rules": "chaos"})
    for uci in ("e2e4", "d2d4", "g1f3"):
        play_move(client, uci)
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, None, FixedEvaluator())

    black = read(analysis_file)["centipawn_loss_and_accuracy"]["sides"]["black"]
    assert [move["ply"] for move in black["moves"]] == [4, 6]


def test_a_move_that_mates_is_perfect_without_searching_the_mated_position(faceoff, tmp_path):
    client, _, _ = faceoff(["f3", "g4"], ["e5", "Qh4#"])  # Fool's mate
    for _ in range(4):
        client.post("/api/games/current/llm-turn")
    log, analysis_file = game_files(tmp_path / "games")
    evaluator = FixedEvaluator({fen_after("f3", "e5", "g4"): Mate(1)})

    analyse_game(log, None, evaluator)

    black = read(analysis_file)["centipawn_loss_and_accuracy"]["sides"]["black"]
    assert [(move["move"], move["centipawn_loss"], move["accuracy"]) for move in black["moves"]] == [
        ("e7e5", 0, 100),
        ("d8h4", 0, 100),
    ]
    assert fen_after("f3", "e5", "g4", "Qh4#") not in evaluator.asked


class UnavailableEvaluator:
    """Test fake for the Evaluator port when Stockfish isn't installed."""

    search = {"depth": 1}

    @property
    def version(self) -> str:
        raise StockfishUnavailable("stockfish is not on the PATH")

    def evaluate(self, fen: str) -> Score:
        raise StockfishUnavailable("stockfish is not on the PATH")


class UnavailableMoveModel:
    """Test fake for the MoveModel port when Maia-2 can't start."""

    @property
    def version(self) -> str:
        raise Maia2Unavailable("uv is not installed")

    @property
    def ratings(self) -> list[int]:
        raise Maia2Unavailable("uv is not installed")

    def probabilities(self, fen: str, move: str) -> list[float]:
        raise Maia2Unavailable("uv is not installed")


def test_without_stockfish_the_move_quality_estimate_is_still_analysed(scripted, tmp_path):
    scholars_mate(scripted)
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, FlatMoveModel(), UnavailableEvaluator())

    analysis = read(analysis_file)
    assert analysis["versions"] == {"move_model": "fake-move-model 1"}
    assert analysis["move_quality"] is not None
    assert analysis["centipawn_loss_and_accuracy"] is None


def test_without_maia2_centipawn_loss_and_accuracy_are_still_analysed(scripted, tmp_path):
    scholars_mate(scripted)
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, UnavailableMoveModel(), FixedEvaluator())

    analysis = read(analysis_file)
    assert analysis["versions"] == {"stockfish": "fake-engine 1"}
    assert analysis["move_quality"] is None
    assert analysis["centipawn_loss_and_accuracy"]["sides"]["black"]["accuracy"] == 100


def test_re_analysing_all_games_recomputes_them(scripted, tmp_path):
    scholars_mate(scripted)
    log, analysis_file = game_files(tmp_path / "games")
    analyse_game(log, None, FixedEvaluator())

    written = analyse_games(tmp_path / "games", None, FixedEvaluator(SCHOLARS_MATE_SCORES), reanalyse=True)

    assert written == [analysis_file]
    assert read(analysis_file)["centipawn_loss_and_accuracy"]["sides"]["black"]["average_centipawn_loss"] == 1100 / 3


def leaderboard_entries(client):
    response = client.get("/api/leaderboard")
    assert response.status_code == 200, response.text
    return response.json()["configurations"]


def test_the_leaderboard_averages_centipawn_loss_and_accuracy_over_all_analysed_moves(scripted, tmp_path):
    client = scholars_mate(scripted, replies=["e5", "Nc6", "Nf6", "e5", "Ke3", "Qh6", "Nf3", "Rh5"])
    client.post("/api/games", json=play_llm(model="qwen3.5:9b"))  # 1...e5, then a forfeit before a second move
    play_move(client, "e2e4")
    assert play_move(client, "f1c4").json()["end_reason"] == "forfeit"
    first, second = sorted((tmp_path / "games").glob("*.jsonl"))
    analyse_game(first, None, FixedEvaluator(SCHOLARS_MATE_SCORES))
    analyse_game(second, None, FixedEvaluator())

    [qwen] = leaderboard_entries(client)

    # Pooled over the four moves, not averaged over the two games (which would give 1100 / 6).
    assert qwen["average_centipawn_loss"] == pytest.approx(1100 / 4)
    assert qwen["average_accuracy"] == pytest.approx((100 + 67.24 + 10.85 + 100) / 4, abs=0.01)


def test_a_configuration_without_analysed_moves_has_no_centipawn_loss_or_accuracy(scripted, tmp_path):
    client = scholars_mate(scripted)
    [log] = (tmp_path / "games").glob("*.jsonl")
    analyse_game(log, FlatMoveModel(), None)  # Maia-2 ran, Stockfish didn't

    [qwen] = leaderboard_entries(client)

    assert qwen["average_centipawn_loss"] is None
    assert qwen["average_accuracy"] is None


def test_a_game_analysed_by_stockfish_alone_has_no_move_quality_estimate_on_the_leaderboard(scripted, tmp_path):
    client = scholars_mate(scripted)
    [log] = (tmp_path / "games").glob("*.jsonl")
    analyse_game(log, None, FixedEvaluator(SCHOLARS_MATE_SCORES))  # Stockfish ran, Maia-2 didn't

    [qwen] = leaderboard_entries(client)

    assert qwen["move_quality"] is None
    assert qwen["average_centipawn_loss"] == pytest.approx(1100 / 3)


def test_an_anchor_match_is_analysed_for_the_llm_and_not_the_anchor(tmp_path):
    anchor_match(
        ["--games-dir", str(tmp_path / "games"), "--color", "black"],
        player_for=ScriptedPlayer(["e5", "Qh4#"]).for_settings,
        anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, None, FixedEvaluator())

    sides = read(analysis_file)["centipawn_loss_and_accuracy"]["sides"]
    assert sides["white"] is None
    assert [(move["move"], move["accuracy"]) for move in sides["black"]["moves"]] == [("e7e5", 100), ("d8h4", 100)]


def test_a_game_is_analysed_by_stockfish_when_it_ends(scripted, tmp_path):
    scholars_mate(scripted, evaluator=FixedEvaluator(SCHOLARS_MATE_SCORES))

    _, analysis_file = game_files(tmp_path / "games")
    analysis = read(analysis_file)
    assert analysis["versions"] == {"stockfish": "fake-engine 1"}
    assert analysis["centipawn_loss_and_accuracy"]["sides"]["black"]["average_centipawn_loss"] == 1100 / 3
