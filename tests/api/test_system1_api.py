"""A System 1 model plays in the app: a new game takes its side, the page asks for its turns one request each, and a
model or server that isn't there is refused before the game starts."""

import pytest
from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from chessllm.core.config import SYSTEM1_DEFAULT_URL
from chessllm.exceptions import DecisionModelFailed, System1Unavailable
from chessllm.llm.models import LLM_MODELS
from chessllm.system1.prompt import DEFAULT_TEMPLATE, SYSTEM1_TEMPLATES
from tests.conftest import llm_faceoff
from tests.fakes import FakeClock, FakeDecisionModel, ScriptedPlayer

URL = "http://localhost:11434"


def system1(model: str = "d3:2b", **settings) -> dict:
    return {"player": "system1", "model": model, "base_url": URL, **settings}


def play_system1(human_color: str = "black", **settings) -> dict:
    """The new-game request body for Play LLM against a System 1 model."""
    other = "white" if human_color == "black" else "black"
    return {"mode": "play_llm", human_color: {"player": "human"}, other: system1(**settings)}


class Server:
    """Test fake for the System 1 server: the models it has, each a FakeDecisionModel, and the questions it was asked
    which models it has."""

    def __init__(self, **models: FakeDecisionModel) -> None:
        self.models = {name.replace("_", ":"): model for name, model in models.items()}
        self.checked: list[tuple[str, list[str]]] = []
        self.down = False

    def missing_models(self, base_url: str, models: list[str]) -> list[str]:
        self.checked.append((base_url, models))
        if self.down:
            raise System1Unavailable(f"nothing answers at {base_url}")
        return [model for model in models if model not in self.models]


@pytest.fixture
def app(tmp_path):
    """Makes an app with a fake System 1 server. Returns the client and the server."""

    def make(server: Server | None = None, **options) -> tuple[TestClient, Server]:
        server = server or Server(d3_2b=FakeDecisionModel())
        options.setdefault("games_dir", tmp_path / "games")
        options.setdefault("sampling_file", tmp_path / "no-sampling.toml")
        options.setdefault("prompt_library_dir", tmp_path / "prompt_library")
        options.setdefault("clock", FakeClock())
        client = TestClient(
            create_app(
                ScriptedPlayer([]).for_settings,
                decision_model_for=lambda side: server.models[side.model],
                system1_missing_models=server.missing_models,
                **options,
            )
        )
        return client, server

    return make


def test_a_human_plays_a_system_1_model_to_the_end_one_request_a_turn(app):
    client, _ = app(Server(d3_2b=FakeDecisionModel.favouring("e4", "Bc4", "Qh5", "Qxf7#")))

    started = client.post("/api/games", json=play_system1("black"))
    assert started.status_code == 200, started.text
    assert started.json()["settings"]["white"] == {
        "player": "system1", "model": "d3:2b", "base_url": URL, "choice_temperature": 1.0
    }
    for reply in ["e7e5", "b8c6", "g8f6"]:
        state = client.post("/api/games/current/system1-turn").json()
        assert (state["turn"], state["human_legal_moves"] != []) == ("black", True)
        state = client.post("/api/games/current/moves", json={"uci": reply}).json()
        assert (state["turn"], state["human_legal_moves"]) == ("white", [])

    state = client.post("/api/games/current/system1-turn").json()

    assert (state["status"], state["result"], state["end_reason"]) == ("over", "1-0", "checkmate")


def test_a_system_1_faceoff_runs_on_its_own_to_the_end(app):
    server = Server(d3_2b=FakeDecisionModel.favouring("e4"), d1_2b=FakeDecisionModel([{"e5": 1}, DecisionModelFailed("down")]))
    client, _ = app(server)
    body = {"mode": "llm_faceoff", "white": system1("d3:2b"), "black": system1("d1:2b")}
    assert client.post("/api/games", json=body).status_code == 200

    state = client.post("/api/games/current/system1-turn").json()
    while state["status"] == "playing":
        state = client.post("/api/games/current/system1-turn").json()

    assert (state["result"], state["end_reason"]) == ("1-0", "forfeit")
    assert [ply["written"] for ply in state["plies"]][:2] == ["e4", "e5"]


def test_a_system_1_turn_that_fails_is_a_forfeit(app):
    client, _ = app(Server(d3_2b=FakeDecisionModel([DecisionModelFailed("down")])))
    client.post("/api/games", json=play_system1("black"))

    state = client.post("/api/games/current/system1-turn").json()

    assert (state["status"], state["result"], state["end_reason"]) == ("over", "0-1", "forfeit")


def test_a_system_1_forfeit_says_why_in_the_state(app):
    client, _ = app(Server(d3_2b=FakeDecisionModel([DecisionModelFailed("down")])))
    started = client.post("/api/games", json=play_system1("black")).json()

    state = client.post("/api/games/current/system1-turn").json()

    assert "system1_forfeit_error" not in started
    assert state["system1_forfeit_error"] == "down"


