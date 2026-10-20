"""Thinking budget: in the benchmark only, a thinking LLM side can have a budget of tokens per attempt, after which
the Ollama player makes it answer (ADR 0007). It reaches the side's player, is logged when set, and is part of the
Player configuration."""

import json

import pytest
from ollama import ChatResponse
from ollama import Message as OllamaMessage

from conftest import ScriptedPlayer, play_llm

from chessllm.__main__ import player_for
from chessllm.faceoff_batch import main
from chessllm.game import BenchmarkLlmSide, LlmSide, Settings
from chessllm.leaderboard import llm_configuration
from chessllm.ollama_player import OllamaPlayer

FOOLS_MATE = ["f3", "e5", "g4", "Qh4#"]
# How an LLM side's game_start entry has looked since log version 2 with the default position (ADR 0004).
PLAIN_SIDE_KEYS = {"player", "model", "thinking", "llm_constraints", "retry_feedback"}
QWEN = "qwen3.8:latest"


def faceoff(tmp_path, *args: str, player_for=None) -> tuple[int, ScriptedPlayer]:
    player = ScriptedPlayer(FOOLS_MATE)
    code = main(
        ["--games", "1", *args, "--games-dir", str(tmp_path), "--no-analysis"],
        player_for=player_for or player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )
    return code, player


def game_log(tmp_path) -> list[dict]:
    [log] = tmp_path.glob("*.jsonl")
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_a_budget_given_for_one_model_reaches_only_its_side_and_is_logged(tmp_path):
    code, player = faceoff(
        tmp_path, "--models", QWEN, "gemma3:12b", "--thinking-for", QWEN, "--thinking-budget-for", f"{QWEN}=3072"
    )

    assert code == 0
    start = game_log(tmp_path)[0]
    assert (start["white"]["thinking"], start["white"]["thinking_budget"]) == (True, 3072)
    assert "thinking_level" not in start["white"]
    assert set(start["black"]) == PLAIN_SIDE_KEYS
    settings = player.built_for[0]
    assert (settings.white.thinking_budget, settings.black.thinking_budget) == (3072, None)


@pytest.mark.parametrize(
    ("model", "budget", "time_limit_s"),
    [
        # 60 s for the prompt, a re-prefill and a model swap, plus the budget at 1.5 times its time at the model's speed.
        (QWEN, 3072, 316.0),  # 60 + 1.5 × 3072 / 18
        ("gemma4:26b", 6144, 316.0),  # 60 + 1.5 × 6144 / 36
        ("qwen3.5:9b", 1024, 300.0),  # never below the five minutes without a budget
        ("qwen3.5:9b", None, 300.0),
    ],
)
def test_the_player_is_built_with_the_budget_and_a_time_limit_derived_from_it(model, budget, time_limit_s):
    side = BenchmarkLlmSide(model=model, thinking=True, thinking_budget=budget)
    settings = Settings("llm_faceoff", side, LlmSide(model="gemma3:12b"))

    player = player_for(settings, "white")

    assert (player.budget, player.timeout_s) == (budget, time_limit_s)
    assert (player_for(settings, "black").budget, player_for(settings, "black").timeout_s) == (None, 300.0)


def attempts(tmp_path, color: str) -> list[dict]:
    return [event for event in game_log(tmp_path) if event["type"] == "llm_attempt" and event["color"] == color]


def test_each_attempt_logs_whether_its_answer_was_forced(tmp_path):
    player = ScriptedPlayer(FOOLS_MATE)
    player.usage = [{"forced": True, "stop_reason": "stop"}, {}, {}, {}]

    faceoff(tmp_path, "--models", QWEN, "gemma3:12b", "--thinking-for", QWEN, "--thinking-budget-for", f"{QWEN}=256",
            player_for=player.for_settings)

    first, second = attempts(tmp_path, "white")
    assert (first["forced"], first["result"]) == (True, "legal")
    assert "forced" not in second  # left out when not forced, so attempts without a budget log as before


def ollama_chat(*responses: ChatResponse):
    replies = list(responses)
    return lambda **request: replies.pop(0)


def answer(content: str, thinking: str | None = None, **counts) -> ChatResponse:
    return ChatResponse(message=OllamaMessage(role="assistant", content=content, thinking=thinking), **counts)


