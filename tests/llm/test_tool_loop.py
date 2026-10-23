"""The Ollama player's tool loop (ADR 0011): with Tools an attempt calls them without the answer schema, each call
answered with a tool message, until the model replies without one or has made its last allowed call, then gives its
move in one more call under the answer schema, with no tools."""

import httpx
import pytest
from ollama import ChatResponse
from ollama import Message as OllamaMessage
from ollama._utils import convert_function_to_tool

from chessllm.exceptions import LlmTimeout
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.llm.players import FailedAfterToolCalls, Message, ToolCall, Tools

TURN = [Message("system", "Play chess."), Message("user", "Opponent's last move: e4\nYour move.")]
ANSWER = '{"move": "e5"}'


def board() -> str:
    """The board."""
    return "the board"


def legal_moves() -> str:
    """The legal moves."""
    return "e5 d5"


def material() -> str:
    """The material."""
    return "even"


TOOLS = Tools((board, legal_moves, material), cap=10)


def calling(*names: str, thinking: str | None = None, content: str = "", **usage) -> ChatResponse:
    """A reply that calls the named tools, in order."""
    calls = [OllamaMessage.ToolCall(function=OllamaMessage.ToolCall.Function(name=name, arguments={})) for name in names]
    message = OllamaMessage(role="assistant", content=content, thinking=thinking, tool_calls=calls or None)
    return ChatResponse(message=message, **usage)


def answering(content: str, thinking: str | None = None, **usage) -> ChatResponse:
    return ChatResponse(message=OllamaMessage(role="assistant", content=content, thinking=thinking), **usage)


class FakeChat:
    """Test fake for ollama's chat: gives the scripted responses in order and records every request."""

    def __init__(self, *responses: ChatResponse | BaseException) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def __call__(self, **request) -> ChatResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def player(chat: FakeChat) -> OllamaPlayer:
    return OllamaPlayer("qwen3.5:9b", True, chat=chat)


def test_the_tool_phase_calls_with_the_tools_and_no_format_then_one_forced_call_gives_the_move():
    chat = FakeChat(
        calling("board", thinking="Look first."),
        calling("legal_moves", thinking="Now the moves."),
        answering("", thinking="e5 mirrors it."),
        answering(ANSWER),
    )

    reply = player(chat).reply(TURN, tools=TOOLS)

    assert reply.raw == ANSWER
    *tool_phase, forced = chat.requests
    for request in tool_phase:
        assert [function.__name__ for function in request["tools"]] == ["board", "legal_moves", "material"]
        assert request.get("format") is None
        assert request["think"] is True
    assert "tools" not in forced or not forced["tools"]
    assert forced["format"]["properties"]["move"]["type"] == "string"
    # Each call is answered with a tool message; the reply without one is handed back for the forced answer.
    assert chat.requests[1]["messages"][2:] == [
        {"role": "assistant", "content": "", "thinking": "Look first.", "tool_calls": [
            {"function": {"name": "board", "arguments": {}}}]},
        {"role": "tool", "tool_name": "board", "content": "the board"},
    ]
    assert forced["messages"][-3:] == [
        {"role": "assistant", "content": "", "thinking": "Now the moves.", "tool_calls": [
            {"function": {"name": "legal_moves", "arguments": {}}}]},
        {"role": "tool", "tool_name": "legal_moves", "content": "e5 d5"},
        {"role": "assistant", "thinking": "e5 mirrors it.", "content": " "},
    ]
    assert [(call.tool, call.arguments, call.result, call.thinking) for call in reply.tool_calls] == [
        ("board", {}, "the board", "Look first."),
        ("legal_moves", {}, "e5 d5", "Now the moves."),
    ]
    assert all(call.latency_s is not None and call.latency_s >= 0 for call in reply.tool_calls)
    # The attempt's Thinking is every call's, in order: the replies that made tool calls included.
    assert reply.thinking == "Look first.\n\nNow the moves.\n\ne5 mirrors it."
    assert not reply.tool_call_as_text and not reply.forced
    # What the tool phase added to the Prompt, as sent before the answer was asked for.
    assert reply.tool_messages == (
        Message("assistant", "", tool_calls=("board",)),
        Message("tool", "the board", tool_name="board"),
        Message("assistant", "", tool_calls=("legal_moves",)),
        Message("tool", "e5 d5", tool_name="legal_moves"),
        Message("assistant", " "),
    )


