"""Anchor match with a System 1 side: one game of a System 1 model against an Anchor, played unattended from the
command line (ADR 0012). The model and its server are injected, so no test needs either."""

import io
import json

import chess.pgn
import pytest

from tests.conftest import FakeDecisionModel, ScriptedAnchor, ScriptedPlayer

from chessllm.cli.anchor_match import main
from chessllm.exceptions import System1Unavailable
from chessllm.game.sides import System1Side

BASE_URL = "http://localhost:8080"
FOOLS_MATE_FOR_BLACK = ["e5", "Qh4#"]


class Server:
    """Test fake for the System 1 server and the models built to ask it: says which models it lacks, records what it
    was asked and every System 1 side a model was built for."""

    def __init__(self, missing: list[str] | BaseException = ()) -> None:
        self.missing = missing
        self.asked: list[tuple[str, list[str]]] = []
        self.built_for: list[System1Side] = []
        self.model = FakeDecisionModel.favouring(*FOOLS_MATE_FOR_BLACK)

    def missing_models(self, base_url: str, models: list[str]) -> list[str]:
        self.asked.append((base_url, models))
        if isinstance(self.missing, BaseException):
            raise self.missing
        return [model for model in models if model in self.missing]

    def decision_model_for(self, side: System1Side) -> FakeDecisionModel:
        self.built_for.append(side)
        return self.model


@pytest.fixture
def system1_match(tmp_path):
    """Runs the command with a Server and a ScriptedAnchor (White: 1. f3 2. g4), logging to tmp_path / "games".
    Returns the exit code, the server, the anchor and the LLM player, which a System 1 game never builds."""

    def run(*args: str, server: Server | None = None, anchor_moves: tuple[str, ...] = ("f3", "g4")):
        server, anchor, player = server or Server(), ScriptedAnchor(list(anchor_moves)), ScriptedPlayer([])
        code = main(
            ["--games-dir", str(tmp_path / "games"), "--system1-model", "d3:2b", "--system1-url", BASE_URL, *args],
            player_for=player.for_settings,
            anchor_for=lambda side: anchor,
            sampling_file=tmp_path / "no-sampling.toml",
            system1_missing_models=server.missing_models,
            decision_model_for=server.decision_model_for,
        )
        return code, server, anchor, player

    return run


def events(games_dir) -> list[dict]:
    [log] = sorted(games_dir.glob("*.jsonl"))
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_the_command_plays_a_system_1_model_against_the_anchor_to_the_end_and_logs_the_game(system1_match, tmp_path):
    code, server, anchor, player = system1_match("--color", "black", "--system1-seed", "7")

    assert code == 0
    games_dir = tmp_path / "games"
    [log] = games_dir.glob("*.jsonl")
    assert log.name.endswith("_dragon-skill1_vs_d3-2b-t1.jsonl")
    start, *moves, end = events(games_dir)
    assert (start["mode"], start["seed"]) == ("anchor_match", 7)
    assert start["white"] == {"player": "anchor", "engine": "dragon", "skill": 1}
    assert {key: start["black"][key] for key in ("player", "model", "base_url", "choice_temperature")} == {
        "player": "system1", "model": "d3:2b", "base_url": BASE_URL, "choice_temperature": 1.0
    }
    assert start["black"]["prompt_template"]["id"].startswith("system1@")
    assert [(event["type"], event["move"]) for event in moves] == [
        ("anchor_move", "f3"), ("system1_turn", "e7e5"), ("anchor_move", "g4"), ("system1_turn", "d8h4"),
    ]
    assert (end["result"], end["reason"], end["plies"]) == ("0-1", "checkmate", 4)
    [pgn_file] = games_dir.glob("*.pgn")
    game = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
    assert game is not None
    assert (game.headers["White"], game.headers["Black"]) == ("Dragon (Skill 1)", "d3:2b (Choice temperature 1)")
    assert anchor.closed and player.built_for == []
    [side] = server.built_for
    assert (side.model, side.base_url, side.choice_temperature) == ("d3:2b", BASE_URL, 1.0)


def test_the_server_is_asked_before_the_game_whether_it_has_the_model(system1_match):
    _, server, _, _ = system1_match("--color", "black")

    assert server.asked == [(BASE_URL, ["d3:2b"])]


