"""One game, each side played by a human, an LLM player or an Anchor as the settings' Mode says."""

import random
import threading
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Annotated, Any, Literal

import chess
from pydantic import Field, ValidationError

from chessllm import chaos
from chessllm.anchors import DRAGON_SKILLS, Anchor, AnchorUnavailable
from chessllm.players import LlmPlayer, LlmReply, LlmTimeout, Message, MoveAnswer, ReasonedMoveAnswer
from chessllm.game_log import GameLog, now
from chessllm.models import LlmModel
from chessllm.prompt import (
    ENFORCED,
    LISTED,
    SYSTEM_PROMPT_FILES,
    LlmConstraints,
    PositionFormat,
    RetryFeedback,
    describe_position,
    retry_feedback,
    turn_messages,
)

Color = Literal["white", "black"]
COLORS: tuple[Color, Color] = ("white", "black")
# Play LLM: a human plays one side and an LLM the other. LLM faceoff: an LLM plays each side. Anchor match: an LLM
# plays an Anchor, started from the command line.
Mode = Literal["play_llm", "llm_faceoff", "anchor_match"]
MODE_NAMES: dict[Mode, str] = {"play_llm": "Play LLM", "llm_faceoff": "LLM faceoff", "anchor_match": "Anchor match"}
# Unattended games, with no human to stop them, end as a draw after MOVE_CAP moves per side (the Move cap, ADR 0005).
UNATTENDED_MODES: tuple[Mode, ...] = ("llm_faceoff", "anchor_match")
MOVE_CAP = 150
# Standard rules never play an illegal move; Chaos rules play an LLM's rule-breaking or ambiguous move (ADR 0006).
Rules = Literal["standard", "chaos"]
# How many illegal moves an LLM may make in one turn before it forfeits: one attempt, the rest retries.
MAX_ATTEMPTS_RANGE = range(1, 26)


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
    # How each turn gives the position; None is the default, fen. Left out of the API's output and the game log
    # (log_shape) when it is fen, so games from before the setting read the same.
    position: Annotated[PositionFormat | None, Field(exclude_if=lambda position: position in (None, "fen"))] = None

    def log_shape(self) -> dict[str, Any]:
        """The side as game_start logs it: without position when it is the default, so that logs from before the
        setting existed and logs since describe the same Player configuration the same way."""
        shape = asdict(self)
        if self.position in (None, "fen"):
            del shape["position"]
        return shape

    def think(self) -> bool | str:
        """The thinking sent to Ollama: on or off, on meaning the model's default level."""
        return self.thinking

    def name(self) -> str:
        """The side's name in the PGN, e.g. "llama3:8b (no thinking)"."""
        return f"{self.model} ({'thinking' if self.thinking else 'no thinking'})"


@dataclass(frozen=True)
class BenchmarkLlmSide(LlmSide):
    """An LLM side with the settings only the benchmark's commands can set: never the API, whose sides are LlmSide,
    so its types and output don't change (#67). Each is left out of the game log (log_shape) when unset, so a side
    without them logs, and keeps its Player configuration id, as a plain LlmSide."""

    # One of the Thinking levels the model offers, e.g. "xhigh", sent instead of plain thinking on; needs thinking on.
    thinking_level: str | None = None

    def log_shape(self) -> dict[str, Any]:
        shape = super().log_shape()
        if self.thinking_level is None:
            del shape["thinking_level"]
        return shape

    def think(self) -> bool | str:
        return self.thinking_level if self.thinking_level is not None else self.thinking

    def name(self) -> str:
        """The side's name in the PGN, e.g. "qwen3.8:latest (thinking xhigh)"."""
        if self.thinking_level is None:
            return super().name()
        return f"{self.model} (thinking {self.thinking_level})"


AnchorEngine = Literal["dragon", "stockfish"]


@dataclass(frozen=True)
class AnchorSide:
    """An Anchor side: Komodo Dragon 1, or Stockfish standing in for it, at a Skill level, in the game log's shape."""

    player: Literal["anchor"] = "anchor"
    engine: AnchorEngine = "dragon"
    skill: int = 1

    def name(self) -> str:
        """The side's name in the PGN, e.g. "Dragon (Skill 1)"."""
        return f"{self.engine.capitalize()} (Skill {self.skill})"

    def file_name(self) -> str:
        """The side's part of the game log's file name, e.g. "dragon-skill1"."""
        return f"{self.engine}-skill{self.skill}"


