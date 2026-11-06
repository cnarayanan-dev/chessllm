"""A System 1 model's Turn (ADR 0012): the legal moves are its options, in SAN and in a random order; it is asked for a
probability of each, and its move is drawn from them at its Choice temperature. A single attempt: it can't propose an
illegal move, and a failed call is a Forfeit. The game plays the move the turn ends with (GameSession)."""

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import chess

from chessllm.core.types import Color
from chessllm.exceptions import DecisionModelFailed
from chessllm.game.llm_turn.prompt import TurnPosition, fill_system_prompt, turn_message
from chessllm.game.sides import PromptTemplate, System1Side
from chessllm.system1.port import DecisionModel


@dataclass(frozen=True)
class Option:
    """One of the options a turn offered: a legal move in SAN, and the probability the model gave it; None if the
    model gave none, as it wasn't asked or failed."""

    san: str
    probability: float | None = None


@dataclass(frozen=True)
class System1Turn:
    """One System 1 turn as the game log has it (the counterpart of an LLM's attempt, without retries): the state and
    question as sent, the options in the order shown with their probabilities, and the move drawn."""

    ply: int
    color: Color
    # False for a position with only one legal move, which is played without asking the model: Ollama's choice
    # questions take 2 to 26 options. Then nothing was sent.
    asked: bool
    state: str | None
    question: str | None
    options: list[Option]
    move: str | None  # the move drawn in UCI, None for a Forfeit
    san: str | None
    time_s: float  # the Turn's Time used, a Forfeit's too
    error: str | None = None  # why the call failed, for a Forfeit

    def log_shape(self) -> dict[str, Any]:
        """The turn as system1_turn logs it: without what it doesn't have, such as the state of a turn that wasn't asked
        or the move of a Forfeit."""
        shape: dict[str, Any] = {"color": self.color, "ply": self.ply, "asked": self.asked}
        if self.asked:
            shape |= {"state": self.state, "question": self.question}
        shape["options"] = [
            {"san": option.san} | ({} if option.probability is None else {"probability": option.probability})
            for option in self.options
        ]
        if self.move is not None:
            shape |= {"move": self.move, "san": self.san}
        if self.error is not None:
            shape["error"] = self.error
        return shape | {"time_s": self.time_s}


@dataclass(frozen=True)
class System1Outcome:
    """How a turn ended, for the game to play: with a move, or a Forfeit."""

    turn: System1Turn
    move: chess.Move | None = None

    @property
    def forfeit(self) -> bool:
        return self.move is None


def draw(probabilities: list[float], choice_temperature: float, rng: random.Random) -> int:
    """The index of the option drawn: probabilities raised to 1/T and renormalised, so at T = 1 each option is drawn as
    often as its probability and below it the favourites more often. At T = 0 the top option, the first of any
    tied (the options are in their shuffled order). Worked in logs so that a small T can't underflow."""
    if choice_temperature == 0:
        return probabilities.index(max(probabilities))
    top = math.log(max(probabilities))
    weights = [math.exp((math.log(p) - top) / choice_temperature) if p > 0 else 0.0 for p in probabilities]
    return rng.choices(range(len(weights)), weights)[0]


class System1Turns:
    """The turns of one System 1 side. rng is the game's random source, shared by both sides if both are System 1
    models, so a seed replays the whole game."""

    def __init__(
        self,
        color: Color,
        side: System1Side,
        template: PromptTemplate,
        model: DecisionModel,
        rng: random.Random,
        clock: Callable[[], float],
    ) -> None:
        self._color = color
        self._temperature = side.choice_temperature
        self._template = template
        self._model = model
        self._rng = rng
        self._clock = clock

    def play(self, board: chess.Board, moves: list[str], started: float) -> System1Outcome:
        """Play a turn in the position on the board, which it leaves unchanged. moves are every ply so far as written
        in the Move record, and started is when the turn started on the clock."""
        ply = len(moves) + 1
        legal = {board.san(move): move for move in board.legal_moves}
        sans = list(legal)
        self._rng.shuffle(sans)
        if len(sans) == 1:
            [san] = sans
            turn = System1Turn(
                ply, self._color, False, None, None, [Option(san)], legal[san].uci(), san, self._time(started)
            )
            return System1Outcome(turn, legal[san])
        state = turn_message(self._template, TurnPosition(board, moves))
        question = fill_system_prompt(self._template.system_prompt, self._color)
        try:
            probabilities = self._model.decide(state, question, sans)
        except DecisionModelFailed as error:
            turn = System1Turn(
                ply, self._color, True, state, question, [Option(san) for san in sans], None, None,
                self._time(started), str(error),
            )
            return System1Outcome(turn)
        san = sans[draw(probabilities, self._temperature, self._rng)]
        options = [Option(option, probability) for option, probability in zip(sans, probabilities, strict=True)]
        turn = System1Turn(
            ply, self._color, True, state, question, options, legal[san].uci(), san, self._time(started)
        )
        return System1Outcome(turn, legal[san])

    def _time(self, started: float) -> float:
        return round(self._clock() - started, 3)
