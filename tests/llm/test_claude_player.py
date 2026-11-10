"""The Claude adapter for the LLM player port, tested against a fake client: no test calls the real API or needs a
token."""

import anthropic
import httpx
import pytest
from anthropic.types import Message as ClaudeMessage
from anthropic.types import TextBlock, ThinkingBlock, Usage

from chessllm.exceptions import HostedModelFailed, LlmTimeout, ReplyDeclined
from chessllm.llm.claude_player import ClaudePlayer
from chessllm.llm.players import LlmReply, Message

REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def answer(
    text: str = '{"move": "e5"}',
    thinking: str | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 40,
    output_tokens: int = 12,
) -> ClaudeMessage:
    content: list = [ThinkingBlock(type="thinking", thinking=thinking, signature="sig")] if thinking is not None else []
    content.append(TextBlock(type="text", text=text))
    return ClaudeMessage(
        id="msg_1", content=content, model="claude-haiku-5-5", role="assistant", stop_reason=stop_reason,
        stop_sequence=None, type="message", usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def player_that_sends(response: ClaudeMessage, calls: list | None = None, **options) -> ClaudePlayer:
    def create(**request):
        if calls is not None:
            calls.append(request)
        return response

    return ClaudePlayer("claude-haiku-5-5", create=create, **options)


def status_error(error: type[anthropic.APIStatusError], status: int, message: str = "nope") -> anthropic.APIStatusError:
    return error(message, response=httpx.Response(status, request=REQUEST), body=None)


def failing_player(error: Exception) -> ClaudePlayer:
    def create(**request):
        raise error

    return ClaudePlayer("claude-haiku-5-5", create=create)


def test_the_adapter_asks_for_the_free_move_schema_with_thinking_on_and_records_the_summary():
    calls = []
    player = player_that_sends(answer(thinking="Mirror the centre pawn."), calls)

    reply = player.reply([Message("system", "Play chess."), Message("user", "PGN: 1. e4")])

    assert reply.raw == '{"move": "e5"}'
    assert reply.thinking == "Mirror the centre pawn."
    assert reply.latency_s >= 0
    assert reply.stop_reason == "end_turn"
    [request] = calls
    assert request["model"] == "claude-haiku-5-5"
    assert request["system"] == "Play chess."
    assert request["messages"] == [{"role": "user", "content": "PGN: 1. e4"}]
    assert request["thinking"] == {"type": "adaptive", "display": "summarized"}
    schema = request["output_config"]["format"]
    assert request["output_config"]["effort"] == "medium"
    assert request["output_config"]["format"]["type"] == "json_schema"
    assert schema["schema"]["required"] == ["move"]
    assert list(schema["schema"]["properties"]) == ["move"]
    assert "enum" not in schema["schema"]["properties"]["move"]


def test_with_thinking_off_the_adapter_turns_thinking_off_and_asks_for_the_reasoning_before_the_move():
    calls = []
    text = '{"reasoning": "Mirror the centre pawn.", "move": "e5"}'
    player = player_that_sends(answer(text), calls, thinking=False)

    reply = player.reply([Message("user", "PGN: 1. e4")])

    assert reply.raw == text
    assert reply.thinking is None
    [request] = calls
    assert request["thinking"] == {"type": "disabled"}
    assert request["output_config"]["effort"] == "medium"
    schema = request["output_config"]["format"]["schema"]
    assert list(schema["properties"]) == ["reasoning", "move"]
    assert schema["required"] == ["reasoning", "move"]


@pytest.mark.parametrize("thinking", [True, False])
def test_under_enforced_decoding_the_move_can_only_be_one_of_the_allowed_moves(thinking):
    calls = []
    player = player_that_sends(answer(), calls, thinking=thinking)

    player.reply([Message("user", "PGN: 1. e4")], allowed_moves=["e5", "c5", "Nf6"])

    [request] = calls
    schema = request["output_config"]["format"]["schema"]
    assert schema["properties"]["move"]["enum"] == ["e5", "c5", "Nf6"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("thinking", [True, False])
def test_no_sampling_option_is_ever_sent_as_the_provider_rejects_non_default_ones(thinking):
    calls = []
    player = player_that_sends(answer(), calls, thinking=thinking)

    player.reply([Message("user", "PGN: 1. e4")], allowed_moves=["e5"])

    [request] = calls
    assert not {"temperature", "top_p", "top_k"} & set(request)
    assert "budget_tokens" not in str(request["thinking"])
    assert "tools" not in request  # no Tool applies to a Hosted model


def test_a_conversation_is_sent_as_it_is_with_no_prefilled_assistant_turn():
    calls = []
    player = player_that_sends(answer(), calls)

    player.reply(
        [
            Message("system", "Play chess."),
            Message("user", "1. e4"),
            Message("assistant", '{"move": "Qh5"}'),
            Message("user", "That was illegal."),
        ]
    )

    [request] = calls
    assert [message["role"] for message in request["messages"]] == ["user", "assistant", "user"]
    assert request["messages"][-1] == {"role": "user", "content": "That was illegal."}


def test_the_reply_counts_the_tokens_the_call_used():
    player = player_that_sends(answer(thinking="a" * 30, text='{"move": "e5"}', input_tokens=77, output_tokens=40))

    reply = player.reply([Message("user", "PGN: 1. e4")])

    assert reply.prompt_tokens == 77
    # The API counts the thinking and the answer together, so they are split by their characters, as Ollama's are
    assert reply.thinking_tokens is not None and reply.answer_tokens is not None
    assert reply.thinking_tokens + reply.answer_tokens == 40
    assert reply.token_split_estimated


def test_with_thinking_off_every_output_token_is_the_answers():
    player = player_that_sends(answer(output_tokens=33), thinking=False)

    reply = player.reply([Message("user", "PGN: 1. e4")])

    assert (reply.thinking_tokens, reply.answer_tokens, reply.token_split_estimated) == (0, 33, False)


def test_a_reply_cut_at_the_token_limit_is_given_as_it_is_with_why_it_stopped():
    player = player_that_sends(answer(text='{"move": "e', stop_reason="max_tokens"))

    reply = player.reply([Message("user", "PGN: 1. e4")])

    assert isinstance(reply, LlmReply)
    assert reply.raw == '{"move": "e'
    assert reply.stop_reason == "max_tokens"


def test_a_refusal_is_a_reply_declined_which_is_a_forfeit():
    refusal = answer(text="", stop_reason="refusal")

    with pytest.raises(ReplyDeclined, match="declined"):
        player_that_sends(refusal).reply([Message("user", "PGN: 1. e4")])


def test_the_adapter_gives_up_after_the_time_limit():
    player = failing_player(anthropic.APITimeoutError(request=REQUEST))

    with pytest.raises(LlmTimeout) as raised:
        player.reply([Message("user", "PGN: 1. e4")])
    assert raised.value.timeout_s == 300


def test_the_default_time_limit_is_five_minutes_and_can_be_set():
    assert ClaudePlayer("claude-haiku-5-5", create=lambda **request: None).timeout_s == 300
    assert ClaudePlayer("claude-haiku-5-5", create=lambda **request: None, timeout_s=60).timeout_s == 60


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (status_error(anthropic.AuthenticationError, 401, "invalid x-api-key"), "refused the token"),
        (status_error(anthropic.PermissionDeniedError, 403), "not allowed"),
        (status_error(anthropic.BadRequestError, 400, "Your credit balance is too low"), "credit"),
        (status_error(anthropic.APIStatusError, 402, "billing problem"), "credit"),
        (status_error(anthropic.RateLimitError, 429), "rate limit"),
        (status_error(anthropic.InternalServerError, 500), "outage"),
        (status_error(anthropic.OverloadedError, 529), "outage"),
        (anthropic.APIConnectionError(request=REQUEST), "reach"),
    ],
)
def test_a_failure_that_is_not_the_models_fault_is_a_hosted_model_failure_with_its_reason(error, reason):
    with pytest.raises(HostedModelFailed, match=reason):
        failing_player(error).reply([Message("user", "PGN: 1. e4")])


def test_the_failure_says_what_the_provider_said_and_never_the_token():
    placeholder = "not-a-real-token"
    error = status_error(anthropic.AuthenticationError, 401, "invalid x-api-key")

    def create(**request):
        raise error

    player = ClaudePlayer("claude-haiku-5-5", token=placeholder, create=create)
    with pytest.raises(HostedModelFailed) as raised:
        player.reply([Message("user", "PGN: 1. e4")])

    assert "invalid x-api-key" in str(raised.value)
    assert placeholder not in str(raised.value)
    assert placeholder not in repr(player)
