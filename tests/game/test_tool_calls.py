"""Calling Tools during a Turn (ADR 0011): the four tools answer about the position, a side with tools plays the Tools
Prompt template by default, and each attempt records its tool calls, which the side's stats add up at game end."""

import json
import re

import chess
import httpx
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from tests.conftest import ScriptedAnchor, ScriptedPlayer

from chessllm.cli.anchor_match import main as anchor_match
from chessllm.game.llm_turn.prompt import TOOLS_SYSTEM_PROMPT_FILE, side_template, tools_template
from chessllm.game.llm_turn.tools import REGISTERED, PositionTools
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.sides import TOOLS, BenchmarkLlmSide
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.logs.llm_turns import logged_llm_turns

ANSWER = '{"move": "%s"}'


def position(sans: list[str], color: str | None = None) -> PositionTools:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return PositionTools(board, sans, color or ("white" if board.turn else "black"))


def test_the_four_tools_are_registered_by_the_decorator_and_take_no_input():
    assert tuple(REGISTERED) == TOOLS
    tools = position([]).functions(frozenset({"material", "board"}))
    assert [function.__name__ for function in tools] == ["board", "material"]
    for function in tools:
        assert function.__doc__ and isinstance(function(), str)


def test_board_gives_a_diagram_with_files_and_ranks_the_fen_whose_move_castling_and_en_passant():
    tools = position(["e4", "Nf6", "e5", "d5"])

    assert tools.board().splitlines() == [
        "8  r n b q k b . r",
        "7  p p p . p p p p",
        "6  . . . . . n . .",
        "5  . . . p P . . .",
        "4  . . . . . . . .",
        "3  . . . . . . . .",
        "2  P P P P . P P P",
        "1  R N B Q K B N R",
        "   a b c d e f g h",
        "Uppercase is White, lowercase Black, . an empty square.",
        "FEN: rnbqkb1r/ppp1pppp/5n2/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3",
        "To move: White",
        "Castling rights: White O-O, O-O-O; Black O-O, O-O-O",
        "En passant: d6",
    ]


def test_board_says_none_for_lost_castling_rights_and_no_en_passant():
    lines = position(["e4", "e5", "Ke2", "Ke7"]).board().splitlines()

    assert lines[-3:] == ["To move: White", "Castling rights: none", "En passant: none"]
    assert position(["h4", "a5", "Rh3"]).board().splitlines()[-2] == "Castling rights: White O-O-O; Black O-O, O-O-O"


def test_move_history_gives_the_moves_so_far_as_pgn_movetext():
    assert position(["e4", "e5", "Nf3"]).move_history() == "1. e4 e5 2. Nf3"
    assert position([]).move_history() == "(no moves yet)"


def test_legal_moves_gives_every_legal_move_in_san_in_a_random_order():
    tools = position(["e4"])
    board = chess.Board()
    board.push_san("e4")
    expected = [board.san(move) for move in board.legal_moves]

    answers = [tools.legal_moves().split() for _ in range(20)]

    assert all(sorted(answer) == sorted(expected) for answer in answers)
    assert len({tuple(answer) for answer in answers}) > 1


def test_material_gives_each_sides_pieces_and_points_and_the_balance_from_the_callers_side():
    after_capture = ["e4", "d5", "exd5", "Qxd5", "Nc3", "Qa5", "Nf3", "Nf6", "Bc4", "Bg4", "Bxf7+"]

    assert position(after_capture).material().splitlines() == [
        "Points: P 1, N 3, B 3, R 5, Q 9 (kings not counted)",
        "White: Q, 2 R, 2 B, 2 N, 7 P = 38 points",
        "Black: Q, 2 R, 2 B, 2 N, 6 P = 37 points",
        "Balance: -1 for you (Black)",
    ]
    assert position(after_capture, "white").material().splitlines()[-1] == "Balance: +1 for you (White)"
    assert position([]).material().splitlines()[-1] == "Balance: 0, even, for you (White)"


