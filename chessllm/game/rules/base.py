"""What the game's Rules decide, fixed for the whole game and applying to every LLM in it: whether an LLM's illegal
move is played, how else the game can end, and what that adds to its checks, logs and PGN."""

from typing import Any, Protocol

import chess

from chessllm.core.types import Color, RulesKey
from chessllm.game.ending import GameEnd
from chessllm.game.records import AttemptResult
from chessllm.game.rules.chaos import ResolvedMove
from chessllm.game.sides import AnchorSide, LlmSide


class Rules(Protocol):
    key: RulesKey  # as the API and the game log give the Rules
    rated: bool  # whether its games count towards the Rating
    # Whether an LLM's illegal move can be played, so a position of its games may not be reachable by legal play.
    plays_illegal_moves: bool

    def check_anchor(self, anchor: AnchorSide) -> None:
        """Raises InvalidSettings, saying why, if the Anchor can't play under these rules."""

    def check_llm(self, color: Color, side: LlmSide) -> None:
        """Raises InvalidSettings, saying why, if the LLM side can't play under these rules."""

    def resolve(self, board: chess.Board, written: str, result: AttemptResult) -> ResolvedMove | None:
        """How the LLM's move, as written and judged, is resolved to be played, or None if it isn't. A resolved
        chaos move or spawn is played at once, with no retry."""

    def end(self, board: chess.Board) -> GameEnd | None:
        """The end of the game the rules add, if the position just played has one. It comes before every other end."""

    def chaos_counts(self, chaos_moves: int, spawns: int) -> tuple[int | None, int | None]:
        """A side's chaos moves and spawns as its totals give them: None where the rules have none."""

    def attempt_log_shape(self, shape: dict[str, Any]) -> dict[str, Any]:
        """The attempt as llm_attempt logs it, from Attempt.log_shape."""

    def game_start_fields(self) -> dict[str, Any]:
        """What the rules add to game_start."""

    def game_end_fields(self, plies: int, first_chaos_ply: int | None) -> dict[str, Any]:
        """What the rules add to game_end, given the plies played and the first chaos move's ply, if any."""

    def pgn_headers(self) -> dict[str, str]:
        """What the rules add to the PGN's headers."""
