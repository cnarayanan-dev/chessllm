"""One game between the human (White) and the LLM player (Black)."""

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

import chess
from pydantic import ValidationError

from chessllm.players import LlmPlayer, LlmTimeout, Message, MoveAnswer, ReasonedMoveAnswer
from chessllm.game_log import GameLog, now
from chessllm.prompt import SYSTEM_PROMPT_FILE, RetryFeedback, retry_feedback, turn_messages


@dataclass(frozen=True)
class Settings:
    """The setup of one game, copied into it when it starts."""

    model: str = "qwen3.5:9b"
    thinking: bool = True
    retry_feedback: RetryFeedback = "explained"
    sampling: dict[str, float] = field(default_factory=dict)  # from the config file; empty means the model's defaults


class RejectedHumanMove(Exception):
    pass


@dataclass(frozen=True)
class GameEnd:
    result: str  # "1-0", "0-1" or "1/2-1/2"
    reason: str  # "checkmate", "stalemate", "threefold_repetition", "fifty_moves", "insufficient_material", "forfeit", ...


# One attempt and three retries per turn; after the fourth illegal move the LLM forfeits.
MAX_ATTEMPTS = 4
ILLEGAL_KINDS = ("invalid", "illegal", "ambiguous")


def reasoning(raw: str) -> str | None:
    """The reasoning of an answer in the thinking-off schema, or None if the answer has none."""
    try:
        return ReasonedMoveAnswer.model_validate_json(raw).reasoning
    except ValidationError:
        return None


def judge(board: chess.Board, raw: str) -> tuple[str, chess.Move | None, str]:
    """Judge the raw answer as given: (the move as written, the legal move or None, "legal" or the failure kind).

    The move is read from either answer schema, since MoveAnswer ignores the reasoning field. An answer that
    isn't the move schema is an invalid move, written as the raw reply."""
    try:
        san = MoveAnswer.model_validate_json(raw).move
    except ValidationError:
        return raw, None, "invalid"
    try:
        move = board.parse_san(san)
    except chess.AmbiguousMoveError:
        return san, None, "ambiguous"
    except chess.IllegalMoveError:
        return san, None, "illegal"
    except chess.InvalidMoveError:
        return san, None, "invalid"
    if not move:  # python-chess reads "--", "0000" and "Z0" as a null move, which would let Black pass
        return san, None, "invalid"
    return san, move, "legal"


