"""The Prompt library (ADR 0010): the default Prompt templates and the saved ones, each a file in the library's folder,
listed with the LLM constraints each fits; a new game picks each LLM side's by its ID."""

import json
import re
from pathlib import Path

from tests.conftest import llm_faceoff, play_llm, play_move

from chessllm.game.llm_turn.prompt import MOVES_SYSTEM_PROMPT_FILES, SYSTEM_PROMPT_FILES, template_version

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
        ("Moves", [], []),  # played only under Turn memory chat_moves, which the app doesn't play yet (#108)
        ("Default listed", LISTED, LISTED),
        ("Described listed", LISTED, []),
        ("Moves listed", [], []),
    ]
    assert re.fullmatch("described-listed@[0-9a-f]{8}", entries[4]["id"])
    assert entries[4]["system_prompt"] == SYSTEM_PROMPT_FILES["listed"].read_text(encoding="utf-8")
    assert entries[4]["turn_template"] == "PGN: $moves\nFEN: $fen\n$description\nLegal moves: $legal_moves"
    assert entries[5]["system_prompt"] == MOVES_SYSTEM_PROMPT_FILES["listed"].read_text(encoding="utf-8")
    assert entries[5]["turn_template"] == "$opponent_played\nLegal moves: $legal_moves"


def test_a_new_game_cant_play_a_moves_template_under_fresh_turn_memory(scripted):
    client, _ = scripted([])

    response = client.post("/api/games", json=play_llm(prompt_template_id=id_of(client, "Moves")))

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "invalid_prompt_template"
    assert "$opponent_played" in response.json()["detail"]


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


def save_request(**fields) -> dict:
    """A Prompt template to save, written for Free unless llm_constraints says otherwise."""
    return {
        "name": "Terse", "system_prompt": "You are $color.", "turn_template": "$recent_moves", "llm_constraints": "free",
    } | fields


def files(folder: Path) -> dict[str, dict]:
    """The library's saved files, by name."""
    return {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(folder.glob("*.json"))}


def test_saving_a_template_returns_its_new_id_and_writes_its_file(scripted, tmp_path):
    client, _ = scripted([])

    response = client.post("/api/prompt-templates", json=save_request())

    assert response.status_code == 200, response.text
    saved = response.json()
    assert re.fullmatch("terse@[0-9a-f]{8}", saved["id"])
    assert (saved["name"], saved["fits"], saved["default_for"]) == ("Terse", FREE, [])
    assert (saved["saved"], saved["hidden"]) == (True, False)
    assert files(tmp_path / "prompt_library") == {
        f"{saved['id']}.json": {
            "id": saved["id"], "name": "Terse", "hidden": False,
            "system_prompt": "You are $color.", "turn_template": "$recent_moves",
        }
    }
    assert library(client)[saved["id"]] == saved


def test_saving_an_edit_makes_another_id_and_leaves_the_first_unchanged(scripted, tmp_path):
    client, player = scripted(["e5"])
    folder = tmp_path / "prompt_library"
    first = client.post("/api/prompt-templates", json=save_request()).json()
    [(first_file, first_content)] = files(folder).items()

    edited = client.post("/api/prompt-templates", json=save_request(turn_template="$recent_moves\n$fen")).json()
    client.post("/api/games", json=play_llm(prompt_template_id=first["id"]))
    play_move(client, "e2e4")

    assert edited["id"] != first["id"] and edited["id"].startswith("terse@")
    assert len(files(folder)) == 2 and files(folder)[first_file] == first_content
    assert library(client)[first["id"]] == first
    assert player.prompts[0][1].content == "1. e4"  # the first version, as it was saved


def test_a_template_saved_without_a_name_gets_an_id_all_the_same(scripted):
    client, _ = scripted([])

    saved = client.post("/api/prompt-templates", json=save_request(name="  ")).json()

    assert saved["name"] is None
    assert re.fullmatch("saved@[0-9a-f]{8}", saved["id"])


def test_saving_a_template_the_library_already_has_writes_nothing_new(scripted, tmp_path):
    client, _ = scripted([])
    first = client.post("/api/prompt-templates", json=save_request()).json()

    again = client.post("/api/prompt-templates", json=save_request())

    assert again.status_code == 200 and again.json() == first
    assert len(files(tmp_path / "prompt_library")) == 1


