"""An LLM's Turn: it is shown the position and replies with a move, with a Retry after each illegal move, until a
move is played or it forfeits. The game plays the move the turn ends with (GameSession)."""

import random
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import chess

from chessllm.core.types import Color
from chessllm.game.llm_turn.conversation import Conversation, reply_reserve
from chessllm.game.llm_turn.counterpart import CounterpartAnswer, ask_legal_counterpart
from chessllm.game.llm_turn.judging import answered, judge, no_answer
from chessllm.game.llm_turn.prompt import TurnPosition, cut_off_feedback, move_record, retry_feedback, turn_message
from chessllm.game.records import (
    ILLEGAL_RESULTS,
    Attempt,
    AttemptResult,
    IllegalMoves,
    LlmSideStats,
    LlmTurn,
)
from chessllm.game.rules import Rules
from chessllm.game.rules.chaos import ResolvedMove
from chessllm.game.sides import ENFORCED, LISTED, LlmConstraints, LlmSide, PromptTemplate
from chessllm.llm.players import LlmPlayer, LlmReply
from chessllm.logs.game_log import GameLog


class SideStats:
    """The totals of one LLM side."""

    def __init__(self, llm_constraints: LlmConstraints, rules: Rules) -> None:
        self.enforced = llm_constraints in ENFORCED
        self.rules = rules
        self.legal_move_streak = 0
        self.streak_broken = False
        self.illegal_moves: dict[str, int] = dict.fromkeys(ILLEGAL_RESULTS, 0)
        self.recovered_turns = 0
        self.notation_slips = 0
        self.chaos_moves = 0  # spawns included, as a spawn is a chaos move
        self.spawns = 0

    def record(self) -> LlmSideStats:
        """Under Enforced decoding the illegal-move metrics are None, not applicable: they would be true by
        construction (ADR 0003). Notation slips can't happen there, so they need no special case. The chaos
        counts are only given under Chaos rules, which Enforced decoding never plays under."""
        if self.enforced:
            return LlmSideStats(
                legal_move_streak=None, illegal_moves=None, recovered_turns=None, notation_slips=self.notation_slips
            )
        chaos_moves, spawns = self.rules.chaos_counts(self.chaos_moves, self.spawns)
        return LlmSideStats(
            legal_move_streak=self.legal_move_streak,
            illegal_moves=IllegalMoves(**self.illegal_moves),
            recovered_turns=self.recovered_turns,
            notation_slips=self.notation_slips,
            chaos_moves=chaos_moves,
            spawns=spawns,
        )


@dataclass(frozen=True)
class TurnOutcome:
    """How a turn ended, for the game to play: with a legal move, a chaos move or spawn, or a Forfeit. With none of
    them, the game was abandoned while the turn ran."""

    turn: LlmTurn
    move: chess.Move | None = None
    chaos_move: ResolvedMove | None = None
    written: str | None = None  # the chaos move as the LLM wrote it, as the Move record has it
    forfeit: bool = False


def token_accounting(reply: LlmReply) -> dict[str, Any]:
    """What the attempt's call used and why generation stopped. Only the game log has these, not the API's state;
    an attempt with no answer has none. forced is there only when the Thinking budget forced the answer, so
    attempts without a budget log as before."""
    return {
        "thinking_tokens": reply.thinking_tokens,
        "answer_tokens": reply.answer_tokens,
        "prompt_tokens": reply.prompt_tokens,
        "stop_reason": reply.stop_reason,
        "token_split_estimated": reply.token_split_estimated,
        **({"forced": True} if reply.forced else {}),
    }