Side = HumanSide | LlmSide | AnchorSide


def side_log_shape(side: Side) -> dict[str, Any]:
    """A side as game_start logs it (ADR 0004)."""
    return side.log_shape() if isinstance(side, LlmSide) else asdict(side)
# How many sides of each kind each Mode has.
MODE_SIDES: dict[Mode, dict[str, int]] = {
    "play_llm": {"human": 1, "llm": 1, "anchor": 0},
    "llm_faceoff": {"human": 0, "llm": 2, "anchor": 0},
    "anchor_match": {"human": 0, "llm": 1, "anchor": 1},
}
SIDE_KINDS = {"human": "human side", "llm": "LLM side", "anchor": "Anchor side"}


@dataclass(frozen=True)
class Settings:
    """The setup of one game, copied into it when it starts. Sampling is shared by every LLM side."""

    mode: Mode = "play_llm"
    white: Side = HumanSide()
    black: Side = LlmSide()
    sampling: dict[str, float] = field(default_factory=dict)  # from the config file; empty means the model's defaults
    rules: Rules = "standard"  # one value for the whole game, applying to every LLM in it
    max_attempts: int = 5  # per LLM turn; after this many illegal moves the LLM forfeits

    def side(self, color: Color) -> Side:
        return self.white if color == "white" else self.black

    def llm_sides(self) -> dict[Color, LlmSide]:
        return {color: side for color in COLORS if isinstance(side := self.side(color), LlmSide)}

    def anchor_sides(self) -> dict[Color, AnchorSide]:
        return {color: side for color in COLORS if isinstance(side := self.side(color), AnchorSide)}

    def side_names(self) -> tuple[str, str]:
        """Who plays White and who plays Black, as the game log's file name has them: "human", the model, or the
        Anchor, e.g. "dragon-skill1"."""

        def name(side: Side) -> str:
            if isinstance(side, LlmSide):
                return side.model
            return side.file_name() if isinstance(side, AnchorSide) else "human"

        return name(self.white), name(self.black)

    def problem(self, models: list[LlmModel]) -> str | None:
        """Why a game can't be played with these settings, or None if it can."""
        for kind, needed in MODE_SIDES[self.mode].items():
            count = sum(side.player == kind for side in (self.white, self.black))
            if count != needed:
                number = {0: "no", 1: "one", 2: "two"}[needed]
                return f"{MODE_NAMES[self.mode]} needs {number} {SIDE_KINDS[kind]}{'s' * (needed == 2)}, not {count}"
        for color, anchor in self.anchor_sides().items():
            if anchor.skill not in DRAGON_SKILLS:
                low, high = DRAGON_SKILLS[0], DRAGON_SKILLS[-1]
                return f"{anchor.engine.capitalize()} ({color}) plays at Skill {low}-{high}, not {anchor.skill}"
        if self.max_attempts not in MAX_ATTEMPTS_RANGE:
            low, high = MAX_ATTEMPTS_RANGE[0], MAX_ATTEMPTS_RANGE[-1]
            return f"An LLM gets {low}-{high} attempts per turn, not {self.max_attempts}"
        for anchor in self.anchor_sides().values():
            if self.rules == "chaos" and anchor.engine != "stockfish":
                return "Only Stockfish can be the Anchor under Chaos rules: it alone copes with chaos positions"
        for color, side in self.llm_sides().items():
            model = next((model for model in models if model.name == side.model), None)
            if model is None:
                return f"{side.model} ({color}) is not in the model list"
            if isinstance(side, BenchmarkLlmSide) and (level := side.thinking_level) is not None:
                if not model.thinking:
                    return f"{side.model} ({color}) cannot think, so it has no Thinking levels"
                if not model.thinking_levels:
                    return f"{side.model} ({color}) has no Thinking levels, only thinking on or off"
                if level not in model.thinking_levels:
                    offered = ", ".join(model.thinking_levels)
                    return f"{side.model} ({color}) has no Thinking level {level}: it offers {offered}"
                if not side.thinking:
                    return f"{side.model} ({color}) has Thinking level {level}, so thinking must be on"
            if side.thinking and not model.thinking:
                return f"{side.model} ({color}) cannot think, so thinking must be off"
            if self.rules == "chaos" and side.llm_constraints in ENFORCED:
                wanted = "Chaos rules need every LLM under Free or Listed"
                return f"{wanted}, not {side.model} ({color}) under {side.llm_constraints}"
        return None


