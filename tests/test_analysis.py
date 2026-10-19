"""Game analysis files: each finished game's Move-quality estimate per LLM side, from a MoveModel.

The fake MoveModel's probabilities are rigged to peak at a known rating, so the estimate must recover it."""

import json
import math

import chess

from conftest import play_llm, play_move

from chessllm.analysis import analyse_game

RATINGS = tuple(range(800, 2001, 100))


class PeakedMoveModel:
    """Test fake for the MoveModel port: every move is most likely for a player rated at the peak of its colour,
    and less likely the further the rating is from it. Records every position and move it is asked about."""

    version = "fake-move-model 1"
    ratings = RATINGS

    def __init__(self, white_peak: int = 1400, black_peak: int = 1400) -> None:
        self.peaks = {chess.WHITE: white_peak, chess.BLACK: black_peak}
        self.asked: list[tuple[str, str]] = []

    def probabilities(self, fen: str, move: str) -> list[float]:
        self.asked.append((fen, move))
        peak = self.peaks[chess.Board(fen).turn]
        return [0.4 * math.exp(-(((rating - peak) / 400) ** 2)) for rating in self.ratings]


def game_files(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return log, log.with_name(f"{log.stem}.analysis.json")


def scholars_mate(scripted, replies=("e5", "Nc6", "Nf6")):
    """A Play LLM game in which the human (White) mates the LLM in four moves."""
    client, _ = scripted(list(replies))
    client.post("/api/games", json=play_llm(model="qwen3.5:9b"))
    for uci in ("e2e4", "f1c4", "d1h5", "h5f7"):
        state = play_move(client, uci).json()
    assert state["status"] == "over"
    return client


def test_a_finished_game_is_analysed_into_a_file_with_the_llms_move_quality_estimate(scripted, tmp_path):
    scholars_mate(scripted)
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, PeakedMoveModel(black_peak=1400))

    analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
    assert analysis["game_log"] == log.name
    assert analysis["versions"] == {"move_model": "fake-move-model 1"}
    quality = analysis["move_quality"]
    assert quality["scale"] == "lichess_rapid"
    assert quality["ratings"] == list(RATINGS)
    black = quality["sides"]["black"]
    assert black["estimate"] == 1400
    low, high = black["interval"]
    assert 800 <= low < 1400 < high <= 2000
    assert [(move["ply"], move["move"]) for move in black["moves"]] == [(2, "e7e5"), (4, "b8c6"), (6, "g8f6")]
    assert len(black["moves"][0]["log_probabilities"]) == len(RATINGS)


def test_each_llm_side_of_a_faceoff_gets_its_own_estimate(faceoff, tmp_path):
    client, _, _ = faceoff(["f3", "g4"], ["e5", "Qh4#"])  # Fool's mate
    for _ in range(4):
        client.post("/api/games/current/llm-turn")
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, PeakedMoveModel(white_peak=1100, black_peak=1700))

    sides = json.loads(analysis_file.read_text(encoding="utf-8"))["move_quality"]["sides"]
    assert (sides["white"]["estimate"], sides["black"]["estimate"]) == (1100, 1700)
    assert [move["move"] for move in sides["white"]["moves"]] == ["f2f3", "g2g4"]
    assert [move["move"] for move in sides["black"]["moves"]] == ["e7e5", "d8h4"]


def test_human_moves_and_illegal_attempts_are_not_scored(scripted, tmp_path):
    model = PeakedMoveModel()
    scholars_mate(scripted, replies=["Qh4", "banana", "e5", "Nc6", "Nf6"])
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, model)

    sides = json.loads(analysis_file.read_text(encoding="utf-8"))["move_quality"]["sides"]
    assert sides["white"] is None
    assert [move["move"] for move in sides["black"]["moves"]] == ["e7e5", "b8c6", "g8f6"]
    assert [move for _, move in model.asked] == ["e7e5", "b8c6", "g8f6"]


def test_chaos_moves_are_not_scored(scripted, tmp_path):
    client, _ = scripted(["Bc5", "Nf6", "Nc6"])  # Bc5 goes through the bishop's own e7 pawn: a chaos move
    client.post("/api/games", json=play_llm() | {"rules": "chaos"})
    for uci in ("e2e4", "d2d4", "g1f3"):
        play_move(client, uci)
    log, analysis_file = game_files(tmp_path / "games")
    attempts = [event for event in map(json.loads, log.read_text().splitlines()) if event["type"] == "llm_attempt"]
    assert [(attempt["ply"], attempt["result"]) for attempt in attempts] == [(2, "illegal"), (4, "legal"), (6, "legal")]

    analyse_game(log, PeakedMoveModel())

    black = json.loads(analysis_file.read_text(encoding="utf-8"))["move_quality"]["sides"]["black"]
    assert [move["ply"] for move in black["moves"]] == [4, 6]


def test_the_game_log_is_unchanged_by_analysis(scripted, tmp_path):
    scholars_mate(scripted)
    log, _ = game_files(tmp_path / "games")
    before = log.read_bytes()

    analyse_game(log, PeakedMoveModel())

    assert log.read_bytes() == before
    assert sorted(path.name for path in log.parent.iterdir()) == sorted(
        [log.name, f"{log.stem}.pgn", f"{log.stem}.analysis.json"]
    )


