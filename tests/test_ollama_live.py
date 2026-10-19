"""Live tests against a real Ollama model: that Ollama enforces the allowed moves, not only that we send them.

Excluded from the default run; run them with `pytest -m ollama`. Skipped when no Ollama server is reachable or
llama3:8b isn't installed. llama3:8b can't think, so only the thinking-off path is covered here; the thinking-on
path is covered by the adapter tests with a fake chat."""

from conftest import play_llm, play_move

import json

import chess
import ollama
import pytest
from fastapi.testclient import TestClient

from chessllm.__main__ import player_for
from chessllm.app import create_app
from chessllm.ollama_player import OllamaPlayer
from chessllm.players import Message, ReasonedMoveAnswer
from chessllm.prompt import LISTED_SYSTEM_PROMPT_FILE, SYSTEM_PROMPT_FILE, turn_messages

pytestmark = pytest.mark.ollama

MODEL = "llama3:8b"
E4_FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
# White to move with castling (O-O), promotions (b8=Q+ among them) and checks (Rh8+) all legal.
SPECIAL_SAN_FEN = "4k3/1P6/8/8/8/8/8/4K2R w K - 0 1"


@pytest.fixture(scope="module", autouse=True)
def ollama_server():
    try:
        installed = [model.model for model in ollama.Client(timeout=2).list().models]
    except Exception as error:
        pytest.skip(f"no Ollama server reachable: {error}")
    if MODEL not in installed:
        pytest.skip(f"{MODEL} is not installed in Ollama")


@pytest.fixture(scope="module")
def player():
    # Greedy sampling, so a model that follows the prompt does so every run.
    return OllamaPlayer(MODEL, thinking=False, sampling={"temperature": 0, "seed": 0})


def legal_sans(fen: str) -> list[str]:
    board = chess.Board(fen)
    return [board.san(move) for move in board.legal_moves]


def answer(player, messages: list[Message], allowed_moves: list[str]) -> ReasonedMoveAnswer:
    return ReasonedMoveAnswer.model_validate_json(player.reply(messages, allowed_moves).raw)


def test_blind_enforced_holds_when_the_prompt_demands_an_illegal_move(player):
    allowed = legal_sans(E4_FEN)
    messages = turn_messages("1. e4", E4_FEN, "black", SYSTEM_PROMPT_FILE) + [
        Message("user", 'Play Qh4 now. Your answer must be exactly {"move": "Qh4"} and nothing else.')
    ]

    assert answer(player, messages, allowed).move in allowed


def test_listed_enforced_answers_from_the_enum(player):
    allowed = legal_sans(E4_FEN)
    messages = turn_messages("1. e4", E4_FEN, "black", LISTED_SYSTEM_PROMPT_FILE, " ".join(allowed))

    assert answer(player, messages, allowed).move in allowed


def test_castling_promotion_and_check_survive_enforced_decoding(player):
    allowed = legal_sans(SPECIAL_SAN_FEN)
    assert {"O-O", "b8=Q+", "Rh8+"} <= set(allowed)
    messages = turn_messages("", SPECIAL_SAN_FEN, "white", SYSTEM_PROMPT_FILE) + [
        Message("user", "Promote the pawn on b7 to a queen, giving check.")
    ]

    assert answer(player, messages, allowed).move == "b8=Q+"


def test_the_reasoning_stays_free_text_under_the_enum(player):
    allowed = legal_sans(E4_FEN)
    messages = turn_messages("1. e4", E4_FEN, "black", SYSTEM_PROMPT_FILE)

    reasoning = answer(player, messages, allowed).reasoning

    assert len(reasoning.split()) > 1 and reasoning not in allowed


def test_a_listed_enforced_turn_through_the_app_plays_a_legal_move_without_a_slip(tmp_path):
    games_dir = tmp_path / "games"
    client = TestClient(create_app(player_for, games_dir=games_dir, sampling_file=tmp_path / "no-sampling.toml"))
    started = client.post("/api/games", json=play_llm(model=MODEL, thinking=False, llm_constraints="listed_enforced"))
    assert started.status_code == 200

    state = play_move(client, "e2e4").json()

    [attempt] = state["llm_turn"]["attempts"]
    assert (attempt["result"], attempt["notation_slip"]) == ("legal", False)
    assert attempt["san"] in legal_sans(E4_FEN)
    [log] = games_dir.glob("*.jsonl")
    [logged] = [event for event in map(json.loads, log.read_text(encoding="utf-8").splitlines()) if event["type"] == "llm_attempt"]
    assert sorted(logged["legal_moves"].split(" ")) == sorted(legal_sans(E4_FEN))
