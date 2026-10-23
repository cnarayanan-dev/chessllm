"""Synthetic finished games for the analytics page's Playwright journey (frontend/e2e/analytics.e2e.ts), written by
the e2e server (tests/e2e/server.py) on POST /e2e/ranking-games. Five models, all under the Reference configuration
but phi4:

- qwen3.5:9b: rated from Anchor matches against Dragon (10 · 1 · 9), with an unvalidated Move-quality estimate from
  its first five games' analysis files
- llama3:8b: lost every anchored game (10, 4 of them by Forfeit), so "< X"; and lost 4 LLM faceoffs to gemma3:12b
- gemma3:12b: those 4 LLM faceoffs only, which lead to no Anchor, so no Rating
- mistral:7b: Play LLM games only (0 · 0 · 25), so no Rating
- phi4:14b: Anchor matches under Listed only, none under the Reference configuration, so listed last"""

import json
import math
from pathlib import Path
from typing import Any

from tests.analytics.test_leaderboard import HUMAN, LLAMA, game, with_start, write_log

QWEN = LLAMA | {"model": "qwen3.5:9b"}
GEMMA = LLAMA | {"model": "gemma3:12b"}
MISTRAL = LLAMA | {"model": "mistral:7b"}
PHI_LISTED = LLAMA | {"model": "phi4:14b", "llm_constraints": "listed"}
MOVE_MODEL_GRID = list(range(1000, 2001, 100))

Events = list[dict[str, Any]]


def dragon(skill: int) -> dict[str, Any]:
    return {"player": "anchor", "engine": "dragon", "skill": skill}


def reference(events: Events) -> Events:
    """The game with 5 attempts a turn, as the Reference configuration has it."""
    return with_start(events, max_retries=4)


def against_dragon(llm: dict[str, Any], skill: int, outcomes: list[str]) -> list[Events]:
    """Anchor match games with these outcomes ("win", "draw", "loss", "forfeit") of the LLM, colours alternating."""
    games = []
    for number, outcome in enumerate(outcomes):
        llm_white = number % 2 == 0
        white, black = (llm, dragon(skill)) if llm_white else (dragon(skill), llm)
        result = "1/2-1/2" if outcome == "draw" else "1-0" if (outcome == "win") == llm_white else "0-1"
        reason = {"draw": "move_cap", "forfeit": "forfeit"}.get(outcome, "checkmate")
        games.append(reference(game(white, black, result, reason, mode="anchor_match")))
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


def write_ranking_games(games_dir: Path) -> None:
    """Replaces every file in games_dir (game logs, PGNs, analysis files) with the games above."""
    for old in games_dir.glob("*"):
        old.unlink()
    qwen = [
        *against_dragon(QWEN, 1, ["win"] * 7 + ["loss"] * 3),
        *against_dragon(QWEN, 3, ["win"] * 3 + ["draw"] + ["loss"] * 6),
    ]
    llama = against_dragon(LLAMA, 1, ["loss"] * 6 + ["forfeit"] * 4)
    faceoffs = [reference(game(GEMMA, LLAMA, "1-0")), reference(game(LLAMA, GEMMA, "0-1"))] * 2
    mistral = [reference(game(HUMAN, MISTRAL, "1-0")) for _ in range(25)]
    phi = against_dragon(PHI_LISTED, 1, ["win"] * 5)
    for number, events in enumerate([*qwen, *llama, *faceoffs, *mistral, *phi]):
        name = f"2026-10-19T10-00-{number:02d}_game"
        write_log(games_dir, name, events)
        if number < 5:  # the first five qwen games
            color = "white" if events[0]["white"] == QWEN else "black"
            analysis = move_quality_analysis(color, 1400, 30)
            (games_dir / f"{name}.analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
