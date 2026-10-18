"""One game between the human (White) and the LLM player (Black)."""

from dataclasses import asdict, dataclass
from typing import Any

import chess
from pydantic import ValidationError

from chessllm.players import LlmPlayer, MoveAnswer
from chessllm.prompt import turn_messages


@dataclass(frozen=True)
class Settings:
    """The setup of one game, copied into it when it starts."""

    model: str = "qwen3.5:9b"
    thinking: bool = True


class RejectedHumanMove(Exception):
    pass


class FailedLlmTurn(Exception):
    """The LLM gave no legal move. Until retries exist, the turn is undone and the human moves again."""


class GameSession:
    def __init__(self, player: LlmPlayer, settings: Settings) -> None:
        self._player = player
        self._settings = settings
        self._board = chess.Board()
        self._llm_turn: dict[str, Any] | None = None

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move (White) and let the LLM reply.

        Raises RejectedHumanMove or FailedLlmTurn and leaves the game unchanged."""
        board = self._board
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise RejectedHumanMove(f"not a UCI move: {uci!r}") from None
        if board.turn != chess.WHITE or not board.is_legal(move):
            raise RejectedHumanMove(f"illegal move: {uci}")
        board.push(move)
        if not board.is_game_over(claim_draw=True):
            try:
                self._play_llm_turn()
            except FailedLlmTurn:
                board.pop()
                raise

    def _play_llm_turn(self) -> None:
        board = self._board
        model = self._settings.model
        try:
            reply = self._player.reply(turn_messages(self._pgn(), board.fen()))
        except Exception as error:
            raise FailedLlmTurn(f"{model} did not reply: {error}") from error
        try:
            answer = MoveAnswer.model_validate_json(reply.raw)
        except ValidationError:
            raise FailedLlmTurn(f"{model} gave an unreadable answer: {reply.raw!r}") from None
        try:
            board.push_san(answer.move)
        except ValueError:
            raise FailedLlmTurn(f"{model} played an illegal move: {answer.move!r}") from None
        self._llm_turn = {
            "attempts": [{"move": answer.move, "result": "legal", "feedback_sent": None}],
            "thinking": reply.thinking,
        }

    def state(self) -> dict[str, Any]:
        board = self._board
        return {
            "fen": board.fen(),
            "pgn": self._pgn(),
            "turn": "white" if board.turn == chess.WHITE else "black",
            "human_legal_moves": [move.uci() for move in board.legal_moves] if board.turn == chess.WHITE else [],
            "last_move": board.peek().uci() if board.move_stack else None,
            "llm_turn": self._llm_turn,
            "settings": asdict(self._settings),
        }

    def _pgn(self) -> str:
        """The moves so far as PGN movetext, e.g. "1. e4 e5"."""
        return chess.Board().variation_san(self._board.move_stack)