def color_name(color: chess.Color) -> Color:
    return "white" if color == chess.WHITE else "black"


class RejectedHumanMove(Exception):
    pass


class RefusedLlmTurn(Exception):
    """An LLM turn can't start: it isn't an LLM's turn, the game is over, or a turn is already running."""


class RefusedAnchorTurn(Exception):
    """An Anchor turn can't start: it isn't an Anchor's turn, or the game is over."""


@dataclass(frozen=True)
class GameEnd:
    result: str  # "1-0", "0-1" or "1/2-1/2"
    # "checkmate", "stalemate", "threefold_repetition", "fifty_moves", "insufficient_material", "forfeit", "move_cap", ...
    reason: str


ILLEGAL_KINDS = ("invalid", "illegal", "ambiguous")


def reasoning(raw: str) -> str | None:
    """The reasoning of an answer in the thinking-off schema, or None if the answer has none."""
    try:
        return ReasonedMoveAnswer.model_validate_json(raw).reasoning
    except ValidationError:
        return None


def token_accounting(reply: LlmReply) -> dict[str, Any]:
    """What the attempt's call used and why generation stopped. Only the game log has these, not the API's state;
    an attempt with no answer has none."""
    return {
        "thinking_tokens": reply.thinking_tokens,
        "answer_tokens": reply.answer_tokens,
        "prompt_tokens": reply.prompt_tokens,
        "stop_reason": reply.stop_reason,
        "token_split_estimated": reply.token_split_estimated,
    }


def logged_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    """The attempt as the game log has it, unchanged since before the API gave the Reasoning a field of its own:
    with thinking off, the Reasoning is the attempt's thinking."""
    logged = {key: value for key, value in attempt.items() if key != "reasoning"}
    if attempt["reasoning"] is not None:
        logged["thinking"] = attempt["reasoning"]
    return logged


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

    def __init__(self, llm_constraints: LlmConstraints, rules: Rules = "standard") -> None:
        self.enforced = llm_constraints in ENFORCED
        self.chaos = rules == "chaos"
        self.legal_move_streak = 0
        self.streak_broken = False
        self.illegal_moves = dict.fromkeys(ILLEGAL_KINDS, 0)
        self.recovered_turns = 0
        self.notation_slips = 0
        self.chaos_moves = 0  # spawns included, as a spawn is a chaos move
        self.spawns = 0

    def as_dict(self) -> dict[str, Any]:
        """Under Enforced decoding the illegal-move metrics are None, not applicable: they would be true by
        construction (ADR 0003). Notation slips can't happen there, so they need no special case. The chaos
        counts are only given under Chaos rules, which Enforced decoding never plays under."""
        if self.enforced:
            not_applicable = {"legal_move_streak": None, "illegal_moves": None, "recovered_turns": None}
            return not_applicable | {"notation_slips": self.notation_slips}
        chaos_counts = {"chaos_moves": self.chaos_moves, "spawns": self.spawns} if self.chaos else {}
        return {
            "legal_move_streak": self.legal_move_streak,
            "illegal_moves": dict(self.illegal_moves),
            "recovered_turns": self.recovered_turns,
            "notation_slips": self.notation_slips,
            **chaos_counts,
        }


