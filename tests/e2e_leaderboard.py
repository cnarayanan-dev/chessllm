"""Synthetic finished games for the analytics page's Playwright journey (frontend/e2e/analytics.e2e.ts), written by
the e2e server (tests/e2e_server.py) on POST /e2e/leaderboard-games. Three Player configurations:

- qwen3.5:9b, Listed enforced, thinking on: rated from Anchor matches against Dragon (10 · 1 · 9, 30 legal moves a
  game), with an unvalidated
  Move-quality estimate from its first five games' analysis files
- llama3:8b, Free: lost every anchored game (10, 4 of them by Forfeit), 3 legal moves in 4 attempts a game, so "< X"
- mistral:7b, Free, bare retry feedback: Play LLM games only (0 · 0 · 25), so no Rating"""

import json
import math
from pathlib import Path
from typing import Any

from tests.test_leaderboard import HUMAN, LLAMA, QWEN, game, write_log

QWEN_ENFORCED = QWEN | {"llm_constraints": "listed_enforced"}
MISTRAL_BARE = LLAMA | {"model": "mistral:7b", "retry_feedback": "bare"}
MOVE_MODEL_GRID = list(range(1000, 2001, 100))

Events = list[dict[str, Any]]


def dragon(skill: int) -> dict[str, Any]:
    return {"player": "anchor", "engine": "dragon", "skill": skill}


def against_dragon(
    llm: dict[str, Any], skill: int, outcomes: list[str], attempts: list[str] | None = None
) -> list[Events]:
    """Anchor match games with these outcomes ("win", "draw", "loss", "forfeit") of the LLM, colours alternating, each
    with the LLM's attempts given."""
    games = []
    for number, outcome in enumerate(outcomes):
        llm_white = number % 2 == 0
        color = "white" if llm_white else "black"
        white, black = (llm, dragon(skill)) if llm_white else (dragon(skill), llm)
        result = "1/2-1/2" if outcome == "draw" else "1-0" if (outcome == "win") == llm_white else "0-1"
        reason = {"draw": "move_cap", "forfeit": "forfeit"}.get(outcome, "checkmate")
        streak = attempts.index("illegal") if attempts and "illegal" in attempts else 0
        games.append(
            game(
                white,
                black,
                result,
                reason,
                attempts={color: attempts} if attempts else None,
                streaks={color: streak},
                mode="anchor_match",
            )
        )
    return games


def move_quality_analysis(color: str, peak: int, moves: int) -> dict[str, Any]:
    """An analysis file as a move model would write it: every move of the LLM side most likely for a player rated peak
    (Lichess Rapid)."""
    log_probabilities = [math.log(0.4) - ((rating - peak) / 400) ** 2 for rating in MOVE_MODEL_GRID]
    side = {
        "estimate": None,
        "interval": None,
        "moves": [
            {"ply": ply, "fen": "", "move": "e2e4", "log_probabilities": log_probabilities} for ply in range(moves)
        ],
    }
    return {
        "analysis_version": 1,
        "versions": {"move_model": "e2e move model"},
        "move_quality": {
            "scale": "lichess_rapid",
            "ratings": MOVE_MODEL_GRID,
            "sides": {other: side if other == color else None for other in ("white", "black")},
        },
    }


def write_leaderboard_games(games_dir: Path) -> None:
    """Replaces every file in games_dir (game logs, PGNs, analysis files) with the games above."""
    for old in games_dir.glob("*"):
        old.unlink()
    legal = ["legal"] * 30
    qwen = [
        *against_dragon(QWEN_ENFORCED, 1, ["win"] * 7 + ["loss"] * 3, legal),
        *against_dragon(QWEN_ENFORCED, 3, ["win"] * 3 + ["draw"] + ["loss"] * 6, legal),
    ]
    llama = against_dragon(LLAMA, 1, ["loss"] * 6 + ["forfeit"] * 4, ["legal", "legal", "legal", "illegal"])
    mistral = [game(HUMAN, MISTRAL_BARE, "1-0") for _ in range(25)]
    for number, events in enumerate([*qwen, *llama, *mistral]):
        name = f"2026-10-19T10-00-{number:02d}_game"
        write_log(games_dir, name, events)
        if number < 5:  # the first five qwen games
            color = "white" if events[0]["white"] == QWEN_ENFORCED else "black"
            analysis = move_quality_analysis(color, 1400, 30)
            (games_dir / f"{name}.analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
