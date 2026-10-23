"""Tool calls in a game (ADR 0011): a side with Tools plays the Tools template by default, calls its tools during
each attempt through the Ollama player, and each attempt records its tool calls, in order, and the messages they added
to its prompt; the side's totals at game end count them. A Retry gets a fresh Tool-call cap."""

import json

import httpx
import pytest
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from tests.fakes import ScriptedPlayer

from chessllm.cli.common import player_for
from chessllm.cli.faceoff_batch import main as faceoff_batch
from chessllm.core.config import PROMPTS_DIR
from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import default_template
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.settings import Settings
from chessllm.game.sides import ALL_TOOLS, BenchmarkLlmSide, LlmSide
from chessllm.llm.models import LLM_MODELS
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.logs.llm_turns import logged_llm_turns

QWEN = "qwen3.5:9b"
WITH_TOOLS = ("--models", QWEN, "gemma3:12b", "--thinking-for", QWEN, "--tools-for", QWEN)


def calling(*tools: str, thinking: str | None = None) -> ChatResponse:
    function = OllamaMessage.ToolCall.Function
    tool_calls = [OllamaMessage.ToolCall(function=function(name=name, arguments={})) for name in tools]
    return ChatResponse(message=OllamaMessage(role="assistant", content="", thinking=thinking, tool_calls=tool_calls))


def answer(content: str, thinking: str | None = None) -> ChatResponse:
    return ChatResponse(message=OllamaMessage(role="assistant", content=content, thinking=thinking))


