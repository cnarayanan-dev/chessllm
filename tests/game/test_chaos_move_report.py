"""The Chaos move report: under Chaos rules, in a conversation kept by Turn memory, a side's turn opens with what each
Chaos move since its last turn did, its own and its opponent's, in the resolver's words. Legal moves get none, and
neither does a fresh turn, whose position already shows the board. The report is part of the turn's message, so it is
recorded and rebuilt like the rest of it (ADR 0009)."""

import pytest

from tests.conftest import ScriptedPlayer
from tests.game.test_turn_memory import START, events, side_prompts

from chessllm.core.types import Color, RulesKey
from chessllm.game.records import GameState
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.logs.game_log import GameLog
from chessllm.logs.llm_turns import logged_llm_turns

LLAMA_CHAT = LlmSide(model="llama3:8b", turn_memory="chat_position")
LLAMA_MOVES = LlmSide(model="llama3:8b", turn_memory="chat_moves")


def play(
    tmp_path, white: LlmSide, black: LlmSide, replies: dict[Color, list[str]], plies: int, rules: RulesKey = "chaos"
) -> tuple[GameSession, dict[Color, ScriptedPlayer]]:
    """Play the first plies of an LLM faceoff, each side's scripted replies one per turn, without Legal counterparts
    so that every reply is a turn's."""
    players = {color: ScriptedPlayer(moves) for color, moves in replies.items()}
    settings = Settings("llm_faceoff", white, black, rules=rules, legal_counterpart=False)
    settings.check(LLM_MODELS)
    game = GameSession(players, settings, GameLog(tmp_path / "games", *settings.side_names()))
    for _ in range(plies):
        game.play_llm_turn()
    return game, players


def openings(player: ScriptedPlayer) -> list[str]:
    """The message that opened each of a side's turns, as sent: the last of each Prompt."""
    return [prompt[-1].content for prompt in player.prompts]


def test_after_its_own_chaos_move_a_sides_next_turn_opens_with_the_report(tmp_path):
    # The queen jumps over the e2 pawn to h5, is taken, and comes back from nowhere.
    _, players = play(
        tmp_path, LLAMA_CHAT, LlmSide(), {"white": ["Qh5", "a3", "Qd5", "g3"], "black": ["Nf6", "Nxh5", "a6"]}, 7
    )

    first, second, third, fourth = openings(players["white"])
    assert first == f"PGN: (no moves yet)\n{START}"
    assert second.startswith("Your Qh5 was played as: queen d1→h5 (the queen on d1 moves).\nPGN: 1. Qh5 Nf6\n")
    assert third.startswith("PGN: ")  # a3 and Nxh5 are legal: no report
    assert fourth.startswith("Your Qd5 was played as: queen spawned on d5.\nPGN: ")


def test_a_chaos_promotion_is_reported_as_the_pawn_that_moved_and_what_it_became(tmp_path):
    # The a2 pawn jumps to a8, takes the rook and becomes a queen.
    _, players = play(tmp_path, LLAMA_CHAT, LlmSide(), {"white": ["a8", "e3"], "black": ["e5"]}, 3)

    assert openings(players["white"])[1].startswith(
        "Your a8 was played as: pawn a2→a8, promoted to a queen "
        "(no pawn can reach a8 by its movement; a2 is nearest; tie broken a1→h8).\n"
    )


@pytest.mark.parametrize("memory", [LLAMA_CHAT, LLAMA_MOVES])
def test_in_a_faceoff_the_opponents_chaos_move_is_reported_to_the_other_side(tmp_path, memory):
    _, players = play(tmp_path, memory, memory, {"white": ["e4", "Nf3", "a3"], "black": ["Bc5", "a6"]}, 5)

    white, black = openings(players["white"]), openings(players["black"])
    assert white[1].startswith("Opponent played Bc5 as: bishop f8→c5 (the bishop on f8 moves).\n")
    assert black[1].startswith("Your Bc5 was played as: bishop f8→c5 (the bishop on f8 moves).\n")
    assert " as: " not in white[2] + black[0]


def test_the_report_is_recorded_and_the_rebuilt_prompt_is_what_the_llm_received(tmp_path):
    game, players = play(tmp_path, LLAMA_CHAT, LLAMA_MOVES, {"white": ["e4", "Nf3", "a3"], "black": ["Bc5", "a6"]}, 5)

    state = game.state()
    logged = GameState.model_construct(llm_turns=logged_llm_turns(events(tmp_path / "games")))
    for rebuilt_from in (state, logged):
        assert side_prompts(rebuilt_from, "white") == players["white"].prompts
        assert side_prompts(rebuilt_from, "black") == players["black"].prompts
    [message] = state.llm_turns[2].attempts[0].prompt or []
    assert message.content.startswith("Opponent played Bc5 as: ")


def test_a_fresh_turn_gets_no_report(tmp_path):
    _, players = play(tmp_path, LlmSide(), LlmSide(), {"white": ["e4", "Nf3"], "black": ["Bc5"]}, 3)

    assert not [opening for opening in openings(players["white"]) if " as: " in opening]


def test_there_is_no_report_under_standard_rules(tmp_path):
    _, players = play(
        tmp_path, LLAMA_CHAT, LLAMA_CHAT, {"white": ["e4", "Nf3"], "black": ["Bc5", "e5"]}, 3, rules="standard"
    )

    assert not [prompt for prompt in players["white"].prompts + players["black"].prompts if " as: " in str(prompt)]