def test_a_side_with_tools_plays_the_tools_template_by_default_and_the_library_keeps_it_hidden(tmp_path):
    template = tools_template()
    side = BenchmarkLlmSide(model="qwen3.5:9b", thinking=True, tools=frozenset({"board"}))

    assert side_template(side) == template
    assert side_template(BenchmarkLlmSide(model="qwen3.5:9b", thinking=True)).id.startswith("default@")
    assert re.fullmatch("tools@[0-9a-f]{8}", template.id) and template.name == "Tools"
    assert template.system_prompt == TOOLS_SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")
    assert template.turn_template == "Opponent's last move: $last_move\nYour move."
    library = PromptLibrary(tmp_path)
    # The app can't give a side tools, so it isn't offered there; a game that played it still resolves it.
    assert template.id not in [entry.template.id for entry in library.entries()]
    assert library.template(template.id) == template


def calling(*names: str, thinking: str = "Look.") -> ChatResponse:
    calls = [OllamaMessage.ToolCall(function=OllamaMessage.ToolCall.Function(name=name, arguments={})) for name in names]
    message = OllamaMessage(role="assistant", content="", thinking=thinking, tool_calls=calls)
    return ChatResponse(message=message, eval_count=5, prompt_eval_count=50)


def answering(content: str, thinking: str | None = None) -> ChatResponse:
    message = OllamaMessage(role="assistant", content=content, thinking=thinking)
    return ChatResponse(message=message, eval_count=5, prompt_eval_count=50, done_reason="stop")


class FakeChat:
    def __init__(self, *responses: ChatResponse | BaseException) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def __call__(self, **request) -> ChatResponse:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def play_with_tools(tmp_path, chat: FakeChat, *args: str) -> list[dict]:
    """Play Fool's mate as Black with tools, the LLM's turns asked through an OllamaPlayer on the fake chat; returns
    the game log's events."""
    code = anchor_match(
        ["--model", "qwen3.5:9b", "--thinking", "--color", "black", "--tools", *args, "--games-dir", str(tmp_path)],
        player_for=lambda settings, color: OllamaPlayer("qwen3.5:9b", True, chat=chat),
        anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )
    assert code == 0
    [log] = tmp_path.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def test_a_turn_with_tools_records_each_call_in_its_attempt_and_its_prompt(tmp_path):
    chat = FakeChat(
        calling("board", "legal_moves", thinking="Look and list."),
        answering("", thinking="e5."),
        answering(ANSWER % "e5"),
        answering("Qh4#", thinking="Mate."),  # no call at all
        answering(ANSWER % "Qh4#"),
    )

    events = play_with_tools(tmp_path, chat, "board,legal_moves")

    start = events[0]
    assert start["black"]["prompt_template"]["id"] == tools_template().id
    first, second = (event for event in events if event["type"] == "llm_attempt")
    calls = first["tool_calls"]
    assert [(call["tool"], call["arguments"], call["thinking"]) for call in calls] == [
        ("board", {}, "Look and list."), ("legal_moves", {}, None),
    ]
    assert calls[0]["result"].startswith("8  r n b q k b n r") and calls[0]["latency_s"] >= 0
    after_f3 = chess.Board()
    after_f3.push_san("f3")
    assert sorted(calls[1]["result"].split()) == sorted(after_f3.san(move) for move in after_f3.legal_moves)
    assert calls[1]["latency_s"] is None
    assert [m["role"] for m in first["prompt"]] == ["system", "user", "assistant", "tool", "tool", "assistant"]
    assert first["prompt"][0]["content"].startswith("You are playing chess as Black against White.")
    assert [m["content"] for m in first["prompt"][3:]] == [calls[0]["result"], calls[1]["result"], " "]
    assert first["prompt"][2]["tool_calls"] == ["board", "legal_moves"]
    assert [m.get("tool_name") for m in first["prompt"][3:5]] == ["board", "legal_moves"]
    assert first["prompt"][1]["content"] == "Opponent's last move: f3\nYour move."
    assert "tool_call_as_text" not in first
    # Tokens add up the attempt's three calls.
    assert (first["thinking_tokens"], first["answer_tokens"], first["prompt_tokens"]) == (10, 5, 150)
    assert "tool_calls" not in second
    # The turn is still decided as any: the forced answer is the move played.
    assert events[-1]["type"] == "game_end" and events[-1]["result"] == "0-1"
    # Read back from the log, the attempts are as the game recorded them.
    first_turn = logged_llm_turns(events)[0]
    assert [call.tool for call in first_turn.attempts[0].tool_calls or []] == ["board", "legal_moves"]