def test_a_forced_answer_cut_off_too_is_its_own_result_and_gets_a_retry_with_a_fresh_budget(tmp_path):
    chat = ollama_chat(
        answer("", "f3 or", eval_count=256, done_reason="length"),
        answer(' {"mo', eval_count=64, done_reason="length"),  # the forced answer is cut off too
        answer('{"move": "f3"}', "f3.", eval_count=40, done_reason="stop"),  # the retry, within its own budget
        answer('{"move": "g4"}', "g4.", eval_count=40, done_reason="stop"),
    )
    black = ScriptedPlayer(["e5", "Qh4#"])

    def player_for(settings, color):
        side = settings.side(color)
        if color == "black":
            return black
        return OllamaPlayer(side.model, side.think(), chat=chat, budget=side.thinking_budget)

    code, _ = faceoff(tmp_path, "--models", QWEN, "gemma3:12b", "--thinking-for", QWEN,
                      "--thinking-budget-for", f"{QWEN}=256", player_for=player_for)

    assert code == 0
    cut, retry, _ = attempts(tmp_path, "white")
    assert (cut["result"], cut["forced"], cut["stop_reason"]) == ("cut_off", True, "length")
    assert retry["result"] == "legal" and "cut off" in retry["feedback_sent"]
    end = game_log(tmp_path)[-1]
    # Not an illegal move: the legal-move metrics stay as if the turn had been answered at once.
    assert end["stats"]["white"]["illegal_moves"] == {"invalid": 0, "illegal": 0, "ambiguous": 0}
    assert (end["stats"]["white"]["legal_move_streak"], end["stats"]["white"]["recovered_turns"]) == (2, 0)


def test_a_budget_is_its_own_player_configuration_and_no_budget_keeps_its_id(tmp_path):
    faceoff(tmp_path / "budget", "--models", QWEN, "gemma3:12b", "--thinking-for", f"{QWEN}=xhigh",
            "--thinking-budget-for", f"{QWEN}=3072")
    faceoff(tmp_path / "none", "--models", QWEN, "gemma3:12b", "--thinking-for", f"{QWEN}=xhigh")

    budgeted, unbudgeted = game_log(tmp_path / "budget")[0], game_log(tmp_path / "none")[0]
    with_budget = llm_configuration(budgeted, "white", budgeted["white"])
    without = llm_configuration(unbudgeted, "white", unbudgeted["white"])
    # The id an xhigh side had before budgets existed, from a log of that time.
    before = llm_configuration(budgeted, "white", {k: v for k, v in budgeted["white"].items() if k != "thinking_budget"})
    assert without.id() == before.id()
    assert with_budget.id() != without.id()
    assert (with_budget.thinking_budget, without.thinking_budget) == (3072, None)


def test_the_pgn_names_the_budget(tmp_path):
    faceoff(tmp_path, "--models", QWEN, "gemma3:12b", "--thinking-for", QWEN, "--thinking-budget-for", f"{QWEN}=3072")

    [pgn] = tmp_path.glob("*.pgn")
    assert '[White "qwen3.8:latest (thinking, budget 3072)"]' in pgn.read_text()


def test_the_api_refuses_a_budget(scripted):
    client, player = scripted([])

    refused = client.post("/api/games", json=play_llm(model=QWEN, thinking=True, thinking_budget=1024))

    assert refused.status_code == 422 and "thinking_budget" in refused.text
    assert not player.built_for


def test_the_leaderboard_shows_a_budgets_configuration_without_the_budget_under_its_own_id(scripted, tmp_path):
    faceoff(tmp_path / "games", "--models", QWEN, "gemma3:12b", "--thinking-for", QWEN,
            "--thinking-budget-for", f"{QWEN}=3072")
    faceoff(tmp_path / "games", "--models", QWEN, "gemma3:12b", "--thinking-for", QWEN)
    client, _ = scripted([], games_dir=tmp_path / "games")

    configurations = client.get("/api/leaderboard").json()["configurations"]

    qwen = [entry for entry in configurations if entry["configuration"]["model"] == QWEN]
    assert len(qwen) == 2 and qwen[0]["id"] != qwen[1]["id"]
    assert qwen[0]["configuration"] == qwen[1]["configuration"]
    assert "thinking_budget" not in qwen[0]["configuration"]


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (["--thinking-budget-for", f"{QWEN}=1024"], f"{QWEN} (white) has a Thinking budget, so thinking must be on"),
        (
            ["--thinking-for", QWEN, "--thinking-budget-for", f"{QWEN}=32"],
            f"{QWEN} (white) has a Thinking budget of 32 tokens, too few to hold an answer: at least 64",
        ),
        (
            ["--thinking-for", QWEN, "--thinking-budget-for", f"{QWEN}=8192"],
            f"{QWEN} (white) has a Thinking budget of 8192 tokens, too many for its 8,192-token context: at most 6144",
        ),
        (
            ["--thinking-for", QWEN, "--thinking-budget-for", f"{QWEN}=1024", "--thinking-budget-for", f"{QWEN}=2048"],
            f"--thinking-budget-for gives {QWEN} two Thinking budgets, 1024 and 2048",
        ),
    ],
)
def test_a_budget_that_cant_work_is_refused_before_any_game(tmp_path, capsys, args, reason):
    code, player = faceoff(tmp_path, "--models", QWEN, "gemma3:12b", *args)

    assert code == 1
    assert reason in capsys.readouterr().err
    assert not list(tmp_path.glob("*.jsonl")) and not player.built_for
