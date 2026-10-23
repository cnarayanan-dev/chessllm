"""Turn memory chat_moves: one conversation for the game, each turn adding only the opponent's last move, so the LLM
keeps track of the board itself. Its side plays the Moves default Prompt template, a System prompt saying so and a
Turn template placing only $opponent_played (and the Legal-move list under Listed)."""

import json
import re

import pytest

from tests.conftest import ScriptedAnchor, ScriptedPlayer

from chessllm.analytics.leaderboard import llm_configuration, settings_configuration
from chessllm.cli.anchor_batch import main as anchor_batch
from chessllm.cli.anchor_match import main as anchor_match
from chessllm.cli.faceoff_batch import main as faceoff_batch
from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.counterpart import counterpart_template
from chessllm.game.llm_turn.prompt import (
    MOVES_SYSTEM_PROMPT_FILES,
    SYSTEM_PROMPT_FILES,
    check_prompt_template,
    default_template,
    fill_system_prompt,
    prompt_file,
    side_template,
)
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import LISTED, LlmConstraints, LlmSide, TurnMemory
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog

EVERY_LLM_CONSTRAINTS: list[LlmConstraints] = ["free", "listed", "blind_enforced", "listed_enforced"]
EVERY_TURN_MEMORY: list[TurnMemory] = ["fresh", "chat_position", "chat_moves"]
PROMPTS = "chessllm/game/prompts"


def move(san: str) -> str:
    return json.dumps({"move": san})


def faceoff(tmp_path, white: LlmSide, black: LlmSide, white_moves: list[str], black_moves: list[str]):
    """Play an LLM faceoff unattended, as the batch commands do; each side's player keeps the Prompts it got."""
    settings = Settings("llm_faceoff", white, black)
    settings.check(LLM_MODELS)
    players = {"white": ScriptedPlayer(white_moves), "black": ScriptedPlayer(black_moves)}
    play_anchor_match(settings, dict(players), {}, GameLog(tmp_path / "games", *settings.side_names()))
    return players


def events(games_dir) -> list[dict]:
    [log] = games_dir.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_as_white_and_as_black_each_turn_adds_only_the_opponents_last_move(tmp_path):
    side = LlmSide(turn_memory="chat_moves")

    players = faceoff(tmp_path, side, side, ["f3", "g4"], ["e5", "Qh4#"])

    white_first, white_second = players["white"].prompts
    black_first, black_second = players["black"].prompts
    assert white_first[0].role == black_first[0].role == "system"
    assert white_first[1:] == [Message("user", "You play White. Make the first move.")]
    assert white_second[1:] == [
        Message("user", "You play White. Make the first move."),
        Message("assistant", move("f3")),
        Message("user", "Opponent played e5."),
    ]
    assert black_first[1:] == [Message("user", "Opponent played f3.")]
    assert black_second[1:] == [
        Message("user", "Opponent played f3."),
        Message("assistant", move("e5")),
        Message("user", "Opponent played g4."),
    ]
    turns = "".join(message.content for prompt in (white_second, black_second) for message in prompt[1:])
    assert "PGN" not in turns and "FEN" not in turns and "/" not in turns  # only moves, never a PGN or a FEN


@pytest.mark.parametrize("llm_constraints", EVERY_LLM_CONSTRAINTS)
def test_under_listed_each_turn_adds_the_legal_move_list_and_otherwise_it_doesnt(tmp_path, llm_constraints):
    side = LlmSide(llm_constraints=llm_constraints, turn_memory="chat_moves")

    players = faceoff(tmp_path, side, side, ["f3", "g4"], ["e5", "Qh4#"])

    *_, second = players["black"].prompts
    turns = [message.content for message in second if message.role == "user"]
    if llm_constraints in LISTED:
        assert [turn.split("\n")[0] for turn in turns] == ["Opponent played f3.", "Opponent played g4."]
        assert all(re.fullmatch(r"Opponent played \w+\.\nLegal moves: (\S+ )+\S+", turn) for turn in turns)
        assert "Legal moves:" in second[0].content  # the System prompt's worked example has it too
    else:
        assert turns == ["Opponent played f3.", "Opponent played g4."]
        assert "Legal moves" not in second[0].content


@pytest.mark.parametrize("turn_memory", EVERY_TURN_MEMORY)
@pytest.mark.parametrize("llm_constraints", EVERY_LLM_CONSTRAINTS)
def test_the_system_prompt_file_is_chosen_by_the_llm_constraints_and_the_turn_memory(llm_constraints, turn_memory):
    side = LlmSide(llm_constraints=llm_constraints, turn_memory=turn_memory)
    names = {
        (False, False): "system.txt",
        (True, False): "system_listed.txt",
        (False, True): "system_moves.txt",
        (True, True): "system_moves_listed.txt",
    }
    expected = f"{PROMPTS}/{names[llm_constraints in LISTED, turn_memory == 'chat_moves']}"

    template = side_template(side)

    file = prompt_file(template, llm_constraints)
    assert file is not None and file.as_posix().endswith(expected)
    assert template.system_prompt == file.read_text(encoding="utf-8")
    check_prompt_template(template, llm_constraints, turn_memory)  # it fits the side it is the default of


