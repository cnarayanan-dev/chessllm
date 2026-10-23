"""Live test of Turn memory against a real Ollama model: the prompt tokens Ollama reports for each call of a short
game in one conversation agree with the conversation sent, so trimming can measure a conversation by them (#106).
They must count the whole conversation, not only what Ollama's prompt cache didn't hold.

Excluded from the default run; run it with `pytest -m ollama`. Skipped when no Ollama server is reachable or
llama3:8b isn't installed."""

import ollama
import pytest

from chessllm.game.llm_turn.conversation import CHARS_PER_TOKEN, characters
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.llm.players import LlmReply, Message
from chessllm.logs.game_log import GameLog

pytestmark = pytest.mark.ollama

MODEL = "llama3:8b"
PLIES = 8
# The most tokens a chat template may add around one message: its role header and end marker.
TEMPLATE_TOKENS_PER_MESSAGE = 10


@pytest.fixture(scope="module", autouse=True)
def ollama_server():
    try:
        installed = [model.model for model in ollama.Client(timeout=2).list().models]
    except Exception as error:
        pytest.skip(f"no Ollama server reachable: {error}")
    if MODEL not in installed:
        pytest.skip(f"{MODEL} is not installed in Ollama")


class Recording:
    """The real Ollama player, recording each call's messages and the prompt tokens Ollama reported for them."""

    def __init__(self, player: OllamaPlayer) -> None:
        self._player = player
        self.calls: list[tuple[list[Message], int | None]] = []

    def reply(self, messages: list[Message], allowed_moves: list[str] | None = None) -> LlmReply:
        reply = self._player.reply(messages, allowed_moves)
        self.calls.append((messages, reply.prompt_tokens))
        return reply


@pytest.mark.parametrize("turn_memory", ["chat_moves", "chat_position"])
def test_the_prompt_tokens_ollama_reports_agree_with_the_conversation_sent(tmp_path, turn_memory):
    side = LlmSide(model=MODEL, turn_memory=turn_memory)
    settings = Settings("llm_faceoff", side, LlmSide(model=MODEL))
    settings.check(LLM_MODELS)
    # Greedy sampling, so the game is the same every run.
    white = Recording(OllamaPlayer(MODEL, thinking=False, sampling={"temperature": 0, "seed": 0}))
    black = OllamaPlayer(MODEL, thinking=False, sampling={"temperature": 0, "seed": 0})
    game = GameSession({"white": white, "black": black}, settings, GameLog(tmp_path, *settings.side_names()))

    for _ in range(PLIES):
        if game.state().end_reason is not None:
            break
        game.play_llm_turn()

    assert len(white.calls) >= 3
    sizes = []
    for messages, reported in white.calls:
        assert reported is not None
        # Never more than the conservative estimate allows, template included, and the whole conversation, not
        # only its newest messages.
        estimate = characters(messages) / CHARS_PER_TOKEN
        assert reported <= estimate + TEMPLATE_TOKENS_PER_MESSAGE * len(messages)
        assert reported >= characters(messages) / 6
        sizes.append(reported)
    assert sizes == sorted(sizes)  # one conversation, growing turn by turn
