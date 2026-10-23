"""The routes' dependencies: what create_app put on app.state, each declared by the routes that need it."""

from typing import Annotated, cast

from fastapi import Depends, Request

from chessllm.api.state import Engines, GameStore
from chessllm.core.config import AppConfig
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.session import GameSession


class AppState:
    """app.state as create_app fills it."""

    config: AppConfig
    engines: Engines
    games: GameStore


def app_state(request: Request) -> AppState:
    return cast(AppState, request.app.state)


def config(request: Request) -> AppConfig:
    return app_state(request).config


def engines(request: Request) -> Engines:
    return app_state(request).engines


def game_store(request: Request) -> GameStore:
    return app_state(request).games


def prompt_library(request: Request) -> PromptLibrary:
    """The Prompt library in the folder create_app was given."""
    return PromptLibrary(config(request).prompt_library_dir)


def current_game(request: Request) -> GameSession:
    """Raises NoGameStarted before the first game."""
    return game_store(request).current()


ConfigDep = Annotated[AppConfig, Depends(config)]
EnginesDep = Annotated[Engines, Depends(engines)]
GameStoreDep = Annotated[GameStore, Depends(game_store)]
PromptLibraryDep = Annotated[PromptLibrary, Depends(prompt_library)]
CurrentGame = Annotated[GameSession, Depends(current_game)]