class GameSession:
    def __init__(
        self,
        players: dict[Color, LlmPlayer],
        settings: Settings,
        log: GameLog,
        anchors: dict[Color, Anchor] | None = None,
    ) -> None:
        """players holds the LLM player of each LLM side, and anchors the Anchor of each Anchor side."""
        self._players = players
        self._anchors = anchors or {}
        self._settings = settings
        self._llm_sides = settings.llm_sides()
        self._chaos = settings.rules == "chaos"
        self._log = log
        self._board = chess.Board()
        # The game's own record of every ply (ADR 0006): a chaos move edits the board by hand, which clears
        # python-chess's move stack, so repetition, the last move and the Move record come from these lists.
        self._positions = [position_key(self._board)]  # the start position, then the position after each ply
        self._moves: list[tuple[str, str]] = []  # each ply's move in UCI and as written in the Move record
        # Each ply as the page gets it for its move history: the move and the whole position before and after it,
        # so the page can step through the game without any chess logic (ADR 0001).
        self._plies: list[dict[str, Any]] = []
        self._standard_moves: list[chess.Move] = []  # the moves up to the first chaos move, for the PGN export
        self._first_chaos_ply: int | None = None
        self._llm_turns: list[dict[str, Any]] = []  # every LLM turn of the game, the last one included
        self._end: GameEnd | None = None
        self._stats = {
            color: SideStats(side.llm_constraints, settings.rules) for color, side in self._llm_sides.items()
        }
        # Requests run in a threadpool, so two could otherwise both find it an LLM's turn and both ask it to move.
        # The lock is the game's own, so a new game can start while an abandoned game's turn finishes.
        self._llm_turn_running = threading.Lock()
        prompt_files = {color: str(SYSTEM_PROMPT_FILES[side.llm_constraints]) for color, side in self._llm_sides.items()}
        # Play LLM and an Anchor match have one LLM side, so one prompt file; a faceoff logs the file of each side,
        # even when shared.
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
            white=side_log_shape(settings.white),
            black=side_log_shape(settings.black),
            sampling=settings.sampling or "model_default",
            max_retries=settings.max_attempts - 1,
            **logged_prompts,
            **({"rules": settings.rules} if self._chaos else {}),  # absent means Standard rules, as in older logs
            # To the microsecond, so games started within the same second still sort in the order they started.
            started_at=now("microseconds"),
        )

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move. The LLM's reply is a separate turn, started with play_llm_turn.

        Raises RejectedHumanMove and leaves the game unchanged."""
        board = self._board
        if self._end is not None:
            raise RejectedHumanMove("the game is over")
        if self._settings.mode != "play_llm":
            raise RejectedHumanMove(f"an {MODE_NAMES[self._settings.mode]} takes no human moves")
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise RejectedHumanMove(f"not a UCI move: {uci!r}") from None
        color = color_name(board.turn)
        if color in self._llm_sides or not board.is_legal(move):
            raise RejectedHumanMove(f"illegal move: {uci}")
        san = self._play_legal(move)
        self._log.write("human_move", color=color, ply=len(self._moves), move=san, fen_after=self._board.fen())
        self._check_end()
        if self._end is not None:
            self._write_end(self._end)

    def play_anchor_turn(self) -> None:
        """Ask the Anchor to move for its move and play it, like a human's move but without a request.

        Raises RefusedAnchorTurn and leaves the game unchanged if it isn't an Anchor's turn or the game is over,
        and AnchorUnavailable if the Anchor fails or answers with an illegal move."""
        board = self._board
        if self._end is not None:
            raise RefusedAnchorTurn("the game is over")
        color = color_name(board.turn)
        anchor = self._anchors.get(color)
        if anchor is None:
            raise RefusedAnchorTurn("it is not an Anchor's turn")
        move = anchor.move(board.copy())
        if not board.is_legal(move):
            raise AnchorUnavailable(f"{self._pgn_name(color)} played an illegal move: {move.uci()}")
        san = self._play_legal(move)
        self._log.write("anchor_move", color=color, ply=len(self._moves), move=san, fen_after=self._board.fen())
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
        # Under Chaos rules, the plies played from the first chaos move on, by any side.
        first_chaos = self._first_chaos_ply
        chaos_plies = {"chaos_plies": len(self._moves) - first_chaos + 1 if first_chaos else 0} if self._chaos else {}
        self._log.write(
            "game_end",
            result=end.result,
            reason=end.reason,
            plies=len(self._moves),
            stats=self._all_stats(),
            **chaos_plies,
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
        if self._chaos:
            headers["Rules"] = "Chaos"
        # A chaos move has no valid PGN, so the export stops at the first one (ADR 0006).
        standard = chess.Board()
        for move in self._standard_moves:
            standard.push(move)
        self._log.write_pgn(standard, headers)

    def _pgn_name(self, color: Color) -> str:
        side = self._settings.side(color)
        return "Human" if isinstance(side, HumanSide) else side.name()

    def _check_end(self) -> None:
        """End the game if the position is over, counting claimable draws (threefold repetition, fifty moves), or
        an unattended game at the Move cap, which gives way to an end by the rules on the same move.

        A draw counts once the position has happened, not when the side to move could claim it with its next
        move (as outcome(claim_draw=True) would), so the LLM is never denied a move it could still play.

        King capture comes first: python-chess would go on judging a position with a king missing. Then a chaos
        move that leaves the mover's own king in check loses at once, before the opponent has to take the king.
        Repetition counts every position of the game, as a chaos move clears python-chess's move stack."""
        board = self._board
        mover = not board.turn
        outcome = board.outcome()
        if board.king(board.turn) is None or board.king(mover) is None:
            # The side left with a king wins: normally the mover, unless it took its own king with a chaos move.
            winner = mover if board.king(mover) is not None else board.turn
            self._end = GameEnd("1-0" if winner == chess.WHITE else "0-1", "king_capture")
        elif board.was_into_check():  # only a chaos move can leave the mover's king attacked
            self._end = GameEnd("0-1" if mover == chess.WHITE else "1-0", "king_left_in_check")
        elif outcome is not None:
            # The termination names double as end reasons, e.g. STALEMATE -> "stalemate".
            self._end = GameEnd(outcome.result(), outcome.termination.name.lower())
        elif self._positions.count(self._positions[-1]) >= 3:
            self._end = GameEnd("1/2-1/2", "threefold_repetition")
        elif board.halfmove_clock >= 100:
            self._end = GameEnd("1/2-1/2", "fifty_moves")
        elif self._settings.mode in UNATTENDED_MODES and len(self._moves) >= 2 * MOVE_CAP:
            self._end = GameEnd("1/2-1/2", "move_cap")

    def _play_llm_turn(self) -> None:
        """Ask the LLM to move for a move, with a retry after each illegal move. It forfeits after max_attempts
        illegal moves, or at once when the call fails or times out: then there is no answer to give feedback on."""
        board = self._board
        color = color_name(board.turn)
        side, player, stats = self._llm_sides[color], self._players[color], self._stats[color]
        model = side.model
        pgn, fen, ply = self._pgn(), board.fen(), len(self._moves) + 1
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
        last_move = self._moves[-1][1] if self._moves else None
        description = describe_position(board, last_move) if side.position == "described" else None
        messages = turn_messages(pgn, fen, color, prompt_file, listed_moves, description)
        attempts: list[dict[str, Any]] = []
        turn: dict[str, Any] = {"ply": ply, "color": color, "attempts": attempts, "thinking": None, "reasoning": None}
        self._llm_turns.append(turn)
        feedback = None
        max_attempts = self._settings.max_attempts
        for number in range(1, max_attempts + 1):
            attempt: dict[str, Any] = {
                "move": None, "san": None, "notation_slip": False, "result": None, "feedback_sent": feedback,
                "raw_reply": None, "thinking": None, "reasoning": None, "error": None, "latency_s": None,
                "prompt": [asdict(message) for message in messages],  # the Prompt as sent for this attempt
            }
            if self._chaos:
                attempt["resolution"] = None  # None when there was no move the resolver could look at
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
                    "llm_attempt", color=color, ply=ply, attempt=number, pgn=pgn, fen=fen, **logged_list,
                    **logged_attempt(attempt),
                )
                turn["reasoning"] = None  # the turn's Reasoning is its last attempt's: none without an answer
                break
            written, move, result = judge(board, reply.raw)
            # Thinking with thinking on; with it off, the Reasoning written in the answer instead.
            thinking, reasoned = (reply.thinking, None) if side.thinking else (None, reasoning(reply.raw))
            attempt |= {
                "move": written, "result": result, "raw_reply": reply.raw, "thinking": thinking, "reasoning": reasoned,
            }
            if move is not None:  # legal as written; a slip if not written exactly as its standard SAN (ADR 0002)
                attempt["san"] = board.san(move)
                attempt["notation_slip"] = written != attempt["san"]
            # Under Chaos rules a rule-breaking or ambiguous move is resolved; badly formed notation never is.
            resolution = chaos.resolve(board, written) if self._chaos and result != "invalid" else None
            if resolution is not None:
                attempt["resolution"] = resolution.as_dict()
            attempt["latency_s"] = reply.latency_s
            self._log.write(
                "llm_attempt", color=color, ply=ply, attempt=number, pgn=pgn, fen=fen, **logged_list,
                **logged_attempt(attempt), **token_accounting(reply),
            )
            turn |= {"thinking": thinking, "reasoning": reasoned}
            if move is not None:
                self._play_legal(move)
                if number > 1:
                    stats.recovered_turns += 1
                if attempt["notation_slip"]:
                    stats.notation_slips += 1
                if not stats.streak_broken:
                    stats.legal_move_streak += 1
                return
            stats.illegal_moves[result] += 1
            stats.streak_broken = True
            if resolution is not None and resolution.kind in ("chaos", "spawn"):  # played at once, with no retry
                self._play_chaos(resolution, written)
                stats.chaos_moves += 1
                stats.spawns += resolution.kind == "spawn"
                return
            feedback = retry_feedback(side.retry_feedback, written, result, number, max_attempts, legal_moves)
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
            "last_move": self._moves[-1][0] if self._moves else None,
            "plies": self._plies,
            "check": board.is_check(),  # the side to move's king, so the page needn't work it out (ADR 0001)
            "llm_turn": self._llm_turns[-1] if self._llm_turns else None,
            "llm_turns": self._llm_turns,
            "settings": asdict(self._settings)
            | {color: side_log_shape(self._settings.side(color)) for color in COLORS},
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
        """The Move record: the moves so far as PGN movetext, e.g. "1. e4 e5", a chaos move in the LLM's own
        spelling. Under Standard rules it is valid PGN."""
        return " ".join(
            f"{ply // 2 + 1}. {written}" if ply % 2 == 0 else written for ply, (_, written) in enumerate(self._moves)
        )

    def _play_legal(self, move: chess.Move) -> str:
        """Play a legal move, the human's or the LLM's, and return its SAN."""
        san, fen_before = self._board.san(move), self._board.fen()
        self._board.push(move)
        if self._first_chaos_ply is None:
            self._standard_moves.append(move)
        self._played(move.uci(), san, fen_before)
        return san

    def _play_chaos(self, resolution: chaos.Resolution, written: str) -> None:
        """Play a chaos move or spawn by editing the board by hand (ADR 0006), recorded as the LLM wrote it."""
        uci, fen_before = resolution.uci(self._board), self._board.fen()
        self._board = chaos.apply(self._board, resolution)
        if self._first_chaos_ply is None:
            self._first_chaos_ply = len(self._moves) + 1
        self._played(uci, written, fen_before, resolution)

    def _played(self, uci: str, written: str, fen_before: str, resolution: chaos.Resolution | None = None) -> None:
        """Record the ply just played. Only a chaos move or spawn has a resolution, the same as the attempt that
        played it has, so the page can replay it without resolving it again."""
        self._moves.append((uci, written))
        self._positions.append(position_key(self._board))
        ply: dict[str, Any] = {"ply": len(self._moves), "color": color_name(not self._board.turn), "move": uci}
        ply |= {"written": written, "fen_before": fen_before, "fen_after": self._board.fen()}
        ply["check"] = self._board.is_check()  # after the ply, as the state's check is for the live position
        if resolution is not None:
            ply["resolution"] = resolution.as_dict()
        self._plies.append(ply)


def position_key(board: chess.Board) -> str:
    """What makes two positions the same for repetition: the placement, the side to move, the castling rights
    and an en passant square only if a capture there is legal (the first four fields of the FEN)."""
    return " ".join(board.fen().split()[:4])
