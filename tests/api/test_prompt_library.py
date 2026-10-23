"""The Prompt library (ADR 0010): the default Prompt templates and the saved ones, each a file in the library's folder,
listed with the LLM constraints each fits; a new game picks each LLM side's by its ID."""

import json
import re
from pathlib import Path

from tests.conftest import llm_faceoff, play_llm, play_move

from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES

FREE = ["free", "blind_enforced"]
LISTED = ["listed", "listed_enforced"]


def library(client) -> dict[str, dict]:
    response = client.get("/api/prompt-templates")
    assert response.status_code == 200, response.text
    return {entry["id"]: entry for entry in response.json()}


def id_of(client, name: str) -> str:
    return next(entry["id"] for entry in library(client).values() if entry["name"] == name)


def save(folder: Path, file_name: str, **entry) -> None:
    """A saved Prompt template as its file in the library holds it."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / file_name).write_text(json.dumps(entry, indent=2), encoding="utf-8")


def game_start(games_dir: Path) -> dict:
    [log] = games_dir.glob("*.jsonl")
    return json.loads(log.read_text(encoding="utf-8").splitlines()[0])


def test_the_library_lists_the_default_templates_with_the_llm_constraints_each_fits(scripted):
    client, _ = scripted([])

    entries = list(library(client).values())

    assert [(entry["name"], entry["fits"], entry["default_for"]) for entry in entries] == [
        ("Default", FREE, FREE),
        ("Described", FREE, []),
        ("Default listed", LISTED, LISTED),
        ("Described listed", LISTED, []),
    ]
    assert re.fullmatch("described-listed@[0-9a-f]{8}", entries[3]["id"])
    assert entries[3]["system_prompt"] == SYSTEM_PROMPT_FILES["listed"].read_text(encoding="utf-8")
    assert entries[3]["turn_template"] == "PGN: $moves\nFEN: $fen\n$description\nLegal moves: $legal_moves"


def test_a_game_started_with_a_templates_id_sends_its_prompts_and_records_its_text(scripted, tmp_path):
    client, player = scripted(["e5"])
    described = library(client)[id_of(client, "Described")]

    response = client.post("/api/games", json=play_llm(prompt_template_id=described["id"]))
    play_move(client, "e2e4")

    assert response.status_code == 200, response.text
    assert response.json()["settings"]["black"]["prompt_template_id"] == described["id"]
    [prompt] = player.prompts
    assert prompt[1].content.splitlines()[2:] == [
        "Last move: e4",
        "Your pieces (Black): King e8; Queen d8; Rooks a8, h8; Bishops c8, f8; Knights b8, g8; "
        "Pawns a7, b7, c7, d7, e7, f7, g7, h7",
        "Opponent's pieces (White): King e1; Queen d1; Rooks a1, h1; Bishops c1, f1; Knights b1, g1; "
        "Pawns a2, b2, c2, d2, e4, f2, g2, h2",
    ]
    assert game_start(tmp_path / "games")["black"]["prompt_template"] == {
        key: described[key] for key in ("id", "name", "system_prompt", "turn_template")
    }


def test_a_side_without_a_templates_id_plays_the_default_for_its_llm_constraints(scripted, tmp_path):
    client, _ = scripted([])

    state = client.post("/api/games", json=play_llm(llm_constraints="listed")).json()

    assert "prompt_template_id" not in state["settings"]["black"]
    assert game_start(tmp_path / "games")["black"]["prompt_template"]["id"] == id_of(client, "Default listed")


def test_an_unknown_templates_id_is_refused(scripted, tmp_path):
    client, _ = scripted([])

    response = client.post("/api/games", json=llm_faceoff(black={"prompt_template_id": "nope@12345678"}))

    assert response.status_code == 400
    assert response.json() == {
        "detail": "The Prompt library has no Prompt template nope@12345678: the LLM side (black) can't play it",
        "code": "unknown_prompt_template",
    }
    assert not list((tmp_path / "games").glob("*.jsonl"))


def test_a_template_that_doesnt_fit_the_sides_llm_constraints_is_refused(scripted):
    client, _ = scripted([])

    response = client.post(
        "/api/games", json=play_llm(llm_constraints="listed", prompt_template_id=id_of(client, "Described"))
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_prompt_template"
    assert "must place $legal_moves" in response.json()["detail"]


def test_a_saved_template_is_listed_from_its_file_and_can_be_played(scripted, tmp_path):
    folder = tmp_path / "prompt_library"
    save(folder, "terse.json", id="terse@1", name="Terse", hidden=False,
         system_prompt="You are $color.", turn_template="$recent_moves")
    save(folder, "nameless.json", id="nameless@1", hidden=False,
         system_prompt="You are $color.", turn_template="Choose: $legal_moves")
    client, player = scripted(["e5"], prompt_library_dir=folder)

    entries = library(client)
    client.post("/api/games", json=play_llm(prompt_template_id="terse@1"))
    play_move(client, "e2e4")

    assert (entries["terse@1"]["name"], entries["terse@1"]["fits"], entries["terse@1"]["default_for"]) == (
        "Terse", FREE, []
    )
    assert (entries["nameless@1"]["name"], entries["nameless@1"]["fits"]) == (None, LISTED)
    assert [message.content for message in player.prompts[0]] == ["You are Black.", "1. e4"]


def test_a_hidden_template_is_left_out_of_the_list_but_still_plays(scripted, tmp_path):
    folder = tmp_path / "prompt_library"
    save(folder, "old.json", id="old@1", name="Old", hidden=True, system_prompt="$color", turn_template="$moves")
    client, _ = scripted([], prompt_library_dir=folder)

    response = client.post("/api/games", json=play_llm(prompt_template_id="old@1"))

    assert "old@1" not in library(client)
    assert response.status_code == 200, response.text
    assert game_start(tmp_path / "games")["black"]["prompt_template"]["id"] == "old@1"


def test_a_new_game_takes_a_template_by_its_id_not_its_text(scripted, tmp_path):
    client, _ = scripted([])
    side = {"prompt_template": {"id": "x", "name": None, "system_prompt": "$color", "turn_template": "$moves"}}

    response = client.post("/api/games", json=play_llm(**side))

    assert response.status_code == 400
    assert response.json() == {
        "detail": "A new game takes a Prompt template by its ID in the Prompt library (prompt_template_id), "
        "not its text: the LLM side (black)",
        "code": "prompt_template_not_accepted",
    }
    assert not list((tmp_path / "games").glob("*.jsonl"))
