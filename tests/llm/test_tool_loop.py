"""The tool loop of the Ollama player (ADR 0011): an attempt with Tools calls Ollama with tools= and no format, runs
every tool call and answers it with a tool message, each call counting against the Tool-call cap, until the model
replies without one or has made its last allowed call; then one more call with no tools and the answer schema gives
the move."""

import httpx
import pytest
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from chessllm.exceptions import LlmTimeout
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.llm.players import FailedAfterToolCalls, Message

TURN = [Message("system", "You play Black. You have tools."), Message("user", "Opponent played e4.")]


def board() -> str:
    """The board."""
    return "BOARD"


def legal_moves() -> str:
    """The legal moves."""
    return "e5 Nf6 d5"


def material() -> str:
    """The material."""
    return "even"


TOOLS = [board, legal_moves, material]


def scripted_chat(*responses: ChatResponse):
    calls: list[dict] = []
    replies = list(responses)

    def chat(**request):
        calls.append(request | {"messages": list(request["messages"])})
        reply = replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    return chat, calls


def calling(*tools: str, thinking: str | None = None, content: str = "", **counts) -> ChatResponse:
    """A reply that calls the tools natively, in one message."""
    function = OllamaMessage.ToolCall.Function
    tool_calls = [OllamaMessage.ToolCall(function=function(name=name, arguments={})) for name in tools]
    message = OllamaMessage(role="assistant", content=content, thinking=thinking, tool_calls=tool_calls)
    return ChatResponse(message=message, **counts)


def answer(content: str, thinking: str | None = None, **counts) -> ChatResponse:
    return ChatResponse(message=OllamaMessage(role="assistant", content=content, thinking=thinking), **counts)


def player(chat, cap: int = 10) -> OllamaPlayer:
    return OllamaPlayer("qwen3.5:9b", chat=chat, tool_call_cap=cap)


def test_tool_calls_are_run_and_answered_until_the_model_stops_calling_then_the_move_is_forced():
    chat, calls = scripted_chat(
        calling("board", thinking="Look first.", prompt_eval_count=100, eval_count=20),
        calling("legal_moves", thinking="Which moves?", prompt_eval_count=150, eval_count=20),
        answer("I play e5.", "e5 mirrors it.", prompt_eval_count=200, eval_count=30),
        answer('{"move": "e5"}', prompt_eval_count=230, eval_count=6, done_reason="stop"),
    )

    reply = player(chat).reply(TURN, tools=TOOLS)

    first, second, third, forced = calls
    for request in (first, second, third):
        assert request["tools"] == TOOLS and "format" not in request
    assert first["messages"] == [
        {"role": "system", "content": "You play Black. You have tools."},
        {"role": "user", "content": "Opponent played e4."},
    ]
    assert second["messages"] == first["messages"] + [
        {"role": "assistant", "content": "", "thinking": "Look first.",
         "tool_calls": [{"function": {"name": "board", "arguments": {}}}]},
        {"role": "tool", "content": "BOARD", "tool_name": "board"},
    ]
    # The move under the answer schema, with no tools, the last reply's thinking handed back as ADR 0007 does.
    assert "tools" not in forced and forced["format"]["required"] == ["move"]
    handed_back = {"role": "assistant", "thinking": "e5 mirrors it.", "content": " "}
    assert forced["messages"] == third["messages"] + [handed_back]
    assert (reply.raw, reply.thinking, reply.stop_reason) == ('{"move": "e5"}', "e5 mirrors it.", "stop")
    assert [(call.tool, call.arguments, call.result, call.thinking) for call in reply.tool_calls] == [
        ("board", {}, "BOARD", "Look first."),
        ("legal_moves", {}, "e5 Nf6 d5", "Which moves?"),
    ]
    assert all(call.latency_s is not None and call.latency_s >= 0 for call in reply.tool_calls)
    # The tool calls and results as the attempt's prompt records them, after the turn's messages.
    assert reply.tool_messages == (
        Message("assistant", "", tool_calls=("board",)),
        Message("tool", "BOARD", tool_name="board"),
        Message("assistant", "", tool_calls=("legal_moves",)),
        Message("tool", "e5 Nf6 d5", tool_name="legal_moves"),
        Message("assistant", "I play e5."),  # the reply that called none, as written: its thinking was handed back
    )
    assert reply.tool_call_as_text is False
    # Tokens add up all four calls.
    assert reply.prompt_tokens == 680
    assert (reply.thinking_tokens or 0) + (reply.answer_tokens or 0) == 76