def test_a_version_1_log_is_analysed_from_its_llm_attempts(tmp_path):
    e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
    log = tmp_path / "2026-10-18T20-58-46_qwen3.5-9b.jsonl"
    lines = [
        {"type": "game_start", "game_id": "v1", "model": "qwen3.5:9b", "llm_color": "black", "mode": "free"},
        {"type": "human_move", "ply": 1, "move": "e4", "fen_after": e4},
        {"type": "llm_attempt", "ply": 2, "attempt": 1, "pgn": "1. e4", "fen": e4, "move": "e5", "result": "legal"},
        {"type": "game_end", "result": "1-0", "reason": "forfeit", "plies": 2},
    ]
    log.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")

    analyse_game(log, PeakedMoveModel(black_peak=1200))

    analysis = json.loads((tmp_path / "2026-10-18T20-58-46_qwen3.5-9b.analysis.json").read_text(encoding="utf-8"))
    assert analysis["game_id"] == "v1"
    sides = analysis["move_quality"]["sides"]
    assert sides["white"] is None
    assert sides["black"]["estimate"] == 1200
    assert [(move["ply"], move["move"]) for move in sides["black"]["moves"]] == [(2, "e7e5")]


def test_an_llm_side_without_a_legal_move_has_no_estimate(scripted, tmp_path):
    client, _ = scripted(["Qh4", "Qh5", "Qh6", "Ke2"])  # four illegal moves: a forfeit before any legal move
    client.post("/api/games", json=play_llm())
    assert play_move(client, "e2e4").json()["end_reason"] == "forfeit"
    log, analysis_file = game_files(tmp_path / "games")

    analyse_game(log, PeakedMoveModel())

    black = json.loads(analysis_file.read_text(encoding="utf-8"))["move_quality"]["sides"]["black"]
    assert black == {"estimate": None, "interval": None, "moves": []}


def finished_and_unfinished_games(scripted, tmp_path):
    """Two finished games and one still being played, in tmp_path / "games"."""
    client, _ = scripted(["e5", "Nc6", "Nf6", "e5", "Nc6", "Nf6", "e5"])
    for _ in range(2):
        client.post("/api/games", json=play_llm())
        for uci in ("e2e4", "f1c4", "d1h5", "h5f7"):
            play_move(client, uci)
    client.post("/api/games", json=play_llm())
    play_move(client, "e2e4")
    return sorted((tmp_path / "games").glob("*.jsonl"))


def test_the_command_analyses_every_finished_game_without_an_analysis_file(scripted, tmp_path):
    from chessllm.analysis import analyse_games

    first, second, unfinished = finished_and_unfinished_games(scripted, tmp_path)
    first.with_name(f"{first.stem}.analysis.json").write_text("earlier analysis", encoding="utf-8")

    written = analyse_games(tmp_path / "games", PeakedMoveModel())

    assert written == [second.with_name(f"{second.stem}.analysis.json")]
    assert first.with_name(f"{first.stem}.analysis.json").read_text(encoding="utf-8") == "earlier analysis"
    assert not unfinished.with_name(f"{unfinished.stem}.analysis.json").exists()


def test_the_command_re_analyses_every_finished_game_when_asked(scripted, tmp_path):
    from chessllm.analysis import analyse_games

    first, second, unfinished = finished_and_unfinished_games(scripted, tmp_path)
    first.with_name(f"{first.stem}.analysis.json").write_text("earlier analysis", encoding="utf-8")

    written = analyse_games(tmp_path / "games", PeakedMoveModel(), reanalyse=True)

    assert written == [log.with_name(f"{log.stem}.analysis.json") for log in (first, second)]
    assert json.loads(written[0].read_text(encoding="utf-8"))["move_quality"]["sides"]["black"]["estimate"] == 1400


def test_a_game_is_analysed_when_it_ends(scripted, tmp_path):
    client, _ = scripted(["e5", "Nc6", "Nf6"], move_model=PeakedMoveModel(black_peak=1600))
    client.post("/api/games", json=play_llm())

    for uci in ("e2e4", "f1c4", "d1h5"):
        play_move(client, uci)
    log, analysis_file = game_files(tmp_path / "games")
    assert not analysis_file.exists()  # not while the game goes on
    play_move(client, "h5f7")

    analysis = json.loads(analysis_file.read_text(encoding="utf-8"))
    assert analysis["move_quality"]["sides"]["black"]["estimate"] == 1600


def test_a_faceoff_is_analysed_when_its_last_llm_turn_ends_it(faceoff, tmp_path):
    client, _, _ = faceoff(["f3", "g4"], ["e5", "Qh4#"], move_model=PeakedMoveModel(white_peak=900))

    for _ in range(4):
        client.post("/api/games/current/llm-turn")

    _, analysis_file = game_files(tmp_path / "games")
    assert json.loads(analysis_file.read_text(encoding="utf-8"))["move_quality"]["sides"]["white"]["estimate"] == 900