def test_an_invalid_template_is_refused_with_the_reason_and_nothing_is_written(scripted, tmp_path):
    client, _ = scripted([])

    refused = [
        client.post("/api/prompt-templates", json=save_request(turn_template="$moves $board")),
        client.post("/api/prompt-templates", json=save_request(llm_constraints="listed")),
        client.post("/api/prompt-templates", json=save_request(turn_template="$moves $legal_moves")),
    ]

    assert [(response.status_code, response.json()["code"]) for response in refused] == [
        (400, "invalid_prompt_template")
    ] * 3
    assert refused[0].json()["detail"] == "the Turn template has an unknown placeholder: $board"
    assert "must place $legal_moves" in refused[1].json()["detail"]
    assert "only Listed and Listed enforced show the Legal-move list" in refused[2].json()["detail"]
    assert not (tmp_path / "prompt_library").exists()


def test_a_hidden_template_is_left_out_of_the_list_but_still_resolves_for_a_game_that_used_it(scripted, tmp_path):
    client, player = scripted(["e5", "Nc6", "d5"])
    saved = client.post("/api/prompt-templates", json=save_request()).json()
    client.post("/api/games", json=play_llm(prompt_template_id=saved["id"]))
    play_move(client, "e2e4")

    hidden = client.post(f"/api/prompt-templates/{saved['id']}/hide")
    play_move(client, "g1f3")
    probe = {"ply": 4, "color": "black", "prompt_template_id": saved["id"]}
    probed = client.post("/api/games/current/probes", json=probe)
    rematch = client.post("/api/games", json=play_llm(prompt_template_id=saved["id"]))

    assert hidden.status_code == 200 and hidden.json() == saved | {"hidden": True}
    assert saved["id"] not in library(client)
    assert files(tmp_path / "prompt_library")[f"{saved['id']}.json"]["hidden"] is True
    assert [prompt[1].content for prompt in player.prompts] == ["1. e4", "1. e4 e5 2. Nf3", "1. e4 e5 2. Nf3"]
    assert probed.status_code == 200 and probed.json()["template"]["id"] == saved["id"]
    assert rematch.status_code == 200, rematch.text


def test_saving_a_hidden_templates_text_again_shows_it_again(scripted):
    client, _ = scripted([])
    saved = client.post("/api/prompt-templates", json=save_request()).json()
    client.post(f"/api/prompt-templates/{saved['id']}/hide")

    again = client.post("/api/prompt-templates", json=save_request()).json()

    assert again == saved
    assert saved["id"] in library(client)


def test_a_default_or_unknown_template_cant_be_hidden(scripted):
    client, _ = scripted([])
    described = id_of(client, "Described")

    default = client.post(f"/api/prompt-templates/{described}/hide")
    unknown = client.post("/api/prompt-templates/nope@12345678/hide")

    assert (default.status_code, default.json()["code"]) == (400, "default_prompt_template")
    assert (unknown.status_code, unknown.json()["code"]) == (400, "unknown_prompt_template")
    assert described in library(client)


def test_saving_never_overwrites_a_file_even_one_named_like_the_new_id(scripted, tmp_path):
    client, _ = scripted([])
    folder = tmp_path / "prompt_library"
    version = template_version("You are $color.", "$recent_moves")
    stranger = {"id": "stranger@1", "hidden": False, "system_prompt": "$color", "turn_template": "$moves"}
    save(folder, f"terse@{version}.json", **stranger)

    saved = client.post("/api/prompt-templates", json=save_request()).json()

    assert saved["id"] == f"terse-2@{version}"
    assert files(folder)[f"terse@{version}.json"] == stranger
    assert files(folder)[f"terse-2@{version}.json"]["name"] == "Terse"
    assert not [path for path in folder.iterdir() if not path.name.endswith(".json")]  # no temporary file left


def test_the_same_text_saved_under_another_name_of_the_same_slug_keeps_its_name_under_its_own_id(scripted):
    client, _ = scripted([])
    first = client.post("/api/prompt-templates", json=save_request()).json()

    second = client.post("/api/prompt-templates", json=save_request(name="TERSE!")).json()
    again = client.post("/api/prompt-templates", json=save_request(name="TERSE!")).json()

    assert second["name"] == "TERSE!" and second["id"] != first["id"]
    assert second["id"].startswith("terse-2@") and again == second
    assert {first["id"], second["id"]} <= set(library(client))


def test_a_template_is_fetched_by_its_id_hidden_or_not(scripted):
    client, _ = scripted([])
    saved = client.post("/api/prompt-templates", json=save_request()).json()
    client.post(f"/api/prompt-templates/{saved['id']}/hide")
    described = id_of(client, "Described")

    hidden = client.get(f"/api/prompt-templates/{saved['id']}")
    default = client.get(f"/api/prompt-templates/{described}")
    unknown = client.get("/api/prompt-templates/nope@12345678")

    assert hidden.status_code == 200 and hidden.json() == saved | {"hidden": True}
    assert default.json() == library(client)[described] and default.json()["saved"] is False
    assert (unknown.status_code, unknown.json()["code"]) == (400, "unknown_prompt_template")
