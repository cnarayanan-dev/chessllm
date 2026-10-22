from tests.conftest import play_llm, play_move

from chessllm.game.settings import Settings
from chessllm.llm.models import LlmModel


def test_the_models_offered_are_the_saved_list_with_whether_each_can_think(scripted):
    client, _ = scripted([])

    response = client.get("/api/models")

    assert response.status_code == 200
    assert [(model["name"], model["thinking"]) for model in response.json()] == [
        ("qwen3.5:9b", True),
        ("qwen3.8:latest", True),
        ("llama3:8b", False),
        ("gemma3:12b", False),
        ("gemma4:26b", True),
    ]


def test_each_model_shows_its_sampling_defaults_overridden_by_the_config(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("temperature = 0.2\n")
    defaults = {"qwen3.5:9b": {"temperature": 1, "top_p": 0.95}, "llama3:8b": {}}
    models = [LlmModel("qwen3.5:9b", (False, True)), LlmModel("llama3:8b")]
    client, _ = scripted([], models=models, sampling_defaults=defaults.__getitem__, sampling_file=config)

    assert client.get("/api/models").json() == [
        {"name": "qwen3.5:9b", "thinking": True, "sampling": {"temperature": 0.2, "top_p": 0.95}},
        {"name": "llama3:8b", "thinking": False, "sampling": {"temperature": 0.2}},
    ]


def test_a_model_ollama_cannot_show_is_still_offered_without_sampling(scripted):
    def not_installed(model: str) -> dict[str, float]:
        raise ConnectionError("Failed to connect to Ollama")

    client, _ = scripted([], models=[LlmModel("llama3:8b")], sampling_defaults=not_installed)

    assert client.get("/api/models").json() == [{"name": "llama3:8b", "thinking": False, "sampling": None}]


def test_the_settings_of_a_new_game_by_default_are_offered_before_any_game(scripted):
    client, _ = scripted([])

    response = client.get("/api/games/defaults")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "play_llm",
        "white": {"player": "human"},
        "black": {
            "player": "llm",
            "model": "llama3:8b",
            "thinking": False,
            "llm_constraints": "free",
            "retry_feedback": "explained",
        },
        "rules": "standard",
        "max_attempts": 5,
    }
    assert client.get("/api/games/current").status_code == 404


def test_a_game_started_with_the_defaults_is_the_game_started_without_settings(scripted):
    client, _ = scripted([])

    with_defaults = client.post("/api/games", json=client.get("/api/games/defaults").json()).json()
    without = client.post("/api/games").json()

    assert with_defaults["settings"] == without["settings"]


def test_a_game_cannot_start_with_a_model_that_isnt_in_the_list(scripted):
    client, player = scripted([])

    response = client.post("/api/games", json=play_llm(model="gemma3:4b"))

    assert response.status_code == 400
    assert "gemma3:4b" in response.json()["detail"]
    assert player.built_for == []


def test_a_game_cannot_start_with_thinking_on_for_a_model_that_cannot_think(scripted):
    client, player = scripted([])

    response = client.post("/api/games", json=play_llm(model="llama3:8b", thinking=True))

    assert response.status_code == 400
    assert "llama3:8b" in response.json()["detail"]
    assert player.built_for == []


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
    playing = play_move(client, "e2e4").json()
    next_game = client.post("/api/games").json()

    assert playing["settings"]["sampling"] == {"temperature": 0.2, "top_k": 40}
    assert next_game["settings"]["sampling"] == {"temperature": 0.9}
    assert [settings.sampling for settings in player.built_for] == [{"temperature": 0.2, "top_k": 40}, {"temperature": 0.9}]


def test_sampling_cannot_be_set_through_the_api(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("")
    client, player = scripted([], sampling_file=config)

    response = client.post("/api/games", json={"sampling": {"temperature": 2}})

    assert response.status_code == 422
    assert player.built_for == []


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
