"""The request bodies of a game: the new game's settings, and a human's move."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from chessllm.game.session import HumanSide, LlmSide, MAX_ATTEMPTS_RANGE, Rules, Settings


class HumanMove(BaseModel):
    uci: str


# The app starts Play LLM games and LLM faceoffs; an Anchor match is started from the command line
# (anchor-match), so no Anchor side is taken here.
AppMode = Literal["play_llm", "llm_faceoff"]
SideIn = Annotated[HumanSide | LlmSide, Field(discriminator="player")]


class NewGame(BaseModel):
    """The settings chosen in the New game sheet: the Mode and who plays each side, with the settings of each LLM
    side, and the rules for every LLM in the game. Sampling isn't one of them: it comes from the config file."""

    model_config = ConfigDict(extra="forbid")

    mode: AppMode = "play_llm"
    white: SideIn = HumanSide()
    black: SideIn = LlmSide()
    rules: Rules = Settings.rules  # refused unless every LLM side is under Free or Listed
    # Illegal moves per turn before an LLM forfeits, the same for every LLM in the game.
    max_attempts: int = Field(default=Settings.max_attempts, ge=MAX_ATTEMPTS_RANGE[0], le=MAX_ATTEMPTS_RANGE[-1])
