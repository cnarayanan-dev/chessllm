"""The Modes as objects: each says who plays its sides and how its games are run, looked up by the key the API and
the game log give it."""

import pytest

from chessllm.exceptions import InvalidSettings
from chessllm.game.modes import ANCHOR_MATCH, LLM_FACEOFF, MODES, PLAY_LLM, mode_named
from chessllm.game.sides import AnchorSide, HumanSide, LlmSide


def test_each_mode_is_found_by_its_key_and_has_its_name():
    assert {key: mode.name for key, mode in MODES.items()} == {
        "play_llm": "Play LLM",
        "llm_faceoff": "LLM faceoff",
        "anchor_match": "Anchor match",
    }
    assert mode_named("llm_faceoff") is LLM_FACEOFF
    assert mode_named("matchup") is None


def test_only_play_llm_takes_human_moves_and_only_the_others_run_unattended():
    assert [mode.accepts_human_moves for mode in (PLAY_LLM, LLM_FACEOFF, ANCHOR_MATCH)] == [True, False, False]
    assert [mode.unattended for mode in (PLAY_LLM, LLM_FACEOFF, ANCHOR_MATCH)] == [False, True, True]


def test_play_llm_games_do_not_count_towards_the_rating():
    assert [mode.rated for mode in (PLAY_LLM, LLM_FACEOFF, ANCHOR_MATCH)] == [False, True, True]


def test_only_an_anchor_match_is_played_against_an_anchor():
    assert [mode.against_an_anchor for mode in (PLAY_LLM, LLM_FACEOFF, ANCHOR_MATCH)] == [False, False, True]


def test_a_mode_accepts_the_sides_it_needs():
    PLAY_LLM.check_sides(LlmSide(), HumanSide())
    LLM_FACEOFF.check_sides(LlmSide(), LlmSide(model="qwen3.5:9b"))
    ANCHOR_MATCH.check_sides(AnchorSide(), LlmSide())


@pytest.mark.parametrize(
    ("mode", "white", "black", "why"),
    [
        (PLAY_LLM, LlmSide(), LlmSide(), "Play LLM needs one human side, not 0"),
        (LLM_FACEOFF, HumanSide(), LlmSide(), "LLM faceoff needs no human side, not 1"),
        (ANCHOR_MATCH, LlmSide(), LlmSide(), "Anchor match needs one LLM side, not 2"),
        (LLM_FACEOFF, AnchorSide(), AnchorSide(), "LLM faceoff needs two LLM sides, not 0"),
    ],
)
def test_a_mode_refuses_sides_it_does_not_have(mode, white, black, why):
    with pytest.raises(InvalidSettings, match=f"^{why}$"):
        mode.check_sides(white, black)


def test_a_faceoff_logs_the_prompt_file_of_each_side_and_the_other_modes_their_one_file():
    files = {"white": "system.txt", "black": "system_listed.txt"}

    assert LLM_FACEOFF.logged_prompt_files(files) == {"prompt_files": files}
    assert PLAY_LLM.logged_prompt_files({"black": "system.txt"}) == {"prompt_file": "system.txt"}
