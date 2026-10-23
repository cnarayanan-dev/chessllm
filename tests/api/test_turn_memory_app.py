"""Turn memory in the app (#108): a new game takes each LLM side's Turn memory, its state gives it back unless fresh,
so a Rematch, which the page asks for with the state's settings, keeps it; and the side plays a template that fits it,
by default the Moves template under chat_moves."""

import json

import pytest
from tests.conftest import llm_faceoff, play_llm, play_move

from chessllm.game.llm_turn.prompt import default_template


def game_start(games_dir) -> dict:
    """The game_start of the last game started."""
    log = max(games_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime_ns)
    return json.loads(log.read_text(encoding="utf-8").splitlines()[0])


@pytest.mark.parametrize(
    ("memory", "second_prompt"),
    [
        ("fresh", ["system", "user"]),
        ("chat_position", ["system", "user", "assistant", "user"]),
        ("chat_moves", ["system", "user", "assistant", "user"]),
    ],
)
def test_a_new_game_with_each_turn_memory_starts_that_game(scripted, tmp_path, memory, second_prompt):
    client, player = scripted(["e5", "Nc6"])

    response = client.post("/api/games", json=play_llm(turn_memory=memory))
    play_move(client, "e2e4")
    state = play_move(client, "g1f3").json()

    assert response.status_code == 200, response.text
    black = state["settings"]["black"]
    logged = game_start(tmp_path / "games")["black"]
    # Left out when fresh, as in the game log, so a fresh game reads as before Turn memory.
    assert black.get("turn_memory", "fresh") == logged.get("turn_memory", "fresh") == memory
    assert ("turn_memory" in black) == (memory != "fresh")
    assert [message.role for message in player.prompts[1]] == second_prompt
    if memory == "chat_moves":
        assert player.prompts[1][-1].content == "Opponent played Nf3."
    remembered = [turn.get("remembered") for turn in state["llm_turns"]]
    assert remembered == ([None, None] if memory == "fresh" else [0, 1])


def test_a_rematch_keeps_each_sides_turn_memory(faceoff, tmp_path):
    client, state, _ = faceoff([], [], {"turn_memory": "chat_moves"}, {"turn_memory": "chat_position"})
    settings = state["settings"]

    # The page's Rematch: the same settings, each side taking the other colour.
    rematch = {"mode": settings["mode"], "white": settings["black"], "black": settings["white"]}
    response = client.post("/api/games", json=rematch | {"max_attempts": settings["max_attempts"]})

    assert response.status_code == 200, response.text
    swapped = response.json()["settings"]
    assert (swapped["white"]["turn_memory"], swapped["black"]["turn_memory"]) == ("chat_position", "chat_moves")
    logged = game_start(tmp_path / "games")
    assert (logged["white"]["turn_memory"], logged["black"]["turn_memory"]) == ("chat_position", "chat_moves")


@pytest.mark.parametrize(("constraints", "moves"), [("free", "Moves"), ("listed", "Moves listed")])
def test_a_side_under_chat_moves_plays_the_moves_template_of_its_constraints_by_default(scripted, constraints, moves):
    client, _ = scripted([])

    state = client.post("/api/games", json=play_llm(turn_memory="chat_moves", llm_constraints=constraints)).json()

    assert state["prompt_template_ids"]["black"] == default_template(constraints, "moves").id
    assert default_template(constraints, "moves").name == moves


def test_a_template_that_doesnt_fit_the_sides_turn_memory_is_refused(scripted):
    client, _ = scripted([])
    default = default_template("free").id
    chat_moves_side = {"turn_memory": "chat_moves", "prompt_template_id": default}

    response = client.post("/api/games", json=llm_faceoff(white=chat_moves_side))

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_prompt_template"
    assert "must place $opponent_played" in response.json()["detail"]
