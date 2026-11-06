"""A System 1 model plays whole games through the runner the batches use (ADR 0012): the side to move is dispatched to
its Anchor, its LLM or its decision model, and the game plays to its end with the seed and turns logged."""

import json

import pytest

from tests.conftest import FakeClock, FakeDecisionModel, ScriptedAnchor, ScriptedPlayer

from chessllm.engines.anchors import RandomAnchor
from chessllm.exceptions import DecisionModelFailed
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import AnchorSide, LlmSide, System1Side
from chessllm.logs.game_log import GameLog

BASE_URL = "http://localhost:11434"
SYSTEM1 = System1Side(model="d3:2b", base_url=BASE_URL)


def events(log: GameLog) -> list[dict]:
    return [json.loads(line) for line in log.path.read_text(encoding="utf-8").splitlines()]


def test_a_system_1_side_plays_an_anchor_to_the_end_and_the_game_logs_its_sides_seed_and_turns(tmp_path):
    settings = Settings("anchor_match", AnchorSide(engine="dragon", skill=1), SYSTEM1)
    log = GameLog(tmp_path, *settings.side_names())
    model = FakeDecisionModel.favouring("e5", "Qh4#")

    state = play_anchor_match(
        settings, {}, {"white": ScriptedAnchor(["f3", "g4"])}, log, decision_models={"black": model}, seed=42
    )

    assert (state.pgn, state.result, state.end_reason) == ("1. f3 e5 2. g4 Qh4#", "0-1", "checkmate")
    start, *rest = events(log)
    assert start["white"] == {"player": "anchor", "engine": "dragon", "skill": 1}
    assert list(start["black"]) == ["player", "model", "base_url", "choice_temperature", "prompt_template"]
    assert (start["black"]["model"], start["black"]["base_url"]) == ("d3:2b", BASE_URL)
    assert start["seed"] == 42 and "prompt_file" not in start and "prompt_files" not in start
    assert [(event["type"], event["color"], event["move"]) for event in rest if event["type"] != "game_end"] == [
        ("anchor_move", "white", "f3"),
        ("system1_turn", "black", "e7e5"),
        ("anchor_move", "white", "g4"),
        ("system1_turn", "black", "d8h4"),
    ]
    assert rest[-1]["type"] == "game_end" and rest[-1]["reason"] == "checkmate"
    assert log.path.name.endswith("_dragon-skill1_vs_d3-2b-t1.jsonl")


def test_a_system_1_side_playing_white_is_dispatched_too(tmp_path):
    settings = Settings("anchor_match", SYSTEM1, AnchorSide(engine="dragon", skill=1))
    log = GameLog(tmp_path, *settings.side_names())
    model = FakeDecisionModel.favouring("f3", "g4")

    state = play_anchor_match(
        settings, {}, {"black": ScriptedAnchor(["e5", "Qh4#"])}, log, decision_models={"white": model}, seed=1
    )

    assert (state.pgn, state.result) == ("1. f3 e5 2. g4 Qh4#", "0-1")
    assert [event["type"] for event in events(log)] == [
        "game_start", "system1_turn", "anchor_move", "system1_turn", "anchor_move", "game_end"
    ]


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_game_against_the_random_mover_plays_to_its_end_and_is_reproduced_from_its_seed(tmp_path, seed):
    settings = Settings("anchor_match", AnchorSide.random_mover(seed), SYSTEM1)

    def play(name: str):
        log = GameLog(tmp_path / name, *settings.side_names())
        state = play_anchor_match(
            settings, {}, {"white": RandomAnchor(seed)}, log, decision_models={"black": FakeDecisionModel()}, seed=seed
        )
        return state, log

    first, first_log = play("a")
    second, _ = play("b")

    assert first.status == "over" and first.result is not None
    assert first.pgn == second.pgn
    turns = [event for event in events(first_log) if event["type"] == "system1_turn"]
    assert turns and all(turn["color"] == "black" for turn in turns)
    assert events(first_log)[-1]["type"] == "game_end"


def test_a_failed_call_forfeits_the_game_through_the_runner(tmp_path):
    settings = Settings("anchor_match", AnchorSide(engine="dragon", skill=1), SYSTEM1)
    log = GameLog(tmp_path, *settings.side_names())
    model = FakeDecisionModel([DecisionModelFailed("d3:2b at http://localhost:11434/v1/systemone: timed out")])

    state = play_anchor_match(
        settings, {}, {"white": ScriptedAnchor(["e4"])}, log, decision_models={"black": model}
    )

    assert (state.result, state.end_reason) == ("1-0", "forfeit")
    assert any(event["type"] == "system1_turn" and "error" in event for event in events(log))


def test_a_system_1_model_and_an_llm_play_each_other_to_the_end(tmp_path):
    settings = Settings("llm_faceoff", LlmSide(model="llama3:8b"), SYSTEM1)
    log = GameLog(tmp_path, *settings.side_names())
    player = ScriptedPlayer(["f3", "g4"])

    state = play_anchor_match(
        settings,
        {"white": player.for_settings(settings, "white")},
        {},
        log,
        decision_models={"black": FakeDecisionModel.favouring("e5", "Qh4#")},
        seed=5,
    )

    assert (state.pgn, state.result) == ("1. f3 e5 2. g4 Qh4#", "0-1")
    start = events(log)[0]
    assert start["mode"] == "llm_faceoff" and start["seed"] == 5
    assert start["prompt_files"] == {"white": start["prompt_files"]["white"]}  # the LLM's only


def test_two_system_1_models_play_each_other_to_the_end(tmp_path):
    other = System1Side(model="d1:2b", base_url=BASE_URL, choice_temperature=0)
    settings = Settings("llm_faceoff", SYSTEM1, other)
    log = GameLog(tmp_path, *settings.side_names())
    models = {"white": FakeDecisionModel.favouring("f3", "g4"), "black": FakeDecisionModel.favouring("e5", "Qh4#")}

    state = play_anchor_match(settings, {}, {}, log, decision_models=models, seed=9)

    assert (state.pgn, state.result) == ("1. f3 e5 2. g4 Qh4#", "0-1")
    assert [event["color"] for event in events(log) if event["type"] == "system1_turn"] == [
        "white", "black", "white", "black"
    ]
    assert log.path.name.endswith("_d3-2b-t1_vs_d1-2b-t0.jsonl")


def test_the_clock_times_a_system_1_sides_turns(tmp_path):
    settings = Settings("anchor_match", AnchorSide(engine="dragon", skill=1), SYSTEM1)
    log = GameLog(tmp_path, *settings.side_names())
    clock, model = FakeClock(), FakeDecisionModel.favouring("e5", "Qh4#")
    model.clock, model.think_s = clock, [1.5, 2.0]

    state = play_anchor_match(
        settings, {}, {"white": ScriptedAnchor(["f3", "g4"])}, log, clock=clock, decision_models={"black": model}
    )

    assert state.time_used.black == 3.5
