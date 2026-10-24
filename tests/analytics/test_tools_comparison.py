"""The Tools comparison (chessllm.analytics.tools_comparison): for each model, one column per tool set it played
under otherwise the same Player configuration, over every finished game in the games directory. On synthetic logs."""

import json
from datetime import date

from chessllm.analytics.tools_comparison import markdown, tools_comparison

QWEN = {"player": "llm", "model": "qwen3.5:9b", "thinking": True, "llm_constraints": "free",
        "retry_feedback": "explained"}
ALL_FOUR = ["board", "legal_moves", "material", "move_history"]
TOOLS = QWEN | {"tools": ALL_FOUR, "tool_call_cap": 10}
LLAMA = QWEN | {"model": "llama3:8b", "thinking": False}
PROMPTS = "chessllm/game/prompts/"


def dragon(skill):
    return {"player": "anchor", "engine": "dragon", "skill": skill}


RANDOM = {"player": "anchor", "engine": "random", "seed": 1}


def attempt(color, ply, result="legal", number=1, tool_calls=(), as_text=False):
    event = {"type": "llm_attempt", "color": color, "ply": ply, "attempt": number, "fen": "x", "move": "e4",
             "result": result, "latency_s": 1.0}
    if tool_calls:
        event["tool_calls"] = [{"tool": tool, "arguments": {}, "result": "..."} for tool in tool_calls]
    if as_text:
        event["tool_call_as_text"] = True
    return event


class Games:
    """Writes synthetic game logs into a games directory, each started a second after the last."""

    def __init__(self, games_dir):
        self.dir = games_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.count = 0

    def write(self, white, black, result, reason="checkmate", attempts=(), time_used=None, streaks=None,
              finished=True, mode=None):
        mode = mode or ("anchor_match" if "anchor" in (white["player"], black["player"]) else "llm_faceoff")
        prompt_files = {
            color: PROMPTS + ("system_tools.txt" if side.get("tools") else "system.txt")
            for color, side in (("white", white), ("black", black)) if side["player"] == "llm"
        }
        start = {"type": "game_start", "game_id": str(self.count), "log_version": 2, "mode": mode, "white": white,
                 "black": black, "sampling": {}, "max_retries": 4, "prompt_files": prompt_files,
                 "started_at": f"2026-10-20T10:00:{self.count:02d}+02:00"}
        events = [start, *attempts]
        if finished:
            stats = {color: {"legal_move_streak": (streaks or {}).get(color, 0), "notation_slips": 0}
                     if side["player"] == "llm" else None for color, side in (("white", white), ("black", black))}
            events.append({"type": "game_end", "result": result, "reason": reason, "plies": 10, "stats": stats,
                           "time_used": time_used or {"white": 0.0, "black": 0.0}})
        path = self.dir / f"2026-10-20T10-00-{self.count:02d}_{self.count}.jsonl"
        path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        self.count += 1
        return path


def columns(comparison):
    return {column.tools: column for column in comparison.columns}


def test_each_tool_set_of_a_model_is_a_column_no_tools_first(tmp_path):
    games = Games(tmp_path / "games")
    games.write(QWEN, dragon(1), "1-0")
    games.write(dragon(1), QWEN, "1/2-1/2", "move_cap")
    games.write(TOOLS, RANDOM, "1-0")
    games.write(QWEN | {"tools": ["board"], "tool_call_cap": 5}, RANDOM, "0-1", "forfeit")
    games.write(TOOLS, RANDOM, "1-0", finished=False)  # unfinished: left out
    games.write(LLAMA, dragon(1), "0-1")  # a model that never had Tools: not compared

    [comparison] = tools_comparison(tmp_path / "games")

    assert comparison.model == "qwen3.5:9b"
    assert [(column.tools, column.tool_call_cap) for column in comparison.columns] == [
        ((), None), (tuple(ALL_FOUR), 10), (("board",), 5),
    ]
    no_tools, all_four, board = comparison.columns
    assert (no_tools.games, no_tools.wins, no_tools.draws, no_tools.losses) == (2, 1, 1, 0)
    assert (all_four.games, all_four.wins) == (1, 1)
    assert (board.games, board.losses, board.forfeits) == (1, 1, 1)


def test_illegal_moves_per_game_the_median_legal_move_streak_and_time_used_per_move(tmp_path):
    games = Games(tmp_path / "games")
    # Two illegal moves in the first game (one turn retried twice), none in the second; three LLM turns in each.
    games.write(TOOLS, RANDOM, "1-0", attempts=[
        attempt("white", 1), attempt("white", 3, "illegal"), attempt("white", 3, "invalid", 2),
        attempt("white", 3, number=3), attempt("white", 5),
    ], streaks={"white": 1}, time_used={"white": 30.0, "black": 0.1})
    games.write(RANDOM, TOOLS, "0-1", attempts=[attempt("black", 2), attempt("black", 4), attempt("black", 6)],
                streaks={"black": 3}, time_used={"white": 0.1, "black": 15.0})
    games.write(TOOLS, RANDOM, "1-0", streaks={"white": 7})

    [comparison] = tools_comparison(tmp_path / "games")

    [column] = comparison.columns
    assert column.illegal_moves_per_game == 2 / 3
    assert column.median_legal_move_streak == 3
    assert column.time_used_per_move_s == 45.0 / 6


