"""Game log writer: one JSON Lines file per game, appended as the game goes, plus a PGN file when it ends."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import chess
import chess.pgn

GAMES_DIR = Path("games")


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class GameLog:
    """The files of one game, named by start time and model, e.g. games/2026-10-18T20-31-05_qwen3.5-9b.jsonl.

    Every event is written as it happens, so a game abandoned with "New game" keeps its log so far."""

    def __init__(self, games_dir: Path, model: str) -> None:
        games_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{datetime.now():%Y-%m-%dT%H-%M-%S}_{model.replace(':', '-').replace('/', '-')}"
        self.game_id = uuid.uuid4().hex
        self.path = games_dir / f"{stem}.jsonl"
        number = 1
        while self.path.exists():  # two games started within the same second
            number += 1
            self.path = games_dir / f"{stem}_{number}.jsonl"

    def write(self, event_type: str, **fields: Any) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"type": event_type, **fields}, ensure_ascii=False) + "\n")

    def write_pgn(self, board: chess.Board, headers: dict[str, str]) -> None:
        game = chess.pgn.Game.from_board(board)
        game.headers.update(headers)
        self.path.with_suffix(".pgn").write_text(str(game) + "\n", encoding="utf-8")
