"""Turn memory chat_moves: an LLM side keeps one conversation for the game, each turn adding only the opponent's last
move, so the LLM keeps track of the board itself. Its default Prompt templates, Moves and Moves listed, have their own
System prompts, system_moves.txt and system_moves_listed.txt."""

import re
from dataclasses import replace
from pathlib import PurePath

import chess
import pytest

from tests.conftest import ScriptedAnchor, ScriptedPlayer
from tests.game.test_turn_memory import events, faceoff

from chessllm.analytics.leaderboard import llm_configuration, settings_configuration
from chessllm.cli.anchor_batch import main as anchor_batch
from chessllm.cli.faceoff_batch import main as faceoff_batch
from chessllm.core.config import PROMPTS_DIR
from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import default_template, side_template
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.settings import Settings
from chessllm.game.sides import HumanSide, LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message

LLAMA_MOVES = LlmSide(model="llama3:8b", turn_memory="chat_moves")
# A FEN's board, or a PGN's move number: neither is ever in a chat_moves conversation.
FEN_OR_PGN = re.compile(r"[1-8pnbrqkPNBRQK]{1,8}(/[1-8pnbrqkPNBRQK]{1,8}){7}|(^|\s)\d+\.|FEN|PGN")


def test_each_turn_adds_only_the_opponents_last_move_as_white_and_as_black(tmp_path):
    white, black = ScriptedPlayer(["f3", "g4"]), ScriptedPlayer(["e5", "Qh4#"])

    faceoff(tmp_path, LLAMA_MOVES, LLAMA_MOVES, {"white": white, "black": black})

    [first, second] = white.prompts
    assert first[1:] == [Message("user", "You play White. Make the first move.")]
    assert second[1:] == [
        Message("user", "You play White. Make the first move."),
        Message("assistant", '{"move": "f3"}'),
        Message("user", "Opponent played e5."),
    ]
    assert [prompt[-1].content for prompt in black.prompts] == ["Opponent played f3.", "Opponent played g4."]
    for prompt in white.prompts + black.prompts:
        assert prompt[0].role == "system"
        assert not [message.content for message in prompt if FEN_OR_PGN.search(message.content)]


@pytest.mark.parametrize(
    ("llm_constraints", "listed"),
    [("free", False), ("listed", True), ("blind_enforced", False), ("listed_enforced", True)],
)
def test_under_listed_each_turn_adds_the_legal_move_list_after_the_opponents_move(tmp_path, llm_constraints, listed):
    white, black = ScriptedPlayer(["f3", "g4"]), ScriptedPlayer(["e5", "Qh4#"])
    side = replace(LLAMA_MOVES, llm_constraints=llm_constraints)

    faceoff(tmp_path, side, side, {"white": white, "black": black})

    turns = [prompt[-1].content.splitlines() for prompt in white.prompts + black.prompts]
    assert [lines[0] for lines in turns] == [
        "You play White. Make the first move.", "Opponent played e5.", "Opponent played f3.", "Opponent played g4."
    ]
    if listed:
        assert [lines[1].split(": ")[0] for lines in turns] == ["Legal moves"] * 4
        start = chess.Board()
        assert sorted(turns[0][1].split(": ")[1].split()) == sorted(start.san(move) for move in start.legal_moves)
    else:
        assert [len(lines) for lines in turns] == [1] * 4


@pytest.mark.parametrize("turn_memory", ["fresh", "chat_position", "chat_moves"])
@pytest.mark.parametrize("llm_constraints", ["free", "listed", "blind_enforced", "listed_enforced"])
def test_the_system_prompt_file_is_chosen_by_the_llm_constraints_and_the_turn_memory(llm_constraints, turn_memory):
    side = LlmSide(llm_constraints=llm_constraints, turn_memory=turn_memory)
    settings = Settings("play_llm", HumanSide(), side)

    expected = {
        (False, False): "system.txt",
        (True, False): "system_listed.txt",
        (False, True): "system_moves.txt",
        (True, True): "system_moves_listed.txt",
    }[(llm_constraints in ("listed", "listed_enforced"), turn_memory == "chat_moves")]
    assert settings_configuration(settings, "black").prompt == expected
    assert side_template(side).system_prompt == (PROMPTS_DIR / expected).read_text(encoding="utf-8")


def test_the_moves_templates_are_left_out_of_the_librarys_list_but_resolve(tmp_path):
    library = PromptLibrary(tmp_path / "prompt_library")
    moves = default_template("listed", "moves")

    assert re.fullmatch("moves-listed@[0-9a-f]{8}", moves.id) and moves.name == "Moves listed"
    assert moves.id not in [entry.template.id for entry in library.entries()]
    assert library.template(moves.id) == moves


def test_both_batch_commands_play_chat_with_moves_and_log_its_prompt_file(tmp_path):
    player = ScriptedPlayer(["f3", "e5", "g4", "Qh4#"])

    code = faceoff_batch(
        ["--models", "gemma3:12b", "llama3:8b", "--games", "1", "--turn-memory", "chat_moves", "--games-dir",
         str(tmp_path / "faceoff"), "--no-analysis"],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    start, *_ = events(tmp_path / "faceoff")
    assert start["white"]["turn_memory"] == start["black"]["turn_memory"] == "chat_moves"
    assert [PurePath(file).name for file in start["prompt_files"].values()] == ["system_moves.txt"] * 2
    assert [prompt[-1].content for prompt in player.prompts] == [
        "You play White. Make the first move.", "Opponent played f3.", "Opponent played e5.", "Opponent played g4."
    ]
    configuration = llm_configuration(start, "white", start["white"])
    assert (configuration.prompt, configuration.turn_memory) == ("system_moves.txt", "chat_moves")

    llm = ScriptedPlayer(["f3", "g4"])
    code = anchor_batch(
        ["--games", "1", "--turn-memory", "chat_moves", "--llm-constraints", "listed", "--games-dir",
         str(tmp_path / "anchor"), "--no-analysis"],
        player_for=llm.for_settings,
        anchor_for=lambda side: ScriptedAnchor(["e5", "Qh4#"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    start, *_ = events(tmp_path / "anchor")
    assert start["white"]["turn_memory"] == "chat_moves"
    assert PurePath(start["prompt_file"]).name == "system_moves_listed.txt"
    assert [prompt[-1].content.splitlines()[0] for prompt in llm.prompts] == [
        "You play White. Make the first move.", "Opponent played e5."
    ]


@pytest.mark.parametrize(
    ("turn_memory", "kind"),
    [("chat_moves", "default"), ("chat_moves", "described"), ("fresh", "moves"), ("chat_position", "moves")],
)
def test_a_default_template_that_doesnt_fit_the_turn_memory_is_refused(turn_memory, kind):
    side = LlmSide(turn_memory=turn_memory, prompt_template=default_template("free", kind))

    with pytest.raises(InvalidSettings, match="Turn memory") as refused:
        Settings("play_llm", HumanSide(), side).check(LLM_MODELS)

    assert refused.value.code == "invalid_prompt_template"


def test_a_batch_command_refuses_chat_with_moves_under_the_described_template(tmp_path, capsys):
    code = faceoff_batch(
        ["--models", "gemma3:12b", "llama3:8b", "--turn-memory", "chat_moves", "--prompt-template", "described",
         "--games-dir", str(tmp_path)],
        player_for=ScriptedPlayer([]).for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code != 0
    assert "Turn memory chat_moves" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl"))