def test_a_system_1_turn_on_another_sides_turn_is_refused_with_its_code(app):
    client, _ = app()
    client.post("/api/games", json=play_system1("white"))

    response = client.post("/api/games/current/system1-turn")

    assert (response.status_code, response.json()) == (
        409,
        {"detail": "it is not a System 1 model's turn", "code": "not_system1_turn"},
    )


def test_a_system_1_turn_is_refused_before_any_game(app):
    client, _ = app()

    assert client.post("/api/games/current/system1-turn").json()["code"] == "no_current_game"


def test_an_llm_turn_is_refused_on_a_system_1_models_turn(app):
    client, _ = app()
    client.post("/api/games", json=play_system1("black"))

    assert client.post("/api/games/current/llm-turn").json()["code"] == "not_llm_turn"


def test_a_model_the_server_lacks_is_refused_naming_it_before_the_game_starts(app, tmp_path):
    client, server = app(Server(d1_2b=FakeDecisionModel()))

    response = client.post("/api/games", json=play_system1("black", model="d3:2b"))

    assert (response.status_code, response.json()) == (
        400,
        {"detail": f"The System 1 server at {URL} doesn't have d3:2b (white)", "code": "invalid_settings"},
    )
    assert server.checked == [(URL, ["d3:2b"])]
    assert client.get("/api/games/current").status_code == 404
    assert not (tmp_path / "games").exists()  # no game logged


def test_a_server_that_does_not_answer_is_refused_before_the_game_starts(app, tmp_path):
    client, server = app()
    server.down = True

    response = client.post("/api/games", json=play_system1("black"))

    assert (response.status_code, response.json()) == (
        400,
        {"detail": f"d3:2b (white) can't play: nothing answers at {URL}", "code": "system1_unavailable"},
    )
    assert not (tmp_path / "games").exists()


def test_llms_and_anchors_are_not_asked_about_a_system_1_server(app):
    client, server = app()

    client.post("/api/games", json={"mode": "llm_faceoff", "white": {"player": "llm"}, "black": system1()})

    assert server.checked == [(URL, ["d3:2b"])]


def test_settings_a_system_1_side_cant_play_under_are_refused(app):
    client, _ = app()

    cold = client.post("/api/games", json=play_system1("black", choice_temperature=-1))
    chaos = client.post("/api/games", json=play_system1("black") | {"rules": "chaos"})

    assert cold.json()["code"] == "invalid_settings" and "Choice temperature" in cold.json()["detail"]
    assert chaos.json()["code"] == "invalid_settings" and "Standard rules" in chaos.json()["detail"]


def test_a_system_1_side_plays_the_prompt_template_its_id_names(app):
    client, _ = app()

    state = client.post("/api/games", json=play_system1("black", prompt_template_id=DEFAULT_TEMPLATE.id)).json()
    bad = client.post("/api/games", json=play_system1("black", prompt_template_id="system1@nonesuch"))

    assert state["prompt_templates"]["white"] == {"id": DEFAULT_TEMPLATE.id, "name": DEFAULT_TEMPLATE.name}
    assert state["settings"]["white"]["prompt_template_id"] == DEFAULT_TEMPLATE.id
    assert bad.status_code == 400 and bad.json()["code"] == "unknown_prompt_template"


def test_the_system_1_templates_are_listed_the_default_first(app):
    client, _ = app()

    options = client.get("/api/system1/options").json()
    listed = options["templates"]

    assert options["default_url"] == SYSTEM1_DEFAULT_URL
    assert [template["id"] for template in listed] == list(SYSTEM1_TEMPLATES)
    assert listed[0] == {
        "id": DEFAULT_TEMPLATE.id,
        "name": DEFAULT_TEMPLATE.name,
        "system_prompt": DEFAULT_TEMPLATE.system_prompt,
        "turn_template": DEFAULT_TEMPLATE.turn_template,
    }


def test_a_system_1_side_may_play_an_llm_in_a_faceoff(app):
    client, _ = app()

    started = client.post("/api/games", json=llm_faceoff() | {"black": system1()})

    assert started.status_code == 200, started.text
    assert started.json()["settings"]["white"]["player"] == "llm"


def test_a_system_1_side_may_play_any_system_1_template_the_list_offers(app):
    client, _ = app()

    for listed in client.get("/api/system1/options").json()["templates"]:
        state = client.post("/api/games", json=play_system1("black", prompt_template_id=listed["id"])).json()

        assert state["prompt_templates"]["white"]["id"] == listed["id"]


def test_the_installed_decision_models_are_offered_to_a_system_1_side_and_left_out_of_the_llms(app):
    client, _ = app(system1_models=lambda: ["d3:2b", "d3:9b", "d1:2b"])

    assert client.get("/api/system1/options").json()["models"] == ["d3:2b", "d3:9b", "d1:2b"]
    assert [model["name"] for model in client.get("/api/models").json()] == [m.name for m in LLM_MODELS]


def test_without_ollama_the_system_1_options_list_no_models(app):
    client, _ = app()

    response = client.get("/api/system1/options")

    assert response.status_code == 200
    assert response.json()["models"] == []
