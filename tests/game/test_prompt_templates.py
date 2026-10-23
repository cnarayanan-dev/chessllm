"""Prompt templates (ADR 0010): every Prompt is built from the side's System prompt and Turn template, fixed when the
game starts and recorded in full in game_start; the defaults send exactly what was sent before templates existed."""

import json
import random
import re
from pathlib import Path

import chess
import pytest

from tests.conftest import ScriptedPlayer, llm_faceoff, play_llm, play_move

from chessllm.analytics.leaderboard import llm_configuration
from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES, default_template
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmConstraints, LlmSide, PromptTemplate
from chessllm.llm.models import LLM_MODELS
from chessllm.logs.game_log import GameLog

# Every Prompt of a faceoff, both sides with the same settings, as the game sent them before Prompt templates: White
# makes an illegal move, then 1. e4 e5 2. Nf3 Nc6. By "<llm_constraints>/<position>", then by colour; the described
# position is now the Described default template.
BEFORE_TEMPLATES = json.loads((Path(__file__).parent / "prompts_before_templates.json").read_text(encoding="utf-8"))

# Eleven plies, so the twelfth, Black's, is the first whose last ten plies start on a Black ply.
ELEVEN_PLIES = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d3", "d6", "O-O"]
EVERY_TURN_PLACEHOLDER = (
    "moves: $moves\nrecent: $recent_moves\nlast: $last_move\nfen: $fen\ndescription:\n$description"
)


def template(system_prompt: str = "You play $color against $opponent.", turn_template: str = "PGN: $moves") -> PromptTemplate:
    return PromptTemplate(id="test", name=None, system_prompt=system_prompt, turn_template=turn_template)


def faceoff_settings(black: LlmSide, white: LlmSide | None = None) -> Settings:
    return Settings("llm_faceoff", white or LlmSide(), black)


def play_faceoff(settings: Settings, white: list[str], black: list[str], games_dir: Path) -> dict[str, ScriptedPlayer]:
    """Play the faceoff to its end as the benchmark's commands do; each side's player keeps the Prompts it got."""
    settings.check(LLM_MODELS)
    players = {"white": ScriptedPlayer(white), "black": ScriptedPlayer(black)}
    play_anchor_match(settings, dict(players), {}, GameLog(games_dir, *settings.side_names()))
    return players


def game_start(games_dir: Path) -> dict:
    [log] = games_dir.glob("*.jsonl")
    return json.loads(log.read_text(encoding="utf-8").splitlines()[0])


@pytest.mark.parametrize("settings", list(BEFORE_TEMPLATES))
def test_with_the_default_templates_every_prompt_is_what_it_was_before_templates(tmp_path, settings):
    llm_constraints, position = settings.split("/")
    described = default_template(llm_constraints, "described") if position == "described" else None
    side = LlmSide(llm_constraints=llm_constraints, prompt_template=described)
    random.seed(112)  # Listed shows the legal moves in a random order, as when the Prompts were recorded

    # White's fourth turn has no reply scripted, so it forfeits, after the turns recorded.
    players = play_faceoff(faceoff_settings(side, white=side), ["Ke2", "e4", "Nf3"], ["e5", "Nc6"], tmp_path)

    for color, player in players.items():
        sent = [[[message.role, message.content] for message in prompt] for prompt in player.prompts]
        assert sent[: len(BEFORE_TEMPLATES[settings][color])] == BEFORE_TEMPLATES[settings][color]


