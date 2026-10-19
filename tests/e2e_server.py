"""The app as the Playwright journeys (frontend/e2e/) see it: the built page and the real API, with scripted LLM players
instead of Ollama, and the game logs in a temporary directory.

    uv run python -m tests.e2e_server --port 8123

POST /e2e/script {"white": [...], "black": [...]} sets the SAN replies of each side's LLM for the games started after
it; each game's LLM plays its own copy of the script, from the start (a ScriptedPlayer, as in tests/conftest.py)."""

import argparse
import tempfile
from pathlib import Path

import uvicorn
from pydantic import BaseModel

from chessllm.app import create_app
from chessllm.game import Color, Settings
from tests.conftest import ScriptedPlayer


class Script(BaseModel):
    white: list[str] = []
    black: list[str] = []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    port = parser.parse_args().port

    script = Script()

    def player_for(settings: Settings, color: Color) -> ScriptedPlayer:
        return ScriptedPlayer(list(getattr(script, color))).for_settings(settings, color)

    temp = Path(tempfile.mkdtemp(prefix="chessllm-e2e-"))
    app = create_app(player_for, games_dir=temp / "games", sampling_file=temp / "no-sampling.toml")

    @app.post("/e2e/script", include_in_schema=False)
    def set_script(new: Script) -> None:
        nonlocal script
        script = new

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