def test_the_choice_temperature_is_set_by_its_flag_and_is_part_of_the_logged_side_and_the_names(system1_match, tmp_path):
    code, server, _, _ = system1_match("--color", "black", "--choice-temperature", "0")

    assert code == 0
    games_dir = tmp_path / "games"
    assert events(games_dir)[0]["black"]["choice_temperature"] == 0.0
    [log] = games_dir.glob("*.jsonl")
    assert log.name.endswith("_vs_d3-2b-t0.jsonl")
    assert server.built_for[0].choice_temperature == 0.0


def test_a_system_1_model_can_play_white(system1_match, tmp_path):
    server = Server()
    server.model = FakeDecisionModel.favouring("f3", "g4")
    code, _, _, _ = system1_match("--color", "white", server=server, anchor_moves=("e5", "Qh4#"))

    start = events(tmp_path / "games")[0]
    assert code == 0 and start["white"]["player"] == "system1" and start["black"]["player"] == "anchor"


def test_without_a_seed_each_game_gets_a_fresh_one_logged(system1_match, tmp_path):
    system1_match("--color", "black")

    assert isinstance(events(tmp_path / "games")[0]["seed"], int)


def test_the_system_1_seed_is_apart_from_the_random_movers_seed(system1_match, tmp_path):
    code, _, _, _ = system1_match("--color", "black", "--engine", "random", "--seed", "5", "--system1-seed", "9")

    start = events(tmp_path / "games")[0]
    assert code == 0
    assert start["white"] == {"player": "anchor", "engine": "random", "seed": 5}
    assert start["seed"] == 9


def test_a_model_the_server_lacks_stops_the_command_before_the_game_naming_the_model(system1_match, tmp_path, capsys):
    server = Server(missing=["d3:2b"])

    code, server, anchor, _ = system1_match("--color", "black", server=server)

    assert code == 1
    error = capsys.readouterr().err
    assert "d3:2b" in error and BASE_URL in error and "Anchor match not played" in error
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*"))
    assert server.built_for == [] and not anchor.positions


def test_a_server_that_does_not_answer_stops_the_command_before_the_game_naming_the_model_and_the_server(
    system1_match, tmp_path, capsys
):
    down = System1Unavailable(f"the server at {BASE_URL} isn't running or can't be reached: connection refused")

    code, server, _, _ = system1_match("--color", "black", server=Server(missing=down))

    assert code == 1
    error = capsys.readouterr().err
    assert "d3:2b" in error and BASE_URL in error and "isn't running" in error
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*"))
    assert server.built_for == []


@pytest.mark.parametrize(
    ("flags", "named"),
    [
        (["--thinking"], "--thinking"),
        (["--llm-constraints", "listed"], "--llm-constraints"),
        (["--retry-feedback", "bare"], "--retry-feedback"),
        (["--turn-memory", "chat_position"], "--turn-memory"),
        (["--rules", "chaos", "--engine", "random"], "--rules"),
        (["--max-attempts", "3"], "--max-attempts"),
        (["--tools"], "--tools"),
        (["--thinking-budget", "3072"], "--thinking-budget"),
    ],
)
def test_a_setting_that_only_an_llm_has_is_refused_for_a_system_1_side_not_ignored(
    system1_match, tmp_path, capsys, flags, named
):
    code, server, _, _ = system1_match("--color", "black", *flags)

    assert code == 1
    assert named in capsys.readouterr().err
    assert server.asked == [] and server.built_for == []


def test_a_negative_choice_temperature_is_refused(system1_match, capsys):
    code, server, _, _ = system1_match("--color", "black", "--choice-temperature", "-1")

    assert code == 1
    assert "Choice temperature" in capsys.readouterr().err
    assert server.asked == []


def test_the_server_is_by_default_the_local_ollama(tmp_path):
    server = Server()
    code = main(
        ["--games-dir", str(tmp_path), "--system1-model", "d3:2b", "--color", "black"],
        anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
        sampling_file=tmp_path / "no-sampling.toml",
        system1_missing_models=server.missing_models,
        decision_model_for=server.decision_model_for,
    )

    assert code == 0
    assert server.asked == [("http://localhost:11434", ["d3:2b"])]
