"""The Anchor port: an opponent of known strength that, given a position, returns a move (ADR 0005).

The adapters are Komodo Dragon 1 and Stockfish, both driven over UCI by python-chess. Dragon isn't bundled: it is
downloaded from komodochess.com (/pub/dragon.zip) and its executable's path is configured, with --dragon or
CHESSLLM_DRAGON. Stockfish is the stand-in where Dragon can't be had: its own strength settings don't go as low as
Dragon's Skill levels, so each of its Skill levels is a Stockfish Skill Level held to a shallow search depth, and its
ratings are rough guesses, not published ones. The random legal mover, the lowest Anchor (ADR 0011), needs no engine:
it plays a uniformly random legal move, from a seed drawn per game and logged with its side, so the game can be
replayed."""

import platform
import random
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import chess
import chess.engine

from chessllm.core.config import (
    DRAGON_PATH_VARIABLE,
    STOCKFISH_PATH_VARIABLE,
    dragon_path_from_environment,
    stockfish_path_from_environment,
)
from chessllm.exceptions import AnchorUnavailable

# The Dragon Skill levels that are Anchors: Skill s is rated 125 × (s + 1) on the chess.com scale.
DRAGON_SKILLS = range(1, 8)
# Dragon's strength is set by its Skill, not by its thinking time; this only keeps a game quick.
MOVE_TIME_S = 0.1
START_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class AnchorRating:
    """An Anchor's strength on the chess.com Rapid scale: its rating and the standard deviation of the Gaussian prior
    the Rating fit holds it at (ADR 0005)."""

    rating: float
    uncertainty: float


# Every Anchor's rating, by the Anchor's name (see anchor_name). The one place they are set: another Anchor is added
# here and then rated games against it count towards the Rating.
ANCHOR_RATINGS: dict[str, AnchorRating] = {
    f"anchor:dragon:{skill}": AnchorRating(rating=125 * (skill + 1), uncertainty=100) for skill in DRAGON_SKILLS
}
# Stockfish's Skill s (Stockfish Skill Level and search depth below) is guessed to play about as well as Dragon's Skill
# s. The guess is uncalibrated, so its prior is three times as wide as Dragon's and the fit can move it a long way.
STOCKFISH_LEVELS: dict[int, tuple[int, int]] = {1: (0, 1), 2: (0, 2), 3: (1, 3), 4: (2, 4), 5: (3, 5), 6: (4, 6), 7: (5, 7)}
ANCHOR_RATINGS |= {
    f"anchor:stockfish:{skill}": AnchorRating(rating=125 * (skill + 1), uncertainty=300) for skill in STOCKFISH_LEVELS
}
# The random legal mover is at LLM Chess's calibration, -122.3 on the same Dragon-anchored chess.com scale
# (docs/research/elo-estimation.md). It is published, not measured here, and was fitted from a pool scoring near 0%
# against Dragon Skill 1, where the logistic model is least sure, so its prior is twice as wide as Dragon's; but the
# mover is exactly the same program as theirs, so it is narrower than Stockfish's uncalibrated guess.
RANDOM_MOVER = "anchor:random"
ANCHOR_RATINGS[RANDOM_MOVER] = AnchorRating(rating=-122, uncertainty=200)


def anchor_name(side: dict[str, Any]) -> str:
    """An Anchor side's name, from its description in game_start, e.g. "anchor:dragon:3" for Dragon at Skill 3."""
    return ":".join(["anchor", *(str(side[key]) for key in ("engine", "skill") if key in side)])


class Anchor(Protocol):
    def move(self, board: chess.Board) -> chess.Move:
        """A legal move in the position on the board, which it leaves unchanged. Raises AnchorUnavailable."""
        ...

    def close(self) -> None:
        """Stop the Anchor's engine, if it has one."""
        ...


def new_seed() -> int:
    """A fresh seed for one game's random legal mover."""
    return secrets.randbits(32)


class RandomAnchor:
    """The random legal mover: in any position, a uniformly random legal move, the same ones for the same seed. The
    moves are drawn from in UCI order, so a seed replays the game whatever order python-chess generates them in."""

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def move(self, board: chess.Board) -> chess.Move:
        moves = sorted(board.legal_moves, key=chess.Move.uci)
        if not moves:
            raise AnchorUnavailable("the random mover has no legal move")
        return self._random.choice(moves)

    def close(self) -> None:
        pass  # no engine to stop


def configured_dragon_path(path: str | None = None) -> Path:
    """The Dragon executable: the given path, else the CHESSLLM_DRAGON environment variable.

    Raises AnchorUnavailable if neither is set."""
    path = path or dragon_path_from_environment()
    if not path:
        raise AnchorUnavailable(
            f"Dragon isn't configured: pass --dragon or set {DRAGON_PATH_VARIABLE} to the path of the Dragon "
            "executable (from dragon.zip at komodochess.com)."
        )
    return Path(path).expanduser()


