"""What the app holds for its requests besides its AppConfig: the Engines it plays and analyses games with, and the
GameStore of its one current game. create_app puts them on app.state; the routes get them from chessllm.api.deps."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from chessllm.core.types import Color, Sampling
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.exceptions import NoGameStarted, System1Unavailable
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.game.sides import System1Side
from chessllm.llm.models import LlmModel
from chessllm.llm.players import LlmPlayer
from chessllm.system1.port import DecisionModel


def no_decision_model(side: System1Side) -> DecisionModel:
    """The default decision_model_for: an app started without a System 1 server can't play a System 1 model."""
    raise System1Unavailable(f"this server isn't set up to play System 1 models ({side.model})")


@dataclass(frozen=True)
class Engines:
    """player_for builds the LLM player of each LLM side of a game, from that game's settings and the side's colour.

    models are the models the game can be played against, and sampling_defaults gives a model's own sampling.
    missing_models gives those of the models it is given that Ollama doesn't have, or raises OllamaUnavailable;
    a game whose LLM side's model is missing is refused (Settings.check_installed).
    decision_model_for builds the decision model of each System 1 side of a game, and system1_missing_models(base_url,
    models) gives those of the models that the System 1 server at base_url doesn't have, or raises System1Unavailable;
    a game whose System 1 side's model is missing is refused (Settings.check_served).
    With a move_model or an evaluator, each game is analysed into its analysis file when it ends: its Move-quality
    estimate with the move_model, and its centipawn loss and accuracy with the evaluator. clock times each game's
    moves, its sides' Time used."""

    player_for: Callable[[Settings, Color], LlmPlayer]
    models: list[LlmModel]
    sampling_defaults: Callable[[str], Sampling]
    missing_models: Callable[[list[str]], list[str]] = lambda models: []
    move_model: MoveModel | None = None
    evaluator: Evaluator | None = None
    clock: Callable[[], float] = time.monotonic
    decision_model_for: Callable[[System1Side], DecisionModel] = no_decision_model
    system1_missing_models: Callable[[str, list[str]], list[str]] = lambda base_url, models: []

    def analyses_games(self) -> bool:
        return self.move_model is not None or self.evaluator is not None


class GameStore:
    """The one current game of this server. Starting a game replaces it, and abandons the one it replaces."""

    def __init__(self) -> None:
        self._game: GameSession | None = None
        self._swap = threading.Lock()  # so each new game abandons the one it replaces, even if two start at once

    def start(self, game: GameSession) -> None:
        with self._swap:
            previous, self._game = self._game, game
        if previous is not None:
            previous.abandon()

    def current(self) -> GameSession:
        """Raises NoGameStarted before the first game."""
        game = self._game
        if game is None:
            raise NoGameStarted()
        return game
