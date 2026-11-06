"""What a Mode decides, fixed for the whole game: who plays each side, and how its games are run and counted."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from chessllm.core.types import Color, ModeKey
from chessllm.exceptions import InvalidSettings
from chessllm.game.sides import Side, SideKind

# What a Mode counts its sides by: who plays them, or "model", a Model player of either kind (an LLM or a System 1
# model).
SideSlot = SideKind | Literal["model"]
SIDE_KINDS: dict[SideSlot, str] = {
    "human": "human side", "llm": "LLM side", "model": "Model player side", "anchor": "Anchor side"
}
MODEL_KINDS: tuple[SideKind, ...] = ("llm", "system1")


@dataclass(frozen=True)
class Mode:
    key: ModeKey  # as the API and the game log give the Mode
    name: str  # e.g. in the PGN
    sides: Mapping[SideSlot, int]  # how many sides of each kind it has
    # With no human to stop them, its games end as a draw at the Move cap (ADR 0005).
    unattended: bool
    rated: bool  # whether its games count towards the Rating

    @property
    def accepts_human_moves(self) -> bool:
        return self.sides["human"] > 0

    @property
    def against_an_anchor(self) -> bool:
        """Whether an LLM plays an Anchor in its games, so their results place the LLM on the Anchors' scale."""
        return self.sides["anchor"] > 0

    def check_sides(self, white: Side, black: Side) -> None:
        """Raises InvalidSettings, saying why, unless the two sides are the kinds the Mode has."""
        for slot, needed in self.sides.items():
            kinds = MODEL_KINDS if slot == "model" else (slot,)
            count = sum(side.player in kinds for side in (white, black))
            if count != needed:
                number = {0: "no", 1: "one", 2: "two"}[needed]
                sides = f"{SIDE_KINDS[slot]}{'s' * (needed == 2)}"
                raise InvalidSettings(f"{self.name} needs {number} {sides}, not {count}")

    def logged_prompt_files(self, prompt_files: dict[Color, str]) -> dict[str, Any]:
        """The system prompt files as game_start logs them: with one Model player side, its file; with two, the file
        of each side, even when shared. Only an LLM side playing a default Prompt template has one, so a System 1
        side adds none; with none, nothing is logged."""
        if not prompt_files:
            return {}
        if self.sides.get("model", 0) == 2:
            return {"prompt_files": prompt_files}
        return {"prompt_file": next(iter(prompt_files.values()))}
