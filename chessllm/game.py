"""One game between the human (White) and the LLM player (Black)."""

from dataclasses import dataclass
from typing import Any

import chess

from chessllm.players import LlmPlayer, Message


class RejectedHumanMove(Exception):
    pass


@dataclass(frozen=True)
class GameEnd:
    result: str  # "1-0", "0-1" or "1/2-1/2"
    reason: str  # "checkmate", "stalemate", "threefold_repetition", "fifty_moves", "insufficient_material", "forfeit", ...


class GameSession:
    def __init__(self, player: LlmPlayer) -> None:
        self._player = player
        self._board = chess.Board()
        self._end: GameEnd | None = None

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move (White) and let the LLM reply. Raises RejectedHumanMove and leaves the game unchanged."""
        board = self._board
        if self._end is not None:
            raise RejectedHumanMove("the game is over")
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise RejectedHumanMove(f"not a UCI move: {uci!r}") from None
        if board.turn != chess.WHITE or not board.is_legal(move):
            raise RejectedHumanMove(f"illegal move: {uci}")
        board.push(move)
        self._check_end()
        if self._end is None:
            self._play_llm_turn()
            self._check_end()

    def _check_end(self) -> None:
        """End the game if the position is over, counting claimable draws (threefold repetition, fifty moves)."""
        outcome = self._board.outcome(claim_draw=True)
        if outcome is not None:
            # The termination names double as end reasons, e.g. THREEFOLD_REPETITION -> "threefold_repetition".
            self._end = GameEnd(outcome.result(), outcome.termination.name.lower())

    def _play_llm_turn(self) -> None:
        board = self._board
        reply = self._player.reply([Message("user", f"PGN: {self._pgn()}\nFEN: {board.fen()}")])
        board.push_san(reply.raw)

    def state(self) -> dict[str, Any]:
        board = self._board
        return {
            "fen": board.fen(),
            "pgn": self._pgn(),
            "turn": "white" if board.turn == chess.WHITE else "black",
            "human_legal_moves": self._human_legal_moves(),
            "last_move": board.peek().uci() if board.move_stack else None,
            "status": "over" if self._end else "playing",
            "result": self._end.result if self._end else None,
            "end_reason": self._end.reason if self._end else None,
        }

    def _human_legal_moves(self) -> list[str]:
        board = self._board
        if self._end is not None or board.turn != chess.WHITE:
            return []
        return [move.uci() for move in board.legal_moves]

    def _pgn(self) -> str:
        """The moves so far as PGN movetext, e.g. "1. e4 e5"."""
        return chess.Board().variation_san(self._board.move_stack)
