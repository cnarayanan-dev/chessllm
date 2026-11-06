"""Anchor match batches of a System 1 model: the same adaptive ladder as an LLM's, from the random legal mover up
Dragon's Skill levels, resuming from the Player configuration's earlier games (ADR 0012). The model and its server are
injected, so no test needs either; each game ends in a planted result, as in test_anchor_batch.

Every assertion is on the game logs the batch writes, the server's questions and the command's output."""

import pytest

from tests.cli.test_anchor_batch import SCRIPTS, PlantedResults, logs
from tests.conftest import FakeDecisionModel

from chessllm.cli.anchor_batch import main
from chessllm.exceptions import DecisionModelFailed, System1Unavailable
from chessllm.game.sides import System1Side
from chessllm.system1.prompt import POSITION_ONLY_TEMPLATE

BASE_URL = "http://localhost:8080"
MODEL = "d3:2b"
SYSTEM1 = ["--system1-model", MODEL, "--system1-url", BASE_URL]


class PlantedSystem1(PlantedResults):
    """PlantedResults for a System 1 model: builds, for each game in turn, a FakeDecisionModel that plays the next
    planted result for the model, against a ScriptedAnchor. Colours alternate from White, `earlier` games after the
    games already logged. Also the System 1 server: says which models it lacks, records what it was asked and every
    System 1 side a model was built for."""

    def __init__(self, results: list[str], earlier: int = 0, missing: list[str] | BaseException = ()) -> None:
        super().__init__(results)
        self.earlier = earlier
        self.missing = missing
        self.asked: list[tuple[str, list[str]]] = []
        self.built_for: list[System1Side] = []

    def missing_models(self, base_url: str, models: list[str]) -> list[str]:
        self.asked.append((base_url, models))
        if isinstance(self.missing, BaseException):
            raise self.missing
        return [model for model in models if model in self.missing]

    def decision_model_for(self, side: System1Side) -> FakeDecisionModel:
        self._unplayed = False
        self.built_for.append(side)
        color = "white" if (self.earlier + self.anchors_built) % 2 else "black"
        model_moves, anchor_moves = SCRIPTS[(self.results[self.anchors_built - 1], color)]
        self.anchors[-1].script(anchor_moves)
        return FakeDecisionModel(
            [DecisionModelFailed("planted loss") if isinstance(move, BaseException) else {move: 1.0} for move in model_moves]  # fmt: skip
        )


def played(games_dir, choice_temperature: float | None = 1.0) -> list[tuple[str, int, str]]:
    """Each logged game of a System 1 model at the Choice temperature as (its colour, the ladder's rung: 0 for the
    random mover, else Dragon's Skill, its result), oldest first; None for any. Other games are left out."""
    found = []
    for start, *_, end in logs(games_dir):
        temperatures = [start[color].get("choice_temperature") for color in ("white", "black")]
        if temperatures == [None, None] or choice_temperature not in (None, *temperatures):
            continue
        color = "white" if start["white"]["player"] == "system1" else "black"
        anchor = start["black" if color == "white" else "white"]
        won = "1-0" if color == "white" else "0-1"
        result = "draw" if end["result"] == "1/2-1/2" else "win" if end["result"] == won else "loss"
        found.append((color, 0 if anchor["engine"] == "random" else anchor["skill"], result))
    return found


@pytest.fixture
def batch(tmp_path):
    """Runs the batch command for a System 1 model into tmp_path / "games" with the planted results. Returns the exit
    code and the PlantedSystem1, which is the server and the anchors."""

    def run(results: list[str], *args: str, earlier: int = 0, server: PlantedSystem1 | None = None):
        planted = server or PlantedSystem1(results, earlier)
        code = main(
            ["--games-dir", str(tmp_path / "games"), "--no-analysis", *SYSTEM1, *args],
            player_for=lambda settings, color: pytest.fail("an LLM was built for a System 1 side"),
            anchor_for=planted.anchor_for,
            sampling_file=tmp_path / "no-sampling.toml",
            system1_missing_models=planted.missing_models,
            decision_model_for=planted.decision_model_for,
        )
        return code, planted

    return run


def test_a_batch_plays_a_system_1_models_ladder_up_from_the_random_mover_and_stops_at_its_budget(batch, tmp_path):
    results = ["win", "win", "win", "draw", "win", "loss"]

    code, planted = batch(results, "--games", "6")

    assert code == 0
    assert played(tmp_path / "games") == [
        ("white", 0, "win"), ("black", 0, "win"),  # a pair won: up to Skill 1
        ("white", 1, "win"), ("black", 1, "draw"),  # 1.5 of 2: up to Skill 2
        ("white", 2, "win"), ("black", 2, "loss"),
    ]
    assert all(anchor.closed for anchor in planted.anchors)
    assert {side.model for side in planted.built_for} == {MODEL}


