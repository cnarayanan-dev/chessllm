"""The app as the Playwright journeys (frontend/e2e/) see it: the built page and the real API, with scripted LLM players
instead of Ollama, and the game logs in a temporary directory.

    uv run python -m tests.e2e.server --port 8123

POST /e2e/script {"white": [...], "black": [...]} sets the SAN replies of each side's LLM for the games started after
it; each game's LLM plays its own copy of the script, from the start (a ScriptedPlayer, as in tests/conftest.py). With
thinking off each reply carries a Reasoning, "Reasoning for <san>.", as Ollama's answers do. Every ply is judged by
material alone (tests/fakes.py's MaterialEvaluator), a stand-in for Stockfish, so a faceoff shows its Evaluation bar.

POST /e2e/script also takes "system1": {"<model>": [...]}, the SAN moves each System 1 model of that name plays, in turn
(a FakeDecisionModel giving the move all the probability; once the script runs out it gives equal probabilities). Every
System 1 server has every model, except those "system1_missing" names (a game with one is refused, as when the server
lacks the model).

The app has a token for the Hosted model (a placeholder: nothing calls the provider), so Claude Haiku 5.5 is offered; it
plays from the script like any LLM. POST /e2e/script also takes "provider_failure": the reason, when set, the provider
fails with at the Hosted model's first turn of each game, which aborts the game.

POST /e2e/ranking-games replaces every game log with the synthetic games of tests/e2e/ranking.py, for the
analytics page.

POST /e2e/restart stands in for restarting the server: the app is built afresh, with no current game, as on a first
visit. The script and the game logs are kept."""

import argparse
import json
import os
import tempfile
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.types import Receive, Scope, Send

from chessllm.api.app import create_app
from chessllm.core.config import CLAUDE_TOKEN_VARIABLE
from chessllm.core.types import Color
from chessllm.exceptions import HostedModelFailed
from chessllm.game.settings import Settings
from chessllm.game.sides import System1Side
from chessllm.llm.models import is_hosted
from tests.conftest import Raw, ScriptedPlayer
from tests.fakes import FakeDecisionModel, MaterialEvaluator
from tests.e2e.ranking import write_ranking_games


class Script(BaseModel):
    white: list[str] = []
    black: list[str] = []
    system1: dict[str, list[str]] = {}  # by model name
    system1_missing: list[str] = []  # the models no System 1 server has
    provider_failure: str | None = None  # why the Hosted model's provider fails, at its first turn of each game


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    port = parser.parse_args().port
    os.environ.setdefault(CLAUDE_TOKEN_VARIABLE, "e2e-placeholder-not-a-token")  # offers the Hosted model; never used

    script = Script()

    def player_for(settings: Settings, color: Color) -> ScriptedPlayer:
        replies: list[str | BaseException] = list(getattr(script, color))
        if script.provider_failure is not None and is_hosted(settings.llm_sides()[color].model):
            return ScriptedPlayer([HostedModelFailed(script.provider_failure)]).for_settings(settings, color)
        if not settings.llm_sides()[color].thinking:
            replies = [Raw(json.dumps({"reasoning": f"Reasoning for {san}.", "move": san})) for san in replies]
        return ScriptedPlayer(replies).for_settings(settings, color)

    def decision_model_for(side: System1Side) -> FakeDecisionModel:
        return FakeDecisionModel.favouring(*script.system1.get(side.model, []))

    def system1_missing_models(base_url: str, models: list[str]) -> list[str]:
        return [model for model in models if model in script.system1_missing]

    temp = Path(tempfile.mkdtemp(prefix="chessllm-e2e-"))
    games_dir = temp / "games"

    def build() -> FastAPI:
        app = create_app(
            player_for,
            games_dir=games_dir,
            sampling_file=temp / "no-sampling.toml",
            move_quality_validation=temp / "no-validation.json",  # no validation has run: estimates are unvalidated
            evaluator=MaterialEvaluator(),
            prompt_library_dir=temp / "prompt_library",  # the default Prompt templates only
            decision_model_for=decision_model_for,
            system1_missing_models=system1_missing_models,
        )

        @app.post("/e2e/script", include_in_schema=False)
        def set_script(new: Script) -> None:
            nonlocal script
            script = new

        @app.post("/e2e/ranking-games", include_in_schema=False)
        def set_ranking_games() -> None:
            write_ranking_games(games_dir)

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