def test_a_player_without_tools_asks_as_before():
    chat = FakeChat(answering(ANSWER))

    reply = player(chat).reply(TURN)

    [request] = chat.requests
    assert "tools" not in request
    assert (reply.tool_calls, reply.tool_messages, reply.tool_call_as_text) == ((), (), False)


def test_the_sdk_builds_each_tools_schema_from_its_function():
    chat = FakeChat(answering(""), answering(ANSWER))

    player(chat).reply(TURN, tools=TOOLS)

    schemas = [convert_function_to_tool(function).model_dump(exclude_none=True) for function in chat.requests[0]["tools"]]
    assert schemas[0] == {
        "type": "function",
        "function": {"name": "board", "description": "The board.", "parameters": {"type": "object", "properties": {}}},
    }


def test_parallel_calls_in_one_reply_are_each_run_and_answered_and_share_its_thinking_and_latency():
    chat = FakeChat(calling("board", "material", thinking="Both."), answering(""), answering(ANSWER))

    reply = player(chat).reply(TURN, tools=TOOLS)

    assert chat.requests[1]["messages"][2:] == [
        {"role": "assistant", "content": "", "thinking": "Both.", "tool_calls": [
            {"function": {"name": "board", "arguments": {}}}, {"function": {"name": "material", "arguments": {}}}]},
        {"role": "tool", "tool_name": "board", "content": "the board"},
        {"role": "tool", "tool_name": "material", "content": "even"},
    ]
    first, second = reply.tool_calls
    assert (first.tool, first.thinking, second.tool, second.result) == ("board", "Both.", "material", "even")
    # The reply's thinking and latency go with its first call only, so adding them up counts them once.
    assert first.latency_s is not None
    assert (second.thinking, second.latency_s) == (None, None)


def test_the_last_allowed_call_ends_the_tool_phase_and_calls_beyond_the_cap_are_not_run():
    chat = FakeChat(calling("board"), calling("legal_moves", "material"), answering(ANSWER))

    reply = player(chat).reply(TURN, tools=Tools(TOOLS.functions, cap=2))

    assert [call.tool for call in reply.tool_calls] == ["board", "legal_moves"]
    assert len(chat.requests) == 3
    forced = chat.requests[-1]
    assert forced["format"] is not None
    # The cap's call is answered, and the answer asked for straight after its result.
    assert forced["messages"][-2:] == [
        {"role": "assistant", "content": "", "thinking": None, "tool_calls": [
            {"function": {"name": "legal_moves", "arguments": {}}}]},
        {"role": "tool", "tool_name": "legal_moves", "content": "e5 d5"},
    ]


def test_an_answer_with_no_tool_call_is_handed_back_and_the_move_still_asked_for():
    chat = FakeChat(answering(ANSWER, thinking="Easy."), answering(ANSWER))

    reply = player(chat).reply(TURN, tools=TOOLS)

    assert reply.raw == ANSWER and reply.tool_calls == ()
    assert chat.requests[1]["messages"][-1] == {"role": "assistant", "thinking": "Easy.", "content": ANSWER}
    assert chat.requests[1]["format"] is not None


@pytest.mark.parametrize(
    "written",
    [
        '<tool_call>{"name": "legal_moves", "arguments": {}}</tool_call>',
        '{"name": "board", "arguments": {}}',
        "```tool_code\nprint(legal_moves())\n```",
        "Let me check material() first.",
    ],
)
def test_a_tool_call_written_as_text_is_not_run_and_ends_the_tool_phase(written):
    chat = FakeChat(answering(written, thinking="Call it."), answering(ANSWER))

    reply = player(chat).reply(TURN, tools=TOOLS)

    assert reply.tool_call_as_text
    assert reply.tool_calls == ()
    assert len(chat.requests) == 2
    assert chat.requests[1]["messages"][-1] == {"role": "assistant", "thinking": "Call it.", "content": written}