def test_a_turn_template_gets_each_placeholder_filled_in_for_the_position(tmp_path):
    side = LlmSide(prompt_template=template(turn_template=EVERY_TURN_PLACEHOLDER))
    white_moves = ELEVEN_PLIES[0::2] + ["Re1"]
    black_moves = ELEVEN_PLIES[1::2] + ["a6", "Qe7"]

    players = play_faceoff(faceoff_settings(side), white_moves, black_moves, tmp_path)

    first, twelfth = players["black"].prompts[0], players["black"].prompts[5]
    assert first[0].content == "You play Black against White."
    board = chess.Board()
    for san in ELEVEN_PLIES:
        board.push_san(san)
    moves, recent, last, fen, description, *pieces = twelfth[1].content.splitlines()
    assert moves == "moves: 1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O"
    # The last ten plies, from Black's first move.
    assert recent == "recent: 1... e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O"
    assert last == "last: O-O"
    assert fen == f"fen: {board.fen()}"
    assert description == "description:"
    assert pieces[0] == "Last move: O-O"
    assert pieces[1].startswith("Your pieces (Black): King e8; Queen d8;")
    assert first[1].content.splitlines()[:3] == ["moves: 1. e4", "recent: 1. e4", "last: e4"]


def test_the_recent_moves_are_the_last_ten_plies_from_a_white_ply_too(tmp_path):
    side = LlmSide(prompt_template=template(turn_template="$recent_moves"))
    white_moves = ELEVEN_PLIES[0::2] + ["Re1"]
    black_moves = ELEVEN_PLIES[1::2] + ["a6", "Qe7"]

    players = play_faceoff(faceoff_settings(LlmSide(), white=side), white_moves, black_moves, tmp_path)

    # White's seventh turn, after twelve plies: plies 3 to 12.
    assert players["white"].prompts[6][1].content == "2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d3 d6 6. O-O a6"
    assert players["white"].prompts[0][1].content == "(no moves yet)"


def test_the_legal_move_list_is_filled_in_as_listed_shows_it(tmp_path):
    side = LlmSide(llm_constraints="listed", prompt_template=template(turn_template="Choose from: $legal_moves"))

    players = play_faceoff(faceoff_settings(side), ["e4", "Qh5", "Qxf7#"], ["e5", "Ke7"], tmp_path)

    shown = players["black"].prompts[0][1].content.removeprefix("Choose from: ").split(" ")
    after_e4 = chess.Board()
    after_e4.push_san("e4")
    assert sorted(shown) == sorted(after_e4.san(move) for move in after_e4.legal_moves)


@pytest.mark.parametrize(
    ("llm_constraints", "prompt_template", "reason"),
    [
        ("free", template(turn_template="PGN: $pgn"), "the Turn template has an unknown placeholder: $pgn"),
        ("free", template(system_prompt="As $colour, $side"), "the System prompt has unknown placeholders: $colour, $side"),
        ("free", template(turn_template="$fen costs $5"), "the Turn template has a $ that starts no placeholder"),
        ("free", template(turn_template="$moves\n$legal_moves"), "only Listed and Listed enforced show"),
        ("blind_enforced", template(turn_template="$legal_moves"), "only Listed and Listed enforced show"),
        ("listed", template(turn_template="$moves"), "must place $legal_moves"),
        ("listed_enforced", template(turn_template="$moves"), "must place $legal_moves"),
    ],
)
def test_a_template_that_doesnt_fit_is_refused_at_game_start_with_the_reason(
    llm_constraints: LlmConstraints, prompt_template: PromptTemplate, reason: str
):
    side = LlmSide(llm_constraints=llm_constraints, prompt_template=prompt_template)

    with pytest.raises(InvalidSettings, match="llama3:8b \\(black\\)") as refused:
        faceoff_settings(side).check(LLM_MODELS)

    assert reason in str(refused.value)


def test_game_start_records_each_sides_template_in_full(tmp_path):
    white = LlmSide(llm_constraints="listed")
    black = LlmSide(prompt_template=default_template("free", "described"))

    play_faceoff(faceoff_settings(black, white=white), ["f3", "g4"], ["e5", "Qh4#"], tmp_path)

    start = game_start(tmp_path)
    assert re.fullmatch("default-listed@[0-9a-f]{8}", start["white"]["prompt_template"].pop("id"))
    assert re.fullmatch("described@[0-9a-f]{8}", start["black"]["prompt_template"].pop("id"))
    assert start["white"]["prompt_template"] == {
        "name": "Default listed",
        "system_prompt": SYSTEM_PROMPT_FILES["listed"].read_text(encoding="utf-8"),
        "turn_template": "PGN: $moves\nFEN: $fen\nLegal moves: $legal_moves",
    }
    assert start["black"]["prompt_template"] == {
        "name": "Described",
        "system_prompt": SYSTEM_PROMPT_FILES["free"].read_text(encoding="utf-8"),
        "turn_template": "PGN: $moves\nFEN: $fen\n$description",
    }


