"""The Stockfish adapter of the Evaluator port, through python-chess's UCI engine support.

Stockfish isn't bundled: it's found on the PATH (`brew install stockfish`) unless a path is given. Every position
is searched to a fixed depth with one thread, and with the hash cleared first (a new UCI game), so the same
position gets the same evaluation whatever was analysed before it."""

import shutil
import threading
from pathlib import Path
from types import TracebackType
from typing import Self

import chess
import chess.engine

DEPTH = 16
THREADS = 1
HASH_MB = 64


class StockfishUnavailable(Exception):
    """Stockfish can't be started: it isn't installed, or it won't run."""


class StockfishEvaluator:
    """Starts Stockfish the first time it's needed and keeps it for every later game. Safe to share between
    threads: one position at a time goes to the engine."""

    def __init__(self, path: Path | str | None = None, depth: int = DEPTH) -> None:
        self._path = path
        self._depth = depth
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = threading.Lock()

    def _started(self) -> chess.engine.SimpleEngine:
        if self._engine is None:
            path = self._path or shutil.which("stockfish")
            if path is None:
                raise StockfishUnavailable("stockfish is not on the PATH; install it with `brew install stockfish`")
            try:
                engine = chess.engine.SimpleEngine.popen_uci(str(path))
                engine.configure({"Threads": THREADS, "Hash": HASH_MB})
            except (OSError, chess.engine.EngineError, chess.engine.EngineTerminatedError) as error:
                raise StockfishUnavailable(f"stockfish at {path} won't start: {error}") from error
            self._engine = engine
        return self._engine

    @property
    def version(self) -> str:
        with self._lock:
            return self._started().id.get("name", "Stockfish")

    @property
    def search(self) -> dict[str, int]:
        return {"depth": self._depth, "threads": THREADS, "hash_mb": HASH_MB}

    def evaluate(self, fen: str) -> chess.engine.Score:
        with self._lock:
            engine = self._started()
            # A new game object for every position makes python-chess send ucinewgame, which clears the hash.
            info = engine.analyse(chess.Board(fen), chess.engine.Limit(depth=self._depth), game=object())
        return info["score"].relative

    def close(self) -> None:
        with self._lock:
            if self._engine is not None:
                self._engine.quit()
                self._engine = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()
