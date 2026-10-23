import httpx
import pytest
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.llm.players import LlmReply, Message
from chessllm.exceptions import LlmTimeout


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


def test_the_adapter_sends_the_sampling_options_and_the_context_size():
    calls = []

    def chat(**request):
        calls.append(request)
        return ChatResponse(message=OllamaMessage(role="assistant", content='{"move": "e5"}'))

    OllamaPlayer("qwen3.5:9b", chat=chat, sampling={"temperature": 0.2}).reply([Message("user", "PGN: 1. e4")])
    OllamaPlayer("qwen3.5:9b", chat=chat).reply([Message("user", "PGN: 1. e4")])

    assert [request["options"] for request in calls] == [{"temperature": 0.2, "num_ctx": 8192}, {"num_ctx": 8192}]


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


def test_thinking_off_is_sent_as_off_for_a_model_that_thinks_by_default():
    # Gemma 4 thinks unless told not to, so off must be sent, not left out.
    calls = []

    def chat(**request):
        calls.append(request)
        message = OllamaMessage(role="assistant", content='{"reasoning": "Mirror the centre pawn.", "move": "e5"}')
        return ChatResponse(message=message)

    OllamaPlayer("gemma4:26b", thinking=False, chat=chat).reply([Message("user", "PGN: 1. e4")])

    [request] = calls
    assert request["model"] == "gemma4:26b"
    assert request["think"] is False


def test_a_thinking_level_is_sent_as_it_is_with_the_thinking_on_schema():
    calls = []

    def chat(**request):
        calls.append(request)
        return ChatResponse(message=OllamaMessage(role="assistant", content='{"move": "e5"}', thinking="Mirror it."))

    reply = OllamaPlayer("qwen3.8:latest", thinking="xhigh", chat=chat).reply([Message("user", "PGN: 1. e4")])

    [request] = calls
    assert request["think"] == "xhigh"
    assert request["format"]["required"] == ["move"]
    assert reply.thinking == "Mirror it."


def test_the_reply_carries_the_token_counts_and_stop_reason_with_the_thinking_and_answer_split_by_characters():
    def chat(**request):
        message = OllamaMessage(role="assistant", content='{"move": "e5"}', thinking="M" * 42)  # 14 + 42 characters
        return ChatResponse(message=message, prompt_eval_count=812, eval_count=200, done_reason="stop")

    reply = OllamaPlayer("qwen3.5:9b", chat=chat).reply([Message("user", "PGN: 1. e4")])

    # Ollama counts thinking and answer together, so 200 tokens split 42:14 is an estimate.
    assert (reply.thinking_tokens, reply.answer_tokens, reply.prompt_tokens) == (150, 50, 812)
    assert reply.stop_reason == "stop"
    assert reply.token_split_estimated is True


@pytest.mark.parametrize(
    ("thinking", "content", "tokens"),
    [(None, '{"reasoning": "Mirror it.", "move": "e5"}', (0, 31)), ("Cut short while think", "", (31, 0))],
)
def test_with_only_thinking_or_only_an_answer_the_count_is_exact(thinking, content, tokens):
    def chat(**request):
        message = OllamaMessage(role="assistant", content=content, thinking=thinking)
        return ChatResponse(message=message, prompt_eval_count=90, eval_count=31, done_reason="length")

    reply = OllamaPlayer("qwen3.5:9b", thinking=thinking is not None, chat=chat).reply([Message("user", "PGN: 1. e4")])

    assert (reply.thinking_tokens, reply.answer_tokens, reply.prompt_tokens) == tokens + (90,)
    assert reply.stop_reason == "length"
    assert reply.token_split_estimated is False


def test_a_reply_without_counts_carries_none():
    def chat(**request):
        return ChatResponse(message=OllamaMessage(role="assistant", content='{"move": "e5"}', thinking="Mirror."))

    reply = OllamaPlayer("qwen3.5:9b", chat=chat).reply([Message("user", "PGN: 1. e4")])

    assert (reply.thinking_tokens, reply.answer_tokens, reply.prompt_tokens, reply.stop_reason) == (None,) * 4
    assert reply.token_split_estimated is False


BUDGET_SENTENCE = "\n\nConsidering the limited time, I have to give my move now, based on the thinking so far."
TURN = [Message("system", "Play chess."), Message("user", "PGN: 1. e4")]


def scripted_chat(*responses: ChatResponse):
    """A fake chat call answering with the responses in order, recording every request."""
    calls: list[dict] = []
    replies = list(responses)

    def chat(**request):
        calls.append(request)
        return replies.pop(0)

    return chat, calls


def answer(content: str, thinking: str | None = None, **counts) -> ChatResponse:
    return ChatResponse(message=OllamaMessage(role="assistant", content=content, thinking=thinking), **counts)


