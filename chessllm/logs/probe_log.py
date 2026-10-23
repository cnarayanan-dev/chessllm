"""The probe log of a game (ADR 0010): one JSON Lines file per game in the probes/ folder next to the game logs,
named by the game's id, e.g. games/probes/<game_id>.jsonl, appended a probe event per Probe. Kept out of the game
logs' folder itself, so nothing that reads every game log (the leaderboard, the analysis, the report) ever reads it,
and the game log is never touched."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from chessllm.game.llm_turn.probe import Probe

PROBES_FOLDER = "probes"


class ProbeLog:
    """The probes of the game game_id, whose log is in games_dir. The file is only made with the first probe."""

    def __init__(self, games_dir: Path, game_id: str) -> None:
        self.path = games_dir / PROBES_FOLDER / f"{game_id}.jsonl"

    def write(self, probe: Probe, **fields: Any) -> None:
        """Append the probe, with fields only the log has (its call's token counts)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        shape = {"type": "probe", **probe.model_dump(mode="json", by_alias=True), **fields}
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(shape, ensure_ascii=False) + "\n")

    def probes(self) -> list[Probe]:
        """Every probe of the game, in the order asked; none for a game never probed. A line that can't be read, such
        as a write cut off by a crash, is skipped, so the others are still listed."""
        if not self.path.is_file():
            return []
        probes = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                probes.append(Probe.model_validate(json.loads(line)))
            except (json.JSONDecodeError, ValidationError):
                logging.getLogger(__name__).warning("skipped line %d of %s: not a probe", number, self.path)
        return probes
