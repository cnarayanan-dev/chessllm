"""The probe log of a game: its Probes, one JSON line each, appended as they are asked, in a file of its own next to
the game's log, which no probe ever touches (ADR 0010): games/<stem>.probes.ndjson for games/<stem>.jsonl.

It is JSON Lines like the game log, but not named *.jsonl, so every reader of the games folder's game logs (the
leaderboard, the reports, the analysis) leaves it out."""

import json
from pathlib import Path

from chessllm.game.llm_turn.probe import Probe

SUFFIX = ".probes.ndjson"


def probe_log_path(game_log: Path) -> Path:
    """The probe log of the game whose log is game_log."""
    return game_log.with_suffix(SUFFIX)


class ProbeLog:
    """The probe log of one game, created with its first Probe."""

    def __init__(self, game_log: Path) -> None:
        self.path = probe_log_path(game_log)

    def write(self, probe: Probe) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"type": "probe", **probe.model_dump(mode="json")}, ensure_ascii=False) + "\n")


def read_probes(path: Path) -> list[Probe]:
    """The Probes of a probe log, in the order they were asked."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Probe.model_validate({key: value for key, value in json.loads(line).items() if key != "type"}) for line in lines]


def probes_of(games_dir: Path, game_id: str) -> list[Probe]:
    """The Probes of the game with this id in the games folder, in the order they were asked; none for a game that has
    no probe log, or that the folder doesn't hold. Read from the files, so a game's probes are there after a restart."""
    for path in sorted(games_dir.glob(f"*{SUFFIX}")) if games_dir.is_dir() else []:
        with path.open(encoding="utf-8") as file:
            first = file.readline()
        if first and json.loads(first)["game_id"] == game_id:  # each log holds one game's probes
            return read_probes(path)
    return []
