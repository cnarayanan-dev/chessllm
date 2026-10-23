"""Evaluation: Stockfish judges every ply as it is played, through the Evaluator port, and each Ply carries its
Evaluation from White's point of view, in pawns capped at ±10, or a mate in N (CONTEXT.md)."""

import json
import threading

import chess
from chess.engine import Cp, EngineTerminatedError, Mate, Score
from fastapi.testclient import TestClient

from tests.conftest import ScriptedPlayer, llm_faceoff, play_llm, play_move
from tests.fakes import FixedEvaluator, UnavailableEvaluator

from chessllm.api.app import create_app

CHAOS = {"rules": "chaos"}


class BlockingEvaluator(FixedEvaluator):
    """Test fake for the Evaluator port that holds each evaluation until released, so a search can be kept
    running. searching is set once it has been given a position."""

    def __init__(self) -> None:
        super().__init__()
        self.searching = threading.Event()
        self.release = threading.Event()

    def evaluate(self, fen: str) -> Score:
        self.searching.set()
        assert self.release.wait(timeout=5)
        return super().evaluate(fen)


def in_background(request) -> tuple[threading.Thread, list]:
    """Run a request in a thread of its own; its response lands in the list."""
    responses: list = []
    thread = threading.Thread(target=lambda: responses.append(request()))
    thread.start()
    return thread, responses


class FailingEvaluator(FixedEvaluator):
    """Test fake for the Evaluator port whose engine dies on the first position it is given."""

    def evaluate(self, fen: str) -> Score:
        raise EngineTerminatedError("engine terminated")


def fen_after(*sans: str) -> str:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board.fen()


def events(games_dir):
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def a_faceoff(tmp_path, white, black, evaluator=None, rules=None) -> TestClient:
    """An LLM faceoff between two ScriptedPlayers, judged by the evaluator, started."""
    players = {"white": ScriptedPlayer(white), "black": ScriptedPlayer(black)}
    client = TestClient(
        create_app(
            lambda settings, color: players[color].for_settings(settings, color),
            games_dir=tmp_path / "games",
            sampling_file=tmp_path / "no-sampling.toml",
            evaluator=evaluator,
        )
    )
    response = client.post("/api/games", json=llm_faceoff() | (rules or {}))
    assert response.status_code == 200, response.text
    return client


def turns(client: TestClient, count: int) -> dict:
    for _ in range(count):
        response = client.post("/api/games/current/llm-turn")
        assert response.status_code == 200, response.text
    return response.json()


def evaluations(state) -> list:
    return [ply.get("evaluation") for ply in state["plies"]]


def test_every_ply_carries_its_evaluation_from_whites_point_of_view_in_pawns(tmp_path):
    # The evaluator judges relative to the side to move: after 1. e4 Black is to move, after 1... e5 White.
    evaluator = FixedEvaluator({fen_after("e4"): Cp(-34), fen_after("e4", "e5"): Cp(-120)})
    client = a_faceoff(tmp_path, ["e4"], ["e5"], evaluator)

    state = turns(client, 2)

    assert evaluations(state) == [
        {"pawns": 0.34, "mate": None, "unjudged": None},
        {"pawns": -1.2, "mate": None, "unjudged": None},
    ]


def test_an_evaluation_is_capped_at_ten_pawns_either_way(tmp_path):
    evaluator = FixedEvaluator({fen_after("e4"): Cp(-2500), fen_after("e4", "e5"): Cp(-1800)})
    client = a_faceoff(tmp_path, ["e4"], ["e5"], evaluator)

    state = turns(client, 2)

    assert [evaluation["pawns"] for evaluation in evaluations(state)] == [10.0, -10.0]


def test_a_mate_is_reported_as_mate_in_n_from_whites_point_of_view(tmp_path):
    # After 1. f3 Black to move mates in 2; after 1... e5 White to move is mated in 1 (as Stockfish would see it).
    evaluator = FixedEvaluator({fen_after("f3"): Mate(2), fen_after("f3", "e5"): Mate(-1)})
    client = a_faceoff(tmp_path, ["f3"], ["e5"], evaluator)

    state = turns(client, 2)

    assert evaluations(state) == [
        {"pawns": -10.0, "mate": -2, "unjudged": None},
        {"pawns": -10.0, "mate": -1, "unjudged": None},
    ]


def test_a_position_that_ends_the_game_has_no_evaluation_and_is_never_judged(tmp_path):
    evaluator = FixedEvaluator()
    client = a_faceoff(tmp_path, ["f3", "g4"], ["e5", "Qh4#"], evaluator)

    state = turns(client, 4)

    assert state["end_reason"] == "checkmate"
    assert "evaluation" not in state["plies"][-1]
    assert all("evaluation" in ply for ply in state["plies"][:-1])
    assert state["fen"] not in evaluator.asked