def test_a_budgeted_reply_that_stops_normally_makes_one_call_capped_at_the_budget():
    chat, calls = scripted_chat(answer('{"move": "e5"}', "Mirror it.", eval_count=300, done_reason="stop"))

    player = OllamaPlayer("qwen3.8:latest", thinking="medium", chat=chat, sampling={"temperature": 0.6}, budget=1024)
    reply = player.reply(TURN, allowed_moves=["e5", "Nf6"])

    [request] = calls
    assert request["options"] == {"temperature": 0.6, "num_ctx": 8192, "num_predict": 1024}
    assert (reply.raw, reply.forced, reply.stop_reason) == ('{"move": "e5"}', False, "stop")


def test_a_reply_cut_while_thinking_is_forced_in_one_more_call_with_the_thinking_handed_back():
    chat, calls = scripted_chat(
        answer("", "Nf6 develops, but", prompt_eval_count=400, eval_count=1024, done_reason="length"),
        answer(' {"move": "Nf6"}', prompt_eval_count=1430, eval_count=8, done_reason="stop"),
    )

    player = OllamaPlayer("qwen3.8:latest", thinking="medium", chat=chat, sampling={"temperature": 0.6}, budget=1024)
    reply = player.reply(TURN, allowed_moves=["e5", "Nf6"])

    first, forced = calls
    # The same model, thinking value and answer schema, enum included, with the turn's messages unchanged.
    assert {key: forced[key] for key in ("model", "think", "format")} == {
        key: first[key] for key in ("model", "think", "format")
    }
    assert forced["format"]["properties"]["move"]["enum"] == ["e5", "Nf6"]
    assert forced["messages"] == first["messages"] + [
        {"role": "assistant", "thinking": "Nf6 develops, but" + BUDGET_SENTENCE, "content": " "}
    ]
    assert forced["options"] == {"temperature": 0.6, "num_ctx": 8192, "num_predict": 64}
    assert (reply.raw, reply.thinking, reply.forced) == (' {"move": "Nf6"}', "Nf6 develops, but", True)
    # All of the first call was thinking; the answer is the forced call's; the prompt is the turn's, the first call's.
    assert (reply.thinking_tokens, reply.answer_tokens, reply.prompt_tokens) == (1024, 8, 400)
    assert (reply.stop_reason, reply.token_split_estimated) == ("stop", False)


def test_a_reply_cut_while_answering_hands_back_the_complete_thinking_unchanged():
    # 18 characters of thinking and 6 of a cut answer share the first call's 32 tokens.
    chat, calls = scripted_chat(
        answer('{"move', "Nf6 develops. Nf6.", prompt_eval_count=400, eval_count=32, done_reason="length"),
        answer(' {"move": "Nf6"}', eval_count=8, done_reason="stop"),
    )

    reply = OllamaPlayer("qwen3.5:9b", chat=chat, budget=64).reply(TURN, allowed_moves=["e5", "Nf6"])

    _, forced = calls
    assert forced["messages"][-1] == {"role": "assistant", "thinking": "Nf6 develops. Nf6.", "content": " "}
    assert (reply.raw, reply.forced) == (' {"move": "Nf6"}', True)
    assert (reply.thinking_tokens, reply.answer_tokens, reply.token_split_estimated) == (24, 8, True)


def test_gemma4_cut_while_thinking_is_forced_by_the_same_chat_route_under_the_same_schema_and_enum():
    # Ollama's gemma4 renderer answers the handed-back thinking in a new model turn, but carries it, so Gemma 4 takes
    # the chat route like the Qwen models, with no Gemma-specific request (docs/research/thinking-budget.md).
    chat, calls = scripted_chat(
        answer("", "Bxf7+ wins a pawn, but", prompt_eval_count=372, eval_count=256, done_reason="length"),
        answer('{"move": "Bb3"}', prompt_eval_count=651, eval_count=7, done_reason="stop"),
    )

    reply = OllamaPlayer("gemma4:26b", chat=chat, budget=256).reply(TURN, allowed_moves=["Bxf7+", "Bb3", "d3"])

    first, forced = calls  # exactly one forced-answer call
    assert (first["model"], first["think"]) == ("gemma4:26b", True)
    assert first["options"] == {"num_ctx": 8192, "num_predict": 256}
    assert (forced["model"], forced["think"], forced["format"]) == ("gemma4:26b", True, first["format"])
    assert forced["format"]["properties"]["move"]["enum"] == ["Bxf7+", "Bb3", "d3"]
    assert forced["messages"] == first["messages"] + [
        {"role": "assistant", "thinking": "Bxf7+ wins a pawn, but" + BUDGET_SENTENCE, "content": " "}
    ]
    assert forced["options"] == {"num_ctx": 8192, "num_predict": 64}
    assert (reply.raw, reply.forced, reply.thinking_tokens, reply.answer_tokens) == ('{"move": "Bb3"}', True, 256, 7)