def test_parallel_calls_in_one_reply_are_each_run_and_answered():
    chat, calls = scripted_chat(
        calling("board", "material", thinking="Both."),
        answer("", "Done."),
        answer('{"move": "e5"}'),
    )

    reply = player(chat).reply(TURN, tools=TOOLS)

    _, second, _ = calls
    assert second["messages"][-2:] == [
        {"role": "tool", "content": "BOARD", "tool_name": "board"},
        {"role": "tool", "content": "even", "tool_name": "material"},
    ]
    # The reply's thinking and latency go with its first call only.
    assert [(call.tool, call.thinking) for call in reply.tool_calls] == [("board", "Both."), ("material", None)]
    assert reply.tool_calls[1].latency_s is None


def test_at_the_cap_the_move_is_forced_after_the_last_allowed_call_and_extra_calls_are_not_run():
    chat, calls = scripted_chat(
        calling("board", thinking="One."),
        calling("legal_moves", "material", thinking="Two more."),  # only one of them fits in a cap of 2
        answer('{"move": "Nf6"}', "Nf6 then."),
    )

    reply = player(chat, cap=2).reply(TURN, tools=TOOLS)

    _, second, forced = calls
    assert [call.tool for call in reply.tool_calls] == ["board", "legal_moves"]
    assert forced["messages"] == second["messages"] + [
        {"role": "assistant", "content": "", "thinking": "Two more.",
         "tool_calls": [{"function": {"name": "legal_moves", "arguments": {}}}]},
        {"role": "tool", "content": "e5 Nf6 d5", "tool_name": "legal_moves"},
    ]
    assert "tools" not in forced and "format" in forced
    assert (reply.raw, reply.thinking) == ('{"move": "Nf6"}', "Nf6 then.")


def test_an_answer_with_no_tool_call_is_still_asked_for_its_move_under_the_schema_and_enum():
    chat, calls = scripted_chat(answer("e5", "Easy."), answer('{"move": "e5"}'))

    reply = player(chat).reply(TURN, allowed_moves=["e5", "Nf6"], tools=TOOLS)

    first, forced = calls
    assert "format" not in first
    assert forced["format"]["properties"]["move"]["enum"] == ["e5", "Nf6"]
    assert (reply.tool_calls, reply.tool_call_as_text) == ((), False)
    assert reply.tool_messages == (Message("assistant", "e5"),)  # recorded as written, though not sent back


@pytest.mark.parametrize(
    "written",
    [
        '<tool_call>{"name": "legal_moves", "arguments": {}}</tool_call>',
        '{"name": "board", "arguments": {}}',
        "Let me call legal_moves() first.",
    ],
)
def test_a_tool_call_written_as_text_is_not_run_and_ends_the_tool_phase(written):
    chat, calls = scripted_chat(answer(written, "Call it."), answer('{"move": "e5"}'))

    reply = player(chat).reply(TURN, tools=TOOLS)

    assert len(calls) == 2  # the forced answer straight after
    assert (reply.tool_calls, reply.tool_call_as_text) == ((), True)
    assert reply.tool_messages == (Message("assistant", written),)  # what set the flag, as written


def test_a_move_in_words_is_no_tool_call_written_as_text():
    chat, _ = scripted_chat(answer("I'll look at the board and play e5.", "Fine."), answer('{"move": "e5"}'))

    assert player(chat).reply(TURN, tools=TOOLS).tool_call_as_text is False


def test_each_reply_gets_a_fresh_cap():
    chat, calls = scripted_chat(
        calling("board"), answer('{"move": "e5"}'),
        calling("board"), answer('{"move": "e5"}'),
    )
    capped = player(chat, cap=1)

    assert len(capped.reply(TURN, tools=TOOLS).tool_calls) == 1
    assert len(capped.reply(TURN, tools=TOOLS).tool_calls) == 1
    assert len(calls) == 4


def test_a_call_that_times_out_after_tool_calls_raises_the_timeout_with_the_calls_made():
    chat, _ = scripted_chat(calling("board"), httpx.ReadTimeout("slow"))

    with pytest.raises(FailedAfterToolCalls) as failed:
        player(chat).reply(TURN, tools=TOOLS)

    assert isinstance(failed.value.error, LlmTimeout)
    assert [call.tool for call in failed.value.tool_calls] == ["board"]
    assert failed.value.tool_messages[-1] == Message("tool", "BOARD", tool_name="board")


def test_a_call_that_times_out_before_any_tool_call_raises_the_timeout_itself():
    chat, _ = scripted_chat(httpx.ReadTimeout("slow"))

    with pytest.raises(LlmTimeout):
        player(chat).reply(TURN, tools=TOOLS)


def test_without_tools_the_reply_has_no_tool_calls_and_one_call():
    chat, calls = scripted_chat(answer('{"move": "e5"}'))

    reply = player(chat).reply(TURN)

    [request] = calls
    assert "tools" not in request
    assert (reply.tool_calls, reply.tool_messages) == ((), ())
