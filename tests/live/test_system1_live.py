"""Live test of the /v1/systemone adapter against a real System 1 model server: that the request shape we send is the
one the server answers with a probability for every move.

Excluded from the default run; run it with `pytest -m system1`. The server is the operator's to start (Ollama with
`ollama pull d3:2b`, llama-server, or a publisher's server). It is found at CHESSLLM_SYSTEM1_URL (default Ollama's
http://localhost:11434) and the model is CHESSLLM_SYSTEM1_MODEL (default d3:2b); the test is skipped when the server
doesn't answer or doesn't have the model."""

import os

import chess
import pytest

from chessllm.exceptions import System1Unavailable
from chessllm.system1.http_model import SystemOneModel, missing_models

pytestmark = pytest.mark.system1

BASE_URL = os.environ.get("CHESSLLM_SYSTEM1_URL", "http://localhost:11434")
MODEL = os.environ.get("CHESSLLM_SYSTEM1_MODEL", "d3:2b")


@pytest.fixture(scope="module", autouse=True)
def system1_server():
    try:
        missing = missing_models(BASE_URL, [MODEL])
    except System1Unavailable as error:
        pytest.skip(str(error))
    if missing:
        pytest.skip(f"{MODEL} is not served at {BASE_URL}")


def test_the_server_gives_a_probability_for_every_legal_move_of_the_start_position():
    board = chess.Board()
    options = [board.san(move) for move in board.legal_moves]

    probabilities = SystemOneModel(BASE_URL, MODEL).decide(
        f"FEN: {board.fen()}", "Which move should White play?", options
    )

    assert len(probabilities) == len(options) == 20
    assert sum(probabilities) == pytest.approx(1.0)
    assert all(p >= 0 for p in probabilities)
