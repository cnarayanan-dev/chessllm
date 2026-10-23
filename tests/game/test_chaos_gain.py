"""The Chaos gain: how much a Chaos move gained its mover, in pawns from the mover's point of view, over its Legal
counterpart and over Stockfish's best move (the Gain baselines, CONTEXT.md). Each Evaluation is capped at ±10, a King
capture counting as +10 and a King left in check as -10, so the gain is capped at ±20."""

import json
import threading

import chess
from chess.engine import Cp, Score
from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from tests.conftest import Raw, ScriptedPlayer, play_llm, play_move
from tests.fakes import FixedEvaluator

CHAOS = {"rules": "chaos"}
# The placements the games below reach, Black being the LLM.
AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"  # Black to move
AFTER_BC5 = "rnbqk1nr/pppppppp/8/2b5/4P3/8/PPPP1PPP/RNBQKBNR"  # 1... Bc5, through the e7 pawn: White to move
AFTER_E5 = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR"  # 1... e5, the Legal counterpart: White to move


class ByPlacement(FixedEvaluator):
    """Test fake for the Evaluator port: each position's evaluation by its placement alone, relative to the side to
    move, and 0 for any other."""

    def evaluate(self, fen: str) -> Score:
        self.asked.append(fen)
        return self.scores.get(fen.split()[0], Cp(0))


def events(games_dir, kind):
    [log] = sorted(games_dir.glob("*.jsonl"))
    logged = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [event for event in logged if event["type"] == kind]


def chaos_game(scripted, replies, scores, *ucis, **new_game):
    """A Play LLM game under Chaos rules, the human as White, judged by placement; the human's moves played, each
    followed by the LLM's turn. Returns the last state and the evaluator."""
    evaluator = ByPlacement(scores)
    client, _ = scripted(replies, evaluator=evaluator)
    assert client.post("/api/games", json=play_llm() | CHAOS | new_game).status_code == 200
    state = {}
    for uci in ucis:
        response = play_move(client, uci)
        assert response.status_code == 200, response.text
        state = response.json()
    return state, evaluator


def test_the_chaos_gain_is_over_the_legal_counterpart_and_over_stockfishs_best_move_from_the_movers_point_of_view(
    scripted, tmp_path
):
    # For Black: -0.3 before Bc5 (White to move after 1. e4 is +0.3), +3 after it, -0.5 after its counterpart e5.
    scores = {AFTER_E4: Cp(-30), AFTER_BC5: Cp(-300), AFTER_E5: Cp(50)}
    state, _ = chaos_game(scripted, ["Bc5", "e5"], scores, "e2e4")

    turn = state["llm_turn"]
    assert turn["legal_counterpart"]["evaluation"] == {"pawns": 0.5, "mate": None, "unjudged": None}
    assert turn["chaos_gain"] == {
        "best_evaluation": {"pawns": 0.3, "mate": None, "unjudged": None},
        "vs_counterpart": 3.5,
        "vs_best": 3.3,
    }
    assert events(tmp_path / "games", "chaos_gain") == [
        {
            "type": "chaos_gain",
            "color": "black",
            "ply": 2,
            "counterpart_evaluation": {"pawns": 0.5, "mate": None, "unjudged": None},
            "best_evaluation": {"pawns": 0.3, "mate": None, "unjudged": None},
            "vs_counterpart": 3.5,
            "vs_best": 3.3,
        }
    ]


def test_each_evaluation_is_capped_at_ten_pawns_so_the_gain_is_capped_at_twenty(scripted):
    # For Black: -15 before Bc5, +25 after it, -25 after its counterpart, each capped at 10.
    scores = {AFTER_E4: Cp(-1500), AFTER_BC5: Cp(-2500), AFTER_E5: Cp(2500)}
    state, _ = chaos_game(scripted, ["Bc5", "e5"], scores, "e2e4")

    gain = state["llm_turn"]["chaos_gain"]
    assert (gain["best_evaluation"]["pawns"], gain["vs_counterpart"], gain["vs_best"]) == (10.0, 20.0, 20.0)


