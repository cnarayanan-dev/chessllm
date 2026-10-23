"""One game, each side played by a human, an LLM player or an Anchor as the settings' Mode says: the board, the
order of turns, and the human's and the Anchor's moves. An LLM's turn is played by llm_turn, under the game's Rules."""

import logging
import threading
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import chess

from chessllm.core.types import COLORS, Color, color_of
from chessllm.engines.anchors import Anchor
from chessllm.engines.evaluator import Evaluator
from chessllm.exceptions import AnchorUnavailable, RefusedAnchorTurn, RefusedLlmTurn, RejectedHumanMove
from chessllm.game.ending import GameEnd, check_end, position_key
from chessllm.game.evaluation import judge
from chessllm.game.llm_turn.prompt import move_record, prompt_file, side_template
from chessllm.game.llm_turn.turn import LlmTurns
from chessllm.game.records import EvaluationEngine, GameSettings, GameState, LlmTurn, Ply, Stats, TimeUsed
from chessllm.game.rules.chaos import ResolvedMove, apply
from chessllm.game.settings import Settings
from chessllm.game.sides import HumanSide, side_log_shape
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog, now


def started(evaluator: Evaluator | None) -> tuple[Evaluator | None, EvaluationEngine | None]:
    """The evaluator and the engine it runs, once it has started; neither if it can't start (Stockfish isn't
    installed), and the game is played without Evaluations."""
    if evaluator is None:
        return None, None
    try:
        return evaluator, EvaluationEngine(version=evaluator.version, search=evaluator.search)
    except Exception:  # the game goes on without Evaluations; the analysis says so again at its end
        logging.getLogger(__name__).exception("the evaluator won't start, so this game gets no Evaluations")
        return None, None


