"""The Chaos move report: under Chaos rules, in a conversation kept by Turn memory, a side's turn opens with what each
chaos move since its last turn did, its own and its opponent's, in the resolver's words (ADR 0006). Legal moves get
none, and so does a fresh turn, whose position already shows the board. The report is part of the turn's message,
so it is recorded and rebuilt like the rest (ADR 0009)."""

import threading

import chess
import pytest

from tests.conftest import ScriptedPlayer
from tests.fakes import FakeClock

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import full_prompt
from chessllm.game.llm_turn.prompt import chaos_move_report, side_template
from chessllm.game.llm_turn.turn import LlmTurns
from chessllm.game.records import GameState, Ply, Resolution
from chessllm.game.rules import CHAOS, STANDARD, Rules
from chessllm.game.runner import play_anchor_match
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide, TurnMemory
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.players import Message
from chessllm.logs.game_log import GameLog

CHAT_MOVES = LlmSide(turn_memory="chat_moves")
CHAT_POSITION = LlmSide(turn_memory="chat_position")
FRESH = LlmSide()


def faceoff(tmp_path, white: LlmSide, black: LlmSide, white_moves, black_moves, rules="chaos"):
    """Play an LLM faceoff to its end, unattended, without Legal counterparts, so that every scripted reply is a
    turn's. Returns its last state and each side's player, which keeps the Prompts it got."""
    settings = Settings("llm_faceoff", white, black, rules=rules, legal_counterpart=False)
    settings.check(LLM_MODELS)
    players = {"white": ScriptedPlayer(white_moves), "black": ScriptedPlayer(black_moves)}
    log = GameLog(tmp_path / "games", *settings.side_names())
    state = play_anchor_match(settings, {color: player for color, player in players.items()}, {}, log)
    return state, players


def turn_messages(player: ScriptedPlayer) -> list[str]:
    """The message that opened each of the side's turns: the last user message of the turn's first Prompt."""
    return [[message for message in prompt if message.role == "user"][-1].content for prompt in player.prompts]


def side_prompts(state: GameState, color: Color) -> list[list[Message]]:
    """The whole Prompt of every attempt of a side, rebuilt from the state's records."""
    return [
        [Message(message.role, message.content) for message in full_prompt(state.llm_turns, turn.ply, number)]
        for turn in state.llm_turns
        if turn.color == color
        for number in range(1, len(turn.attempts) + 1)
    ]


def test_after_its_own_chaos_move_a_sides_next_turn_opens_with_the_report(tmp_path):
    # 1. Bd3 is no legal move (e2 is in the way): the bishop on f1 is played to d3 anyway.
    state, players = faceoff(tmp_path, CHAT_MOVES, FRESH, ["Bd3", "Nf3"], ["e5", "Qh4"])

    _, second, *_ = turn_messages(players["white"])
    assert second == "Your Bd3 was played as: bishop f1→d3 (the bishop on f1 moves).\nOpponent played e5."
    assert state.plies[0].resolution is not None and state.plies[0].resolution.kind == "chaos"


def test_after_a_spawn_the_report_says_the_piece_spawned(tmp_path):
    # 1. f3 e5 2. Qxf7+?? (chaos: the queen on d1 to f7) Kxf7 3. Qh5+ spawns a queen, as White has none left.
    _, players = faceoff(tmp_path, CHAT_MOVES, FRESH, ["f3", "Qxf7", "Qh5", "Nh3"], ["e5", "Kxf7", "Ke7", "Ke6"])

    _, second, third, fourth, *_ = turn_messages(players["white"])
    assert second == "Opponent played e5."
    assert third == (
        "Your Qxf7 was played as: queen d1→f7 (no queen can reach f7 by its movement; d1 is nearest).\n"
        "Opponent played Kxf7."
    )
    assert fourth == "Your Qh5 was played as: queen spawned on h5.\nOpponent played Ke7."


