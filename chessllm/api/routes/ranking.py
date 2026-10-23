from typing import Annotated

from fastapi import APIRouter, Query

from chessllm.analytics.ranking import ALL_MODES, Ranking, ranking
from chessllm.api.deps import ConfigDep
from chessllm.core.types import ModeKey

router = APIRouter()


@router.get("/api/ranking")
def get_ranking(config: ConfigDep, mode: Annotated[list[ModeKey] | None, Query()] = None) -> Ranking:
    """Every model by its Rating under the Reference configuration, read from the game logs. With mode given, once
    for each Mode, every number comes from those Modes' games alone; without, from every Mode's."""
    return ranking(config.games_dir, mode or ALL_MODES, config.move_quality_validation)
