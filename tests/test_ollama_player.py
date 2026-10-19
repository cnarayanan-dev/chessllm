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


def test_with_thinking_off_the_adapter_asks_for_the_reasoning_before_the_move():
    calls = []

    def chat(**request):
        calls.append(request)
        message = OllamaMessage(role="assistant", content='{"reasoning": "Mirror the centre pawn.", "move": "e5"}')
        return ChatResponse(message=message)

    player = OllamaPlayer("qwen3.5:9b", thinking=False, chat=chat)

    reply = player.reply([Message("user", "PGN: 1. e4")])

    assert reply.raw == '{"reasoning": "Mirror the centre pawn.", "move": "e5"}'
    assert reply.thinking is None
    [request] = calls
    assert request["model"] == "qwen3.5:9b"
    assert request["think"] is False
    schema = request["format"]
    assert list(schema["properties"]) == ["reasoning", "move"]
    assert schema["required"] == ["reasoning", "move"]
    assert schema["properties"]["reasoning"]["type"] == "string"
    assert schema["properties"]["move"]["type"] == "string"
    assert "enum" not in schema["properties"]["move"]


@pytest.mark.parametrize("thinking", [True, False])
def test_the_adapter_gives_up_after_the_time_limit(thinking):
    def chat(**request):
        raise httpx.ReadTimeout("timed out")

    player = OllamaPlayer("qwen3.5:9b", thinking=thinking, chat=chat, timeout_s=180)

    with pytest.raises(LlmTimeout) as raised:
        player.reply([Message("user", "PGN: 1. e4")])
    assert raised.value.timeout_s == 180


def test_the_default_time_limit_is_five_minutes():
    assert OllamaPlayer("qwen3.5:9b", chat=lambda **request: None).timeout_s == 300


def test_the_adapter_sends_the_sampling_options():
    calls = []

    def chat(**request):
        calls.append(request)
        return ChatResponse(message=OllamaMessage(role="assistant", content='{"move": "e5"}'))

    OllamaPlayer("qwen3.5:9b", chat=chat, sampling={"temperature": 0.2}).reply([Message("user", "PGN: 1. e4")])
    OllamaPlayer("qwen3.5:9b", chat=chat).reply([Message("user", "PGN: 1. e4")])

    assert [request["options"] for request in calls] == [{"temperature": 0.2}, None]


@pytest.mark.parametrize("thinking", [True, False])
def test_enforced_decoding_puts_the_allowed_moves_as_an_enum_on_the_move_only(thinking):
    calls = []

    def chat(**request):
        calls.append(request)
        return ChatResponse(message=OllamaMessage(role="assistant", content='{"move": "e5"}'))

    player = OllamaPlayer("qwen3.5:9b", thinking=thinking, chat=chat)

    player.reply([Message("user", "PGN: 1. e4")], allowed_moves=["e5", "Nf6", "O-O"])

    [request] = calls
    properties = request["format"]["properties"]
    assert properties["move"] == {"title": "Move", "type": "string", "enum": ["e5", "Nf6", "O-O"]}
    if thinking:
        assert list(properties) == ["move"]
    else:
        assert properties["reasoning"] == {"title": "Reasoning", "type": "string"}
        assert list(properties) == ["reasoning", "move"]