def test_a_chaos_move_leaving_a_pawn_on_the_back_rank_is_not_judged_and_never_sent_to_the_evaluator(tmp_path):
    # 1... b8: the b-pawn steps back onto b8, taking its own knight, a position no game of chess can reach.
    evaluator = FixedEvaluator()
    client = a_faceoff(tmp_path, ["e4", "d4"], ["b8"], evaluator, CHAOS)

    state = turns(client, 3)

    assert state["plies"][1]["resolution"]["kind"] == "chaos"
    not_judged = {"pawns": None, "mate": None, "unjudged": "a pawn stands on a back rank"}
    assert evaluations(state)[1:] == [not_judged, not_judged]  # the pawn still stands there after 2. d4
    assert evaluator.asked == [fen_after("e4")]


def test_the_game_log_records_each_plys_evaluation_with_the_engine_and_its_search(tmp_path):
    evaluator = FixedEvaluator({fen_after("e4"): Cp(-34)})
    client = a_faceoff(tmp_path, ["e4"], ["e5"], evaluator)

    turns(client, 2)

    log = events(tmp_path / "games")
    assert log[0]["evaluator"] == {"version": "fake-engine 1", "search": {"depth": 1}}
    assert [event for event in log if event["type"] == "evaluation"] == [
        {"type": "evaluation", "ply": 1, "pawns": 0.34, "mate": None, "unjudged": None},
        {"type": "evaluation", "ply": 2, "pawns": 0.0, "mate": None, "unjudged": None},
    ]
    # Each after the move it judges.
    assert [event["type"] for event in log] == ["game_start", "llm_attempt", "evaluation", "llm_attempt", "evaluation"]


def test_the_state_names_the_engine_the_evaluations_come_from(tmp_path):
    client = a_faceoff(tmp_path, [], [], FixedEvaluator())

    state = client.get("/api/games/current").json()

    assert state["evaluator"] == {"version": "fake-engine 1", "search": {"depth": 1}}


def test_without_an_evaluator_there_are_no_evaluations(tmp_path):
    client = a_faceoff(tmp_path, ["e4"], ["e5"])

    state = turns(client, 2)

    assert evaluations(state) == [None, None]
    assert "evaluator" not in state
    log = events(tmp_path / "games")
    assert "evaluator" not in log[0]
    assert all(event["type"] != "evaluation" for event in log)


def test_an_evaluator_that_cant_start_leaves_the_game_without_evaluations(tmp_path):
    client = a_faceoff(tmp_path, ["e4"], ["e5"], UnavailableEvaluator())

    state = turns(client, 2)

    assert evaluations(state) == [None, None]
    assert "evaluator" not in state


def test_an_engine_failing_on_a_position_leaves_it_not_judged_and_the_game_going_on(tmp_path):
    client = a_faceoff(tmp_path, ["e4"], ["e5"], FailingEvaluator())

    state = turns(client, 2)

    assert state["status"] == "playing"
    assert evaluations(state)[0] == {"pawns": None, "mate": None, "unjudged": "the engine failed: engine terminated"}


def test_the_humans_move_in_play_llm_is_evaluated_too(scripted):
    evaluator = FixedEvaluator({fen_after("e4"): Cp(-50)})
    client, _ = scripted(["e5"], evaluator=evaluator)
    client.post("/api/games", json=play_llm())

    state = play_move(client, "e2e4").json()

    assert evaluations(state) == [
        {"pawns": 0.5, "mate": None, "unjudged": None},
        {"pawns": 0.0, "mate": None, "unjudged": None},
    ]


def test_while_the_engine_searches_the_state_shows_the_ply_landed_without_its_evaluation_yet(tmp_path):
    evaluator = BlockingEvaluator()
    client = a_faceoff(tmp_path, ["e4"], [], evaluator)

    thread, responses = in_background(lambda: client.post("/api/games/current/llm-turn"))
    assert evaluator.searching.wait(timeout=5)
    during = client.get("/api/games/current").json()
    evaluator.release.set()
    thread.join(timeout=5)

    # The position, its ply and its LLM turn all landed together; only the Evaluation is still to come.
    assert during["fen"] == during["plies"][-1]["fen_after"] == fen_after("e4")
    assert len(during["llm_turns"]) == 1
    assert "evaluation" not in during["plies"][-1]
    assert responses[0].json()["plies"][-1]["evaluation"] == {"pawns": 0.0, "mate": None, "unjudged": None}


def test_a_game_abandoned_while_the_engine_searches_gets_no_evaluation_in_its_state_or_log(tmp_path):
    evaluator = BlockingEvaluator()
    client = a_faceoff(tmp_path, ["e4"], [], evaluator)
    [old_log] = (tmp_path / "games").glob("*.jsonl")

    thread, responses = in_background(lambda: client.post("/api/games/current/llm-turn"))
    assert evaluator.searching.wait(timeout=5)
    assert client.post("/api/games", json=llm_faceoff()).status_code == 200
    evaluator.release.set()
    thread.join(timeout=5)

    assert "evaluation" not in responses[0].json()["plies"][-1]
    old = [json.loads(line) for line in old_log.read_text(encoding="utf-8").splitlines()]
    assert [event["type"] for event in old] == ["game_start", "llm_attempt"]
