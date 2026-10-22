"""Standard rules: the normal rules of chess, under which an illegal move is never played."""

from typing import Any

import chess

from chessllm.core.types import Color, RulesKey
from chessllm.game.ending import GameEnd
from chessllm.game.records import AttemptResult
from chessllm.game.rules.chaos import ResolvedMove
from chessllm.game.sides import AnchorSide, LlmSide


class StandardRules:
    """The default. They add nothing to a game's checks, logs or PGN, so a Standard rules game reads as it did before
    Chaos rules existed."""

    key: RulesKey = "standard"
    rated = True
    plays_illegal_moves = False

    def check_anchor(self, anchor: AnchorSide) -> None:
        pass

    def check_llm(self, color: Color, side: LlmSide) -> None:
        pass

    def resolve(self, board: chess.Board, written: str, result: AttemptResult) -> ResolvedMove | None:
        return None

    def end(self, board: chess.Board) -> GameEnd | None:
        return None

    def chaos_counts(self, chaos_moves: int, spawns: int) -> tuple[int | None, int | None]:
        return None, None

    def attempt_log_shape(self, shape: dict[str, Any]) -> dict[str, Any]:
        return shape

    def game_start_fields(self) -> dict[str, Any]:
        return {}  # no rules field means Standard rules, as in older logs

    def game_end_fields(self, plies: int, first_chaos_ply: int | None) -> dict[str, Any]:
        return {}

    def pgn_headers(self) -> dict[str, str]:
        return {}


STANDARD = StandardRules()