@pytest.mark.parametrize(
    "content",
    [
        '{"move": "e5"}',
        "I need to see the board before I choose my material plan.",
        "Looking at the board (after e4), e5 is natural.",
        "My material (3 points) is ahead.",
        "No tool_call or function_call is needed; I'll answer.",
        'The answer has a "name" field? No: {"move": "board"}',
    ],
)
def test_text_that_only_mentions_a_tool_is_no_tool_call(content):
    chat = FakeChat(answering(content), answering(ANSWER))

    assert not player(chat).reply(TURN, tools=TOOLS).tool_call_as_text


def test_a_call_to_a_tool_the_side_lacks_is_answered_with_why_and_counts_against_the_cap():
    chat = FakeChat(calling("fen"), answering(ANSWER))

    reply = player(chat).reply(TURN, tools=Tools((board,), cap=1))

    assert reply.tool_calls == (
        ToolCall(tool="fen", arguments={}, result="No tool fen: the tools are board.", thinking=None,
                 latency_s=reply.tool_calls[0].latency_s),
    )
    assert len(chat.requests) == 2


def test_latency_and_tokens_add_up_all_the_attempts_calls():
    chat = FakeChat(
        calling("board", thinking="Look.", eval_count=10, prompt_eval_count=100),
        answering("", thinking="Fine.", eval_count=20, prompt_eval_count=150),
        answering(ANSWER, eval_count=7, prompt_eval_count=160, done_reason="stop"),
    )

    reply = player(chat).reply(TURN, tools=TOOLS)

    assert (reply.thinking_tokens, reply.answer_tokens, reply.prompt_tokens) == (30, 7, 410)
    assert reply.stop_reason == "stop"
    assert reply.latency_s >= sum(call.latency_s or 0 for call in reply.tool_calls)


def test_a_call_that_times_out_after_a_tool_call_gives_no_answer_but_keeps_the_calls_made():
    chat = FakeChat(calling("board", thinking="Look."), httpx.ReadTimeout("timed out"))

    with pytest.raises(FailedAfterToolCalls) as raised:
        OllamaPlayer("qwen3.5:9b", True, chat=chat, timeout_s=120).reply(TURN, tools=TOOLS)

    failed = raised.value
    assert isinstance(failed.error, LlmTimeout) and failed.error.timeout_s == 120
    assert [(call.tool, call.result, call.thinking) for call in failed.tool_calls] == [("board", "the board", "Look.")]
    assert failed.tool_messages == (
        Message("assistant", "", tool_calls=("board",)), Message("tool", "the board", tool_name="board"),
    )
    assert not failed.tool_call_as_text


def test_the_answer_call_failing_after_a_call_written_as_text_keeps_that_it_was():
    chat = FakeChat(answering("legal_moves()"), RuntimeError("connection refused"))

    with pytest.raises(FailedAfterToolCalls) as raised:
        player(chat).reply(TURN, tools=TOOLS)

    assert raised.value.tool_call_as_text and raised.value.tool_calls == ()
    assert str(raised.value.error) == "connection refused"


def test_a_call_that_fails_before_any_tool_call_fails_as_without_tools():
    chat = FakeChat(httpx.ReadTimeout("timed out"))

    with pytest.raises(LlmTimeout):
        OllamaPlayer("qwen3.5:9b", True, chat=chat, timeout_s=120).reply(TURN, tools=TOOLS)


def test_each_reply_gets_a_fresh_cap():
    chat = FakeChat(
        calling("board"), calling("board"), answering(ANSWER),
        calling("board"), calling("board"), answering(ANSWER),
    )
    llm = player(chat)
    capped = Tools(TOOLS.functions, cap=2)

    first, second = llm.reply(TURN, tools=capped), llm.reply(TURN, tools=capped)

    assert len(first.tool_calls) == len(second.tool_calls) == 2
