"""The pure parts of the budget probe (scripts/probe_thinking_budget.py): loading the fixed positions, the grid of
conditions per model, one call judged and scored as the game would, resuming, and the summary table."""

import json

import chess
import httpx
from chess.engine import Cp
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from chessllm.game.llm_turn.prompt import LISTED_SYSTEM_PROMPT_FILE, system_prompt
from scripts.probe_board_images import Position
from scripts.probe_thinking_budget import (
    PASSES,
    POSITIONS_FILE,
    Condition,
    ask,
    condition_problem,
    done_keys,
    grid,
    into_note,
    pending,
    summary,
    listed_moves,
    load_positions,
)

AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"


class FakeEvaluator:
    """Stockfish's evaluations, relative to the side to move, by FEN; 0 for any other position."""

    def __init__(self, scores):
        self.scores = scores
        self.asked = []

    version = "Fake"
    search = {"depth": 1}

    def evaluate(self, fen):
        self.asked.append(fen)
        return Cp(self.scores.get(fen, 0))


def scripted(*replies):
    """A chat function that answers with the replies in turn and keeps every request."""
    calls = []

    def chat(**request):
        calls.append(request)
        reply = replies[len(calls) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    return chat, calls


def response(content="", thinking=None, done_reason="stop", eval_count=None, prompt_eval_count=None):
    message = OllamaMessage(role="assistant", content=content, thinking=thinking)
    return ChatResponse(message=message, done_reason=done_reason, eval_count=eval_count,
                        prompt_eval_count=prompt_eval_count)


def after(*moves):
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return board.fen()


def position(fen=AFTER_E4, pgn="1. e4", color="black", ply=2, phase="opening", in_check=False):
    return Position(fen, pgn, color, ply, phase, in_check, "game.jsonl")


def test_the_positions_are_the_board_image_studys_sixty_in_their_order(tmp_path):
    positions = load_positions(POSITIONS_FILE)
    frozen = json.loads(POSITIONS_FILE.read_text(encoding="utf-8"))

    assert POSITIONS_FILE.name == "board-images-positions.json"
    assert len(positions) == 60 == len({p.fen for p in positions})
    assert [p.fen for p in positions] == [row["fen"] for row in frozen]
    assert positions[1].fen == "r1bqkb1r/ppp2ppp/3p1n2/n3p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 6"
    small = tmp_path / "positions.json"
    small.write_text(json.dumps([position().__dict__]), encoding="utf-8")
    assert load_positions(small) == [position()]


def test_each_model_is_probed_off_unbounded_and_at_four_budgets_and_qwen38_also_at_xhigh():
    labels = {model: [c.label for c in grid(model)] for model in ("qwen3.5:9b", "qwen3.8:latest", "gemma4:26b")}

    assert labels["qwen3.5:9b"] == labels["gemma4:26b"] == ["off", "on", "on@512", "on@1024", "on@2048", "on@4096"]
    # qwen3.8's thinking on is sent as its level, medium, so it doesn't depend on Ollama's default.
    assert labels["qwen3.8:latest"] == [
        "off", "medium", "medium@512", "medium@1024", "medium@2048", "medium@4096", "xhigh@2048", "xhigh@4096",
    ]


def test_a_condition_reads_from_its_label_and_is_sent_as_the_game_would_send_it():
    assert Condition.parse("off") == Condition(False, None, None)
    assert Condition.parse("on@1024") == Condition(True, None, 1024)
    assert Condition.parse("xhigh@3072") == Condition(True, "xhigh", 3072)
    assert Condition.parse("medium").label == "medium"
    assert [Condition.parse(label).think for label in ("off", "on@512", "xhigh")] == [False, True, "xhigh"]


def test_a_condition_the_model_cant_take_is_refused_with_the_games_reason():
    assert condition_problem("qwen3.8:latest", Condition.parse("medium@3072")) is None
    assert condition_problem("qwen3.5:9b", Condition.parse("xhigh")) == (
        "qwen3.5:9b has no Thinking levels, only thinking on or off"
    )
    assert "no Thinking level high" in condition_problem("qwen3.8:latest", Condition.parse("high"))
    assert "too few to hold an answer" in condition_problem("gemma4:26b", Condition.parse("on@32"))
    assert "too many" in condition_problem("gemma4:26b", Condition.parse("on@8192"))
    assert "cannot think" in condition_problem("gemma3:12b", Condition.parse("on"))
    assert "not in the model list" in condition_problem("nope:1b", Condition.parse("off"))


def test_listed_enforced_shows_and_holds_the_legal_moves_and_scores_the_move_by_centipawn_loss():
    chat, calls = scripted(
        response(thinking="Nf6 develops.", done_reason="length", eval_count=512, prompt_eval_count=400),
        response('{"move": "Nf6"}', eval_count=8),
    )
    evaluator = FakeEvaluator({AFTER_E4: -30, after("e4", "Nf6"): 80})  # Black is 30 down, then 80 down

    row = ask(chat, "gemma4:26b", 7, position(), Condition.parse("on@512"), "listed_enforced", evaluator, {})

    first, forced = calls
    legal = sorted(chess.Board(AFTER_E4).san(m) for m in chess.Board(AFTER_E4).legal_moves)
    assert sorted(first["format"]["properties"]["move"]["enum"]) == legal
    assert first["messages"][0]["content"] == system_prompt("black", LISTED_SYSTEM_PROMPT_FILE)
    assert first["messages"][1]["content"].endswith(f"Legal moves: {' '.join(listed_moves(AFTER_E4))}")
    assert first["think"] is True and first["options"] == {"num_predict": 512}
    assert forced["format"] == first["format"]
    assert row["latency_s"] >= 0
    assert row | {"latency_s": 0} == {
        "model": "gemma4:26b", "condition": "on@512", "level": True, "budget": 512, "pass": "listed_enforced",
        "position": 7, "fen": AFTER_E4, "phase": "opening", "in_check": False,
        "raw": '{"move": "Nf6"}', "move": "Nf6", "result": "legal", "centipawn_loss": 50,
        "evaluation_before": -30, "evaluation_after": -80,
        "thinking_tokens": 512, "answer_tokens": 8, "prompt_tokens": 400, "stop_reason": "stop", "forced": True,
        "latency_s": 0, "time_limit_s": 300.0,
    }


def test_the_listed_order_is_shuffled_but_the_same_for_every_condition():
    board = chess.Board(AFTER_E4)

    shown = listed_moves(AFTER_E4)

    assert shown == listed_moves(AFTER_E4)
    assert sorted(shown) == sorted(board.san(m) for m in board.legal_moves)
    assert shown != [board.san(m) for m in board.legal_moves]


def test_free_shows_no_legal_moves_and_an_illegal_answer_gets_no_centipawn_loss():
    chat, calls = scripted(response('{"reasoning": "x", "move": "Ke2"}', eval_count=40, prompt_eval_count=300))
    evaluator = FakeEvaluator({})

    row = ask(chat, "qwen3.8:latest", 0, position(), Condition.parse("off"), "free", evaluator, {"temperature": 0.7})

    [request] = calls
    assert "enum" not in request["format"]["properties"]["move"]
    assert "Legal moves" not in request["messages"][1]["content"]
    assert request["think"] is False and request["options"] == {"temperature": 0.7}
    assert (row["result"], row["move"], row["centipawn_loss"], row["forced"]) == ("illegal", "Ke2", None, False)
    assert (row["level"], row["budget"], row["thinking_tokens"], row["answer_tokens"]) == (False, None, 0, 40)
    assert evaluator.asked == []


def test_a_forced_answer_cut_off_too_is_its_own_result_and_a_timeout_is_recorded():
    cut, _ = scripted(response(thinking="hmm", done_reason="length", eval_count=512),
                      response('{"move": "N', done_reason="length", eval_count=64))
    slow, _ = scripted(httpx.ReadTimeout("slow"))
    level = Condition.parse("xhigh@4096")

    cut_row = ask(cut, "qwen3.8:latest", 0, position(), Condition.parse("medium@512"), "free", FakeEvaluator({}), {})
    slow_row = ask(slow, "qwen3.8:latest", 0, position(), level, "listed_enforced", FakeEvaluator({}), {})

    assert (cut_row["result"], cut_row["forced"], cut_row["level"]) == ("cut_off", True, "medium")
    assert slow_row["result"] == "timeout" and slow_row["level"] == "xhigh" and slow_row["centipawn_loss"] is None
    assert slow_row["time_limit_s"] == 60 + 1.5 * 4096 / 18  # derived from the budget at qwen3.8's speed


def test_a_rerun_skips_the_calls_already_made_but_asks_again_after_an_error(tmp_path):
    first, second = position(), position(fen=after("e4", "e5"), pgn="1. e4 e5", color="white", ply=3)
    done = {"model": "gemma4:26b", "condition": "off", "pass": "free", "fen": AFTER_E4, "result": "legal"}
    rows = [
        done,
        done | {"pass": "listed_enforced", "result": "timeout"},  # a timeout is the condition's outcome: kept
        done | {"condition": "on", "result": "error"},  # Ollama wasn't there: asked again
    ]
    out = tmp_path / "results.jsonl"
    out.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    conditions = [Condition.parse("off"), Condition.parse("on")]

    calls = [(model, index, c.label, pass_) for model, index, _, c, pass_ in
             pending(["gemma4:26b"], conditions, [first, second], PASSES, done_keys(out))]

    # Position by position, so a run stopped anywhere leaves every condition on the same positions.
    assert calls == [
        ("gemma4:26b", 0, "on", "free"), ("gemma4:26b", 0, "on", "listed_enforced"),
        ("gemma4:26b", 1, "off", "free"), ("gemma4:26b", 1, "off", "listed_enforced"),
        ("gemma4:26b", 1, "on", "free"), ("gemma4:26b", 1, "on", "listed_enforced"),
    ]
    assert done_keys(tmp_path / "none.jsonl") == set()


def row(condition="on@512", pass_="free", result="legal", fen=AFTER_E4, **fields):
    return {"model": "gemma4:26b", "condition": condition, "pass": pass_, "fen": fen, "result": result,
            "centipawn_loss": None, "thinking_tokens": None, "forced": False, "latency_s": None,
            "time_limit_s": 300.0} | fields


def test_the_summary_has_a_line_per_model_and_condition_with_legality_quality_tokens_and_time():
    rows = [
        row(fen="a", result="error", error="connection refused"),  # asked again below: the latest row counts
        row(fen="a", thinking_tokens=200, latency_s=10),
        row(fen="b", result="illegal", thinking_tokens=300, latency_s=20),
        row(fen="c", result="timeout"),  # counted at its time limit
        row(fen="d", result="error"),  # never answered: left out
        row(pass_="listed_enforced", fen="a", centipawn_loss=10, thinking_tokens=512, forced=True, latency_s=30),
        row(pass_="listed_enforced", fen="b", centipawn_loss=250, thinking_tokens=100, latency_s=40),
        row(pass_="listed_enforced", fen="c", result="cut_off", thinking_tokens=512, forced=True, latency_s=50),
        row(condition="off", fen="a", thinking_tokens=0, latency_s=5),
        row(condition="off", pass_="listed_enforced", fen="a", centipawn_loss=0, thinking_tokens=0, latency_s=6),
    ]

    lines = summary(rows).splitlines()

    assert lines[2:] == [
        "| gemma4:26b | off | 1/1 (100%) | 0 (1) | 0 | 0 / 0 | 0% | 5.5 | 0 |",
        "| gemma4:26b | on@512 | 1/3 (33%) | 130 (2) | 1 | 300 / 512 | 40% | 35.0 | 2 |",
    ]
    assert lines[0].startswith("| Model | Condition | Free: legal first attempt | Listed enforced: mean centipawn")


def test_the_table_goes_between_the_notes_markers_and_replaces_what_was_there():
    note = "# Note\n\nBefore.\n<!-- budget-probe:start -->\nold\n<!-- budget-probe:end -->\nAfter.\n"

    written = into_note(note, "| new |")

    assert written == "# Note\n\nBefore.\n<!-- budget-probe:start -->\n| new |\n<!-- budget-probe:end -->\nAfter.\n"
    assert into_note(written, "| new |") == written
