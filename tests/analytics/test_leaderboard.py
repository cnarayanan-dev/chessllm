import json

import pytest
from fastapi.testclient import TestClient

from chessllm.analytics.leaderboard import side_outcome
from chessllm.api.app import create_app

PROMPT = "/somewhere/chessllm/prompts/system.txt"
LLAMA = {"player": "llm", "model": "llama3:8b", "thinking": False, "llm_constraints": "free", "retry_feedback": "explained"}
QWEN = LLAMA | {"model": "qwen3.5:9b", "thinking": True}
HUMAN = {"player": "human"}


def stats(streak=0, enforced=False):
    if enforced:
        return {"legal_move_streak": None, "illegal_moves": None, "recovered_turns": None, "notation_slips": 0}
    return {
        "legal_move_streak": streak,
        "illegal_moves": {"invalid": 0, "illegal": 0, "ambiguous": 0},
        "recovered_turns": 0,
        "notation_slips": 0,
    }


def write_log(games_dir, name, events):
    games_dir.mkdir(parents=True, exist_ok=True)
    path = games_dir / f"{name}.jsonl"
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def attempt(color, result):
    return {"type": "llm_attempt", "color": color, "move": "e4", "result": result}


def game(
    white,
    black,
    result,
    reason="checkmate",
    attempts=None,
    streaks=None,
    mode=None,
    sampling="model_default",
    rules=None,
    ended=True,
):
    """A version 2 game log: game_start, the LLM attempts given as {color: [result, ...]}, and game_end."""
    mode = mode or ("play_llm" if HUMAN in (white, black) else "llm_faceoff")
    sides = {"white": white, "black": black}
    llms = [color for color, side in sides.items() if side["player"] == "llm"]
    prompts = {"prompt_file": PROMPT} if mode == "play_llm" else {"prompt_files": dict.fromkeys(llms, PROMPT)}
    start = {
        "type": "game_start",
        "game_id": "x",
        "log_version": 2,
        "mode": mode,
        "white": white,
        "black": black,
        "sampling": sampling,
        "max_retries": 3,
        **prompts,
        **({"rules": rules} if rules else {}),
        "started_at": "2026-10-19T10:00:00+02:00",
    }
    moves = [attempt(color, outcome) for color, outcomes in (attempts or {}).items() for outcome in outcomes]
    enforced = {color: sides[color]["llm_constraints"].endswith("enforced") for color in llms}
    end_stats = {
        color: stats((streaks or {}).get(color, 0), enforced[color]) if color in llms else None for color in sides
    }
    end = {"type": "game_end", "result": result, "reason": reason, "plies": 10, "stats": end_stats}
    return [start, *moves, *([end] if ended else [])]


@pytest.fixture
def leaderboard(tmp_path):
    """Writes the given game logs into a temporary games directory and returns the leaderboard the API makes of them."""

    def make(*games) -> list[dict]:
        games_dir = tmp_path / "games"
        for number, events in enumerate(games):
            write_log(games_dir, f"2026-10-19T10-00-{number:02d}_game", events)
        client = TestClient(create_app(lambda settings, color: None, games_dir=games_dir))
        response = client.get("/api/leaderboard")
        assert response.status_code == 200, response.text
        return response.json()["configurations"]

    return make


def by_model(configurations):
    return {(c["configuration"]["model"], c["configuration"]["llm_constraints"]): c for c in configurations}


def test_games_with_identical_llm_settings_are_one_player_configuration(leaderboard):
    configurations = leaderboard(
        game(HUMAN, LLAMA, "1-0"),
        game(LLAMA, HUMAN, "1-0"),
        game(HUMAN, LLAMA | {"llm_constraints": "listed"}, "0-1"),
    )

    assert len(configurations) == 2
    free, listed = by_model(configurations)[("llama3:8b", "free")], by_model(configurations)[("llama3:8b", "listed")]
    assert free["configuration"] == {
        "model": "llama3:8b",
        "thinking": False,
        "llm_constraints": "free",
        "rules": "standard",
        "retry_feedback": "explained",
        "max_retries": 3,
        "sampling": {},
        "prompt": "system.txt",
    }
    assert (free["games"], free["wins"], free["draws"], free["losses"]) == (2, 1, 0, 1)
    assert (listed["games"], listed["wins"]) == (1, 1)
    assert free["id"] != listed["id"]


def with_start(events, **fields):
    """The game with fields changed in its game_start."""
    start, *rest = events
    return [start | fields, *rest]


@pytest.mark.parametrize(
    "other",
    [
        game(HUMAN, LLAMA | {"thinking": True}, "1-0"),
        game(HUMAN, LLAMA | {"retry_feedback": "hinted"}, "1-0"),
        game(HUMAN, LLAMA | {"model": "gemma3:12b"}, "1-0"),
        game(HUMAN, LLAMA, "1-0", sampling={"temperature": 0.2}),
        game(HUMAN, LLAMA, "1-0", rules="chaos"),
        with_start(game(HUMAN, LLAMA, "1-0"), prompt_file="/somewhere/chessllm/prompts/other.txt"),
    ],
    ids=["thinking", "retry_feedback", "model", "sampling", "rules", "prompt"],
)
def test_games_differing_in_any_setting_are_different_player_configurations(leaderboard, other):
    configurations = leaderboard(game(HUMAN, LLAMA, "1-0"), other)

    assert [c["games"] for c in configurations] == [1, 1]