class GameSession:
    def __init__(self, player: LlmPlayer, settings: Settings, log: GameLog) -> None:
        self._player = player
        self._settings = settings
        self._log = log
        self._board = chess.Board()
        self._llm_turns: list[dict[str, Any]] = []  # every LLM turn of the game, the last one included
        self._end: GameEnd | None = None
        self._legal_move_streak = 0
        self._streak_broken = False
        self._illegal_moves = dict.fromkeys(ILLEGAL_KINDS, 0)
        self._recovered_turns = 0
        log.write(
            "game_start",
            game_id=log.game_id,
            model=settings.model,
            llm_color="black",
            mode="free",
            thinking=settings.thinking,
            sampling=settings.sampling or "model_default",
            retry_feedback=settings.retry_feedback,
            max_retries=MAX_ATTEMPTS - 1,
            prompt_file=str(SYSTEM_PROMPT_FILE),
            started_at=now(),
        )

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move (White) and let the LLM reply.

        Raises RejectedHumanMove and leaves the game unchanged."""
        board = self._board
        if self._end is not None:
            raise RejectedHumanMove("the game is over")
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise RejectedHumanMove(f"not a UCI move: {uci!r}") from None
        if board.turn != chess.WHITE or not board.is_legal(move):
            raise RejectedHumanMove(f"illegal move: {uci}")
        san = board.san(move)
        board.push(move)
        self._log.write("human_move", ply=len(board.move_stack), move=san, fen_after=board.fen())
        self._check_end()
        if self._end is None:
            self._play_llm_turn()
            if self._end is None:
                self._check_end()
        if self._end is not None:
            self._write_end(self._end)

    def _write_end(self, end: GameEnd) -> None:
        board = self._board
        stats = self._stats()
        self._log.write(
            "game_end", result=end.result, reason=end.reason, plies=len(board.move_stack), **stats, ended_at=now()
        )
        thinking = "thinking" if self._settings.thinking else "no thinking"
        self._log.write_pgn(
            board,
            {
                "Event": "ChessLLM",
                "Date": f"{date.today():%Y.%m.%d}",
                "White": "Human",
                "Black": f"{self._settings.model} ({thinking})",
                "Result": end.result,
                "Termination": end.reason,
            },
        )

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
        """Ask the LLM for a move, with a retry after each illegal move. It forfeits after MAX_ATTEMPTS illegal
        moves, or at once when the call fails or times out: then there is no answer to give feedback on."""
        board = self._board
        model = self._settings.model
        pgn, fen, ply = self._pgn(), board.fen(), len(board.move_stack) + 1
        messages = turn_messages(pgn, fen)
        attempts: list[dict[str, Any]] = []
        turn: dict[str, Any] = {"ply": ply, "attempts": attempts, "thinking": None}
        self._llm_turns.append(turn)
        feedback = None
        for number in range(1, MAX_ATTEMPTS + 1):
            attempt: dict[str, Any] = {"move": None, "result": None, "feedback_sent": feedback}
            attempt |= {"raw_reply": None, "thinking": None, "error": None, "latency_s": None}
            attempts.append(attempt)
            try:
                reply = self._player.reply(messages)
            except LlmTimeout as timeout:
                minutes = timeout.timeout_s / 60
                error_text = f"Too long thinking: {model} gave no answer within {minutes:g} minutes."
                attempt |= {"result": "timeout", "error": error_text}
            except Exception as error:
                attempt |= {"result": "error", "error": f"{model} did not reply: {error}"}
            if attempt["error"] is not None:
                self._log.write("llm_attempt", ply=ply, attempt=number, pgn=pgn, fen=fen, **attempt)
                break
            written, move, result = judge(board, reply.raw)
            # With thinking off, the reasoning in the answer stands in for the thinking text.
            thinking = reply.thinking if self._settings.thinking else reasoning(reply.raw)
            attempt |= {"move": written, "result": result, "raw_reply": reply.raw, "thinking": thinking}
            attempt["latency_s"] = reply.latency_s
            self._log.write("llm_attempt", ply=ply, attempt=number, pgn=pgn, fen=fen, **attempt)
            turn["thinking"] = thinking
            if move is not None:
                board.push(move)
                if number > 1:
                    self._recovered_turns += 1
                if not self._streak_broken:
                    self._legal_move_streak += 1
                return
            self._illegal_moves[result] += 1
            self._streak_broken = True
            legal_moves = [board.san(legal) for legal in board.legal_moves]
            feedback = retry_feedback(self._settings.retry_feedback, written, result, number, MAX_ATTEMPTS, legal_moves)
            messages = messages + [Message("assistant", reply.raw), Message("user", feedback)]
        self._end = GameEnd("1-0", "forfeit")

    def state(self) -> dict[str, Any]:
        board = self._board
        return {
            "fen": board.fen(),
            "pgn": self._pgn(),
            "turn": "white" if board.turn == chess.WHITE else "black",
            "human_legal_moves": self._human_legal_moves(),
            "last_move": board.peek().uci() if board.move_stack else None,
            "llm_turn": self._llm_turns[-1] if self._llm_turns else None,
            "llm_turns": self._llm_turns,
            "settings": asdict(self._settings),
            "status": "over" if self._end else "playing",
            "result": self._end.result if self._end else None,
            "end_reason": self._end.reason if self._end else None,
            "stats": self._stats(),
        }

    def _stats(self) -> dict[str, Any]:
        return {
            "legal_move_streak": self._legal_move_streak,
            "illegal_moves": dict(self._illegal_moves),
            "recovered_turns": self._recovered_turns,
        }

    def _human_legal_moves(self) -> list[str]:
        board = self._board
        if self._end is not None or board.turn != chess.WHITE:
            return []
        return [move.uci() for move in board.legal_moves]

    def _pgn(self) -> str:
        """The moves so far as PGN movetext, e.g. "1. e4 e5"."""
        return chess.Board().variation_san(self._board.move_stack)