class LlmTurns:
    """One LLM side's turns in a game, each played with the side's settings and LLM player under the game's Rules,
    counted in the side's totals and written to the game log."""

    def __init__(
        self,
        color: Color,
        side: LlmSide,
        template: PromptTemplate,
        player: LlmPlayer,
        rules: Rules,
        max_attempts: int,
        log: GameLog,
        abandoned: threading.Event,
        clock: Callable[[], float],
    ) -> None:
        """template is the Prompt template the side plays the game with. abandoned is the game's: once it is set, a
        running turn makes no further attempts. clock is the game's, which times each turn."""
        self._color = color
        self._side = side
        self._template = template
        self._player = player
        self._rules = rules
        self._max_attempts = max_attempts
        self._log = log
        self._abandoned = abandoned
        self._clock = clock
        self.stats = SideStats(side.llm_constraints, rules)
        # What the side's turns send: one conversation for the game, or a new one every turn (Turn memory).
        self._conversation = Conversation(side.turn_memory, color, template)

    def play(self, board: chess.Board, moves: Sequence[str], started: float) -> TurnOutcome:
        """Ask the LLM to move for a move, with a retry after each illegal move. It forfeits after max_attempts
        illegal moves, or at once when the call fails or times out: then there is no answer to give feedback on.

        board is the position to move in, moves every ply so far as written in the Move record, and started when the
        turn started, by the game's clock. The board is left as it is: the game plays the move."""
        color, side, player, stats = self._color, self._side, self._player, self.stats
        model = side.model
        ply = len(moves) + 1
        pgn = move_record(moves)
        fen = board.fen()
        legal_moves = [board.san(legal) for legal in board.legal_moves]
        # Enforced decoding holds the move to exactly the legal moves, rebuilt from the position every turn.
        allowed_moves = list(legal_moves) if side.llm_constraints in ENFORCED else None
        # Listed shows the legal moves in a new random order every turn; the log keeps each list as shown.
        listed = side.llm_constraints in LISTED
        if listed:
            random.shuffle(legal_moves)
        listed_moves = " ".join(legal_moves) if listed else None
        logged_list = {"legal_moves": listed_moves} if listed else {}
        conversation = self._conversation
        conversation.start_turn(turn_message(self._template, TurnPosition(board, moves, listed_moves)))
        remembered = conversation.remembered
        logged_remembered = {"remembered": remembered} if remembered is not None else {}
        turn = LlmTurn(
            ply=ply, color=color, attempts=[], time_s=0.0, thinking=None, reasoning=None, remembered=remembered
        )
        feedback = None
        illegal_in_turn = False  # a turn recovers only from an illegal move, not from a cut-off answer
        max_attempts = self._max_attempts
        for number in range(1, max_attempts + 1):
            if self._abandoned.is_set():
                return TurnOutcome(turn)
            # The Prompt as sent for this attempt, or in a conversation what it added (ADR 0009).
            prompt = conversation.record()
            messages = conversation.messages()
            # Until a conversation is trimmed to the context (#106), the log says when Ollama may have cut it.
            logged_context = {"context_may_be_cut": True} if conversation.may_not_fit(reply_reserve(side)) else {}
            try:
                reply = player.reply(messages, allowed_moves)
            except Exception as error:
                attempt = no_answer(model, error, prompt, feedback)
                turn.attempts.append(attempt)
                self._log.write(
                    "llm_attempt", color=color, ply=ply, attempt=number, pgn=pgn, fen=fen, **logged_list,
                    **self._rules.attempt_log_shape(attempt.log_shape()), **logged_remembered, **logged_context,
                    **self._ended(turn, started),
                )
                turn.reasoning = None  # the turn's Reasoning is its last attempt's: none without an answer
                break
            result: AttemptResult
            written, move, result = judge(board, reply.raw)
            if result == "invalid" and reply.forced and reply.stop_reason == "length":
                result = "cut_off"  # the forced answer ran out of tokens too: no answer, rather than a bad one
            resolution = self._rules.resolve(board, written, result)
            recorded = resolution.record() if resolution is not None else None
            attempt = answered(board, reply, written, move, result, side.thinking, prompt, feedback, recorded)
            turn.attempts.append(attempt)
            chaos = move is None and resolution is not None and resolution.kind in ("chaos", "spawn")
            last = move is not None or chaos or number == max_attempts  # it is played, or the turn forfeits
            self._log.write(
                "llm_attempt", color=color, ply=ply, attempt=number, pgn=pgn, fen=fen, **logged_list,
                **self._rules.attempt_log_shape(attempt.log_shape()), **logged_remembered, **logged_context,
                **token_accounting(reply), **(self._ended(turn, started) if last else {}),
            )
            conversation.answered(reply.raw)
            turn.thinking, turn.reasoning = attempt.thinking, attempt.reasoning
            if move is not None:
                if illegal_in_turn:
                    stats.recovered_turns += 1
                if attempt.notation_slip:
                    stats.notation_slips += 1
                if not stats.streak_broken:
                    stats.legal_move_streak += 1
                return TurnOutcome(turn, move=move)
            if result == "cut_off":
                feedback = cut_off_feedback(number, max_attempts)
                conversation.retry(feedback)
                continue
            illegal_in_turn = True
            stats.illegal_moves[result] += 1
            stats.streak_broken = True
            if chaos and resolution is not None:  # played at once, with no retry
                stats.chaos_moves += 1
                stats.spawns += resolution.kind == "spawn"
                return TurnOutcome(turn, chaos_move=resolution, written=written)
            if side.retry_feedback == "repeat":  # another sample: the first Prompt again, the rejected move unseen
                feedback = None
                conversation.drop_answer()
            else:
                feedback = retry_feedback(side.retry_feedback, written, result, number, max_attempts, legal_moves)
                conversation.retry(feedback)
        return TurnOutcome(turn, forfeit=True)

    def _ended(self, turn: LlmTurn, started: float) -> dict[str, Any]:
        """Time the turn, as its last attempt ends it, and return what that attempt logs of it. Only the turn's own
        attempts are timed: anything asked after them is not its Time used."""
        turn.time_s = round(self._clock() - started, 3)
        return turn.log_shape()

    def legal_counterpart(self, board: chess.Board, moves: Sequence[str]) -> CounterpartAnswer | None:
        """Ask for the Legal counterpart of the chaos move a turn just ended in. board and moves are as the turn had
        them: the chaos move isn't played yet. None in an abandoned game, which asks for nothing more.

        It is asked apart from the turn, after it, so its call is none of the turn's attempts and its time none of
        the turn's (Time used), and nothing about it counts in the side's totals."""
        if self._abandoned.is_set():
            return None
        return ask_legal_counterpart(self._player, self._side, self._template, self._color, board, moves)

    def log_legal_counterpart(self, answer: CounterpartAnswer, ply: int) -> None:
        """Log the Legal counterpart of the chaos move of ply, once its turn has landed."""
        counterpart = answer.counterpart
        self._log.write(
            "legal_counterpart", color=self._color, ply=ply, pgn=answer.pgn, fen=answer.fen,
            legal_moves=answer.listed_moves, **counterpart.attempt.log_shape(), uci=counterpart.move,
            fen_after=counterpart.fen_after, **(token_accounting(answer.reply) if answer.reply is not None else {}),
        )