def test_the_same_prompt_file_in_another_checkout_is_the_same_player_configuration(leaderboard):
    moved = with_start(game(HUMAN, LLAMA, "1-0"), prompt_file="/elsewhere/chessllm/prompts/system.txt")

    [configuration] = leaderboard(game(HUMAN, LLAMA, "1-0"), moved)

    assert configuration["games"] == 2


def test_chaos_rules_and_sampling_are_part_of_the_player_configuration(leaderboard):
    [configuration] = leaderboard(game(HUMAN, LLAMA, "1-0", rules="chaos", sampling={"temperature": 0.2, "top_k": 40}))

    assert configuration["configuration"]["rules"] == "chaos"
    assert configuration["configuration"]["sampling"] == {"temperature": 0.2, "top_k": 40}


def test_both_llm_sides_of_a_faceoff_count_each_towards_its_own_configuration(leaderboard):
    configurations = by_model(leaderboard(game(QWEN, LLAMA, "1-0"), game(LLAMA, QWEN, "1/2-1/2", reason="stalemate")))

    qwen, llama = configurations[("qwen3.5:9b", "free")], configurations[("llama3:8b", "free")]
    assert (qwen["wins"], qwen["draws"], qwen["losses"]) == (1, 1, 0)
    assert (llama["wins"], llama["draws"], llama["losses"]) == (0, 1, 1)
    assert qwen["opponents"] == [{"opponent": llama["id"], "games": 2, "wins": 1, "draws": 1, "losses": 0}]
    assert llama["opponents"] == [{"opponent": qwen["id"], "games": 2, "wins": 0, "draws": 1, "losses": 1}]


def test_a_faceoff_of_one_configuration_against_itself_counts_a_game_for_each_side(leaderboard):
    [llama] = leaderboard(game(LLAMA, LLAMA, "0-1"))

    assert (llama["games"], llama["wins"], llama["losses"]) == (2, 1, 1)
    assert llama["opponents"] == [{"opponent": llama["id"], "games": 2, "wins": 1, "draws": 0, "losses": 1}]


def test_results_against_a_human_name_the_opponent_human(leaderboard):
    configurations = by_model(leaderboard(game(HUMAN, LLAMA, "1-0"), game(QWEN, LLAMA, "0-1")))

    llama, qwen = configurations[("llama3:8b", "free")], configurations[("qwen3.5:9b", "free")]
    assert sorted(llama["opponents"], key=lambda results: results["opponent"] == "human") == [
        {"opponent": qwen["id"], "games": 1, "wins": 1, "draws": 0, "losses": 0},
        {"opponent": "human", "games": 1, "wins": 0, "draws": 0, "losses": 1},
    ]


def test_results_forfeits_legal_moves_attempts_and_the_average_streak_add_up(leaderboard):
    [llama] = leaderboard(
        game(HUMAN, LLAMA, "0-1", attempts={"black": ["legal"] * 4}, streaks={"black": 4}),
        game(HUMAN, LLAMA, "1-0", "forfeit", attempts={"black": ["legal", "illegal", "invalid"]}, streaks={"black": 1}),
        game(LLAMA, HUMAN, "1/2-1/2", "stalemate", attempts={"white": ["illegal", "legal", "timeout"]}),
        game(LLAMA, HUMAN, "0-1", "checkmate", attempts={"white": ["legal", "legal"]}, streaks={"white": 2}),
    )

    assert (llama["games"], llama["wins"], llama["draws"], llama["losses"]) == (4, 1, 1, 2)
    assert llama["score"] == 0.375
    assert llama["forfeits"] == 1
    assert (llama["legal_moves"], llama["attempts"]) == (8, 12)
    assert llama["average_legal_move_streak"] == 1.75


def test_a_win_by_the_opponents_forfeit_is_not_a_forfeit(leaderboard):
    [qwen, llama] = sorted(leaderboard(game(QWEN, LLAMA, "1-0", "forfeit")), key=lambda c: c["wins"], reverse=True)

    assert (qwen["wins"], qwen["forfeits"], llama["losses"], llama["forfeits"]) == (1, 0, 1, 1)


def test_attempts_and_the_streak_are_null_under_enforced_decoding(leaderboard):
    enforced = LLAMA | {"llm_constraints": "listed_enforced"}

    [llama] = leaderboard(game(HUMAN, enforced, "0-1", attempts={"black": ["legal"] * 5}))

    assert (llama["legal_moves"], llama["attempts"], llama["average_legal_move_streak"]) == (5, None, None)