def test_a_retry_gets_a_fresh_cap_and_the_side_stats_add_up_the_tool_use(tmp_path):
    chat = FakeChat(
        calling("board"), calling("material"),  # the cap of 2
        answering(ANSWER % "Ke7"),  # illegal: a Retry
        calling("board"), calling("board"),  # a fresh cap of 2
        answering(ANSWER % "e5"),
        answering('<tool_call>{"name": "board"}</tool_call>', thinking="Call it."),  # written as text
        answering(ANSWER % "Qh4#"),
    )

    events = play_with_tools(tmp_path, chat, "board,material", "--tool-call-cap", "2")

    attempts = [event for event in events if event["type"] == "llm_attempt"]
    assert [len(attempt.get("tool_calls", [])) for attempt in attempts] == [2, 2, 0]
    assert attempts[0]["result"] == "illegal" and attempts[1]["result"] == "legal"
    assert attempts[2]["tool_call_as_text"] is True
    assert attempts[2]["prompt"][-1] == {"role": "assistant", "content": '<tool_call>{"name": "board"}</tool_call>'}
    # The retry is asked afresh: the turn's message, the rejected answer and the feedback, no earlier tool calls.
    assert [m["role"] for m in attempts[1]["prompt"]] == [
        "system", "user", "assistant", "user", "assistant", "tool", "assistant", "tool",
    ]
    end = events[-1]
    assert end["stats"]["black"]["tool_use"] == {
        "tool_calls": {"board": 3, "material": 1},
        "attempts_without_tool_calls": 1,
        "attempts_at_cap": 2,
        "tool_calls_as_text": 1,
    }


def test_a_side_without_tools_is_given_none_and_has_no_tool_use_in_its_stats(tmp_path):
    player = ScriptedPlayer(["e5", "Qh4#"])
    code = anchor_match(
        ["--model", "qwen3.5:9b", "--thinking", "--color", "black", "--games-dir", str(tmp_path)],
        player_for=player.for_settings,
        anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    assert player.tools == [None, None]
    [log] = tmp_path.glob("*.jsonl")
    end = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "tool_use" not in end["stats"]["black"]


def test_a_side_with_tools_is_given_them_bound_to_each_turns_position_with_its_cap(tmp_path):
    player = ScriptedPlayer(["e5", "Qh4#"])
    code = anchor_match(
        ["--model", "qwen3.5:9b", "--thinking", "--color", "black", "--tools", "move_history,board",
         "--tool-call-cap", "3", "--games-dir", str(tmp_path)],
        player_for=player.for_settings,
        anchor_for=lambda side: ScriptedAnchor(["f3", "g4"]),
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    first, second = player.tools
    assert first is not None and second is not None
    assert (first.cap, [function.__name__ for function in first.functions]) == (3, ["board", "move_history"])
    assert first.functions[1]() == "1. f3"
    assert second.functions[1]() == "1. f3 e5 2. g4"


def test_a_call_that_fails_after_tool_calls_forfeits_but_its_attempt_keeps_and_counts_them(tmp_path):
    chat = FakeChat(calling("board", thinking="Look."), httpx.ReadTimeout("timed out"))

    events = play_with_tools(tmp_path, chat, "board")

    [attempt] = [event for event in events if event["type"] == "llm_attempt"]
    assert attempt["result"] == "timeout"
    assert [(call["tool"], call["thinking"]) for call in attempt["tool_calls"]] == [("board", "Look.")]
    assert [m["role"] for m in attempt["prompt"]] == ["system", "user", "assistant", "tool"]
    end = events[-1]
    assert end["reason"] == "forfeit"
    assert end["stats"]["black"]["tool_use"] == {
        "tool_calls": {"board": 1}, "attempts_without_tool_calls": 0, "attempts_at_cap": 0, "tool_calls_as_text": 0,
    }


def test_the_attempts_thinking_is_every_calls_in_order(tmp_path):
    chat = FakeChat(
        calling("board", thinking="Look."), answering("", thinking="e5."), answering(ANSWER % "e5"),
        answering("", thinking="Mate."), answering(ANSWER % "Qh4#"),
    )

    events = play_with_tools(tmp_path, chat, "board")

    first = next(event for event in events if event["type"] == "llm_attempt")
    assert first["thinking"] == "Look.\n\ne5."