def faceoff(tmp_path, *responses: ChatResponse | BaseException, args: tuple[str, ...] = ()) -> list[dict]:
    """One faceoff of Qwen with Tools as White, its Ollama player answered by responses in order, against a scripted
    Gemma 3 to Fool's mate; the game log's events."""
    replies = list(responses)
    requests: list[dict] = []

    def chat(**request):
        requests.append(request)
        reply = replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    black = ScriptedPlayer(["e5", "Qh4#"])

    def build(settings, color):
        side = settings.side(color)
        if color == "black":
            return black
        return OllamaPlayer(side.model, side.think(), chat=chat, tool_call_cap=side.tool_call_cap)

    code = faceoff_batch(
        ["--games", "1", *WITH_TOOLS, *args, "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=build,
        sampling_file=tmp_path / "no-sampling.toml",
    )
    assert code == 0 and not replies
    [log] = tmp_path.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def white_attempts(events: list[dict]) -> list[dict]:
    return [event for event in events if event["type"] == "llm_attempt" and event["color"] == "white"]


def test_each_attempt_records_its_tool_calls_and_their_messages_in_its_prompt(tmp_path):
    events = faceoff(
        tmp_path,
        calling("move_history", thinking="What happened?"), answer("", "f3."), answer('{"move": "f3"}'),
        answer("", "g4."), answer('{"move": "g4"}'),
    )

    first, second = white_attempts(events)
    [call] = first["tool_calls"]
    assert {key: call[key] for key in ("tool", "arguments", "result", "thinking")} == {
        "tool": "move_history", "arguments": {}, "result": "(no moves yet)", "thinking": "What happened?",
    }
    assert call["latency_s"] >= 0
    assert first["prompt"][2:] == [
        {"role": "assistant", "content": "", "tool_calls": ["move_history"]},
        {"role": "tool", "content": "(no moves yet)", "tool_name": "move_history"},
    ]
    assert (first["result"], first["thinking"]) == ("legal", "f3.")
    # Left out when none, so attempts without tools log as before.
    assert "tool_calls" not in second and "tool_call_as_text" not in second
    assert [message["role"] for message in second["prompt"]] == ["system", "user"]
    # The attempt's tool calls are read back from the log with it.
    [turn, _] = [turn for turn in logged_llm_turns(events) if turn.color == "white"]
    assert [tool_call.tool for tool_call in turn.attempts[0].tool_calls or []] == ["move_history"]


def test_a_side_with_tools_plays_the_tools_template_by_default(tmp_path):
    events = faceoff(tmp_path, answer("", "f3."), answer('{"move": "f3"}'), answer("", "g4."), answer('{"move": "g4"}'))

    template = events[0]["white"]["prompt_template"]
    assert template["id"].startswith("tools@")
    assert template["system_prompt"] == (PROMPTS_DIR / "system_tools.txt").read_text(encoding="utf-8")
    first, second = white_attempts(events)
    # Only whose move it is and the opponent's last move: the rest is for the tools to tell.
    assert first["prompt"][1] == {"role": "user", "content": "You play White. Make the first move."}
    assert second["prompt"][1] == {"role": "user", "content": "Opponent played e5."}
    assert first["prompt"][0]["content"].startswith("You are playing chess as White against Black.")


def test_a_retry_gets_a_fresh_cap_and_the_side_totals_count_the_tool_calls(tmp_path):
    events = faceoff(
        tmp_path,
        calling("legal_moves"), answer('{"move": "Ke2"}'),  # the cap of 1 used, then an illegal move
        calling("board"), answer('{"move": "f3"}'),  # the Retry calls again
        answer('<tool_call>{"name": "board"}</tool_call>', "Call it."), answer('{"move": "g4"}'),
        args=("--tool-call-cap-for", f"{QWEN}=1"),
    )

    illegal, retry, written = white_attempts(events)
    assert [call["tool"] for call in illegal["tool_calls"]] == ["legal_moves"]
    assert [call["tool"] for call in retry["tool_calls"]] == ["board"]
    assert written["tool_call_as_text"] is True and "tool_calls" not in written
    # The text that set the flag, as the reply wrote it.
    assert written["prompt"][-1] == {"role": "assistant", "content": '<tool_call>{"name": "board"}</tool_call>'}
    stats = events[-1]["stats"]
    assert stats["white"]["tools"] == {
        "tool_calls": {"board": 1, "move_history": 0, "legal_moves": 1, "material": 0},
        "attempts_without_tool_call": 1,
        "attempts_at_cap": 2,
        "tool_calls_as_text": 1,
    }
    assert "tools" not in stats["black"]  # only a side with tools has them


def test_tool_calls_made_before_a_timeout_are_recorded_on_the_forfeited_attempt_and_counted(tmp_path):
    events = faceoff(tmp_path, calling("board", thinking="Look."), httpx.ReadTimeout("slow"))

    [attempt] = white_attempts(events)
    assert attempt["result"] == "timeout"
    assert [call["tool"] for call in attempt["tool_calls"]] == ["board"]
    assert attempt["prompt"][-1]["role"] == "tool"
    end = events[-1]
    assert end["reason"] == "forfeit"
    assert end["stats"]["white"]["tools"]["tool_calls"]["board"] == 1


def test_the_player_is_built_with_the_sides_tool_call_cap():
    side = BenchmarkLlmSide(model=QWEN, thinking=True, tools=ALL_TOOLS, tool_call_cap=3)
    settings = Settings("llm_faceoff", side, LlmSide(model="gemma3:12b"))

    assert (player_for(settings, "white").tool_call_cap, player_for(settings, "black").tool_call_cap) == (3, 10)


def test_the_tools_template_is_hidden_in_the_prompt_library_as_the_app_cant_give_a_side_tools(tmp_path):
    library = PromptLibrary(tmp_path)
    tools = default_template("free", "tools")

    assert tools.id not in {entry.template.id for entry in library.entries()}
    assert library.template(tools.id) == tools


def test_the_tools_template_is_refused_for_a_side_without_tools():
    side = BenchmarkLlmSide(model=QWEN, thinking=True, prompt_template=default_template("free", "tools"))

    with pytest.raises(InvalidSettings, match="leaves the rest to Tools"):
        Settings("llm_faceoff", side, LlmSide(model="gemma3:12b")).check(LLM_MODELS)