def v1_game(llm_color, result, reason, attempts, end_stats, constraints_key="mode", constraints="free"):
    """A version 1 game log: one LLM at llm_color with its settings at the top level, the human on the other side.
    Early version 1 logs called the LLM constraints `mode`, later ones `llm_constraints`."""
    start = {
        "type": "game_start",
        "game_id": "x",
        "model": "llama3:8b",
        "llm_color": llm_color,
        constraints_key: constraints,
        "thinking": False,
        "sampling": "model_default",
        "retry_feedback": "explained",
        "max_retries": 3,
        "prompt_file": PROMPT,
        "started_at": "2026-10-18T21:22:15+02:00",
    }
    moves = [{"type": "llm_attempt", "ply": 2, "attempt": 1, "move": "e5", "result": outcome} for outcome in attempts]
    end = {"type": "game_end", "result": result, "reason": reason, "plies": 41, **end_stats}
    return [start, {"type": "human_move", "ply": 1, "move": "e4"}, *moves, end]


def test_version_1_logs_are_read_with_their_mode_as_the_llm_constraints(leaderboard):
    configurations = leaderboard(
        v1_game("black", "1-0", "forfeit", ["legal", "illegal", "illegal"], stats(1)),
        v1_game("black", "0-1", "checkmate", ["legal"] * 3, stats(3), constraints_key="llm_constraints"),
        game(HUMAN, LLAMA, "1/2-1/2", "stalemate", attempts={"black": ["legal"]}, streaks={"black": 2}),
    )

    [llama] = configurations
    assert llama["configuration"]["llm_constraints"] == "free"
    assert (llama["games"], llama["wins"], llama["draws"], llama["losses"], llama["forfeits"]) == (3, 1, 1, 1, 1)
    assert (llama["legal_moves"], llama["attempts"]) == (5, 7)
    assert llama["average_legal_move_streak"] == 2
    assert llama["opponents"] == [{"opponent": "human", "games": 3, "wins": 1, "draws": 1, "losses": 1}]


def test_a_version_1_llm_playing_white_under_enforced_decoding(leaderboard):
    log = v1_game("white", "1-0", "checkmate", ["legal"] * 4, stats(enforced=True), "llm_constraints", "blind_enforced")

    [llama] = leaderboard(log)

    assert llama["configuration"]["llm_constraints"] == "blind_enforced"
    assert (llama["wins"], llama["legal_moves"], llama["attempts"], llama["average_legal_move_streak"]) == (
        1,
        4,
        None,
        None,
    )


def test_the_leaderboard_is_the_same_whatever_order_the_games_are_in(leaderboard, tmp_path):
    games = [
        game(QWEN, LLAMA, "1-0", attempts={"white": ["legal"], "black": ["illegal", "legal"]}, streaks={"white": 1}),
        game(HUMAN, LLAMA, "0-1", sampling={"temperature": 0.2}),
        v1_game("black", "1-0", "forfeit", ["illegal"] * 4, stats(0)),
        game(LLAMA | {"llm_constraints": "listed_enforced"}, HUMAN, "1/2-1/2", "stalemate"),
        game(HUMAN, QWEN, "1-0", rules="chaos"),
        game(HUMAN, LLAMA, "1-0", streaks={"black": 3}),
    ]

    forwards = leaderboard(*games)
    for path in (tmp_path / "games").iterdir():
        path.unlink()
    backwards = leaderboard(*reversed(games))

    assert backwards == forwards
    assert len(forwards) == 5


def test_unfinished_games_and_files_that_are_not_game_logs_are_left_out(leaderboard, tmp_path):
    games_dir = tmp_path / "games"
    games_dir.mkdir()
    (games_dir / "2026-10-19T09-00-00_human_vs_llama3-8b.pgn").write_text('[Result "1-0"]\n\n1-0\n')
    (games_dir / "2026-10-19T09-00-00_human_vs_llama3-8b.analysis.jsonl").write_text('{"type": "analysis"}\n')
    (games_dir / "2026-10-19T09-00-00_human_vs_llama3-8b.analysis.json").write_text('{"type": "game_end"}\n')
    (games_dir / "notes.jsonl").write_text("not json\n")

    [llama] = leaderboard(game(HUMAN, LLAMA, "1-0"), game(HUMAN, LLAMA, "0-1", ended=False))

    assert llama["games"] == 1


def test_no_games_make_an_empty_leaderboard(tmp_path):
    client = TestClient(create_app(lambda settings, color: None, games_dir=tmp_path / "no-games-yet"))

    assert client.get("/api/leaderboard").json() == {"configurations": []}


@pytest.mark.parametrize(
    "result, white, black",
    [("1-0", "win", "loss"), ("0-1", "loss", "win"), ("1/2-1/2", "draw", "draw")],
)
def test_a_sides_outcome_is_read_from_the_result_from_its_own_side(result, white, black):
    assert (side_outcome(result, "white"), side_outcome(result, "black")) == (white, black)