def test_the_moves_system_prompts_say_the_llm_keeps_track_of_the_board_with_a_short_exchange_as_example():
    white = side_template(LlmSide(turn_memory="chat_moves"))
    black_listed = side_template(LlmSide(llm_constraints="listed", turn_memory="chat_moves"))
    assert MOVES_SYSTEM_PROMPT_FILES["free"] != SYSTEM_PROMPT_FILES["free"]

    as_white = fill_system_prompt(white.system_prompt, "white")
    as_black = fill_system_prompt(black_listed.system_prompt, "black")

    for text in (as_white, as_black):
        assert "standard starting position" in text and "Keep track of the board yourself" in text
        assert "FEN" not in text and "PGN" not in text
    assert as_white.endswith(
        'Example:\nYou play White. Make the first move.\nAnswer: {"move": "e4"}\n'
        'Opponent played e5.\nAnswer: {"move": "Nf3"}\n'
    )
    example = as_black.split("Example:\n")[1].split("\n")
    assert example[0] == "Opponent played e4."
    assert example[1].startswith("Legal moves: ") and "e5" in example[1].split()
    assert example[2:4] == ['Answer: {"move": "e5"}', "Opponent played Nf3."]
    assert example[4].startswith("Legal moves: ") and "Nc6" in example[4].split()
    assert example[5] == 'Answer: {"move": "Nc6"}'


def test_the_moves_templates_are_two_more_defaults_that_fit_only_chat_with_moves():
    moves, listed = default_template("free", "moves"), default_template("listed", "moves")

    assert (moves.name, listed.name) == ("Moves", "Moves listed")
    assert re.fullmatch("moves@[0-9a-f]{8}", moves.id) and re.fullmatch("moves-listed@[0-9a-f]{8}", listed.id)
    assert (moves.turn_template, listed.turn_template) == ("$opponent_played", "$opponent_played\nLegal moves: $legal_moves")
    for memory in ("fresh", "chat_position"):
        with pytest.raises(InvalidSettings, match=r"\$opponent_played"):
            check_prompt_template(moves, "free", memory)
    with pytest.raises(InvalidSettings, match="chat_moves"):
        check_prompt_template(default_template("free", "described"), "free", "chat_moves")


def test_a_counterpart_asked_fresh_never_gets_a_template_that_shows_no_position():
    counterpart = counterpart_template(default_template("listed", "moves"))

    assert counterpart == default_template("listed_enforced")


def test_a_faceoff_batch_plays_chat_with_moves_as_its_own_player_configuration(tmp_path, capsys):
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])

    code = faceoff_batch(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "1", "--turn-memory", "chat_moves", "--games-dir",
         str(tmp_path), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0, capsys.readouterr().err
    start, *_ = events(tmp_path)
    assert start["white"]["turn_memory"] == start["black"]["turn_memory"] == "chat_moves"
    assert start["prompt_files"]["white"].endswith("system_moves.txt")
    assert start["white"]["prompt_template"]["turn_template"] == "$opponent_played"
    assert [prompt[-1].content for prompt in player.prompts] == [
        "You play White. Make the first move.", "Opponent played f3.", "Opponent played e5.", "Opponent played g4."
    ]
    configuration = llm_configuration(start, "white", start["white"])
    assert (configuration.prompt, configuration.turn_memory) == ("system_moves.txt", "chat_moves")
    assert configuration.position == "moves"  # it showed no FEN, only the opponent's moves
    assert configuration == settings_configuration(player.built_for[0], "white")
    chat_position = llm_configuration(start, "white", start["white"] | {"turn_memory": "chat_position"})
    assert configuration.id() != chat_position.id()


def test_an_anchor_match_plays_chat_with_moves_under_listed(tmp_path):
    player = ScriptedPlayer(["e5", "Qh4#"])

    code = anchor_match(
        ["--model", "llama3:8b", "--color", "black", "--turn-memory", "chat_moves", "--llm-constraints", "listed",
         "--games-dir", str(tmp_path)],
        player_for=player.for_settings,
        anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    start, *_ = events(tmp_path)
    assert start["black"]["turn_memory"] == "chat_moves"
    assert start["prompt_file"].endswith("system_moves_listed.txt")
    first, second = player.prompts
    assert first[1].content.startswith("Opponent played f3.\nLegal moves: ")
    assert [message.role for message in second] == ["system", "user", "assistant", "user"]
    assert second[3].content.startswith("Opponent played g4.\nLegal moves: ")


def test_an_anchor_batch_plays_chat_with_moves(tmp_path, capsys):
    player = ScriptedPlayer(["f3", "g4"])

    code = anchor_batch(
        ["--model", "llama3:8b", "--games", "1", "--turn-memory", "chat_moves", "--games-dir", str(tmp_path),
         "--no-analysis"],
        player_for=player.for_settings,
        anchor_for=lambda side: ScriptedAnchor(["e5", "Qh4#"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0, capsys.readouterr().err
    start, *_ = events(tmp_path)
    assert start["white"]["turn_memory"] == "chat_moves"
    assert start["prompt_file"].endswith("system_moves.txt")
    first, second = player.prompts
    assert [message.content for message in second[1:]] == [
        "You play White. Make the first move.", move("f3"), "Opponent played e5."
    ]
    assert first == second[:2]


def test_a_batch_with_chat_with_moves_refuses_a_template_that_shows_the_position(tmp_path, capsys):
    code = faceoff_batch(
        ["--models", "gemma3:12b", "llama3:8b", "--turn-memory", "chat_moves", "--prompt-template", "described",
         "--games-dir", str(tmp_path)],
        player_for=ScriptedPlayer([]).for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code != 0
    assert "chat_moves" in capsys.readouterr().err
