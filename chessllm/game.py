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


@dataclass(frozen=True)
class GameEnd:
    result: str  # "1-0", "0-1" or "1/2-1/2"
    reason: str  # "checkmate", "stalemate", "threefold_repetition", "fifty_moves", "insufficient_material", "forfeit", ...


class FailedLlmTurn(Exception):
    """The LLM gave no legal move. Until retries exist, the turn is undone and the human moves again."""


class GameSession:
    def __init__(self, player: LlmPlayer, settings: Settings) -> None:
        self._player = player
        self._settings = settings
        self._board = chess.Board()
        self._llm_turn: dict[str, Any] | None = None
        self._end: GameEnd | None = None

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move (White) and let the LLM reply.

        Raises RejectedHumanMove or FailedLlmTurn and leaves the game unchanged."""
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
            try:
                self._play_llm_turn()
            except FailedLlmTurn:
                board.pop()
                raise
            self._check_end()

    def _check_end(self) -> None:
        """End the game if the position is over, counting claimable draws (threefold repetition, fifty moves).

        A draw counts once the position has happened, not when the side to move could claim it with its next
        move (as outcome(claim_draw=True) would), so the LLM is never denied a move it could still play."""
        board = self._board
        outcome = board.outcome()
        if outcome is not None:
            # The termination names double as end reasons, e.g. STALEMATE -> "stalemate".
            self._end = GameEnd(outcome.result(), outcome.termination.name.lower())
        elif board.is_repetition(3):
            self._end = GameEnd("1/2-1/2", "threefold_repetition")
        elif board.halfmove_clock >= 100:
            self._end = GameEnd("1/2-1/2", "fifty_moves")

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
            "human_legal_moves": self._human_legal_moves(),
            "last_move": board.peek().uci() if board.move_stack else None,
            "llm_turn": self._llm_turn,
            "settings": asdict(self._settings),
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
