from typing import Annotated

from fastapi import APIRouter, Query

from chessllm.analytics.ranking import ALL_MODES, Ranking, ranking
from chessllm.api.deps import ConfigDep
from chessllm.core.types import ModeKey

router = APIRouter()


@router.get("/api/ranking")
def get_ranking(config: ConfigDep, modes: Annotated[list[ModeKey] | None, Query()] = None) -> Ranking:
    """The models ranked by their Rating under the Reference configuration, read from the game logs. modes narrows
    it to those Modes' games, every number refitted from them alone; all Modes when left out."""
    return ranking(config.games_dir, modes or ALL_MODES, config.move_quality_validation)
