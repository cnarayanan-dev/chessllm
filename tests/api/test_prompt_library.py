"""The Prompt library (ADR 0010): the default Prompt templates and the saved ones, each a file in the library's folder,
listed with the LLM constraints each fits; a new game picks each LLM side's by its ID."""

import json
import re
from pathlib import Path

from tests.conftest import llm_faceoff, play_llm, play_move

from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES

FREE = ["free", "blind_enforced"]
LISTED = ["listed", "listed_enforced"]
# The Turn memories under which a turn shows the position: every one but chat_moves.
SHOWN = ["fresh", "chat_position"]


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

    assert [(entry["name"], entry["fits"], entry["turn_memories"], entry["default_for"]) for entry in entries] == [
        ("Default", FREE, SHOWN, FREE),
        ("Described", FREE, SHOWN, []),
        ("Moves", FREE, ["chat_moves"], FREE),  # the Default under chat_moves
        ("Default listed", LISTED, SHOWN, LISTED),
        ("Described listed", LISTED, SHOWN, []),
        ("Moves listed", LISTED, ["chat_moves"], LISTED),
    ]
    assert re.fullmatch("described-listed@[0-9a-f]{8}", entries[4]["id"])
    assert entries[4]["system_prompt"] == SYSTEM_PROMPT_FILES["listed"].read_text(encoding="utf-8")
    assert entries[4]["turn_template"] == "PGN: $moves\nFEN: $fen\n$description\nLegal moves: $legal_moves"
    assert not any(entry["saved"] for entry in entries)  # a default isn't saved, so it can't be hidden


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
    assert entries["terse@1"]["turn_memories"] == ["fresh", "chat_position", "chat_moves"]  # theirs to fit
    assert entries["terse@1"]["saved"] and entries["nameless@1"]["saved"]
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


def save_new(client, **template):
    """Save a Prompt template through the API, as the Prompt lab's dock does."""
    return client.post("/api/prompt-templates", json=template)


def saved_file(folder: Path, template_id: str) -> Path:
    return next(path for path in folder.glob("*.json") if json.loads(path.read_text())["id"] == template_id)


def test_saving_a_template_makes_a_new_one_with_a_new_id_in_its_own_file(scripted, tmp_path):
    folder = tmp_path / "prompt_library"
    client, _ = scripted([])
    terse = {"system_prompt": "You are $color.", "turn_template": "$recent_moves", "llm_constraints": "free"}

    first = save_new(client, name="Terse", **terse)
    first_text = saved_file(folder, first.json()["id"]).read_text(encoding="utf-8")
    edited = save_new(client, name="Terse", **terse | {"turn_template": "$recent_moves\n$fen"})
    again = save_new(client, name=None, **terse)

    assert [response.status_code for response in (first, edited, again)] == [200, 200, 200], first.text
    ids = [response.json()["id"] for response in (first, edited, again)]
    assert len(set(ids)) == 3  # the same text saved twice is still two Prompt templates
    assert re.fullmatch("terse@[0-9a-f]{8}", ids[0]) and re.fullmatch("saved@[0-9a-f]{8}", ids[2])
    assert (first.json()["name"], first.json()["fits"], first.json()["default_for"]) == ("Terse", FREE, [])
    assert first.json()["saved"]
    assert json.loads(first_text) == {
        "id": ids[0], "name": "Terse", "hidden": False,
        "system_prompt": "You are $color.", "turn_template": "$recent_moves",
    }
    assert saved_file(folder, ids[0]).read_text(encoding="utf-8") == first_text
    assert len(list(folder.glob("*.json"))) == 3
    assert [library(client)[id]["turn_template"] for id in ids] == [
        "$recent_moves", "$recent_moves\n$fen", "$recent_moves"
    ]


def test_an_invalid_template_is_refused_with_the_reason_and_nothing_is_written(scripted, tmp_path):
    client, _ = scripted([])

    refusals = [
        save_new(client, name="Typo", system_prompt="You are $colour.", turn_template="$moves", llm_constraints="free"),
        save_new(client, name=None, system_prompt="$color", turn_template="$moves", llm_constraints="listed"),
        save_new(client, name=None, system_prompt="$color", turn_template="$legal_moves", llm_constraints="free"),
    ]

    assert [(response.status_code, response.json()["code"]) for response in refusals] == [
        (400, "invalid_prompt_template"),
    ] * 3
    assert refusals[0].json()["detail"] == "the System prompt has an unknown placeholder: $colour"
    assert "must place $legal_moves: listed shows the Legal-move list" in refusals[1].json()["detail"]
    assert not (tmp_path / "prompt_library").exists()


def test_a_hidden_template_is_left_out_of_the_list_but_still_resolves_for_the_game_that_used_it(scripted, tmp_path):
    client, _ = scripted(["e5", "Nc6"])
    saved_id = save_new(
        client, name="Old", system_prompt="You are $color.", turn_template="$moves", llm_constraints="free"
    ).json()["id"]
    client.post("/api/games", json=play_llm(prompt_template_id=saved_id))
    play_move(client, "e2e4")

    hidden = client.post(f"/api/prompt-templates/{saved_id}/hide")
    probed = client.post("/api/games/current/probes", json={"ply": 2, "color": "black", "prompt_template_id": saved_id})
    restarted = client.post("/api/games", json=play_llm(prompt_template_id=saved_id))

    assert hidden.status_code == 200, hidden.text
    assert saved_id not in [entry["id"] for entry in hidden.json()]
    assert saved_id not in library(client)
    assert json.loads(saved_file(tmp_path / "prompt_library", saved_id).read_text())["hidden"] is True
    assert probed.status_code == 200, probed.text
    assert probed.json()["prompt_template"]["system_prompt"] == "You are $color."
    assert restarted.status_code == 200, restarted.text


def test_only_a_saved_template_can_be_hidden(scripted):
    client, _ = scripted([])

    refusals = [
        client.post(f"/api/prompt-templates/{id_of(client, 'Described')}/hide"),
        client.post("/api/prompt-templates/nope@12345678/hide"),
    ]

    assert [(response.status_code, response.json()["code"]) for response in refusals] == [
        (400, "default_prompt_template"),
        (400, "unknown_prompt_template"),
    ]
    assert "Described" in [entry["name"] for entry in library(client).values()]