def needs_rosetta() -> bool:
    """Whether this is a Mac on Apple silicon, where Dragon's x86_64-only macOS build runs under Rosetta 2."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


class DragonAnchor:
    """Komodo Dragon 1 at a Skill level, with Threads = 1, Auto Skill off and its default Personality, so that its
    strength matches the published Skill levels and doesn't vary between runs.

    The engine starts when the Anchor is made, so a missing or failing Dragon is found before the game starts.
    With rosetta (the default on Apple silicon) it runs under `arch -x86_64`."""

    def __init__(self, path: Path, skill: int, rosetta: bool | None = None, move_time_s: float = MOVE_TIME_S) -> None:
        if not path.is_file():
            raise AnchorUnavailable(f"Dragon isn't installed at {path}: no such file.")
        command = [str(path)]
        if needs_rosetta() if rosetta is None else rosetta:
            command = ["arch", "-x86_64", *command]
        self._limit = chess.engine.Limit(time=move_time_s)
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(command, timeout=START_TIMEOUT_S)
        except Exception as error:
            raise AnchorUnavailable(f"Dragon at {path} won't start: {error or type(error).__name__}") from error
        try:
            missing = [name for name in ("Skill", "Threads", "Auto Skill") if name not in self._engine.options]
            if missing:
                raise AnchorUnavailable(
                    f"{path} doesn't look like Dragon: it has no {', '.join(missing)} option "
                    f"(it calls itself {self._engine.id.get('name', 'nothing')!r})."
                )
            self._engine.configure({"Skill": skill, "Threads": 1, "Auto Skill": False})
        except AnchorUnavailable:
            self.close()
            raise
        except Exception as error:
            self.close()
            raise AnchorUnavailable(f"Dragon at {path} won't take Skill {skill}: {error}") from error

    def move(self, board: chess.Board) -> chess.Move:
        try:
            move = self._engine.play(board, self._limit).move
        except Exception as error:
            raise AnchorUnavailable(f"Dragon stopped answering: {error or type(error).__name__}") from error
        if move is None:
            raise AnchorUnavailable("Dragon gave no move")
        return move

    def close(self) -> None:
        try:
            self._engine.quit()
        except Exception:
            pass  # it has stopped already


def configured_stockfish_path(path: str | None = None) -> Path:
    """The Stockfish executable: the given path, else the CHESSLLM_STOCKFISH environment variable, else stockfish on
    the PATH. Raises AnchorUnavailable if there is none."""
    path = path or stockfish_path_from_environment() or shutil.which("stockfish")
    if not path:
        raise AnchorUnavailable(
            f"Stockfish isn't installed: pass --stockfish or set {STOCKFISH_PATH_VARIABLE} to its executable."
        )
    return Path(path).expanduser()


class StockfishAnchor:
    """Stockfish at one of its Skill levels (STOCKFISH_LEVELS): a Stockfish Skill Level and a search depth, with
    Threads = 1. The engine starts when the Anchor is made, so a missing Stockfish is found before the game starts."""

    def __init__(self, path: Path, skill: int) -> None:
        if not path.is_file():
            raise AnchorUnavailable(f"Stockfish isn't installed at {path}: no such file.")
        self._path = path
        self._skill_level, depth = STOCKFISH_LEVELS[skill]
        self._limit = chess.engine.Limit(depth=depth)
        self._engine = self._start()
        self.fallback_moves = 0  # moves in positions Stockfish refused, chosen by greedy_move instead

    def _start(self) -> chess.engine.SimpleEngine:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(str(self._path), timeout=START_TIMEOUT_S)
        except Exception as error:
            raise AnchorUnavailable(f"Stockfish at {self._path} won't start: {error or type(error).__name__}") from error
        try:
            engine.configure({"Skill Level": self._skill_level, "Threads": 1})
        except Exception as error:
            engine.quit()
            raise AnchorUnavailable(f"{self._path} won't take Skill Level {self._skill_level}: {error}") from error
        return engine

    def move(self, board: chess.Board) -> chess.Move:
        """Stockfish's move. Under Chaos rules the position can be one python-chess calls invalid, and Stockfish quits
        on those (ADR 0006): then it takes the enemy king if it can, else asks Stockfish about the position with any
        pawn on a back rank made a queen, and if Stockfish still won't have it, plays greedy_move."""
        if board.is_valid():
            return self._play(board)
        king_captures = [move for move in board.legal_moves if board.piece_type_at(move.to_square) == chess.KING]
        if king_captures:
            return king_captures[0]
        cleaned = board.copy(stack=False)
        for square in cleaned.pieces(chess.PAWN, chess.WHITE) | cleaned.pieces(chess.PAWN, chess.BLACK):
            if chess.square_rank(square) in (0, 7):
                cleaned.set_piece_at(square, chess.Piece(chess.QUEEN, cleaned.color_at(square) or chess.WHITE))
        if cleaned.is_valid():
            move = self._play(cleaned)
            if move in board.legal_moves:
                return move
        self.fallback_moves += 1
        return greedy_move(board)

    def _play(self, board: chess.Board) -> chess.Move:
        try:
            move = self._engine.play(board, self._limit).move
        except Exception as error:
            self.close()
            self._engine = self._start()  # it quits on a position it won't have; the game goes on with greedy_move
            if board.is_valid():
                raise AnchorUnavailable(f"Stockfish stopped answering: {error or type(error).__name__}") from error
            self.fallback_moves += 1
            return greedy_move(board)
        if move is None:
            raise AnchorUnavailable("Stockfish gave no move")
        return move

    def close(self) -> None:
        try:
            self._engine.quit()
        except Exception:
            pass  # it has stopped already


PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def greedy_move(board: chess.Board) -> chess.Move:
    """A move for a position no engine will take: the most valuable capture, else a check, else the first legal
    move. Raises AnchorUnavailable when there is no legal move."""
    moves = list(board.legal_moves)
    if not moves:
        raise AnchorUnavailable("no legal move in a position Stockfish won't take")

    def value(move: chess.Move) -> tuple[int, bool]:
        taken = board.piece_type_at(move.to_square)
        return (PIECE_VALUES[taken] if taken else 0, board.gives_check(move))

    return max(moves, key=value)