def test_the_opponent_llms_chaos_move_is_reported_to_the_other_side(tmp_path):
    # 1. e4 Qh4 (the e7 pawn is in the way: the queen on d8 is played to h4 anyway) 2. Qxf7+?? (chaos) Kxf7.
    state, players = faceoff(tmp_path, CHAT_POSITION, CHAT_MOVES, ["e4", "Qxf7", "Nf3"], ["Qh4", "Kxf7"])

    _, white_second, _ = turn_messages(players["white"])
    assert white_second.startswith("Opponent played Qh4 as: queen d8→h4 (the queen on d8 moves).\nPGN: 1. e4 Qh4\n")
    black_first, black_second, black_third = turn_messages(players["black"])
    assert black_first == "Opponent played e4."
    assert black_second == (
        "Your Qh4 was played as: queen d8→h4 (the queen on d8 moves).\n"
        "Opponent played Qxf7 as: queen d1→f7 (no queen can reach f7 by its movement; d1 is nearest)."
    )  # under chat_moves the report line says the opponent's chaos move, in place of "Opponent played Qxf7."
    assert black_third == "Opponent played Nf3."  # Kxf7 was legal
    # It is part of the turn's message, recorded only once and rebuilt with the rest of the conversation.
    assert side_prompts(state, "black") == players["black"].prompts
    assert side_prompts(state, "white") == players["white"].prompts
    [added] = [turn for turn in state.llm_turns if turn.ply == 4][0].attempts[0].prompt or []
    assert added.content == black_second


@pytest.mark.parametrize("turn_memory", ["chat_position", "chat_moves"])
def test_legal_moves_get_no_report(tmp_path, turn_memory: TurnMemory):
    side = LlmSide(turn_memory=turn_memory)

    _, players = faceoff(tmp_path, side, side, ["f3", "g4"], ["e5", "Qh4#"])

    messages = turn_messages(players["white"]) + turn_messages(players["black"])
    assert not any("was played as" in message or " as: " in message for message in messages)


@pytest.mark.parametrize("rules", [STANDARD, CHAOS])
def test_only_chaos_rules_give_a_report(tmp_path, rules: Rules):
    # Standard rules never play a chaos move, so a turn is given one here as if they had.
    side = LlmSide(turn_memory="chat_moves")
    player = ScriptedPlayer(["e5"])
    log = GameLog(tmp_path / "games", "llama3:8b", "llama3:8b")
    turns = LlmTurns("black", side, side_template(side), player, rules, 5, log, threading.Event(), FakeClock())
    board = chess.Board("rnbqkbnr/pppppppp/8/8/8/3B4/PPPPPPPP/RNBQK1NR b KQkq - 1 1")  # after 1. Bd3, as chaos
    chaos = ply(1, "white", "Bd3", chess.STARTING_FEN, kind="chaos", **{"from": "f1"}, to="d3", piece="B", rook=None,
                reason="the bishop on f1 moves")

    turns.play(board, [chaos], started=1000.0)

    [prompt] = player.prompts
    reported = "Opponent played Bd3 as: bishop f1→d3 (the bishop on f1 moves)."
    assert prompt[-1].content == (reported if rules is CHAOS else "Opponent played Bd3.")


def test_a_fresh_turn_gets_no_report(tmp_path):
    _, players = faceoff(tmp_path, FRESH, FRESH, ["Bd3", "Nf3"], ["Qh4", "e5"])

    assert not any(" as: " in message.content for prompt in players["white"].prompts for message in prompt)
    assert not any(" as: " in message.content for prompt in players["black"].prompts for message in prompt)


def ply(number: int, color: Color, written: str, fen_before: str, **resolution) -> Ply:
    return Ply(
        ply=number, color=color, move="", written=written, fen_before=fen_before, fen_after="", check=False,
        time_s=0.0, resolution=Resolution.model_validate(resolution) if resolution else None,
    )


def test_a_pawn_that_becomes_another_piece_and_a_castle_are_reported_as_the_board_saw_them():
    pawn_on_e7 = "4k3/4P3/8/8/8/8/8/4K2R w K - 0 1"
    promotion = ply(1, "white", "e8", pawn_on_e7, kind="chaos", **{"from": "e7"}, to="e8", piece="Q", rook=None,
                    reason="the pawn on e7 moves")
    castle = ply(2, "black", "O-O", "4k2r/8/8/8/8/8/8/4K3 b - - 0 1", kind="chaos", **{"from": "e8"}, to="g8",
                 piece="k", rook=["h8", "f8"], reason="illegal O-O: king e8→g8, rook h8→f8")

    assert chaos_move_report([promotion, castle], "white") == (
        "Your e8 was played as: pawn e7→e8, becoming a queen (the pawn on e7 moves).\n"
        "Opponent played O-O as: king e8→g8 (illegal O-O: king e8→g8, rook h8→f8)."
    )
    assert chaos_move_report([ply(1, "white", "e4", pawn_on_e7)], "black") is None
