"""Live test of the Thinking budget against a real Ollama model: a budgeted qwen3.8 move under Listed enforced is
forced to answer, and the forced answer is still held to the legal moves (ADR 0007).

Excluded from the default run; run it with `pytest -m ollama`. Skipped when no Ollama server is reachable or
qwen3.8:latest isn't installed. gemma4:26b's live test follows in its own ticket (#73)."""

import chess
import ollama
import pytest

from chessllm.models import LLM_MODELS
from chessllm.ollama_player import OllamaPlayer, time_limit_s
from chessllm.players import MoveAnswer
from chessllm.prompt import LISTED_SYSTEM_PROMPT_FILE, turn_messages

pytestmark = pytest.mark.ollama

MODEL = "qwen3.8:latest"
# White's sixth move in an Italian Game (docs/research/board-images-positions.json #1): 33 legal moves, so qwen3.8
# thinks for far longer than the budget.
FEN = "r1bqkb1r/ppp2ppp/3p1n2/n3p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 6"
PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 d6 4. Ng1 Nf6 5. Nf3 Na5"
BUDGET = 128  # small, so the budget binds


@pytest.fixture(scope="module", autouse=True)
def ollama_server():
    try:
        installed = [model.model for model in ollama.Client(timeout=2).list().models]
    except Exception as error:
        pytest.skip(f"no Ollama server reachable: {error}")
    if MODEL not in installed:
        pytest.skip(f"{MODEL} is not installed in Ollama")


def test_a_budgeted_listed_enforced_move_is_forced_and_from_the_list():
    board = chess.Board(FEN)
    allowed = [board.san(move) for move in board.legal_moves]
    messages = turn_messages(PGN, FEN, "white", LISTED_SYSTEM_PROMPT_FILE, " ".join(allowed))
    speed = next(model.tokens_per_s for model in LLM_MODELS if model.name == MODEL)
    player = OllamaPlayer(MODEL, thinking=True, timeout_s=time_limit_s(BUDGET, speed), budget=BUDGET)

    reply = player.reply(messages, allowed)

    assert reply.forced is True
    assert reply.thinking_tokens == BUDGET and reply.stop_reason == "stop"
    assert MoveAnswer.model_validate_json(reply.raw).move in allowed
