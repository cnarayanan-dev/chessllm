"""The Maia-2 adapter of the MoveModel port: the rapid model, on MPS where there is one.

maia2 supports only Python < 3.13 and pins torch 2.8, while this project runs on 3.13, so it can't be a
dependency, not even an optional one. The adapter runs chessllm/maia2_worker.py instead in an environment of its
own, built and cached by uv on first use: `uv run --no-project --python 3.12 --with maia2==0.11.0`. The first
run downloads torch and the 280 MB rapid checkpoint (into ~/.cache/chessllm/maia2), so it takes a while; later
runs start in seconds."""

import json
import shutil
import subprocess
import threading
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any, Self

MAIA2_REQUIREMENT = "maia2==0.11.0"
WORKER = Path(__file__).with_name("maia2_worker.py")
SAVE_ROOT = Path.home() / ".cache" / "chessllm" / "maia2"


class Maia2Unavailable(Exception):
    """Maia-2 can't be started: uv is missing, or its environment or model can't be set up."""


class Maia2MoveModel:
    """Starts the worker the first time it's needed and keeps it for every later game. Safe to share between
    threads: one request at a time goes to the worker."""

    def __init__(self, save_root: Path = SAVE_ROOT, device: str = "auto") -> None:
        self._save_root = save_root
        self._device = device
        self._process: subprocess.Popen[str] | None = None
        self._version = ""
        self._ratings: list[int] = []
        self._lock = threading.Lock()

    def command(self) -> list[str]:
        uv = shutil.which("uv")
        if uv is None:
            raise Maia2Unavailable("uv is not installed, and Maia-2 runs in an environment uv makes")
        return [
            uv, "run", "--quiet", "--no-project", "--python", "3.12", "--with", MAIA2_REQUIREMENT,
            "python", "-I", str(WORKER), "--save-root", str(self._save_root), "--device", self._device,
        ]  # fmt: skip

    def _worker(self) -> subprocess.Popen[str]:
        if self._process is None:
            process = subprocess.Popen(self.command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            hello = self._read(process)
            self._process, self._version, self._ratings = process, hello["version"], hello["ratings"]
        return self._process

    @staticmethod
    def _read(process: subprocess.Popen[str]) -> dict[str, Any]:
        assert process.stdout is not None
        line = process.stdout.readline()
        if not line:
            process.wait()
            raise Maia2Unavailable(f"the Maia-2 worker stopped (exit code {process.returncode}); see its output above")
        answer: dict[str, Any] = json.loads(line)
        return answer

    @property
    def version(self) -> str:
        with self._lock:
            self._worker()
            return self._version

    @property
    def ratings(self) -> Sequence[int]:
        with self._lock:
            self._worker()
            return list(self._ratings)

    def probabilities(self, fen: str, move: str) -> list[float]:
        with self._lock:
            process = self._worker()
            assert process.stdin is not None
            process.stdin.write(json.dumps({"fen": fen, "move": move}) + "\n")
            process.stdin.flush()
            answer = self._read(process)
        if "error" in answer:
            raise ValueError(f"Maia-2 could not score {move} in {fen}: {answer['error']}")
        probabilities: list[float] = answer["probabilities"]
        return probabilities

    def close(self) -> None:
        with self._lock:
            if self._process is not None:
                assert self._process.stdin is not None
                self._process.stdin.close()  # the worker ends at the end of its input
                self._process.wait()
                self._process = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()
