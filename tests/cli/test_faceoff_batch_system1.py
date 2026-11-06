"""Faceoff batch with System 1 sides: a System 1 model against another or against an LLM, played unattended from the
command line, alternating colours (ADR 0012). The models and their servers are injected, so no test needs either."""

import io
import json

import chess.pgn
import pytest

import chessllm.game.ending

from tests.conftest import FakeDecisionModel, NotInstalled, ScriptedPlayer

from chessllm.cli.faceoff_batch import main
from chessllm.exceptions import System1Unavailable
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.sides import System1Side
from chessllm.system1.prompt import DEFAULT_TEMPLATE, POSITION_ONLY_TEMPLATE

FIRST_URL = "http://localhost:8080"
SECOND_URL = "http://localhost:8081"
# Fool's mate: White plays f3 and g4, Black e5 and Qh4#.
WHITE_THEN_BLACK = ["f3", "g4", "e5", "Qh4#"]
BLACK_THEN_WHITE = ["e5", "Qh4#", "f3", "g4"]


class Servers:
    """Test fake for the System 1 servers and the models built to ask them: says which models each server lacks,
    records what it was asked and every System 1 side a model was built for. Each model name has its own fake model,
    scripted to play a game as White then one as Black."""

    def __init__(self, missing: dict[str, list[str] | BaseException] | None = None) -> None:
        self.missing = missing or {}
        self.asked: list[tuple[str, list[str]]] = []
        self.built_for: list[System1Side] = []
        self.models = {
            "d3:2b": FakeDecisionModel.favouring(*WHITE_THEN_BLACK),
            "d3:9b": FakeDecisionModel.favouring(*BLACK_THEN_WHITE),
        }

    def missing_models(self, base_url: str, models: list[str]) -> list[str]:
        self.asked.append((base_url, models))
        lacking = self.missing.get(base_url, [])
        if isinstance(lacking, BaseException):
            raise lacking
        return [model for model in models if model in lacking]

    def decision_model_for(self, side: System1Side) -> FakeDecisionModel:
        self.built_for.append(side)
        return self.models[side.model]


@pytest.fixture
def faceoff(tmp_path):
    """Runs the command with Servers, logging to tmp_path / "games". Returns the exit code, the servers and the LLM
    player."""

    def run(
        *args: str, servers: Servers | None = None, replies: list[str] | None = None, library: PromptLibrary | None = None
    ):
        servers, player = servers or Servers(), ScriptedPlayer(replies or [])
        code = main(
            ["--games-dir", str(tmp_path / "games"), "--no-analysis", *args],
            player_for=player.for_settings,
            sampling_file=tmp_path / "no-sampling.toml",
            system1_missing_models=servers.missing_models,
            decision_model_for=servers.decision_model_for,
            prompt_library=library or PromptLibrary(tmp_path / "library"),
        )
        return code, servers, player

    return run