def test_the_server_is_asked_once_before_the_first_game_whether_it_has_the_model(batch, tmp_path):
    _, planted = batch(["draw"] * 3, "--games", "3")

    assert planted.asked == [(BASE_URL, [MODEL])]


def test_each_game_gets_a_fresh_logged_seed(batch, tmp_path):
    batch(["draw"] * 4, "--games", "4")

    seeds = [log[0]["seed"] for log in logs(tmp_path / "games")]
    assert all(isinstance(seed, int) for seed in seeds) and len(set(seeds)) == 4


def test_the_batch_has_no_system_1_seed_flag(batch, tmp_path):
    with pytest.raises(SystemExit):
        batch(["draw"], "--system1-seed", "7")


def test_a_later_batch_resumes_from_the_logged_games_of_the_same_player_configuration(batch, tmp_path, capsys):
    batch(["win", "win", "win"], "--games", "3")
    capsys.readouterr()

    code, _ = batch(["win", "loss", "loss"], "--games", "3", earlier=3)

    assert code == 0
    assert played(tmp_path / "games")[3:] == [("black", 1, "win"), ("white", 2, "loss"), ("black", 2, "loss")]
    assert "Going on from 3 earlier Anchor matches" in capsys.readouterr().out


@pytest.mark.parametrize(
    "other",
    [
        ["--choice-temperature", "0.5"],
        ["--system1-template", POSITION_ONLY_TEMPLATE.id],
        ["--system1-model", "d3:9b"],
    ],
)
def test_a_different_choice_temperature_template_or_model_starts_its_own_ladder(batch, tmp_path, other):
    batch(["win", "win", "win"], "--games", "3")

    code, _ = batch(["draw", "draw"], "--games", "2", *other)

    assert code == 0
    assert [(rung, color) for color, rung, _ in played(tmp_path / "games", None)[3:]] == [(0, "white"), (0, "black")]


def test_a_model_the_server_lacks_stops_the_batch_before_its_first_game(batch, tmp_path, capsys):
    code, planted = batch([], server=PlantedSystem1([], missing=[MODEL]))

    assert code == 1
    error = capsys.readouterr().err
    assert MODEL in error and BASE_URL in error and "Anchor match batch stopped" in error
    assert planted.anchors_built == 0 and planted.built_for == []
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*"))


def test_a_server_that_does_not_answer_stops_the_batch_before_its_first_game(batch, tmp_path, capsys):
    down = System1Unavailable(f"the server at {BASE_URL} isn't running or can't be reached: connection refused")

    code, planted = batch([], server=PlantedSystem1([], missing=down))

    assert code == 1
    error = capsys.readouterr().err
    assert MODEL in error and BASE_URL in error and "isn't running" in error
    assert planted.anchors_built == 0 and planted.built_for == []
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*"))


def test_a_setting_that_only_an_llm_has_is_refused_before_the_first_game(batch, tmp_path, capsys):
    code, planted = batch([], "--thinking")

    assert code == 1
    assert "--thinking" in capsys.readouterr().err
    assert planted.asked == [] and planted.anchors_built == 0


def test_a_template_without_a_system_1_model_is_refused(tmp_path, capsys):
    code = main(["--games-dir", str(tmp_path), "--system1-template", POSITION_ONLY_TEMPLATE.id])

    assert code == 1
    assert "--system1-template" in capsys.readouterr().err


def test_a_ladder_resumes_only_from_its_own_configurations_games_among_other_configurations_in_the_directory(
    batch, tmp_path, capsys
):
    games_dir = tmp_path / "games"
    # An LLM's ladder and the same model at another Choice temperature, logged in the same directory.
    llm = PlantedResults(["loss"] * 4)
    main(
        ["--games-dir", str(games_dir), "--no-analysis", "--model", "llama3:8b", "--games", "4"],
        player_for=llm.player_for,
        anchor_for=llm.anchor_for,
        sampling_file=tmp_path / "no-sampling.toml",
    )
    batch(["loss"] * 3, "--games", "3", "--choice-temperature", "0.5")
    # Its own: a pair won, so the ladder stands at Skill 1.
    batch(["win", "win"], "--games", "2")
    capsys.readouterr()

    code, _ = batch(["win", "loss"], "--games", "2", earlier=2)

    assert code == 0
    assert played(games_dir) == [
        ("white", 0, "win"), ("black", 0, "win"),  # a pair won: up to Skill 1, whatever the others did
        ("white", 1, "win"), ("black", 1, "loss"),
    ]
    assert "Going on from 2 earlier Anchor matches" in capsys.readouterr().out


def test_the_progress_lines_say_the_model_is_a_system_1_model(batch, capsys):
    batch(["win", "draw"], "--games", "2")

    out = capsys.readouterr().out
    assert "Game 1/2: Random mover, System 1 model as white: win (1-0, checkmate)" in out
    assert "Next game: Skill 1, System 1 model as white." in out