def test_a_king_capture_counts_as_ten_pawns_for_the_mover(scripted, tmp_path):
    scores = {AFTER_E4: Cp(-100), AFTER_E5: Cp(-300)}  # for Black: -1 before Qe1, +3 after its counterpart e5
    state, _ = chaos_game(scripted, ["Qe1", "e5"], scores, "e2e4")

    assert state["end_reason"] == "king_capture"
    assert "evaluation" not in state["plies"][-1]
    gain = state["llm_turn"]["chaos_gain"]
    assert (gain["vs_counterpart"], gain["vs_best"]) == (7.0, 11.0)
    # Logged with its turn, before the game's end.
    [log] = sorted((tmp_path / "games").glob("*.jsonl"))
    logged = [json.loads(line)["type"] for line in log.read_text(encoding="utf-8").splitlines()]
    assert logged[-4:] == ["llm_attempt", "legal_counterpart", "chaos_gain", "game_end"]


def test_a_king_left_in_check_counts_as_minus_ten_pawns_for_the_mover(scripted):
    # 1. e4 e5 2. Bb5 d5: the d-pawn was pinned, so Black's king is left in check by the bishop.
    after_bb5 = "rnbqkbnr/pppp1ppp/8/1B2p3/4P3/8/PPPP1PPP/RNBQK1NR"
    after_c6 = "rnbqkbnr/pp1p1ppp/2p5/1B2p3/4P3/8/PPPP1PPP/RNBQK1NR"
    scores = {after_bb5: Cp(-100), after_c6: Cp(200)}  # for Black: -1 before d5, -2 after its counterpart c6
    state, _ = chaos_game(scripted, ["e5", "d5", "c6"], scores, "e2e4", "f1b5")

    assert state["end_reason"] == "king_left_in_check"
    gain = state["llm_turn"]["chaos_gain"]
    assert (gain["vs_counterpart"], gain["vs_best"]) == (-8.0, -9.0)


def test_a_gain_that_needs_a_position_not_judged_is_null(scripted):
    # 1... b8: the b-pawn steps back onto b8, taking its own knight, a position no game of chess can reach.
    state, evaluator = chaos_game(scripted, ["b8", "e5", "Nf6"], {AFTER_E5: Cp(50)}, "e2e4", "g1f3")

    turn = state["llm_turns"][0]
    assert turn["chaos_gain"] == {
        "best_evaluation": {"pawns": 0.0, "mate": None, "unjudged": None},
        "vs_counterpart": None,
        "vs_best": None,
    }
    assert turn["legal_counterpart"]["evaluation"]["pawns"] == 0.5
    assert all(chess.Board(fen).is_valid() for fen in evaluator.asked)


def test_a_chaos_move_after_a_position_not_judged_has_no_gain_at_all(scripted):
    # 1... b8 leaves the pawn on b8, so neither the position before 2... Bc5 nor its counterpart's is judged.
    state, evaluator = chaos_game(scripted, ["b8", "e5", "Bc5", "e5"], {}, "e2e4", "g1f3")

    turn = state["llm_turns"][1]
    assert turn["chaos_gain"]["best_evaluation"]["unjudged"] == "a pawn stands on a back rank"
    assert (turn["chaos_gain"]["vs_counterpart"], turn["chaos_gain"]["vs_best"]) == (None, None)
    assert turn["legal_counterpart"]["evaluation"]["unjudged"] == "a pawn stands on a back rank"
    assert all(chess.Board(fen).is_valid() for fen in evaluator.asked)