def test_under_blind_enforced_the_illegal_moves_and_the_legal_move_streak_are_not_applicable(tmp_path):
    games = Games(tmp_path / "games")
    enforced = TOOLS | {"llm_constraints": "blind_enforced"}
    games.write(enforced, RANDOM, "1-0", attempts=[attempt("white", 1)])

    [comparison] = tools_comparison(tmp_path / "games")

    [column] = comparison.columns
    assert column.illegal_moves_per_game is None
    assert column.median_legal_move_streak is None
    assert "| illegal moves per game | n/a |" in markdown([comparison], date(2026, 10, 24))
    assert "| median Legal-move streak | n/a |" in markdown([comparison], date(2026, 10, 24))


def test_tool_use_counts_calls_per_attempt_each_tools_share_the_cap_no_calls_and_calls_as_text(tmp_path):
    games = Games(tmp_path / "games")
    capped = QWEN | {"tools": ["board", "legal_moves"], "tool_call_cap": 2}
    games.write(capped, RANDOM, "1-0", attempts=[
        attempt("white", 1, tool_calls=["board", "board"]),  # at the cap
        attempt("white", 3, tool_calls=["legal_moves"]),
        attempt("white", 5, "illegal", as_text=True),  # no call: it wrote one as text
        attempt("white", 5, number=2),
    ])
    games.write(QWEN, RANDOM, "1-0", attempts=[attempt("white", 1)])

    [comparison] = tools_comparison(tmp_path / "games")

    no_tools, tools = comparison.columns
    use = tools.tool_use
    assert (use.attempts, use.calls_per_attempt) == (4, 3 / 4)
    assert dict(use.attempts_using) == {"board": 1, "legal_moves": 1}
    assert (use.attempts_at_cap, use.attempts_without_tool_call, use.tool_calls_as_text) == (1, 2, 1)
    assert no_tools.tool_use.attempts == 0
    report = markdown([comparison], date(2026, 10, 24))
    assert "| | no tools | board+legal_moves, cap 2 |" in report
    assert "| attempts using board | - | 1 (25%) |" in report
    assert "| attempts using material | - | - |" in report  # not one of its tools
    assert "| attempts with no tool call | - | 2 (50%) |" in report


def test_each_tool_set_has_its_own_rating_from_the_anchored_results(tmp_path):
    games = Games(tmp_path / "games")
    for _ in range(2):
        games.write(QWEN, dragon(1), "1-0")
        games.write(dragon(1), QWEN, "1-0")
        games.write(TOOLS, RANDOM, "0-1")
        games.write(RANDOM, TOOLS, "1-0")

    [comparison] = tools_comparison(tmp_path / "games")

    no_tools, tools = comparison.columns
    assert no_tools.rating is not None and no_tools.rating.estimate is not None
    assert tools.rating is not None and tools.rating.estimate is None  # lost every game: an upper bound
    assert tools.rating.high is not None and tools.rating.high < no_tools.rating.estimate


def test_head_to_head_is_the_faceoff_score_of_a_tool_set_against_no_tools(tmp_path):
    games = Games(tmp_path / "games")
    games.write(TOOLS, QWEN, "1-0")
    games.write(QWEN, TOOLS, "1-0")
    games.write(TOOLS, QWEN, "1/2-1/2", "move_cap")
    games.write(TOOLS, LLAMA, "1-0")  # another model: not head to head
    games.write(TOOLS, TOOLS, "1-0")

    [comparison] = tools_comparison(tmp_path / "games")

    [match] = comparison.head_to_head
    assert (match.column.label(), match.wins, match.draws, match.losses) == ("all four", 1, 1, 1)
    assert "- all four vs no tools: 1 W · 1 D · 1 L, 1.5 - 1.5 in 3 games" in markdown([comparison], date(2026, 10, 24))


def test_the_markdown_has_a_section_for_each_model(tmp_path):
    games = Games(tmp_path / "games")
    games.write(TOOLS, RANDOM, "1-0", time_used={"white": 12.0, "black": 0.0}, attempts=[attempt("white", 1)])
    games.write(TOOLS | {"model": "qwen3.8:latest"}, RANDOM, "1-0")

    report = markdown(tools_comparison(tmp_path / "games"), date(2026, 10, 24))

    assert report.startswith("# Tools comparison, 2026-10-24\n")
    assert report.index("## qwen3.5:9b") < report.index("## qwen3.8:latest")
    assert "free / thinking / standard / explained feedback / 5 attempts per turn" in report
    assert "| Time used per move | 12.0 s |" in report
    assert "- all four vs no tools: no games" in report
