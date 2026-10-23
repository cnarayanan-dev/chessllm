"""Synthetic finished games for the analytics page's Playwright journey (frontend/e2e/analytics.e2e.ts), written by
the e2e server (tests/e2e/server.py) on POST /e2e/ranking-games. Every game is under the Reference configuration but
the last model's:

- qwen3.5:9b: rated from Anchor matches against Dragon (10 · 1 · 9), with an unvalidated Move-quality estimate from
  its first five games' analysis files
- llama3:8b: lost every anchored game (10, 4 of them by Forfeit), so "< X", and two LLM faceoffs to gemma3:12b
- gemma3:12b: those two faceoff wins only, so no path to an Anchor
- mistral:7b: Play LLM games only (2 · 0 · 3), so no Rating, with an unvalidated Move-quality estimate from its
  first two
- gemma4:26b: Anchor match wins with thinking on under Listed enforced only, so no games under the Reference
  configuration"""

import json
import math
from pathlib import Path
from typing import Any

from tests.analytics.test_leaderboard import HUMAN, LLAMA, game, write_log
from tests.analytics.test_ranking import QWEN_OFF, anchor_games, faceoff_games, reference

GEMMA = LLAMA | {"model": "gemma3:12b"}
MISTRAL = LLAMA | {"model": "mistral:7b"}
GEMMA4_ENFORCED = LLAMA | {"model": "gemma4:26b", "thinking": True, "llm_constraints": "listed_enforced"}
MOVE_MODEL_GRID = list(range(1000, 2001, 100))


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
    qwen = [*anchor_games(QWEN_OFF, 1, wins=7, losses=3), *anchor_games(QWEN_OFF, 3, wins=3, draws=1, losses=6)]
    llama = anchor_games(LLAMA, 1, losses=6, forfeits=4)
    faceoffs = faceoff_games(GEMMA, LLAMA, wins=2)
    mistral = [reference(game(HUMAN, MISTRAL, result)) for result in ["1-0", "0-1", "1-0", "0-1", "1-0"]]
    gemma4 = anchor_games(GEMMA4_ENFORCED, 7, wins=4)
    games = [*qwen, *llama, *faceoffs, *mistral, *gemma4]
    for number, events in enumerate(games):
        name = f"2026-10-19T10-00-{number:02d}_game"
        write_log(games_dir, name, events)
        analysis = None
        if number < 5:  # the first five qwen games
            analysis = move_quality_analysis("white" if events[0]["white"] == QWEN_OFF else "black", 1400, 30)
        elif any(events is first for first in mistral[:2]):  # the human plays White
            analysis = move_quality_analysis("black", 1200, 30)
        if analysis is not None:
            (games_dir / f"{name}.analysis.json").write_text(json.dumps(analysis), encoding="utf-8")
