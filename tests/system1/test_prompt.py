"""The default System 1 Prompt templates and how a System 1 side picks one from the Prompt library (ADR 0010, ADR
0012): the position with the moves so far, and the position alone, which the operator compares to measure whether the
move history helps."""

import pytest

from tests.system1.test_turn import events, play_out_one_round, side, start
from tests.conftest import FakeDecisionModel

from chessllm.exceptions import InvalidSettings
from chessllm.game.prompt_library import PromptLibrary
from chessllm.system1.prompt import (
    DEFAULT_TEMPLATE,
    POSITION_ONLY_TEMPLATE,
    SYSTEM1_TEMPLATES,
    resolve_system1_template,
)


def asked_state(tmp_path, template) -> str:
    model = FakeDecisionModel.favouring("e5")
    game = start(tmp_path, model, ["e4"], system1=side(prompt_template=template))
    play_out_one_round(game)
    [asked] = model.asked
    return asked.state


def test_the_position_only_template_gives_the_fen_and_where_every_piece_stands_but_not_the_moves_so_far(tmp_path):
    state = asked_state(tmp_path, POSITION_ONLY_TEMPLATE)

    assert state == (
        "FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1\n"
        "Your pieces (Black): King e8; Queen d8; Rooks a8, h8; Bishops c8, f8; Knights b8, g8; "
        "Pawns a7, b7, c7, d7, e7, f7, g7, h7\n"
        "Opponent's pieces (White): King e1; Queen d1; Rooks a1, h1; Bishops c1, f1; Knights b1, g1; "
        "Pawns a2, b2, c2, d2, e4, f2, g2, h2"
    )
    assert "Moves so far" not in state and "Last move" not in state


def test_it_asks_the_same_question_as_the_default(tmp_path):
    model = FakeDecisionModel.favouring("e5")
    game = start(tmp_path, model, ["e4"], system1=side(prompt_template=POSITION_ONLY_TEMPLATE))

    play_out_one_round(game)

    assert model.asked[0].question == "Which move should Black play?"


def test_both_defaults_are_in_the_system_1_templates_by_their_ids_which_differ():
    assert SYSTEM1_TEMPLATES == {
        DEFAULT_TEMPLATE.id: DEFAULT_TEMPLATE,
        POSITION_ONLY_TEMPLATE.id: POSITION_ONLY_TEMPLATE,
    }
    assert DEFAULT_TEMPLATE.id != POSITION_ONLY_TEMPLATE.id
    assert POSITION_ONLY_TEMPLATE.id.startswith("system1-position-only@")


def test_a_game_logs_the_template_it_was_played_with_in_full_so_the_two_defaults_log_different_text(tmp_path):
    logged = []
    for number, template in enumerate((DEFAULT_TEMPLATE, POSITION_ONLY_TEMPLATE)):
        game = start(tmp_path / str(number), FakeDecisionModel(), [], system1=side(prompt_template=template))
        [game_start] = events(game, "game_start")
        logged.append(game_start["black"]["prompt_template"])

    default, position_only = logged
    assert position_only == {
        "id": POSITION_ONLY_TEMPLATE.id,
        "name": "System 1, position only",
        "system_prompt": "Which move should $color play?",
        "turn_template": "FEN: $fen\n$pieces",
    }
    assert default["turn_template"] != position_only["turn_template"]
    assert default["id"] != position_only["id"]


@pytest.mark.parametrize("template", [DEFAULT_TEMPLATE, POSITION_ONLY_TEMPLATE])
def test_a_side_picks_either_default_from_the_prompt_library_by_its_id(tmp_path, template):
    assert resolve_system1_template(template.id, PromptLibrary(tmp_path)) == template


def test_a_side_picks_a_saved_template_by_its_id(tmp_path):
    library = PromptLibrary(tmp_path)
    saved = library.save("Fen only", "Which move should $color play?", "$fen", "free")

    assert resolve_system1_template(saved.template.id, library) == saved.template


def test_an_id_the_library_has_no_template_for_is_refused_naming_it(tmp_path):
    with pytest.raises(InvalidSettings, match="system1@nope") as refused:
        resolve_system1_template("system1@nope", PromptLibrary(tmp_path))

    assert refused.value.code == "unknown_prompt_template"


def test_a_saved_template_placing_the_legal_moves_is_refused_for_a_system_1_side_naming_it_and_why(tmp_path):
    library = PromptLibrary(tmp_path)
    saved = library.save("With options", "Which move should $color play?", "$fen\nOptions: $legal_moves", "listed")

    with pytest.raises(InvalidSettings, match=r"\$legal_moves") as refused:
        resolve_system1_template(saved.template.id, library)

    assert saved.template.id in str(refused.value)
    assert refused.value.code == "invalid_prompt_template"
