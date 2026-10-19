"""One game, each side played by a human or an LLM player as the settings' Mode says."""

import random
import threading
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

import chess
from pydantic import ValidationError

from chessllm.players import LlmPlayer, LlmTimeout, Message, MoveAnswer, ReasonedMoveAnswer
from chessllm.game_log import GameLog, now
from chessllm.models import LlmModel
from chessllm.prompt import (
    ENFORCED,
    LISTED,
    SYSTEM_PROMPT_FILES,
    LlmConstraints,
    RetryFeedback,
    retry_feedback,
    turn_messages,
)

Color = Literal["white", "black"]
COLORS: tuple[Color, Color] = ("white", "black")
# Play LLM: a human plays one side and an LLM the other. LLM faceoff: an LLM plays each side.
Mode = Literal["play_llm", "llm_faceoff"]
MODE_NAMES: dict[Mode, str] = {"play_llm": "Play LLM", "llm_faceoff": "LLM faceoff"}


@dataclass(frozen=True)
class HumanSide:
    player: Literal["human"] = "human"


@dataclass(frozen=True)
class LlmSide:
    """An LLM side with the settings it plays under, in the game log's shape (ADR 0004)."""

    player: Literal["llm"] = "llm"
    model: str = "llama3:8b"
    thinking: bool = False
    llm_constraints: LlmConstraints = "free"
    retry_feedback: RetryFeedback = "explained"

    def name(self) -> str:
        """The side's name in the PGN, e.g. "llama3:8b (no thinking)"."""
        return f"{self.model} ({'thinking' if self.thinking else 'no thinking'})"


Side = HumanSide | LlmSide


@dataclass(frozen=True)
class Settings:
    """The setup of one game, copied into it when it starts. Sampling is shared by every LLM side."""

    mode: Mode = "play_llm"
    white: Side = HumanSide()
    black: Side = LlmSide()
    sampling: dict[str, float] = field(default_factory=dict)  # from the config file; empty means the model's defaults

    def side(self, color: Color) -> Side:
        return self.white if color == "white" else self.black

    def llm_sides(self) -> dict[Color, LlmSide]:
        return {color: side for color in COLORS if isinstance(side := self.side(color), LlmSide)}

    def side_names(self) -> tuple[str, str]:
        """Who plays White and who plays Black: "human" or the model."""
        white, black = (side.model if isinstance(side, LlmSide) else "human" for side in (self.white, self.black))
        return white, black

    def problem(self, models: list[LlmModel]) -> str | None:
        """Why a game can't be played with these settings, or None if it can."""
        humans = sum(isinstance(self.side(color), HumanSide) for color in COLORS)
        if humans != {"play_llm": 1, "llm_faceoff": 0}[self.mode]:
            wanted = "one human side" if self.mode == "play_llm" else "no human side"
            return f"{MODE_NAMES[self.mode]} needs {wanted}, not {humans}"
        for color, side in self.llm_sides().items():
            model = next((model for model in models if model.name == side.model), None)
            if model is None:
                return f"{side.model} ({color}) is not in the model list"
            if side.thinking and not model.thinking:
                return f"{side.model} ({color}) cannot think, so thinking must be off"
        return None


def color_name(color: chess.Color) -> Color:
    return "white" if color == chess.WHITE else "black"


class RejectedHumanMove(Exception):
    pass


class RefusedLlmTurn(Exception):
    """An LLM turn can't start: it isn't an LLM's turn, the game is over, or a turn is already running."""


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
    if not move:  # python-chess reads "--", "0000" and "Z0" as a null move, which would let the LLM pass
        return san, None, "invalid"
    return san, move, "legal"


class SideStats:
    """The totals of one LLM side."""

    def __init__(self, llm_constraints: LlmConstraints) -> None:
        self.enforced = llm_constraints in ENFORCED
        self.legal_move_streak = 0
        self.streak_broken = False
        self.illegal_moves = dict.fromkeys(ILLEGAL_KINDS, 0)
        self.recovered_turns = 0
        self.notation_slips = 0

    def as_dict(self) -> dict[str, Any]:
        """Under Enforced decoding the illegal-move metrics are None, not applicable: they would be true by
        construction (ADR 0003). Notation slips can't happen there, so they need no special case."""
        if self.enforced:
            not_applicable = {"legal_move_streak": None, "illegal_moves": None, "recovered_turns": None}
            return not_applicable | {"notation_slips": self.notation_slips}
        return {
            "legal_move_streak": self.legal_move_streak,
            "illegal_moves": dict(self.illegal_moves),
            "recovered_turns": self.recovered_turns,
            "notation_slips": self.notation_slips,
        }


