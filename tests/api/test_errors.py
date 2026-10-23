from fastapi.testclient import TestClient
from tests.conftest import llm_faceoff, play_llm, play_move


def refusal(response) -> tuple[int, dict]:
    return response.status_code, response.json()


def test_a_request_without_a_game_is_refused_with_its_code(scripted):
    client, _ = scripted([])

    assert refusal(client.get("/api/games/current")) == (404, {"detail": "no game started", "code": "no_current_game"})
    assert refusal(client.post("/api/games/current/llm-turn"))[1]["code"] == "no_current_game"
    assert refusal(client.post("/api/games/current/moves", json={"uci": "e2e4"}))[1]["code"] == "no_current_game"


def test_a_rejected_human_move_says_why_in_its_code(scripted):
    client, _ = scripted([])
    client.post("/api/games")

    assert refusal(client.post("/api/games/current/moves", json={"uci": "e2e5"})) == (
        400,
        {"detail": "illegal move: e2e5", "code": "illegal_move"},
    )
    assert refusal(client.post("/api/games/current/moves", json={"uci": "e2"})) == (
        400,
        {"detail": "not a UCI move: 'e2'", "code": "invalid_move"},
    )


def test_a_human_move_is_refused_once_the_game_is_over_or_when_no_human_plays(scripted, faceoff):
    client, _ = scripted(["f6", "g5"])
    client.post("/api/games")
    for uci in ["e2e4", "d2d4", "d1h5"]:
        play_move(client, uci)

    assert refusal(client.post("/api/games/current/moves", json={"uci": "a2a3"})) == (
        400,
        {"detail": "the game is over", "code": "game_over"},
    )
    assert refusal(client.post("/api/games/current/llm-turn")) == (
        409,
        {"detail": "the game is over", "code": "game_over"},
    )
    faceoff_client, _, _ = faceoff([], [])
    assert refusal(faceoff_client.post("/api/games/current/moves", json={"uci": "e2e4"})) == (
        400,
        {"detail": "an LLM faceoff takes no human moves", "code": "not_human_turn"},
    )


def test_an_llm_turn_on_the_humans_turn_is_refused_with_its_code(scripted):
    client, _ = scripted([])
    client.post("/api/games")

    assert refusal(client.post("/api/games/current/llm-turn")) == (
        409,
        {"detail": "it is not an LLM's turn", "code": "not_llm_turn"},
    )


def test_settings_that_cant_be_played_are_refused_with_their_code(scripted):
    client, _ = scripted([])

    response = client.post("/api/games", json=llm_faceoff({"model": "nonesuch:1b"}))

    assert refusal(response) == (
        400,
        {"detail": "nonesuch:1b (white) is not in the model list", "code": "invalid_settings"},
    )


def test_a_broken_sampling_config_is_a_server_error_with_its_code(scripted, tmp_path):
    config = tmp_path / "sampling.toml"
    config.write_text('temperature = "hot"\nwarmth = 1\n')
    client, _ = scripted([], sampling_file=config)
    error = {"detail": "sampling.toml: unknown sampling options warmth", "code": "config_error"}

    assert refusal(client.get("/api/models")) == (500, error)
    assert refusal(client.post("/api/games", json=play_llm())) == (500, error)


def test_a_malformed_request_keeps_fastapis_own_validation_error(scripted):
    client, _ = scripted([])

    status, body = refusal(client.post("/api/games", json={"max_attempts": 0}))

    assert status == 422
    assert "code" not in body and isinstance(body["detail"], list)


def test_every_refusal_a_route_can_give_is_described_with_the_error_detail(scripted):
    client: TestClient = scripted([])[0]
    description = client.get("/openapi.json").json()

    declared = {
        (method.upper(), path): {
            status
            for status, response in operation["responses"].items()
            if response.get("content", {}).get("application/json", {}).get("schema")
            == {"$ref": "#/components/schemas/ErrorDetail"}
        }
        for path, operations in description["paths"].items()
        if path.startswith("/api/")
        for method, operation in operations.items()
    }

    assert declared == {
        ("GET", "/api/models"): {"500"},
        ("GET", "/api/prompt-templates"): set(),
        ("POST", "/api/prompt-templates"): {"400"},
        ("GET", "/api/prompt-templates/{template_id}"): {"400"},
        ("POST", "/api/prompt-templates/{template_id}/hide"): {"400"},
        ("GET", "/api/games/defaults"): set(),
        ("POST", "/api/games"): {"400", "500"},
        ("GET", "/api/games/current"): {"404"},
        ("POST", "/api/games/current/moves"): {"400", "404"},
        ("POST", "/api/games/current/llm-turn"): {"404", "409"},
        ("POST", "/api/games/current/probes"): {"400", "404", "409"},
        ("GET", "/api/games/{game_id}/probes"): set(),
        ("GET", "/api/ranking"): set(),
    }
    assert description["components"]["schemas"]["ErrorDetail"]["required"] == ["detail", "code"]
