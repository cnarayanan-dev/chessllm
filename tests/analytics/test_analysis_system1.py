"""Game analysis of a game with a System 1 side: its moves get a Move-quality estimate, and a centipawn loss and
accuracy, like an LLM's. They are read from its system1_turn events and the position replayed from the game (a turn that
wasn't asked has no state to read it from)."""

import json

from tests.analytics.test_analysis import PeakedMoveModel
from tests.cli.test_report import game, write_log
from tests.fakes import FixedEvaluator
from tests.system1.logs import Turn, anchor_side, system1_game, system1_side

from chessllm.analytics.analysis import analyse_game, analyse_games

FOOLS_MATE = ["f3", Turn("e5", {"e5": 0.7, "d5": 0.3}), "g4", Turn("Qh4#", {"Qh4#": 1.0})]


def write(tmp_path, events):
    log = tmp_path / "game.jsonl"
    log.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return log


def analysis_of(log, **models):
    analyse_game(log, models.get("move_model"), models.get("evaluator"))
    return json.loads(log.with_name("game.analysis.json").read_text(encoding="utf-8"))


def test_a_system_1_sides_moves_get_a_move_quality_estimate_and_an_anchors_do_not(tmp_path):
    log = write(tmp_path, system1_game(anchor_side(), system1_side(), FOOLS_MATE, "0-1", "checkmate"))

    quality = analysis_of(log, move_model=PeakedMoveModel(black_peak=1400))["move_quality"]

    assert quality["sides"]["white"] is None
    black = quality["sides"]["black"]
    assert black["estimate"] == 1400
    assert [(move["ply"], move["move"]) for move in black["moves"]] == [(2, "e7e5"), (4, "d8h4")]
    assert black["moves"][0]["fen"] == "rnbqkbnr/pppppppp/8/8/8/5P2/PPPPP1PP/RNBQKBNR b KQkq - 0 1"


def test_a_turn_that_was_not_asked_is_scored_from_the_replayed_position(tmp_path):
    # White's second move is forced: after 4...Qxf2+ only Kxf2 is legal.
    plies = [Turn("e3", {"e3": 0.5, "e4": 0.5}), "e5", Turn("c4", {"c4": 1.0}), "Qe7", Turn("g4", {"g4": 1.0}), "Qf6",
             Turn("e4", {"e4": 1.0}), "Qxf2+", Turn("Kxf2")]
    log = write(tmp_path, system1_game(system1_side(), anchor_side(), plies))
    model = PeakedMoveModel(white_peak=1200)

    white = analysis_of(log, move_model=model)["move_quality"]["sides"]["white"]

    forced = white["moves"][-1]
    assert (forced["ply"], forced["move"]) == (9, "e1f2")
    assert forced["fen"] == "rnb1kbnr/pppp1ppp/8/4p3/2P1P1P1/8/PP1P1q1P/RNBQKBNR w KQkq - 0 5"
    assert white["estimate"] == 1200


def test_a_system_1_sides_moves_get_a_centipawn_loss_and_accuracy_too(tmp_path):
    log = write(tmp_path, system1_game(anchor_side(), system1_side(), FOOLS_MATE, "0-1", "checkmate"))

    diagnostics = analysis_of(log, evaluator=FixedEvaluator())["centipawn_loss_and_accuracy"]

    assert diagnostics["sides"]["white"] is None
    assert [move["ply"] for move in diagnostics["sides"]["black"]["moves"]] == [2, 4]


def test_a_forfeited_turn_has_no_move_to_score(tmp_path):
    plies = ["f3", Turn("e5", {"e5": 1.0, "d5": 0.0}), "g4", Turn(None, {"Qh4#": None, "d5": None})]
    log = write(tmp_path, system1_game(anchor_side(), system1_side(), plies, "1-0", "forfeit"))

    black = analysis_of(log, move_model=PeakedMoveModel())["move_quality"]["sides"]["black"]

    assert [move["ply"] for move in black["moves"]] == [2]


def test_a_folder_of_llm_anchor_and_system_1_games_is_analysed_game_by_game(tmp_path):
    llm = {"player": "llm", "model": "llama3:8b", "thinking": False, "llm_constraints": "free",
           "retry_feedback": "explained"}
    games = {
        "a": game(anchor_side(), llm, ["f3", "e5", "g4", "Qh4#"], "0-1", "checkmate"),
        "b": system1_game(anchor_side(), system1_side(), FOOLS_MATE, "0-1", "checkmate"),
        "c": system1_game(system1_side(), llm, [Turn("e4", {"e4": 1.0}), "e5"], "1/2-1/2", "move_cap", mode="llm_faceoff"),
    }
    for name, events in games.items():
        write_log(tmp_path, name, events)

    written = analyse_games(tmp_path, PeakedMoveModel(), FixedEvaluator())

    analysed = {path.name: json.loads(path.read_text(encoding="utf-8"))["move_quality"]["sides"] for path in written}
    scored = {name: {colour: side and len(side["moves"]) for colour, side in sides.items()}
              for name, sides in analysed.items()}
    assert scored == {
        "a.analysis.json": {"white": None, "black": 2},
        "b.analysis.json": {"white": None, "black": 2},
        "c.analysis.json": {"white": 1, "black": 0},
    }
