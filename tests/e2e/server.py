"""The app as the Playwright journeys (frontend/e2e/) see it: the built page and the real API, with scripted LLM players
instead of Ollama, and the game logs in a temporary directory.

    uv run python -m tests.e2e.server --port 8123

POST /e2e/script {"white": [...], "black": [...]} sets the SAN replies of each side's LLM for the games started after
it; each game's LLM plays its own copy of the script, from the start (a ScriptedPlayer, as in tests/conftest.py). With
thinking off each reply carries a Reasoning, "Reasoning for <san>.", as Ollama's answers do.

POST /e2e/leaderboard-games replaces every game log with the synthetic games of tests/e2e/leaderboard.py, for the
analytics page.

POST /e2e/restart stands in for restarting the server: the app is built afresh, with no current game, as on a first
visit. The script and the game logs are kept."""

import argparse
import json
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.types import Receive, Scope, Send

from chessllm.api.app import create_app
from chessllm.core.types import Color
from chessllm.game.session import Settings
from tests.conftest import Raw, ScriptedPlayer
from tests.e2e.leaderboard import write_leaderboard_games


class Script(BaseModel):
    white: list[str] = []
    black: list[str] = []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    port = parser.parse_args().port

    script = Script()

    def player_for(settings: Settings, color: Color) -> ScriptedPlayer:
        replies: list[str | BaseException] = list(getattr(script, color))
        if not settings.llm_sides()[color].thinking:
            replies = [Raw(json.dumps({"reasoning": f"Reasoning for {san}.", "move": san})) for san in replies]
        return ScriptedPlayer(replies).for_settings(settings, color)

    temp = Path(tempfile.mkdtemp(prefix="chessllm-e2e-"))
    games_dir = temp / "games"

    def build() -> FastAPI:
        app = create_app(
            player_for,
            games_dir=games_dir,
            sampling_file=temp / "no-sampling.toml",
            move_quality_validation=temp / "no-validation.json",  # no validation has run: estimates are unvalidated
        )

        @app.post("/e2e/script", include_in_schema=False)
        def set_script(new: Script) -> None:
            nonlocal script
            script = new

        @app.post("/e2e/leaderboard-games", include_in_schema=False)
        def set_leaderboard_games() -> None:
            write_leaderboard_games(games_dir)

        @app.post("/e2e/restart", include_in_schema=False)
        def restart() -> None:
            nonlocal current
            current = build()

        return app

    current = build()

    async def serve(scope: Scope, receive: Receive, send: Send) -> None:
        await current(scope, receive, send)

    uvicorn.run(serve, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
