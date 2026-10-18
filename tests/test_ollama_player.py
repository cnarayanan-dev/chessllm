import httpx
import pytest
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from chessllm.ollama_player import OllamaPlayer
from chessllm.players import LlmReply, LlmTimeout, Message


def test_the_adapter_asks_ollama_with_thinking_on_and_the_free_move_schema():
    calls = []

    def chat(**request):
        calls.append(request)
        message = OllamaMessage(role="assistant", content='{"move": "e5"}', thinking="Mirror the centre pawn.")
        return ChatResponse(message=message)

    player = OllamaPlayer("qwen3.5:9b", chat=chat)

    reply = player.reply([Message("system", "Play chess."), Message("user", "PGN: 1. e4")])

    assert reply == LlmReply(raw='{"move": "e5"}', thinking="Mirror the centre pawn.", latency_s=reply.latency_s)
    assert reply.latency_s >= 0
    [request] = calls
    assert request["model"] == "qwen3.5:9b"
    assert request["think"] is True
    assert request["messages"] == [
        {"role": "system", "content": "Play chess."},
        {"role": "user", "content": "PGN: 1. e4"},
    ]
    schema = request["format"]
    assert schema["required"] == ["move"]
    assert schema["properties"]["move"]["type"] == "string"
    assert "enum" not in schema["properties"]["move"]


def test_the_adapter_gives_up_after_the_time_limit():
    def chat(**request):
        raise httpx.ReadTimeout("timed out")

    player = OllamaPlayer("qwen3.5:9b", chat=chat, timeout_s=180)

    with pytest.raises(LlmTimeout) as raised:
        player.reply([Message("user", "PGN: 1. e4")])
    assert raised.value.timeout_s == 180


def test_the_default_time_limit_is_five_minutes():
    assert OllamaPlayer("qwen3.5:9b", chat=lambda **request: None).timeout_s == 300