class GameSession:
    def __init__(self, players: dict[Color, LlmPlayer], settings: Settings, log: GameLog) -> None:
        """players holds the LLM player of each LLM side."""
        self._players = players
        self._settings = settings
        self._llm_sides = settings.llm_sides()
        self._log = log
        self._board = chess.Board()
        self._llm_turns: list[dict[str, Any]] = []  # every LLM turn of the game, the last one included
        self._end: GameEnd | None = None
        self._stats = {color: SideStats(side.llm_constraints) for color, side in self._llm_sides.items()}
        # Requests run in a threadpool, so two could otherwise both find it an LLM's turn and both ask it to move.
        # The lock is the game's own, so a new game can start while an abandoned game's turn finishes.
        self._llm_turn_running = threading.Lock()
        prompt_files = {color: str(SYSTEM_PROMPT_FILES[side.llm_constraints]) for color, side in self._llm_sides.items()}
        # Play LLM has one LLM side, so one prompt file; a faceoff logs the file of each side, even when shared.
        logged_prompts: dict[str, Any] = (
            {"prompt_files": prompt_files}
            if settings.mode == "llm_faceoff"
            else {"prompt_file": next(iter(prompt_files.values()))}
        )
        log.write(
            "game_start",
            game_id=log.game_id,
            log_version=2,
            mode=settings.mode,
            white=asdict(settings.white),
            black=asdict(settings.black),
            sampling=settings.sampling or "model_default",
            max_retries=MAX_ATTEMPTS - 1,
            **logged_prompts,
            started_at=now(),
        )

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move. The LLM's reply is a separate turn, started with play_llm_turn.

        Raises RejectedHumanMove and leaves the game unchanged."""
        board = self._board
        if self._end is not None:
            raise RejectedHumanMove("the game is over")
        if self._settings.mode == "llm_faceoff":
            raise RejectedHumanMove("an LLM faceoff takes no human moves")
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise RejectedHumanMove(f"not a UCI move: {uci!r}") from None
        color = color_name(board.turn)
        if color in self._llm_sides or not board.is_legal(move):
            raise RejectedHumanMove(f"illegal move: {uci}")
        san = board.san(move)
        board.push(move)
        self._log.write("human_move", color=color, ply=len(board.move_stack), move=san, fen_after=board.fen())
        self._check_end()
        if self._end is not None:
            self._write_end(self._end)

    def play_llm_turn(self) -> None:
        """Play the turn of the LLM to move: it moves or forfeits.

        Raises RefusedLlmTurn and leaves the game unchanged if it isn't an LLM's turn, the game is over, or
        another LLM turn is still running."""
        if not self._llm_turn_running.acquire(blocking=False):
            raise RefusedLlmTurn("an LLM turn is already running")
        try:
            if self._end is not None:
                raise RefusedLlmTurn("the game is over")
            if color_name(self._board.turn) not in self._llm_sides:
                raise RefusedLlmTurn("it is not an LLM's turn")
            self._play_llm_turn()
            if self._end is None:
                self._check_end()
            if self._end is not None:
                self._write_end(self._end)
        finally:
            self._llm_turn_running.release()

    def _write_end(self, end: GameEnd) -> None:
        board = self._board
        self._log.write(
            "game_end",
            result=end.result,
            reason=end.reason,
            plies=len(board.move_stack),
            stats=self._all_stats(),
            ended_at=now(),
        )
        headers = {
            "Event": "ChessLLM",
            "Date": f"{date.today():%Y.%m.%d}",
            "White": self._pgn_name("white"),
            "Black": self._pgn_name("black"),
            "Result": end.result,
            "Termination": end.reason,
            "Mode": MODE_NAMES[self._settings.mode],
        }
        for color, side in self._llm_sides.items():
            headers[f"{color.capitalize()}LLMConstraints"] = side.llm_constraints
        self._log.write_pgn(board, headers)

    def _pgn_name(self, color: Color) -> str:
        side = self._llm_sides.get(color)
        return side.name() if side else "Human"

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
        """Ask the LLM to move for a move, with a retry after each illegal move. It forfeits after MAX_ATTEMPTS
        illegal moves, or at once when the call fails or times out: then there is no answer to give feedback on."""
        board = self._board
        color = color_name(board.turn)
        side, player, stats = self._llm_sides[color], self._players[color], self._stats[color]
        model = side.model
        pgn, fen, ply = self._pgn(), board.fen(), len(board.move_stack) + 1
        legal_moves = [board.san(legal) for legal in board.legal_moves]
        # Enforced decoding holds the move to exactly the legal moves, rebuilt from the position every turn.
        allowed_moves = list(legal_moves) if side.llm_constraints in ENFORCED else None
        # Listed shows the legal moves in a new random order every turn; the log keeps each list as shown.
        listed = side.llm_constraints in LISTED
        if listed:
            random.shuffle(legal_moves)
        listed_moves = " ".join(legal_moves) if listed else None
        logged_list = {"legal_moves": listed_moves} if listed else {}
        prompt_file = SYSTEM_PROMPT_FILES[side.llm_constraints]
        messages = turn_messages(pgn, fen, color, prompt_file, listed_moves)
        attempts: list[dict[str, Any]] = []
        turn: dict[str, Any] = {"ply": ply, "color": color, "attempts": attempts, "thinking": None}
        self._llm_turns.append(turn)
        feedback = None
        for number in range(1, MAX_ATTEMPTS + 1):
            attempt: dict[str, Any] = {
                "move": None, "san": None, "notation_slip": False, "result": None, "feedback_sent": feedback,
                "raw_reply": None, "thinking": None, "error": None, "latency_s": None,
            }
            attempts.append(attempt)
            try:
                reply = player.reply(messages, allowed_moves)
            except LlmTimeout as timeout:
                minutes = timeout.timeout_s / 60
                error_text = f"Too long thinking: {model} gave no answer within {minutes:g} minutes."
                attempt |= {"result": "timeout", "error": error_text}
            except Exception as error:
                attempt |= {"result": "error", "error": f"{model} did not reply: {error}"}
            if attempt["error"] is not None:
                self._log.write(
                    "llm_attempt", color=color, ply=ply, attempt=number, pgn=pgn, fen=fen, **logged_list, **attempt
                )
                break
            written, move, result = judge(board, reply.raw)
            # With thinking off, the reasoning in the answer stands in for the thinking text.
            thinking = reply.thinking if side.thinking else reasoning(reply.raw)
            attempt |= {"move": written, "result": result, "raw_reply": reply.raw, "thinking": thinking}
            if move is not None:  # legal as written; a slip if not written exactly as its standard SAN (ADR 0002)
                attempt["san"] = board.san(move)
                attempt["notation_slip"] = written != attempt["san"]
            attempt["latency_s"] = reply.latency_s
            self._log.write(
                "llm_attempt", color=color, ply=ply, attempt=number, pgn=pgn, fen=fen, **logged_list, **attempt
            )
            turn["thinking"] = thinking
            if move is not None:
                board.push(move)
                if number > 1:
                    stats.recovered_turns += 1
                if attempt["notation_slip"]:
                    stats.notation_slips += 1
                if not stats.streak_broken:
                    stats.legal_move_streak += 1
                return
            stats.illegal_moves[result] += 1
            stats.streak_broken = True
            feedback = retry_feedback(side.retry_feedback, written, result, number, MAX_ATTEMPTS, legal_moves)
            messages = messages + [Message("assistant", reply.raw), Message("user", feedback)]
        self._end = GameEnd("0-1" if color == "white" else "1-0", "forfeit")  # the side to move loses

    def state(self) -> dict[str, Any]:
        board = self._board
        return {
            "game_id": self._log.game_id,
            "fen": board.fen(),
            "pgn": self._pgn(),
            "turn": color_name(board.turn),
            "human_legal_moves": self._human_legal_moves(),
            "last_move": board.peek().uci() if board.move_stack else None,
            "check": board.is_check(),  # the side to move's king, so the page needn't work it out (ADR 0001)
            "llm_turn": self._llm_turns[-1] if self._llm_turns else None,
            "llm_turns": self._llm_turns,
            "settings": asdict(self._settings),
            "status": "over" if self._end else "playing",
            "result": self._end.result if self._end else None,
            "end_reason": self._end.reason if self._end else None,
            "stats": self._all_stats(),
        }

    def _all_stats(self) -> dict[Color, dict[str, Any] | None]:
        """The totals of each side; a human's side has none (ADR 0004)."""
        return {color: stats.as_dict() if (stats := self._stats.get(color)) else None for color in COLORS}

    def _human_legal_moves(self) -> list[str]:
        board = self._board
        if self._end is not None or color_name(board.turn) in self._llm_sides:
            return []
        return [move.uci() for move in board.legal_moves]

    def _pgn(self) -> str:
        """The moves so far as PGN movetext, e.g. "1. e4 e5"."""
        return chess.Board().variation_san(self._board.move_stack)
