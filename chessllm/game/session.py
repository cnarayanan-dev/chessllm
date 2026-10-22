"""One game, each side played by a human, an LLM player or an Anchor as the settings' Mode says: the board, the
order of turns, and the human's and the Anchor's moves. An LLM's turn is played by llm_turn, under the game's Rules."""

import threading
from datetime import date
from pathlib import Path
from typing import Any

import chess

from chessllm.core.types import COLORS, Color, color_of
from chessllm.engines.anchors import Anchor
from chessllm.exceptions import AnchorUnavailable, RefusedAnchorTurn, RefusedLlmTurn, RejectedHumanMove
from chessllm.game.ending import GameEnd, check_end, position_key
from chessllm.game.llm_turn.prompt import SYSTEM_PROMPT_FILES
from chessllm.game.llm_turn.turn import LlmTurns
from chessllm.game.records import GameSettings, GameState, LlmTurn, Ply, Stats
from chessllm.game.rules.chaos import ResolvedMove, apply
from chessllm.game.settings import Settings
from chessllm.game.sides import HumanSide, side_log_shape
from chessllm.llm.players import LlmPlayer
from chessllm.logs.game_log import GameLog, now


class GameSession:
    def __init__(
        self,
        players: dict[Color, LlmPlayer],
        settings: Settings,
        log: GameLog,
        anchors: dict[Color, Anchor] | None = None,
    ) -> None:
        """players holds the LLM player of each LLM side, and anchors the Anchor of each Anchor side."""
        self._anchors = anchors or {}
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
        # The settings as the state has them, fixed for the whole game.
        self._game_settings = GameSettings(
            mode=settings.mode,
            white=settings.white,
            black=settings.black,
            sampling=settings.sampling,
            rules=settings.rules,
            max_attempts=settings.max_attempts,
        )
        # Requests run in a threadpool, so two could otherwise both find it an LLM's turn and both ask it to move.
        # The lock is the game's own, so a new game can start while an abandoned game's turn finishes.
        self._llm_turn_running = threading.Lock()
        self._abandoned = threading.Event()  # set by abandon(), from the request that starts a new game
        # Held while the game is abandoned and while an LLM turn ends the game, so a game is never both.
        self._ending = threading.Lock()
        # The turns of each LLM side, which keep its totals.
        self._turns_of = {
            color: LlmTurns(color, side, players[color], self._rules, settings.max_attempts, log, self._abandoned)
            for color, side in self._llm_sides.items()
        }
        prompt_files = {color: str(SYSTEM_PROMPT_FILES[side.llm_constraints]) for color, side in self._llm_sides.items()}
        log.write(
            "game_start",
            game_id=log.game_id,
            log_version=2,
            mode=settings.mode,
            white=side_log_shape(settings.white),
            black=side_log_shape(settings.black),
            sampling=settings.sampling or "model_default",
            max_retries=settings.max_attempts - 1,
            **self._mode.logged_prompt_files(prompt_files),
            **self._rules.game_start_fields(),
            # To the microsecond, so games started within the same second still sort in the order they started.
            started_at=now("microseconds"),
        )

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
            raise RefusedAnchorTurn("the game is over", code="game_over")
        color = color_of(board.turn)
        anchor = self._anchors.get(color)
        if anchor is None:
            raise RefusedAnchorTurn("it is not an Anchor's turn", code="not_anchor_turn")
        move = anchor.move(board.copy())
        if not board.is_legal(move):
            raise AnchorUnavailable(f"{self._pgn_name(color)} played an illegal move: {move.uci()}")
        san = self._play_legal(move)
        self._log.write("anchor_move", color=color, ply=len(self._moves), move=san, fen_after=self._board.fen())
        self._check_end()
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
            last_move = self._moves[-1][1] if self._moves else None
            outcome = self._turns_of[color].play(self._board, self._pgn(), last_move, len(self._moves) + 1)
            if outcome.move is not None:
                self._play_legal(outcome.move)
            elif outcome.chaos_move is not None and outcome.written is not None:
                self._play_chaos(outcome.chaos_move, outcome.written)
            with self._ending:
                if self._abandoned.is_set():
                    return  # the running turn, stopped early or not, is never published
                self._publish_llm_turn(outcome.turn)
                if outcome.forfeit:
                    self._end = GameEnd("0-1" if color == "white" else "1-0", "forfeit")  # the side to move loses
                else:
                    self._check_end()
                if self._end is not None:
                    self._write_end(self._end)
        finally:
            self._llm_turn_running.release()

    def _publish_llm_turn(self, turn: LlmTurn) -> None:
        """Add the turn just played to the state in one step, so state(), which takes no lock, never shows a turn
        half-built. It comes after the turn's move is on the board and before the game ends: a page waiting on a
        running turn checks for llm_turns to grow or the game to be over, so neither may run ahead of it."""
        self._llm_turns.append(turn)

    def _write_end(self, end: GameEnd) -> None:
        self._log.write(
            "game_end",
            result=end.result,
            reason=end.reason,
            plies=len(self._moves),
            stats=self._all_stats().log_shape(),
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
        )

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
        return " ".join(
            f"{ply // 2 + 1}. {written}" if ply % 2 == 0 else written for ply, (_, written) in enumerate(self._moves)
        )

    def _play_legal(self, move: chess.Move) -> str:
        """Play a legal move, the human's, the Anchor's or the LLM's, and return its SAN."""
        san, fen_before = self._board.san(move), self._board.fen()
        self._board.push(move)
        if self._first_chaos_ply is None:
            self._standard_moves.append(move)
        self._played(move.uci(), san, fen_before)
        return san

    def _play_chaos(self, resolution: ResolvedMove, written: str) -> None:
        """Play a chaos move or spawn by editing the board by hand (ADR 0006), recorded as the LLM wrote it."""
        uci, fen_before = resolution.uci(self._board), self._board.fen()
        self._board = apply(self._board, resolution)
        if self._first_chaos_ply is None:
            self._first_chaos_ply = len(self._moves) + 1
        self._played(uci, written, fen_before, resolution)

    def _played(self, uci: str, written: str, fen_before: str, resolution: ResolvedMove | None = None) -> None:
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
            resolution=resolution.record() if resolution is not None else None,
        )
        self._plies.append(ply)