def test_a_template_without_a_name_is_recorded_without_one(tmp_path):
    side = LlmSide(prompt_template=template())

    play_faceoff(faceoff_settings(side), ["f3", "g4"], ["e5", "Qh4#"], tmp_path)

    assert game_start(tmp_path)["black"]["prompt_template"] == {
        "id": "test", "system_prompt": "You play $color against $opponent.", "turn_template": "PGN: $moves"
    }


def test_a_default_templates_id_is_versioned_by_its_text(tmp_path, monkeypatch):
    system_file = tmp_path / "system.txt"
    system_file.write_text("You play $color.", encoding="utf-8")
    monkeypatch.setitem(SYSTEM_PROMPT_FILES, "free", system_file)
    first, again = default_template("free"), default_template("free")

    system_file.write_text("You play $color, edited.", encoding="utf-8")

    assert first.id == again.id and first.id.startswith("default@")
    assert default_template("free").id.startswith("default@") and default_template("free").id != first.id
    assert default_template("free", "described").id != first.id


def test_the_leaderboard_groups_a_default_game_with_its_template_recorded_as_before(faceoff, tmp_path):
    faceoff(["e4"], ["e5"], {"llm_constraints": "listed"})

    start = game_start(tmp_path / "games")
    for color in ("white", "black"):
        before = {key: value for key, value in start[color].items() if key != "prompt_template"}
        assert llm_configuration(start, color, start[color]).id() == llm_configuration(start, color, before).id()


def test_a_game_with_its_own_template_logs_no_prompt_file_and_is_grouped_by_its_id(tmp_path):
    side = LlmSide(prompt_template=template())

    play_faceoff(faceoff_settings(side), ["f3", "g4"], ["e5", "Qh4#"], tmp_path)

    start = game_start(tmp_path)
    assert list(start["prompt_files"]) == ["white"]
    assert llm_configuration(start, "black", start["black"]).prompt == "test"
    assert llm_configuration(start, "white", start["white"]).prompt == "system.txt"


def test_a_new_game_through_the_api_takes_no_prompt_template_yet(scripted, tmp_path):
    client, player = scripted([])
    side = {"prompt_template": {"id": "x", "name": None, "system_prompt": "$color", "turn_template": "$moves"}}

    response = client.post("/api/games", json=play_llm(**side))

    assert response.status_code == 400
    assert response.json() == {
        "detail": "A new game takes no Prompt template yet: the LLM side (black) plays its default one",
        "code": "prompt_template_not_accepted",
    }
    assert not (tmp_path / "games").exists() or not list((tmp_path / "games").glob("*.jsonl"))


def test_editing_a_default_file_mid_game_doesnt_change_the_games_prompts(scripted, tmp_path, monkeypatch):
    system_file = tmp_path / "system.txt"
    system_file.write_text("You play $color.", encoding="utf-8")
    monkeypatch.setitem(SYSTEM_PROMPT_FILES, "free", system_file)
    client, player = scripted(["e5", "Nc6"])
    client.post("/api/games", json=play_llm())
    play_move(client, "e2e4")

    system_file.write_text("You play $color, edited.", encoding="utf-8")
    play_move(client, "g1f3")

    assert [prompt[0].content for prompt in player.prompts] == ["You play Black.", "You play Black."]
    client.post("/api/games", json=llm_faceoff())  # the next game plays the edited file
    assert game_start_of_latest(tmp_path / "games")["black"]["prompt_template"]["system_prompt"] == (
        "You play $color, edited."
    )


def game_start_of_latest(games_dir: Path) -> dict:
    starts = [json.loads(log.read_text(encoding="utf-8").splitlines()[0]) for log in games_dir.glob("*.jsonl")]
    return max(starts, key=lambda start: start["started_at"])
