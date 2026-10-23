"""Who plays a side of a game: a human, an LLM with the settings it plays under, or an Anchor."""

from dataclasses import asdict, dataclass
from typing import Annotated, Any, Literal

from pydantic import Field

# What the LLM is told after an illegal move: explained (the default), bare or hinted; or repeat, nothing: the turn's
# first Prompt is sent again unchanged, as the control for the other levels.
RetryFeedback = Literal["explained", "bare", "hinted", "repeat"]
# Whether the LLM is shown the legal-move list, and whether Enforced decoding holds its move to the legal moves:
# free (neither, the default), listed (the list only), blind_enforced (enforced only) or listed_enforced (both).
LlmConstraints = Literal["free", "listed", "blind_enforced", "listed_enforced"]
# How the position is given in each turn's message: fen (the PGN and FEN, the default) or described (also the last
# move, where every piece stands and whether the LLM is in check, so it needn't decode the FEN).
PositionFormat = Literal["fen", "described"]
LISTED: set[LlmConstraints] = {"listed", "listed_enforced"}
ENFORCED: set[LlmConstraints] = {"blind_enforced", "listed_enforced"}


@dataclass(frozen=True)
class HumanSide:
    player: Literal["human"] = "human"


@dataclass(frozen=True)
class LlmSide:
    """An LLM side with the settings it plays under, in the game log's shape (ADR 0004)."""

    player: Literal["llm"] = "llm"
    model: str = "llama3:8b"
    thinking: bool = False
    llm_constraints: LlmConstraints = "free"
    retry_feedback: RetryFeedback = "explained"
    # How each turn gives the position; None is the default, fen. Left out of the API's output and the game log
    # (log_shape) when it is fen, so games from before the setting read the same.
    position: Annotated[PositionFormat | None, Field(exclude_if=lambda position: position in (None, "fen"))] = None

    def log_shape(self) -> dict[str, Any]:
        """The side as game_start logs it: without position when it is the default, so that logs from before the
        setting existed and logs since describe the same Player configuration the same way."""
        shape = asdict(self)
        if self.position in (None, "fen"):
            del shape["position"]
        return shape

    def think(self) -> bool | str:
        """The thinking sent to Ollama: on or off, on meaning the model's default level."""
        return self.thinking

    def name(self) -> str:
        """The side's name in the PGN, e.g. "llama3:8b (no thinking)"."""
        return f"{self.model} ({'thinking' if self.thinking else 'no thinking'})"


@dataclass(frozen=True)
class BenchmarkLlmSide(LlmSide):
    """An LLM side with the settings only the benchmark's commands can set: never the API, whose sides are LlmSide,
    so its types and output don't change (#67). Each is left out of the game log (log_shape) when unset, so a side
    without them logs, and keeps its Player configuration id, as a plain LlmSide."""

    # One of the Thinking levels the model offers, e.g. "xhigh", sent instead of plain thinking on; needs thinking on.
    thinking_level: str | None = None
    # The Thinking budget: the most tokens of thinking and answer per attempt before the model is made to answer
    # (ADR 0007); needs thinking on. None is no budget.
    thinking_budget: int | None = None

    def log_shape(self) -> dict[str, Any]:
        shape = super().log_shape()
        for setting in ("thinking_level", "thinking_budget"):
            if shape[setting] is None:
                del shape[setting]
        return shape

    def think(self) -> bool | str:
        return self.thinking_level if self.thinking_level is not None else self.thinking

    def name(self) -> str:
        """The side's name in the PGN, e.g. "qwen3.8:latest (thinking xhigh, budget 3072)"."""
        if self.thinking_level is None and self.thinking_budget is None:
            return super().name()
        thinking = "thinking" if self.thinking_level is None else f"thinking {self.thinking_level}"
        budget = "" if self.thinking_budget is None else f", budget {self.thinking_budget}"
        return f"{self.model} ({thinking}{budget})"


AnchorEngine = Literal["dragon", "stockfish"]


@dataclass(frozen=True)
class AnchorSide:
    """An Anchor side: Komodo Dragon 1, or Stockfish standing in for it, at a Skill level, in the game log's shape."""

    player: Literal["anchor"] = "anchor"
    engine: AnchorEngine = "dragon"
    skill: int = 1

    def name(self) -> str:
        """The side's name in the PGN, e.g. "Dragon (Skill 1)"."""
        return f"{self.engine.capitalize()} (Skill {self.skill})"

    def file_name(self) -> str:
        """The side's part of the game log's file name, e.g. "dragon-skill1"."""
        return f"{self.engine}-skill{self.skill}"


Side = HumanSide | LlmSide | AnchorSide
# Who plays a side: each Side's player.
SideKind = Literal["human", "llm", "anchor"]


def side_log_shape(side: Side) -> dict[str, Any]:
    """A side as game_start logs it (ADR 0004)."""
    return side.log_shape() if isinstance(side, LlmSide) else asdict(side)
