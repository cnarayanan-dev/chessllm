"""The vocabularies every part of the game shares, each defined once, with their helpers next to them."""

from typing import Literal

import chess

Color = Literal["white", "black"]
COLORS: tuple[Color, Color] = ("white", "black")


def color_of(color: chess.Color) -> Color:
    """The name of a python-chess colour, e.g. of board.turn."""
    return "white" if color == chess.WHITE else "black"


def opponent(color: Color) -> Color:
    return "black" if color == "white" else "white"


# Play LLM: a human plays one side and an LLM the other. LLM faceoff: an LLM plays each side. Anchor match: an LLM
# plays an Anchor, started from the command line.
Mode = Literal["play_llm", "llm_faceoff", "anchor_match"]
# Standard rules never play an illegal move; Chaos rules play an LLM's rule-breaking or ambiguous move (ADR 0006).
Rules = Literal["standard", "chaos"]

# How a finished game ended, as PGN writes it.
GameResult = Literal["1-0", "0-1", "1/2-1/2"]


def score_for(result: str, color: Color) -> float:
    """What the result scores for the colour: 1 for a win, 0 for a loss and a half for anything else that ends a
    finished game, a draw. A result is a str, as the game logs give it."""
    winner = {"1-0": "white", "0-1": "black"}.get(result)
    if winner is None:
        return 0.5
    return 1.0 if winner == color else 0.0


# The sampling options an LLM plays with, from the config file or the model's defaults. Each keeps the type it was
# given in: an int stays an int (top_k 40, not 40.0) in the game log, the API's JSON and a Player configuration's id.
Sampling = dict[str, int | float]
