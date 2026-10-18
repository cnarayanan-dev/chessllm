from chessllm.game import Settings
from chessllm.models import InstalledModel


def test_the_installed_chat_models_are_listed(scripted):
    models = [InstalledModel("qwen3.5:9b", {"temperature": 1, "top_p": 0.95}), InstalledModel("llama3:8b", {})]
    client, _ = scripted([], installed_models=lambda: models)

    response = client.get("/api/models")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "qwen3.5:9b", "sampling": {"temperature": 1, "top_p": 0.95}},
        {"name": "llama3:8b", "sampling": {}},
    ]


def test_the_sampling_config_overrides_the_models_defaults_in_the_list(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("temperature = 0.2\n")
    models = [InstalledModel("qwen3.5:9b", {"temperature": 1, "top_p": 0.95})]
    client, _ = scripted([], installed_models=lambda: models, sampling_file=config)

    [model] = client.get("/api/models").json()

    assert model["sampling"] == {"temperature": 0.2, "top_p": 0.95}


def test_without_sampling_config_the_game_runs_at_the_models_defaults(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("# temperature = 0.2\n")
    client, player = scripted([], sampling_file=config)

    state = client.post("/api/games").json()

    assert state["settings"]["sampling"] == {}
    assert player.built_for == [Settings()]


def test_the_sampling_config_is_copied_into_the_next_game_only(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("temperature = 0.2\ntop_k = 40\n")
    client, player = scripted(["e5", "Nc6"], sampling_file=config)
    client.post("/api/games")

    config.write_text("temperature = 0.9\n")
    playing = client.post("/api/games/current/moves", json={"uci": "e2e4"}).json()
    next_game = client.post("/api/games").json()

    assert playing["settings"]["sampling"] == {"temperature": 0.2, "top_k": 40}
    assert next_game["settings"]["sampling"] == {"temperature": 0.9}
    assert [settings.sampling for settings in player.built_for] == [{"temperature": 0.2, "top_k": 40}, {"temperature": 0.9}]


def test_sampling_cannot_be_set_through_the_api(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("")
    client, _ = scripted([], sampling_file=config)

    state = client.post("/api/games", json={"sampling": {"temperature": 2}}).json()

    assert state["settings"]["sampling"] == {}


def test_an_unknown_sampling_option_is_refused(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("temprature = 0.2\n")
    client, _ = scripted([], sampling_file=config)

    response = client.post("/api/games")

    assert response.status_code == 500
    assert "temprature" in response.json()["detail"]


def test_a_sampling_option_that_isnt_a_number_is_refused(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text('temperature = "hot"\n')
    client, _ = scripted([], sampling_file=config)

    response = client.post("/api/games")

    assert response.status_code == 500
    assert "temperature" in response.json()["detail"]


def test_the_model_list_says_why_ollama_could_not_be_asked(scripted):
    def ollama_down() -> list[InstalledModel]:
        raise ConnectionError("Failed to connect to Ollama")

    client, _ = scripted([], installed_models=ollama_down)

    response = client.get("/api/models")

    assert response.status_code == 503
    assert response.json()["detail"] == "Failed to connect to Ollama"
