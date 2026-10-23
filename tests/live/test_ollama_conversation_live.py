"""Live test of trimming a conversation to the context against a real Ollama model: the prompt_tokens Ollama reports
for a conversation agree with the conversation sent, so the trimmer can size it from them, and a conversation
trimmed to a context made small keeps every prompt Ollama counts within it. Played under Turn memory chat_moves.

Excluded from the default run; run it with `pytest -m ollama`. Skipped when no Ollama server is reachable or
llama3:8b isn't installed."""

from collections.abc import Callable

import ollama
import pytest

from chessllm.game.llm_turn import conversation
from chessllm.game.llm_turn.conversation import CHARS_PER_TOKEN, reply_reserve
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.llm.players import LlmReply, Message
from chessllm.logs.game_log import GameLog

pytestmark = pytest.mark.ollama

MODEL = "llama3:8b"
CHAT = LlmSide(model=MODEL, turn_memory="chat_moves")
PLIES = 10


@pytest.fixture(scope="module", autouse=True)
def ollama_server():
    try:
        installed = [model.model for model in ollama.Client(timeout=2).list().models]
    except Exception as error:
        pytest.skip(f"no Ollama server reachable: {error}")
    if MODEL not in installed:
        pytest.skip(f"{MODEL} is not installed in Ollama")


class Recording:
    """The Ollama player, recording each Prompt it sends and the reply."""

    def __init__(self) -> None:
        # Greedy sampling, so a run plays the same game every time.
        self._player = OllamaPlayer(MODEL, thinking=False, sampling={"temperature": 0, "seed": 0})
        self.calls: list[tuple[list[Message], LlmReply]] = []

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        reply = self._player.reply(messages, allowed_moves)
        self.calls.append((messages, reply))
        return reply


def play(tmp_path, after_first: Callable[[Recording], None] = lambda white: None) -> tuple[GameSession, Recording]:
    """A short game of a chat_moves llama3:8b as White against a fresh one; after_first is called with White once
    it has played its first turn."""
    settings = Settings("llm_faceoff", CHAT, LlmSide(model=MODEL))
    settings.check(LLM_MODELS)
    white = Recording()
    players = {"white": white, "black": Recording()}
    game = GameSession(players, settings, GameLog(tmp_path, *settings.side_names()))  # type: ignore[arg-type]
    for _ in range(PLIES):
        if game.state().result is not None:
            break
        game.play_llm_turn()
        if len(game.state().llm_turns) == 1:
            after_first(white)
    return game, white


def test_the_prompt_tokens_ollama_reports_agree_with_the_conversation_sent(tmp_path):
    _, white = play(tmp_path)

    reported = [reply.prompt_tokens or 0 for _, reply in white.calls]
    estimated = [sum(len(message.content) for message in sent) / CHARS_PER_TOKEN for sent, _ in white.calls]
    assert len(reported) >= 3
    # The whole conversation is counted, a prompt cached from the last call included, and never more than the
    # conservative estimate.
    assert all(estimate / 4 < tokens <= estimate for tokens, estimate in zip(reported, estimated))
    assert reported == sorted(reported) and len(set(reported)) == len(reported)  # it grows with every attempt


def test_a_conversation_trimmed_to_a_small_context_stays_within_it_as_ollama_counts_it(tmp_path, monkeypatch):
    reserve = reply_reserve(CHAT)
    context: list[int] = []

    def shrink(white: Recording) -> None:
        """A context with room for the first turn and about two more: later turns must drop the oldest."""
        [(_, first)] = white.calls
        context.append((first.prompt_tokens or 0) + reserve + 150)
        monkeypatch.setattr(conversation, "CONTEXT_TOKENS", context[0])

    game, white = play(tmp_path, shrink)

    turns = [turn for turn in game.state().llm_turns if turn.color == "white"]
    assert any(turn.remembered is not None and turn.remembered < number for number, turn in enumerate(turns))
    assert all((reply.prompt_tokens or 0) + reserve <= context[0] for _, reply in white.calls)
