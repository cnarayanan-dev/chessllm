"""Who plays a side of a game: a human, an LLM with the settings it plays under, or an Anchor."""

from dataclasses import asdict, dataclass
from typing import Annotated, Any, Literal, get_args

from pydantic import Field
from pydantic.json_schema import SkipJsonSchema

# What the LLM is told after an illegal move: explained (the default), bare or hinted; or repeat, nothing: the turn's
# first Prompt is sent again unchanged, as the control for the other levels.
RetryFeedback = Literal["explained", "bare", "hinted", "repeat"]
# Whether the LLM is shown the legal-move list, and whether Enforced decoding holds its move to the legal moves:
# free (neither, the default), listed (the list only), blind_enforced (enforced only) or listed_enforced (both).
LlmConstraints = Literal["free", "listed", "blind_enforced", "listed_enforced"]
# Whether an LLM side's Turns share one conversation, fixed for the game: fresh (every turn starts a new conversation,
# the default), chat_position (one conversation, each turn adding its message as a fresh turn has it) or chat_moves
# (one conversation, each turn adding only the opponent's last move, by the Moves default Prompt template).
TurnMemory = Literal["fresh", "chat_position", "chat_moves"]
# The Tools an LLM may ask the benchmark during its Turn, each answering about the current position (ADR 0011).
Tool = Literal["board", "move_history", "legal_moves", "material"]
TOOLS: tuple[Tool, ...] = get_args(Tool)
# The most Tool calls in one Attempt by default (the Tool-call cap).
DEFAULT_TOOL_CALL_CAP = 10
LISTED: set[LlmConstraints] = {"listed", "listed_enforced"}
ENFORCED: set[LlmConstraints] = {"blind_enforced", "listed_enforced"}


@dataclass(frozen=True)
class PromptTemplate:
    """A System prompt and a Turn template written for each other, which an LLM side plays a whole game with
    (ADR 0010). Both are templates with $placeholders, filled in by llm_turn.prompt; the Answer format is the
    benchmark's, never the template's. The default ones are in llm_turn.prompt."""

    id: str
    name: str | None  # optional, to recognise it by
    system_prompt: str
    turn_template: str

    def log_shape(self) -> dict[str, Any]:
        """The template as game_start logs it, in full: without the name when it has none."""
        shape = asdict(self)
        if self.name is None:
            del shape["name"]
        return shape


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
    # The Prompt template a new game asked for, by its ID in the Prompt library; None for the Default of its LLM
    # constraints, and left out of the API's output then, so a game on the Default reads as before the Prompt
    # library. The API resolves it into prompt_template; game_start logs the template in full instead.
    prompt_template_id: Annotated[str | None, Field(exclude_if=lambda template_id: template_id is None)] = None
    # The Prompt template it plays with; None for the Default of its LLM constraints, read when the game starts
    # (llm_turn.prompt.side_template). The API takes it only by its ID, so it is left out of the API's schema and
    # output; the benchmark's commands give it in full.
    prompt_template: Annotated[SkipJsonSchema[PromptTemplate | None], Field(exclude=True)] = None
    # Whether its turns share one conversation (game/llm_turn/conversation.py). Only the benchmark's commands set it
    # so far: the API refuses any but fresh and leaves it out of its schema and output until the page shows a
    # conversation's whole Prompt (#108). Left out of the game log when fresh, so games from before it log the same.
    turn_memory: Annotated[SkipJsonSchema[TurnMemory], Field(exclude=True)] = "fresh"

    def log_shape(self, template: PromptTemplate) -> dict[str, Any]:
        """The side as game_start logs it, with the Prompt template it plays the game with in full, last, and its
        Turn memory unless fresh."""
        shape = asdict(self)
        del shape["prompt_template_id"], shape["prompt_template"]
        if self.turn_memory == "fresh":
            del shape["turn_memory"]
        return shape | {"prompt_template": template.log_shape()}

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
    # The Tools it may call during an attempt, none by default, and the Tool-call cap on them (ADR 0011); both fixed
    # for the game. Settings.check refuses them where v1 doesn't allow tools (settings.tools_refusal).
    tools: frozenset[Tool] = frozenset()
    tool_call_cap: int = DEFAULT_TOOL_CALL_CAP

    def log_shape(self, template: PromptTemplate) -> dict[str, Any]:
        """As a plain LlmSide's, with the Thinking level and budget when set, and the tools, sorted, and their cap
        when it has tools, so a side without tools logs as before them."""
        shape = super().log_shape(template)
        for setting in ("thinking_level", "thinking_budget"):
            if shape[setting] is None:
                del shape[setting]
        if self.tools:
            shape["tools"] = sorted(self.tools)
        else:
            del shape["tools"], shape["tool_call_cap"]
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


def side_log_shape(side: Side, template: PromptTemplate | None) -> dict[str, Any]:
    """A side as game_start logs it (ADR 0004): an LLM side with the Prompt template it plays the game with."""
    if isinstance(side, LlmSide):
        assert template is not None, "an LLM side plays with a Prompt template"
        return side.log_shape(template)
    return asdict(side)
