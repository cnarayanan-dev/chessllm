from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from chessllm.llm.models import LlmModel
from scripts.generate_api_types import SCHEMA_FILE, api_description, schema_header


def test_every_api_endpoint_describes_its_response_with_a_named_model():
    description = TestClient(create_app(lambda settings, color: None)).get("/openapi.json").json()

    responses = {
        (method.upper(), path): operation["responses"]["200"]["content"]["application/json"]["schema"]
        for path, operations in description["paths"].items()
        if path.startswith("/api/")
        for method, operation in operations.items()
    }

    assert responses == {
        ("GET", "/api/models"): {
            "type": "array",
            "items": {"$ref": "#/components/schemas/ModelInfo"},
            "title": "Response List Models Api Models Get",
        },
        ("GET", "/api/prompt-templates"): {
            "type": "array",
            "items": {"$ref": "#/components/schemas/PromptTemplateInfo"},
            "title": "Response List Prompt Templates Api Prompt Templates Get",
        },
        ("GET", "/api/games/defaults"): {"$ref": "#/components/schemas/NewGame"},
        ("POST", "/api/games"): {"$ref": "#/components/schemas/GameState"},
        ("GET", "/api/games/current"): {"$ref": "#/components/schemas/GameState"},
        ("POST", "/api/games/current/moves"): {"$ref": "#/components/schemas/GameState"},
        ("POST", "/api/games/current/llm-turn"): {"$ref": "#/components/schemas/GameState"},
        ("POST", "/api/games/current/probes"): {"$ref": "#/components/schemas/Probe"},
        ("GET", "/api/games/{game_id}/probes"): {
            "type": "array",
            "items": {"$ref": "#/components/schemas/Probe"},
            "title": "Response List Probes Api Games  Game Id  Probes Get",
        },
        ("GET", "/api/leaderboard"): {"$ref": "#/components/schemas/Leaderboard"},
    }


def test_whole_number_sampling_stays_a_whole_number_in_the_json(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text("top_k = 40\ntemperature = 0.5\n")
    defaults = {"llama3:8b": {"seed": 7, "top_p": 1.0}}
    models = [LlmModel("llama3:8b")]
    client, _ = scripted([], models=models, sampling_defaults=defaults.__getitem__, sampling_file=config)

    assert '"sampling":{"seed":7,"top_p":1.0,"top_k":40,"temperature":0.5}' in client.get("/api/models").text
    assert '"sampling":{"top_k":40,"temperature":0.5}' in client.post("/api/games").text


def test_the_committed_typescript_types_match_the_api_description():
    """schema.ts starts with the fingerprint of the API description it was generated from, so this needs no Node."""
    first_line = SCHEMA_FILE.read_text(encoding="utf-8").splitlines()[0]

    assert first_line == schema_header(api_description()), (
        "frontend/src/api/schema.ts is out of date: run `uv run python -m scripts.generate_api_types`"
    )