class GameSession:
    def __init__(
        self,
        players: dict[Color, LlmPlayer],
        settings: Settings,
        log: GameLog,
        anchors: dict[Color, Anchor] | None = None,
        clock: Callable[[], float] = time.monotonic,
        evaluator: Evaluator | None = None,
    ) -> None:
        """players holds the LLM player of each LLM side, and anchors the Anchor of each Anchor side. clock times
        each side's moves, its Time used. With an evaluator, every ply is judged as it is played, by the request
        that plays it."""
        self._anchors = anchors or {}
        self._clock = clock
        self._evaluator, self._evaluation_engine = started(evaluator)
        self._settings = settings
        self._mode = settings.the_mode()
        self._rules = settings.the_rules()
        self._llm_sides = settings.llm_sides()
        self._log = log
        self._board = chess.Board()
        # The game's own record of every ply (ADR 0006): a chaos move edits the board by hand, which clears
        # python-chess's move stack, so repetition, the last move and the Move record come from these lists.
        self._positions = [position_key(self._board)]  # the start position, then the position after each ply
        self._moves: list[tuple[str, str]] = []  # each ply's move in UCI and as written in the Move record
        # Each ply as the page gets it for its move history: the move and the whole position before and after it,
        # so the page can step through the game without any chess logic (ADR 0001).
        self._plies: list[Ply] = []
        self._standard_moves: list[chess.Move] = []  # the moves up to the first chaos move, for the PGN export
        self._first_chaos_ply: int | None = None
        # Every LLM turn of the game, the last one included. A turn joins only once it has landed, played or
        # forfeited.
        self._llm_turns: list[LlmTurn] = []
        self._end: GameEnd | None = None
        self._time_used: dict[Color, float] = dict.fromkeys(COLORS, 0.0)  # each side's finished moves
        # When the move of the side to move started, while it runs: a human's once the position is ready, an LLM's
        # once its Turn starts and an Anchor's once its move is asked for.
        self._move_started: float | None = None
        # When an LLM's turn ended, while its chaos move waits for its Legal counterpart: the clock stands still.
        self._move_ended: float | None = None
        # The settings as the state has them, fixed for the whole game.
        self._game_settings = GameSettings(
            mode=settings.mode,
            white=settings.white,
            black=settings.black,
            sampling=settings.sampling,
            rules=settings.rules,
            max_attempts=settings.max_attempts,
            legal_counterpart=settings.legal_counterpart if self._rules.plays_illegal_moves else None,
        )
        # Whether each chaos move's Legal counterpart is asked for: never under Standard rules, which have none.
        self._legal_counterparts = bool(self._game_settings.legal_counterpart)
        # Requests run in a threadpool, so two could otherwise both find it an LLM's turn and both ask it to move.
        # The lock is the game's own, so a new game can start while an abandoned game's turn finishes.
        self._llm_turn_running = threading.Lock()
        self._abandoned = threading.Event()  # set by abandon(), from the request that starts a new game
        # Held while the game is abandoned, while an LLM turn ends the game, so a game is never both, and while a
        # ply's Evaluation is added, so an abandoned game never gets one.
        self._ending = threading.Lock()
        # Held while a move lands and while state() is built, so the state never shows a move without its time and
        # the clock it starts, or the reverse. Never held while a side thinks, so a running turn doesn't hold up the
        # state.
        self._landing = threading.Lock()
        # The Prompt template of each LLM side, read once, so the game plays it unchanged whatever happens to its
        # files (ADR 0010).
        templates = {color: side_template(side) for color, side in self._llm_sides.items()}
        # The turns of each LLM side, which keep its totals.
        self._turns_of = {
            color: LlmTurns(
                color, side, templates[color], players[color], self._rules, settings.max_attempts, log,
                self._abandoned, clock,
            )
            for color, side in self._llm_sides.items()
        }
        # The System prompt file of each side playing a default template, which the leaderboard still groups by.
        prompt_files = {
            color: str(file)
            for color, side in self._llm_sides.items()
            if (file := prompt_file(templates[color], side.llm_constraints)) is not None
        }
        log.write(
            "game_start",
            game_id=log.game_id,
            log_version=2,
            mode=settings.mode,
            white=side_log_shape(settings.white, templates.get("white")),
            black=side_log_shape(settings.black, templates.get("black")),
            sampling=settings.sampling or "model_default",
            max_retries=settings.max_attempts - 1,
            **self._mode.logged_prompt_files(prompt_files),
            **self._rules.game_start_fields(),
            **self._game_settings.model_dump(include={"legal_counterpart"}, exclude_none=True),
            **({"evaluator": self._evaluation_engine.log_shape()} if self._evaluation_engine else {}),
            # To the microsecond, so games started within the same second still sort in the order they started.
            started_at=now("microseconds"),
        )
        self._position_ready()

    @property
    def log_path(self) -> Path:
        """The game's log file, which is analysed when the game ends."""
        return self._log.path

    def abandon(self) -> None:
        """Leave the game for a new one. A running LLM turn makes no further attempts, and the game never ends:
        no game_end is written and it is never analysed, so the leaderboard skips it like any abandoned game."""
        with self._ending:
            self._abandoned.set()

    def play_human_move(self, uci: str) -> None:
        """Apply the human's move. The LLM's reply is a separate turn, started with play_llm_turn.

        Raises RejectedHumanMove and leaves the game unchanged."""
        arrived = self._clock()
        board = self._board
        if self._end is not None:
            raise RejectedHumanMove("the game is over", code="game_over")
        if not self._mode.accepts_human_moves:
            raise RejectedHumanMove(f"an {self._mode.name} takes no human moves", code="not_human_turn")
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            raise RejectedHumanMove(f"not a UCI move: {uci!r}", code="invalid_move") from None
        color = color_of(board.turn)
        if color in self._llm_sides or not board.is_legal(move):
            raise RejectedHumanMove(f"illegal move: {uci}", code="illegal_move")
        with self._landing:
            time_s = self._move_time(arrived)
            self._play_legal(move, time_s)
            self._charge(color, time_s)
            self._check_end()
            self._position_ready()
            unjudged = self._ply_to_judge()
        self._log.write("human_move", **self._plies[-1].log_shape())
        self._judge(unjudged)
        if self._end is not None:
            self._write_end(self._end)

    def play_anchor_turn(self) -> None:
        """Ask the Anchor to move for its move and play it, like a human's move but without a request.

        Raises RefusedAnchorTurn and leaves the game unchanged if it isn't an Anchor's turn or the game is over,
        and AnchorUnavailable if the Anchor fails or answers with an illegal move."""
        board = self._board
        if self._end is not None:
            raise RefusedAnchorTurn("the game is over", code="game_over")
        color = color_of(board.turn)
        anchor = self._anchors.get(color)
        if anchor is None:
            raise RefusedAnchorTurn("it is not an Anchor's turn", code="not_anchor_turn")
        self._move_started = self._clock()
        try:
            move = anchor.move(board.copy())
            if not board.is_legal(move):
                raise AnchorUnavailable(f"{self._pgn_name(color)} played an illegal move: {move.uci()}")
        except BaseException:
            self._move_started = None  # no one is making the move now, until it is asked for again
            raise
        with self._landing:
            time_s = self._move_time(self._clock())
            self._play_legal(move, time_s)
            self._charge(color, time_s)
            self._check_end()
            self._position_ready()
            unjudged = self._ply_to_judge()
        self._log.write("anchor_move", **self._plies[-1].log_shape())
        self._judge(unjudged)
        if self._end is not None:
            self._write_end(self._end)

    def play_llm_turn(self) -> None:
        """Play the turn of the LLM to move: it moves or forfeits. In an abandoned game it does neither: a turn
        not started yet is never played, and a running one stops before its next attempt and never ends the game.

        Raises RefusedLlmTurn and leaves the game unchanged if it isn't an LLM's turn, the game is over, or
        another LLM turn is still running."""
        if not self._llm_turn_running.acquire(blocking=False):
            raise RefusedLlmTurn("an LLM turn is already running", code="llm_turn_running")
        try:
            if self._abandoned.is_set():
                return
            if self._end is not None:
                raise RefusedLlmTurn("the game is over", code="game_over")
            color = color_of(self._board.turn)
            if color not in self._llm_sides:
                raise RefusedLlmTurn("it is not an LLM's turn", code="not_llm_turn")
            turns, moves = self._turns_of[color], [written for _, written in self._moves]
            self._move_started = started = self._clock()
            outcome = turns.play(self._board, moves, started)
            time_s = outcome.turn.time_s
            counterpart = None
            if outcome.chaos_move is not None and self._legal_counterparts:
                # Asked once the turn is over and before its chaos move is played, so the move and its counterpart
                # land together. The side's clock stops at the turn's last attempt: the counterpart's call is never
                # its Time used, nor on its running clock.
                with self._landing:
                    self._move_ended = started + time_s
                counterpart = turns.legal_counterpart(self._board, moves)
                if counterpart is not None:
                    outcome.turn.legal_counterpart = counterpart.counterpart
            with self._ending:
                with self._landing:
                    if outcome.move is not None:
                        self._play_legal(outcome.move, time_s)
                    elif outcome.chaos_move is not None and outcome.written is not None:
                        self._play_chaos(outcome.chaos_move, outcome.written, time_s)
                    if self._abandoned.is_set():
                        return  # the running turn, stopped early or not, is never published, nor its time added
                    self._publish_llm_turn(outcome.turn)
                    self._charge(color, time_s)
                    if outcome.forfeit:
                        self._end = GameEnd("0-1" if color == "white" else "1-0", "forfeit")  # the side to move loses
                    else:
                        self._check_end()
                    self._position_ready()
                    played = outcome.move is not None or outcome.chaos_move is not None
                    unjudged = self._ply_to_judge() if played else None
                if counterpart is not None:  # logged only with its turn: an abandoned game's never is
                    turns.log_legal_counterpart(counterpart, len(moves) + 1)
                if self._end is not None:
                    self._write_end(self._end)
            self._judge(unjudged)
        finally:
            self._llm_turn_running.release()

    def _publish_llm_turn(self, turn: LlmTurn) -> None:
        """Add the turn just played to the state in one step, so state() never shows a turn half-built. It comes
        after the turn's move is on the board and before the game ends: a page waiting on a running turn checks for
        llm_turns to grow or the game to be over, so neither may run ahead of it."""
        self._llm_turns.append(turn)

    def _ply_to_judge(self) -> tuple[Evaluator, int, chess.Board] | None:
        """With _landing held, once a ply has landed: what judging it takes, the evaluator, the ply's index and a
        copy of its position, or None without an evaluator or once the game is over, as a position that ends the
        game has no Evaluation (the page shows the result there)."""
        if self._evaluator is None or self._end is not None:
            return None
        return self._evaluator, len(self._plies) - 1, self._board.copy(stack=False)

    def _judge(self, unjudged: tuple[Evaluator, int, chess.Board] | None) -> None:
        """Judge the ply that landed, outside _landing, as the engine can take a while: the ply is in the state
        without its Evaluation until then, which the page shows as evaluating. Its Evaluation joins the ply in one
        step, and the log after the move. An abandoned game is judged no further: its search is skipped, or its
        result dropped, and nothing more is written to its log."""
        if unjudged is None or self._abandoned.is_set():
            return
        evaluator, index, board = unjudged
        evaluation = judge(board, evaluator)
        with self._ending:
            if self._abandoned.is_set():
                return
            with self._landing:
                ply = self._plies[index] = self._plies[index].model_copy(update={"evaluation": evaluation})
            self._log.write("evaluation", ply=ply.ply, **evaluation.log_shape())

    def _write_end(self, end: GameEnd) -> None:
        self._log.write(
            "game_end",
            result=end.result,
            reason=end.reason,
            plies=len(self._moves),
            stats=self._all_stats().log_shape(),
            time_used=self._time_used_record().log_shape(),
            **self._rules.game_end_fields(len(self._moves), self._first_chaos_ply),
            ended_at=now(),
        )
        headers = {
            "Event": "ChessLLM",
            "Date": f"{date.today():%Y.%m.%d}",
            "White": self._pgn_name("white"),
            "Black": self._pgn_name("black"),
            "Result": end.result,
            "Termination": end.reason,
            "Mode": self._mode.name,
        }
        for color, side in self._llm_sides.items():
            headers[f"{color.capitalize()}LLMConstraints"] = side.llm_constraints
        headers |= self._rules.pgn_headers()
        # A chaos move has no valid PGN, so the export stops at the first one (ADR 0006).
        standard = chess.Board()
        for move in self._standard_moves:
            standard.push(move)
        self._log.write_pgn(standard, headers)

    def _pgn_name(self, color: Color) -> str:
        side = self._settings.side(color)
        return "Human" if isinstance(side, HumanSide) else side.name()

    def _check_end(self) -> None:
        """End the game if the position just played ends it: by the game's Rules first, then by the position."""
        self._end = self._rules.end(self._board) or check_end(self._board, self._positions, self._mode.unattended)

    def state(self) -> GameState:
        with self._landing:
            return self._state()

    def _state(self) -> GameState:
        board = self._board
        return GameState(
            game_id=self._log.game_id,
            fen=board.fen(),
            pgn=self._pgn(),
            turn=color_of(board.turn),
            human_legal_moves=self._human_legal_moves(),
            last_move=self._moves[-1][0] if self._moves else None,
            plies=self._plies,
            check=board.is_check(),  # the side to move's king, so the page needn't work it out (ADR 0001)
            llm_turn=self._llm_turns[-1] if self._llm_turns else None,
            llm_turns=self._llm_turns,
            settings=self._game_settings,
            status="over" if self._end else "playing",
            result=self._end.result if self._end else None,
            end_reason=self._end.reason if self._end else None,
            stats=self._all_stats(),
            time_used=self._time_used_record(),
            running_s=self._time_since_move_started(self._clock()) if self._end is None else None,
            evaluator=self._evaluation_engine,
        )

    def _position_ready(self) -> None:
        """Start the human's move once the position is ready for it. An LLM's or an Anchor's move starts only when
        it is asked for, and no one's once the game is over."""
        to_move = self._settings.side(color_of(self._board.turn))
        self._move_started = self._clock() if self._end is None and isinstance(to_move, HumanSide) else None
        self._move_ended = None

    def _time_since_move_started(self, now: float) -> float | None:
        """The time the running move has taken by now, to the millisecond, or None while no move runs. Once an LLM's
        turn has ended and its move waits for its Legal counterpart, the time up to the turn's end."""
        if self._move_started is None:
            return None
        return round((self._move_ended if self._move_ended is not None else now) - self._move_started, 3)

    def _move_time(self, now: float) -> float:
        """The time of the human's or the Anchor's move just finished, to the millisecond. It always started: a
        human's once the position was ready, an Anchor's when it was asked for."""
        time_s = self._time_since_move_started(now)
        return time_s if time_s is not None else 0.0

    def _charge(self, color: Color, time_s: float) -> None:
        """Add a finished move's time to its side's Time used."""
        self._time_used[color] = round(self._time_used[color] + time_s, 3)

    def _time_used_record(self) -> TimeUsed:
        return TimeUsed(**self._time_used)

    def _all_stats(self) -> Stats:
        """The totals of each side; a human's side has none (ADR 0004)."""
        white, black = (turns.stats.record() if (turns := self._turns_of.get(color)) else None for color in COLORS)
        return Stats(white=white, black=black)

    def _human_legal_moves(self) -> list[str]:
        board = self._board
        if self._end is not None or color_of(board.turn) in self._llm_sides:
            return []
        return [move.uci() for move in board.legal_moves]

    def _pgn(self) -> str:
        """The Move record: the moves so far as PGN movetext, e.g. "1. e4 e5", a chaos move in the LLM's own
        spelling. Under Standard rules it is valid PGN."""
        return move_record([written for _, written in self._moves])

    def _play_legal(self, move: chess.Move, time_s: float) -> str:
        """Play a legal move, the human's, the Anchor's or the LLM's, which took time_s, and return its SAN."""
        san, fen_before = self._board.san(move), self._board.fen()
        self._board.push(move)
        if self._first_chaos_ply is None:
            self._standard_moves.append(move)
        self._played(move.uci(), san, fen_before, time_s)
        return san

    def _play_chaos(self, resolution: ResolvedMove, written: str, time_s: float) -> None:
        """Play a chaos move or spawn by editing the board by hand (ADR 0006), recorded as the LLM wrote it."""
        uci, fen_before = resolution.uci(self._board), self._board.fen()
        self._board = apply(self._board, resolution)
        if self._first_chaos_ply is None:
            self._first_chaos_ply = len(self._moves) + 1
        self._played(uci, written, fen_before, time_s, resolution)

    def _played(
        self, uci: str, written: str, fen_before: str, time_s: float, resolution: ResolvedMove | None = None
    ) -> None:
        """Record the ply just played. Only a chaos move or spawn has a resolution, the same as the attempt that
        played it has, so the page can replay it without resolving it again."""
        self._moves.append((uci, written))
        self._positions.append(position_key(self._board))
        ply = Ply(
            ply=len(self._moves),
            color=color_of(not self._board.turn),
            move=uci,
            written=written,
            fen_before=fen_before,
            fen_after=self._board.fen(),
            check=self._board.is_check(),  # after the ply, as the state's check is for the live position
            time_s=time_s,
            resolution=resolution.record() if resolution is not None else None,
        )
        self._plies.append(ply)
