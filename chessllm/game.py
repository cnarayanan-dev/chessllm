"""One game between the human (White) and the LLM player (Black)."""

from typing import Any

import chess

from chessllm.players import LlmPlayer, Message


class RejectedHumanMove(Exception):
    pass


class GameSession:
    def __init__(self, player: LlmPlayer) -> None:
        self._player = player
        self._board = chess.Board()

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move (White) and let the LLM reply. Raises RejectedHumanMove and leaves the game unchanged."""
        board = self._board
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise RejectedHumanMove(f"not a UCI move: {uci!r}") from None
        if board.turn != chess.WHITE or not board.is_legal(move):
            raise RejectedHumanMove(f"illegal move: {uci}")
        board.push(move)
        if not board.is_game_over(claim_draw=True):
            self._play_llm_turn()

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
            "human_legal_moves": [move.uci() for move in board.legal_moves] if board.turn == chess.WHITE else [],
            "last_move": board.peek().uci() if board.move_stack else None,
        }

    def _pgn(self) -> str:
        """The moves so far as PGN movetext, e.g. "1. e4 e5"."""
        return chess.Board().variation_san(self._board.move_stack)
