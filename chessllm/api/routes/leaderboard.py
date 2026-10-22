from fastapi import APIRouter

from chessllm.analytics.leaderboard import Leaderboard, leaderboard
from chessllm.api.deps import ConfigDep

router = APIRouter()


@router.get("/api/leaderboard")
def get_leaderboard(config: ConfigDep) -> Leaderboard:
    """Every finished game's results, grouped by Player configuration, read from the game logs."""
    return leaderboard(config.games_dir, config.move_quality_validation)