def test_with_the_switch_off_the_gain_over_stockfishs_best_move_is_still_recorded(scripted, tmp_path):
    scores = {AFTER_E4: Cp(-30), AFTER_BC5: Cp(-300)}
    state, _ = chaos_game(scripted, ["Bc5"], scores, "e2e4", legal_counterpart=False)

    turn = state["llm_turn"]
    assert "legal_counterpart" not in turn
    assert (turn["chaos_gain"]["vs_counterpart"], turn["chaos_gain"]["vs_best"]) == (None, 3.3)
    [logged] = events(tmp_path / "games", "chaos_gain")
    assert (logged["vs_counterpart"], logged["vs_best"]) == (None, 3.3)
    assert "counterpart_evaluation" not in logged


def test_a_failed_legal_counterpart_has_no_gain_over_it(scripted):
    scores = {AFTER_E4: Cp(-30), AFTER_BC5: Cp(-300)}
    state, _ = chaos_game(scripted, ["Bc5", Raw("I would rather not.")], scores, "e2e4")

    turn = state["llm_turn"]
    assert turn["legal_counterpart"]["move"] is None and "evaluation" not in turn["legal_counterpart"]
    assert (turn["chaos_gain"]["vs_counterpart"], turn["chaos_gain"]["vs_best"]) == (None, 3.3)


def test_a_legal_counterpart_that_would_have_mated_counts_as_ten_pawns_and_is_not_judged(scripted):
    # 1. f3 e5 2. g4 Qa5, through the c7 pawn, where the legal Qh4 would have mated.
    state, evaluator = chaos_game(scripted, ["e5", "Qa5", "Qh4#"], {}, "f2f3", "g2g4")

    turn = state["llm_turn"]
    assert turn["legal_counterpart"]["san"] == "Qh4#" and "evaluation" not in turn["legal_counterpart"]
    assert turn["chaos_gain"]["vs_counterpart"] == -10.0
    assert turn["legal_counterpart"]["fen_after"] not in evaluator.asked


def test_without_an_evaluator_there_is_no_chaos_gain(scripted, tmp_path):
    client, _ = scripted(["Bc5", "e5"])
    client.post("/api/games", json=play_llm() | CHAOS)

    turn = play_move(client, "e2e4").json()["llm_turn"]

    assert "chaos_gain" not in turn and "evaluation" not in turn["legal_counterpart"]
    assert events(tmp_path / "games", "chaos_gain") == []


class HeldOn(ByPlacement):
    """A ByPlacement evaluator that holds its evaluation of one placement until released."""

    def __init__(self, held: str) -> None:
        super().__init__()
        self.held = held
        self.searching = threading.Event()
        self.release = threading.Event()

    def evaluate(self, fen: str) -> Score:
        if fen.split()[0] == self.held:
            self.searching.set()
            assert self.release.wait(timeout=5)
        return super().evaluate(fen)


def test_a_game_abandoned_while_its_legal_counterpart_is_judged_never_gets_a_chaos_gain(tmp_path):
    # The LLM as White: 1. Bc4 goes through the e2 pawn, and its counterpart is e4.
    evaluator = HeldOn("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR")
    player = ScriptedPlayer(["Bc4", "e4"])
    client = TestClient(
        create_app(
            player.for_settings, games_dir=tmp_path / "games", sampling_file=tmp_path / "no-sampling.toml",
            evaluator=evaluator,
        )
    )
    old = client.post("/api/games", json=play_llm("black") | CHAOS).json()
    responses: list = []
    running = threading.Thread(target=lambda: responses.append(client.post("/api/games/current/llm-turn")))
    running.start()
    assert evaluator.searching.wait(timeout=5)
    assert client.post("/api/games", json=play_llm("white")).status_code == 200
    evaluator.release.set()
    running.join(timeout=5)

    assert responses[0].json()["llm_turns"] == []
    [log] = [path for path in (tmp_path / "games").glob("*.jsonl") if old["game_id"] in path.read_text()]
    logged = [json.loads(line)["type"] for line in log.read_text(encoding="utf-8").splitlines()]
    assert logged == ["game_start", "llm_attempt"]
