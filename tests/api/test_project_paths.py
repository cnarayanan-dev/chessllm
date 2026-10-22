"""The app's files are found from the project root, not the working directory it is started from."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from chessllm.api.app import create_app
from tests.conftest import ScriptedPlayer, play_llm

PROJECT_GAMES_DIR = Path(__file__).resolve().parents[2] / "games"


def logs_of(games_dir: Path, game_id: str) -> list[Path]:
    """The game's files in games_dir: its log, and anything else named like it, such as its PGN."""
    logs = [
        path
        for path in games_dir.glob("*.jsonl")
        if json.loads(path.read_text(encoding="utf-8").splitlines()[0]).get("game_id") == game_id
    ]
    return [path for log in logs for path in games_dir.glob(f"{log.stem}.*")]


def test_the_app_started_from_another_folder_logs_its_games_in_the_projects_games_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    existed = PROJECT_GAMES_DIR.is_dir()
    client = TestClient(create_app(ScriptedPlayer([]).for_settings, sampling_file=tmp_path / "no-sampling.toml"))
    game_id = None
    try:
        game_id = client.post("/api/games", json=play_llm()).json()["game_id"]

        assert [path.suffix for path in logs_of(PROJECT_GAMES_DIR, game_id)] == [".jsonl"]
        assert not (tmp_path / "games").exists()
    finally:  # only this game's files go: the real games folder may hold the user's logs
        if game_id is not None:
            for path in logs_of(PROJECT_GAMES_DIR, game_id):
                path.unlink()
        if not existed and PROJECT_GAMES_DIR.is_dir() and not any(PROJECT_GAMES_DIR.iterdir()):
            PROJECT_GAMES_DIR.rmdir()
