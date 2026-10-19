"""The Anchor port: an opponent of known strength that, given a position, returns a move (ADR 0005).

The one adapter is Komodo Dragon 1, driven over UCI by python-chess. Dragon isn't bundled: it is downloaded from
komodochess.com (/pub/dragon.zip) and its executable's path is configured, with --dragon or CHESSLLM_DRAGON."""

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import chess
import chess.engine

# The Dragon Skill levels that are Anchors: Skill s is rated 125 × (s + 1) on the chess.com scale.
DRAGON_SKILLS = range(1, 8)
DRAGON_PATH_VARIABLE = "CHESSLLM_DRAGON"
# Dragon's strength is set by its Skill, not by its thinking time; this only keeps a game quick.
MOVE_TIME_S = 0.1
START_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class AnchorRating:
    """An Anchor's strength on the chess.com Rapid scale: its rating and the standard deviation of the Gaussian prior
    the Rating fit holds it at (ADR 0005)."""

    rating: float
    uncertainty: float


# Every Anchor's rating, by the Anchor's name (see anchor_name). The one place they are set: another Anchor, such as a
# random legal mover at about -122, is added here and then rated games against it count towards the Rating.
ANCHOR_RATINGS: dict[str, AnchorRating] = {
    f"anchor:dragon:{skill}": AnchorRating(rating=125 * (skill + 1), uncertainty=100) for skill in DRAGON_SKILLS
}


def anchor_name(side: dict[str, Any]) -> str:
    """An Anchor side's name, from its description in game_start, e.g. "anchor:dragon:3" for Dragon at Skill 3."""
    return ":".join(["anchor", *(str(side[key]) for key in ("engine", "skill") if key in side)])


class AnchorUnavailable(Exception):
    """The Anchor can't play: its engine isn't configured, isn't there, won't start or stopped answering."""


class Anchor(Protocol):
    def move(self, board: chess.Board) -> chess.Move:
        """A legal move in the position on the board, which it leaves unchanged. Raises AnchorUnavailable."""
        ...

    def close(self) -> None:
        """Stop the Anchor's engine, if it has one."""
        ...


def configured_dragon_path(path: str | None = None) -> Path:
    """The Dragon executable: the given path, else the CHESSLLM_DRAGON environment variable.

    Raises AnchorUnavailable if neither is set."""
    path = path or os.environ.get(DRAGON_PATH_VARIABLE)
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
