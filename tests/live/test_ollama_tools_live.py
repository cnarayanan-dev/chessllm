"""Live test of the tool loop against a real Ollama model (ADR 0011): a thinking Qwen 3.5 with all four Tools, under
Blind enforced, may call them through Ollama's native tool calling, and its forced answer is still held to the legal
moves.

Excluded from the default run; run it with `pytest -m ollama`. Skipped when no Ollama server is reachable, or the
model isn't installed."""

import chess
import ollama
import pytest

from chessllm.game.llm_turn.prompt import TurnPosition, default_template, fresh_prompt
from chessllm.game.sides import ALL_TOOLS
from chessllm.game.tools import TOOLS, ToolPosition, bound_tools
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.llm.players import MoveAnswer

pytestmark = pytest.mark.ollama

MODEL = "qwen3.5:9b"
MOVES = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6"]
CAP = 4


def test_a_move_with_tools_calls_them_natively_and_is_forced_from_the_legal_moves():
    try:
        installed = [model.model for model in ollama.Client(timeout=2).list().models]
    except Exception as error:
        pytest.skip(f"no Ollama server reachable: {error}")
    if MODEL not in installed:
        pytest.skip(f"{MODEL} is not installed in Ollama")
    board = chess.Board()
    for san in MOVES:
        board.push_san(san)
    allowed = [board.san(move) for move in board.legal_moves]
    messages = fresh_prompt(default_template("blind_enforced", "tools"), "white", TurnPosition(board, MOVES))
    player = OllamaPlayer(MODEL, thinking=True, tool_call_cap=CAP)

    reply = player.reply(messages, allowed, bound_tools(ALL_TOOLS, ToolPosition(board, MOVES, "white")))

    assert MoveAnswer.model_validate_json(reply.raw).move in allowed
    assert len(reply.tool_calls) <= CAP
    assert all(call.tool in TOOLS for call in reply.tool_calls)
