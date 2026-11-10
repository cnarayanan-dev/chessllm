"""The app with a Hosted model, Claude Haiku 5.5 (ADR 0013): it is offered only while the app has a token, marked as
hosted, and played in every Mode the app starts. The player is a ScriptedPlayer, so no test calls the real API."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ScriptedPlayer, llm_faceoff, play_llm

from chessllm.api.app import create_app
from chessllm.core.config import CLAUDE_TOKEN_VARIABLE
from chessllm.llm.models import KNOWN_MODELS

HAIKU = "claude-haiku-5-5"


@pytest.fixture
def app(tmp_path):
    """An app with the default models, whatever the token says, logging to tmp_path / "games"."""

    def make(sampling_defaults=lambda model: {}, **options) -> TestClient:
        options.setdefault("games_dir", tmp_path / "games")
        options.setdefault("sampling_file", tmp_path / "no-sampling.toml")
        options.setdefault("prompt_library_dir", tmp_path / "prompt_library")
        return TestClient(create_app(ScriptedPlayer([]).for_settings, sampling_defaults=sampling_defaults, **options))

    return make


def test_without_a_token_claude_is_not_offered(app):
    models = app().get("/api/models").json()

    assert HAIKU not in [model["name"] for model in models]
    assert not any(model.get("hosted") for model in models)


def test_with_a_token_claude_is_offered_after_the_local_models_marked_as_hosted_with_no_sampling(app, monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "a-token-for-a-test")
    asked = []

    def sampling_defaults(model):
        asked.append(model)
        return {"temperature": 1}

    models = app(sampling_defaults).get("/api/models").json()

    assert models[-1] == {"name": HAIKU, "thinking": True, "sampling": None, "hosted": True}
    assert all("hosted" not in model for model in models[:-1])  # a local model's entry reads as it did
    assert HAIKU not in asked  # Ollama knows nothing of it


def test_the_token_is_never_in_what_the_api_says(app, monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "a-token-for-a-test")
    client = app()

    assert "a-token-for-a-test" not in client.get("/api/models").text


def test_without_a_token_a_game_with_claude_is_refused(app):
    response = app().post("/api/games", json=play_llm("white", model=HAIKU))

    assert response.status_code == 400
    assert HAIKU in response.json()["detail"]


def test_a_game_with_claude_is_refused_when_the_models_are_given_but_there_is_no_token(app):
    response = app(models=KNOWN_MODELS).post("/api/games", json=play_llm("white", model=HAIKU))

    assert response.status_code == 400
    assert response.json()["code"] == "hosted_model_unavailable"
    assert CLAUDE_TOKEN_VARIABLE in response.json()["detail"]


@pytest.mark.parametrize("thinking", [False, True])
def test_with_a_token_claude_plays_play_llm_with_its_settings(app, monkeypatch, thinking):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "a-token-for-a-test")
    client = app()

    response = client.post(
        "/api/games", json=play_llm("white", model=HAIKU, thinking=thinking, llm_constraints="listed_enforced")
    )

    assert response.status_code == 200, response.text
    assert response.json()["settings"]["black"]["model"] == HAIKU
    assert response.json()["settings"]["black"]["thinking"] is thinking


def test_with_a_token_claude_plays_an_llm_faceoff_against_a_local_model(app, monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "a-token-for-a-test")

    response = app().post(
        "/api/games", json=llm_faceoff(white={"model": HAIKU}, black={"model": "llama3:8b"})
    )

    assert response.status_code == 200, response.text


def test_ollama_is_not_asked_whether_it_has_claude(app, monkeypatch):
    monkeypatch.setenv(CLAUDE_TOKEN_VARIABLE, "a-token-for-a-test")
    asked: list[list[str]] = []

    def missing_models(models):
        asked.append(models)
        return []

    response = app(missing_models=missing_models).post("/api/games", json=play_llm("white", model=HAIKU))

    assert response.status_code == 200, response.text
    assert all(HAIKU not in models for models in asked)
