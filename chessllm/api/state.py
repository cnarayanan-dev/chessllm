"""What the app holds for its requests besides its AppConfig: the Engines it plays and analyses games with, and the
GameStore of its one current game. create_app puts them on app.state; the routes get them from chessllm.api.deps."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from chessllm.core.types import Color, Sampling
from chessllm.engines.evaluator import Evaluator
from chessllm.engines.move_model import MoveModel
from chessllm.exceptions import NoGameStarted
from chessllm.game.session import GameSession
from chessllm.game.settings import Settings
from chessllm.llm.models import LlmModel
from chessllm.llm.players import LlmPlayer


@dataclass(frozen=True)
class Engines:
    """player_for builds the LLM player of each LLM side of a game, from that game's settings and the side's colour.

    models are the models the game can be played against, and sampling_defaults gives a model's own sampling.
    With a move_model or an evaluator, each game is analysed into its analysis file when it ends: its Move-quality
    estimate with the move_model, and its centipawn loss and accuracy with the evaluator. clock times each game's
    moves, its sides' Time used."""

    player_for: Callable[[Settings, Color], LlmPlayer]
    models: list[LlmModel]
    sampling_defaults: Callable[[str], Sampling]
    move_model: MoveModel | None = None
    evaluator: Evaluator | None = None
    clock: Callable[[], float] = time.monotonic

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