def logs(games_dir) -> list[list[dict]]:
    """The events of every game log, in the order the games were played."""
    games = [
        [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        for log in games_dir.glob("*.jsonl")
    ]
    return sorted(games, key=lambda events: events[0]["started_at"])


SYSTEM1_PAIR = [
    "--first-system1-model", "d3:2b", "--first-system1-url", FIRST_URL,
    "--second-system1-model", "d3:9b", "--second-system1-url", SECOND_URL,
]  # fmt: skip


def test_two_system_1_models_play_the_requested_games_with_colours_alternating(faceoff, tmp_path, capsys):
    code, servers, player = faceoff(*SYSTEM1_PAIR, "--games", "2")

    assert code == 0
    first, second = logs(tmp_path / "games")
    assert [(g[0]["mode"], g[0]["white"]["model"], g[0]["black"]["model"]) for g in (first, second)] == [
        ("llm_faceoff", "d3:2b", "d3:9b"), ("llm_faceoff", "d3:9b", "d3:2b"),
    ]
    assert [(g[-1]["result"], g[-1]["reason"]) for g in (first, second)] == [("0-1", "checkmate")] * 2
    assert {key: first[0]["white"][key] for key in ("player", "base_url", "choice_temperature")} == {
        "player": "system1", "base_url": FIRST_URL, "choice_temperature": 1.0,
    }
    assert second[0]["white"]["base_url"] == SECOND_URL
    # Black mates both games: d3:9b the first, d3:2b the second.
    assert "Batch: d3:2b (Choice temperature 1) 1 - 1 d3:9b (Choice temperature 1)" in capsys.readouterr().out
    assert player.built_for == []


def test_every_system_1_turn_is_logged_as_a_system_1_turn_with_its_time_and_each_game_has_its_own_seed(
    faceoff, tmp_path
):
    faceoff(*SYSTEM1_PAIR, "--games", "2")

    first, second = logs(tmp_path / "games")
    for game in (first, second):
        turns = [event for event in game if event["type"] == "system1_turn"]
        assert [turn["ply"] for turn in turns] == [1, 2, 3, 4]
        assert all(turn["time_s"] >= 0 for turn in turns)
        assert isinstance(game[0]["seed"], int)
    assert first[0]["seed"] != second[0]["seed"]


def test_each_system_1_side_gets_its_own_decision_model_each_game(faceoff):
    _, servers, _ = faceoff(*SYSTEM1_PAIR, "--games", "2")

    assert [(side.model, side.base_url) for side in servers.built_for] == [
        ("d3:2b", FIRST_URL), ("d3:9b", SECOND_URL), ("d3:9b", SECOND_URL), ("d3:2b", FIRST_URL),
    ]


def test_a_system_1_model_plays_an_llm_and_each_side_is_logged_as_its_kind(faceoff, tmp_path):
    # Game 1: d3:2b is White, llama3:8b Black (e5, Qh4#). Game 2: llama3:8b is White (f3, g4), d3:2b Black.
    servers = Servers()
    servers.models["d3:2b"] = FakeDecisionModel.favouring("f3", "g4", "e5", "Qh4#")
    code, servers, player = faceoff(
        "--first-system1-model", "d3:2b", "--first-system1-url", FIRST_URL, "--models", "llama3:8b",
        "--games", "2", servers=servers, replies=["e5", "Qh4#", "f3", "g4"],
    )  # fmt: skip

    assert code == 0
    first, second = logs(tmp_path / "games")
    assert (first[0]["white"]["player"], first[0]["black"]["player"]) == ("system1", "llm")
    assert (second[0]["white"]["player"], second[0]["black"]["player"]) == ("llm", "system1")
    assert first[0]["black"]["model"] == "llama3:8b"
    for game in (first, second):
        kinds = [event["type"] for event in game]
        assert kinds.count("system1_turn") == 2 and kinds.count("llm_attempt") == 2
    assert [color for color in player.colors] == ["black", "white"]
    assert [side.model for side in servers.built_for] == ["d3:2b", "d3:2b"]


def test_the_llm_may_be_the_first_side_and_the_system_1_model_the_second(faceoff, tmp_path):
    servers = Servers()
    servers.models["d3:9b"] = FakeDecisionModel.favouring("e5", "Qh4#", "f3", "g4")
    code, _, _ = faceoff(
        "--models", "llama3:8b", "--second-system1-model", "d3:9b", "--games", "1",
        servers=servers, replies=["f3", "g4"],
    )  # fmt: skip

    [game] = logs(tmp_path / "games")
    assert code == 0
    assert (game[0]["white"]["model"], game[0]["black"]["model"]) == ("llama3:8b", "d3:9b")
    assert game[0]["black"]["base_url"] == "http://localhost:11434"


def test_the_choice_temperature_is_set_per_side_and_the_same_model_may_play_itself_at_two_of_them(
    faceoff, tmp_path, capsys
):
    servers = Servers()
    servers.models["d3:2b"] = FakeDecisionModel.favouring("f3", "e5", "g4", "Qh4#")
    code, _, _ = faceoff(
        "--first-system1-model", "d3:2b", "--first-choice-temperature", "0",
        "--second-system1-model", "d3:2b", "--second-choice-temperature", "0.5",
        "--games", "1", servers=servers,
    )  # fmt: skip

    [game] = logs(tmp_path / "games")
    assert code == 0
    assert (game[0]["white"]["choice_temperature"], game[0]["black"]["choice_temperature"]) == (0.0, 0.5)
    assert "Batch: d3:2b (Choice temperature 0) 0 - 1 d3:2b (Choice temperature 0.5)" in capsys.readouterr().out


def test_both_sides_servers_and_models_are_checked_before_the_first_game(faceoff):
    _, servers, _ = faceoff(*SYSTEM1_PAIR, "--games", "1")

    assert servers.asked == [(FIRST_URL, ["d3:2b"]), (SECOND_URL, ["d3:9b"])]


@pytest.mark.parametrize("lacking_url, lacking_model", [(FIRST_URL, "d3:2b"), (SECOND_URL, "d3:9b")])
def test_a_model_either_server_lacks_stops_the_batch_before_game_1_naming_it(
    faceoff, tmp_path, capsys, lacking_url, lacking_model
):
    code, servers, player = faceoff(*SYSTEM1_PAIR, servers=Servers(missing={lacking_url: [lacking_model]}))

    assert code == 1
    error = capsys.readouterr().err
    assert "Faceoff batch not played" in error and lacking_model in error and lacking_url in error
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*"))
    assert servers.built_for == [] and player.built_for == []


def test_a_server_that_does_not_answer_stops_the_batch_before_game_1_naming_the_model_and_the_server(
    faceoff, tmp_path, capsys
):
    down = System1Unavailable(f"the server at {SECOND_URL} isn't running or can't be reached: connection refused")

    code, servers, _ = faceoff(*SYSTEM1_PAIR, servers=Servers(missing={SECOND_URL: down}))

    assert code == 1
    error = capsys.readouterr().err
    assert "d3:9b" in error and SECOND_URL in error and "isn't running" in error
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*"))
    assert servers.built_for == []


def test_a_system_1_model_of_a_mixed_batch_is_checked_and_so_is_the_llm(faceoff, tmp_path, capsys):
    args = ["--first-system1-model", "d3:2b", "--first-system1-url", FIRST_URL, "--models", "llama3:8b"]
    servers = Servers(missing={FIRST_URL: ["d3:2b"]})
    player = ScriptedPlayer([])

    code = main(
        [*args, "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
        system1_missing_models=servers.missing_models,
        decision_model_for=servers.decision_model_for,
    )
    assert code == 1 and "d3:2b" in capsys.readouterr().err

    code = main(
        [*args, "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
        missing_models=NotInstalled("llama3:8b"),
        system1_missing_models=Servers().missing_models,
        decision_model_for=servers.decision_model_for,
    )
    assert code == 1 and "llama3:8b" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))


@pytest.mark.parametrize(
    "args",
    [
        ["--first-system1-model", "d3:2b"],  # the second side is nobody's
        ["--models", "llama3:8b", "gemma3:12b", "--first-system1-model", "d3:2b"],  # three sides
        [*SYSTEM1_PAIR, "--models", "llama3:8b"],
        [],
    ],
)
def test_the_sides_must_be_exactly_two_between_models_and_system_1_models(faceoff, tmp_path, capsys, args):
    code, servers, _ = faceoff(*args)

    assert code != 0
    assert "--models" in capsys.readouterr().err
    assert servers.asked == [] and servers.built_for == []


@pytest.mark.parametrize(
    ("flags", "named"),
    [
        (["--thinking"], "--thinking"),
        (["--llm-constraints", "listed"], "--llm-constraints"),
        (["--retry-feedback", "bare"], "--retry-feedback"),
        (["--turn-memory", "chat_position"], "--turn-memory"),
        (["--prompt-template", "described"], "--prompt-template"),
        (["--max-attempts", "3"], "--max-attempts"),
        (["--thinking-for", "llama3:8b"], "--thinking-for"),
    ],
)
def test_a_setting_that_only_an_llm_has_is_refused_when_no_side_is_an_llm(faceoff, capsys, flags, named):
    code, servers, _ = faceoff(*SYSTEM1_PAIR, *flags)

    assert code == 1
    assert named in capsys.readouterr().err
    assert servers.asked == [] and servers.built_for == []


def test_chaos_rules_are_refused_when_both_sides_are_system_1_models(faceoff, capsys):
    code, servers, _ = faceoff(*SYSTEM1_PAIR, "--rules", "chaos")

    assert code == 1
    assert "--rules" in capsys.readouterr().err
    assert servers.asked == []


def test_chaos_rules_are_refused_when_one_side_is_a_system_1_model_saying_why(faceoff, capsys):
    code, servers, _ = faceoff("--first-system1-model", "d3:2b", "--models", "llama3:8b", "--rules", "chaos")

    assert code == 1
    assert "Standard rules" in capsys.readouterr().err
    assert servers.asked == []


def test_a_negative_choice_temperature_is_refused(faceoff, capsys):
    code, servers, _ = faceoff(*SYSTEM1_PAIR, "--first-choice-temperature", "-1")

    assert code == 1
    assert "Choice temperature" in capsys.readouterr().err
    assert servers.asked == []


def test_a_system_1_side_stays_a_system_1_side_when_the_llm_flags_are_given_to_the_llm_side(faceoff, tmp_path):
    servers = Servers()
    servers.models["d3:2b"] = FakeDecisionModel.favouring("f3", "g4")
    code, _, _ = faceoff(
        "--first-system1-model", "d3:2b", "--models", "qwen3.8:latest", "--thinking", "--games", "1",
        servers=servers, replies=["e5", "Qh4#"],
    )  # fmt: skip

    [game] = logs(tmp_path / "games")
    assert code == 0
    assert game[0]["black"]["thinking"] is True and "thinking" not in game[0]["white"]


def test_each_system_1_side_plays_with_its_own_prompt_template_logged_in_full(faceoff, tmp_path):
    code, servers, _ = faceoff(*SYSTEM1_PAIR, "--first-system1-template", POSITION_ONLY_TEMPLATE.id, "--games", "2")

    first, second = logs(tmp_path / "games")
    assert code == 0
    assert first[0]["white"]["prompt_template"] == POSITION_ONLY_TEMPLATE.log_shape()
    assert first[0]["black"]["prompt_template"] == DEFAULT_TEMPLATE.log_shape()
    assert second[0]["black"]["prompt_template"] == POSITION_ONLY_TEMPLATE.log_shape()
    assert second[0]["white"]["prompt_template"] == DEFAULT_TEMPLATE.log_shape()
    assert [side.prompt_template for side in servers.built_for[:2]] == [POSITION_ONLY_TEMPLATE, None]


def test_a_saved_template_of_the_prompt_library_is_picked_by_its_id_for_the_second_side(faceoff, tmp_path):
    library = PromptLibrary(tmp_path / "library")
    saved = library.save("Fen only", "Which move should $color play?", "$fen", "free")

    code, _, _ = faceoff(*SYSTEM1_PAIR, "--second-system1-template", saved.template.id, "--games", "1", library=library)

    [game] = logs(tmp_path / "games")
    assert code == 0
    assert game[0]["black"]["prompt_template"]["id"] == saved.template.id
    assert game[0]["white"]["prompt_template"]["id"] == DEFAULT_TEMPLATE.id


def test_a_template_the_library_lacks_stops_the_batch_before_game_1_naming_it(faceoff, tmp_path, capsys):
    code, servers, _ = faceoff(*SYSTEM1_PAIR, "--second-system1-template", "system1@nope")

    assert code == 1
    error = capsys.readouterr().err
    assert "system1@nope" in error and "Faceoff batch not played" in error
    assert servers.asked == [] and servers.built_for == []
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*"))


def test_a_template_for_a_side_that_is_an_llm_is_refused(faceoff, capsys):
    code, servers, _ = faceoff(
        "--first-system1-model", "d3:2b", "--models", "llama3:8b",
        "--second-system1-template", POSITION_ONLY_TEMPLATE.id,
    )  # fmt: skip

    assert code == 1
    assert "--second-system1-template" in capsys.readouterr().err
    assert servers.asked == []


def test_a_game_of_system_1_models_not_ended_by_the_rules_at_the_move_cap_is_a_draw_there(
    faceoff, tmp_path, monkeypatch
):
    # The cap is lowered to four moves per side, so a quiet opening reaches it with no check, no forced reply (which the
    # model isn't asked about) and no mate, whatever the game's seed.
    monkeypatch.setattr(chessllm.game.ending, "MOVE_CAP", 4)
    servers = Servers()
    servers.models = {
        "d3:2b": FakeDecisionModel.favouring("e4", "Nf3", "Bc4", "Nc3"),
        "d3:9b": FakeDecisionModel.favouring("e5", "Nc6", "Bc5", "Nf6"),
    }

    code, _, _ = faceoff(*SYSTEM1_PAIR, "--games", "1", servers=servers)

    [game] = logs(tmp_path / "games")
    assert code == 0
    end = game[-1]
    assert (end["type"], end["result"], end["reason"], end["plies"]) == ("game_end", "1/2-1/2", "move_cap", 8)
    assert [event["san"] for event in game if event["type"] == "system1_turn"] == [
        "e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "Nc3", "Nf6",
    ]


def test_the_pgn_and_the_log_file_name_give_each_system_1_sides_model_and_choice_temperature(faceoff, tmp_path):
    code, _, _ = faceoff(*SYSTEM1_PAIR, "--second-choice-temperature", "0.5", "--games", "2")

    games_dir = tmp_path / "games"
    assert code == 0
    assert sorted(log.name.split("_", 1)[1] for log in games_dir.glob("*.jsonl")) == sorted(
        ["d3-2b-t1_vs_d3-9b-t0.5.jsonl", "d3-9b-t0.5_vs_d3-2b-t1.jsonl"]
    )
    headers = []
    for pgn_file in games_dir.glob("*.pgn"):
        game = chess.pgn.read_game(io.StringIO(pgn_file.read_text(encoding="utf-8")))
        assert game is not None
        headers.append((game.headers["White"], game.headers["Black"]))
    assert sorted(headers) == sorted(
        [
            ("d3:2b (Choice temperature 1)", "d3:9b (Choice temperature 0.5)"),
            ("d3:9b (Choice temperature 0.5)", "d3:2b (Choice temperature 1)"),
        ]
    )
