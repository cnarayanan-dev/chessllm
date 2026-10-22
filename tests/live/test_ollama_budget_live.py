"""Live test of the Thinking budget against real Ollama models: a budgeted move of qwen3.8 and of gemma4:26b under
Listed enforced is forced to answer, and the forced answer is still held to the legal moves (ADR 0007). Both take the
same chat route; gemma4's renderer answers in a new model turn (docs/research/thinking-budget.md).

Excluded from the default run; run it with `pytest -m ollama`. Skipped when no Ollama server is reachable, and per
model when it isn't installed."""

import chess
import ollama
import pytest

from chessllm.llm.models import LLM_MODELS
from chessllm.llm.ollama_player import OllamaPlayer, time_limit_s
from chessllm.llm.players import MoveAnswer
from chessllm.game.prompt import LISTED_SYSTEM_PROMPT_FILE, turn_messages

pytestmark = pytest.mark.ollama

# White's sixth move in an Italian Game (docs/research/board-images-positions.json #1): 33 legal moves, so both
# models think for far longer than the budget.
FEN = "r1bqkb1r/ppp2ppp/3p1n2/n3p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 6"
PGN = "1. e4 e5 2. Nf3 Nc6 3. Bc4 d6 4. Ng1 Nf6 5. Nf3 Na5"
BUDGET = 128  # small, so the budget binds


@pytest.fixture(scope="module")
def installed() -> list[str]:
    try:
        return [model.model for model in ollama.Client(timeout=2).list().models]
    except Exception as error:
        pytest.skip(f"no Ollama server reachable: {error}")


@pytest.mark.parametrize("model", ["qwen3.8:latest", "gemma4:26b"])
def test_a_budgeted_listed_enforced_move_is_forced_and_from_the_list(installed, model):
    if model not in installed:
        pytest.skip(f"{model} is not installed in Ollama")
    board = chess.Board(FEN)
    allowed = [board.san(move) for move in board.legal_moves]
    messages = turn_messages(PGN, FEN, "white", LISTED_SYSTEM_PROMPT_FILE, " ".join(allowed))
    speed = next(llm.tokens_per_s for llm in LLM_MODELS if llm.name == model)
    player = OllamaPlayer(model, thinking=True, timeout_s=time_limit_s(BUDGET, speed), budget=BUDGET)

    reply = player.reply(messages, allowed)

    assert reply.forced is True
    assert reply.thinking_tokens == BUDGET and reply.stop_reason == "stop"
    assert MoveAnswer.model_validate_json(reply.raw).move in allowed
