"""The game's state records: GameSession builds them as the game is played, the API returns them as they are, and
the game log is written from them through their log shapes (ADR 0008).

Changing a record changes the API, and so the frontend's generated types (frontend/src/api/schema.ts)."""

from collections.abc import Sequence
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, Field, SerializerFunctionWrapHandler, model_serializer

from chessllm.core.types import Color, GameResult, ModeKey, RulesKey, Sampling
from chessllm.game.sides import AnchorSide, HumanSide, LlmSide
from chessllm.llm.players import MessageRole

# How the resolver read a move under Chaos rules: legal as it stands, a chaos move, a spawn, or not a move it can play
# (ADR 0006).
ResolutionKind = Literal["legal", "chaos", "spawn", "invalid"]
# The illegal moves: the kinds of answer that aren't a legal move (ADR 0002).
IllegalResult = Literal["invalid", "illegal", "ambiguous"]
ILLEGAL_RESULTS: tuple[IllegalResult, ...] = get_args(IllegalResult)
# What an attempt comes to: a legal move, an illegal one, or no answer, as the call timed out or failed. cut_off is a
# forced answer that was itself cut off at its token cap, so there is no move to judge (ADR 0007). Not an illegal
# move: it takes an attempt and gets a Retry, with a fresh Thinking budget, but no illegal-move metric counts it. Only
# a side with a Thinking budget can have one, so never a game from the app.
AttemptResult = Literal["legal", IllegalResult, "timeout", "error", "cut_off"]

# Why a game ended: the python-chess terminations a standard board reaches without a claim, by name, then the
# draws claimed as soon as they arise, and the ends of the game's own.
EndReason = Literal[
    "checkmate",
    "stalemate",
    "insufficient_material",
    "seventyfive_moves",
    "fivefold_repetition",
    "threefold_repetition",
    "fifty_moves",
    "king_capture",
    "king_left_in_check",
    "forfeit",
    "move_cap",
]

SideOut = Annotated[HumanSide | LlmSide | AnchorSide, Field(discriminator="player")]


def is_none(value: object) -> bool:
    return value is None


class Resolution(BaseModel):
    """How the resolver read an LLM's move under Chaos rules (ADR 0006), so a replay never resolves it again: the
    ResolvedMove the game works with, with square names and the piece's symbol."""

    kind: ResolutionKind
    from_square: str | None = Field(alias="from")  # None for a spawn
    to: str | None
    piece: str | None  # the symbol of the piece that ends up on to, e.g. "q" for a black queen
    rook: list[str] | None  # a castling rook's from and to
    reason: str


class PromptMessage(BaseModel):
    """One message of the Prompt, as sent to the LLM."""

    role: MessageRole
    content: str


class AttemptSummary(BaseModel):
    """One try of an LLM turn, without its text: how it was judged. Most fields are None when the LLM gave no
    answer."""

    move: str | None  # the move as written, or the raw reply if it isn't the move schema
    san: str | None  # the move's standard SAN, when it is legal
    notation_slip: bool
    result: AttemptResult | None
    error: str | None  # why the call failed or timed out
    latency_s: float | None
    # Only under Chaos rules, and only when there was a move to resolve; a chaos move or spawn was played.
    resolution: Resolution | None = Field(default=None, exclude_if=is_none)


# The order of an attempt's fields in the API's JSON and the game log, as it was before the summary had a class of
# its own: the summary's fields come first in the class, not where they always were.
ATTEMPT_FIELD_ORDER = (
    "move", "san", "notation_slip", "result", "feedback_sent", "raw_reply", "thinking", "reasoning", "error",
    "latency_s", "prompt", "resolution",
)


class Attempt(AttemptSummary):
    """One try of an LLM turn, as the game log has it, with what was sent and what came back."""

    feedback_sent: str | None  # the retry feedback this try answers, None on the first
    raw_reply: str | None
    thinking: str | None  # the Thinking, with thinking on
    reasoning: str | None  # the Reasoning in the answer, with thinking off
    prompt: list[PromptMessage] | None = None  # the messages sent for this try; None in games from before it was kept

    # Unannotated, as pydantic would take an annotated return type for the record's schema in the API description.
    @model_serializer(mode="wrap")
    def _in_field_order(self, handler: SerializerFunctionWrapHandler):  # type: ignore[no-untyped-def]
        fields = handler(self)
        ordered = {key: fields[key] for key in ATTEMPT_FIELD_ORDER if key in fields}
        return ordered | fields

    def log_shape(self) -> dict[str, Any]:
        """The attempt as llm_attempt logs it (ADR 0004), unchanged since before the API gave the Reasoning a field
        of its own: with thinking off, the Reasoning is the attempt's thinking. The game's Rules may add to it
        (Rules.attempt_log_shape)."""
        shape: dict[str, Any] = self.model_dump(mode="json", by_alias=True)
        reasoning = shape.pop("reasoning")
        if reasoning is not None:
            shape["thinking"] = reasoning
        return shape


class Evaluation(BaseModel):
    """Stockfish's judgement of the position after a ply or a Legal counterpart, from White's point of view
    (CONTEXT.md): in pawns, capped at ±10, or a mate in so many moves, positive when White mates, with pawns then at
    the cap. A position that isn't valid chess is never judged: unjudged says why, and pawns and mate are None."""

    pawns: float | None
    mate: int | None
    unjudged: str | None

    def log_shape(self) -> dict[str, Any]:
        """The Evaluation as the evaluation event logs it, the same as the API has it."""
        return self.model_dump(mode="json")


class LegalCounterpartSummary(BaseModel):
    """The Legal counterpart of a chaos move: the legal move the same LLM gave for the same position when asked once
    more, under Listed enforced, in one attempt. Never played. Its move and the position it would have left are
    None when it failed: the call timed out or failed, or its answer was no legal move."""

    move: str | None  # in UCI, with any promotion
    san: str | None
    fen_after: str | None  # the position it would have left, so the page can show it without chess logic (ADR 0001)
    attempt: AttemptSummary
    # Only with an evaluator, for a move that doesn't end the game: the Evaluation of the position it would have left,
    # judged like any ply's.
    evaluation: Evaluation | None = Field(default=None, exclude_if=is_none)


class LegalCounterpart(LegalCounterpartSummary):
    attempt: Attempt


class ChaosGain(BaseModel):
    """How much a chaos move gained its mover (CONTEXT.md), in pawns from the mover's point of view: the Evaluation
    after it minus the Evaluation of each Gain baseline, each capped at ±10, a King capture counting as +10 after the
    move and a King left in check as -10 (any other end of the game by its result), so a gain is capped at ±20. A
    gain is None when a position it needs has no Evaluation, and the gain over the Legal counterpart also when none
    was asked for or it failed."""

    # Stockfish's judgement of the position before the chaos move, which its best move keeps: recorded, never shown.
    best_evaluation: Evaluation
    vs_counterpart: float | None
    vs_best: float | None  # recorded, never shown

    def log_shape(self) -> dict[str, Any]:
        """The gains as the chaos_gain event logs them, the same as the API has them."""
        return self.model_dump(mode="json")


class LlmTurnSummary(BaseModel):
    """One LLM turn, its attempts without their text."""

    ply: int
    color: Color
    attempts: Sequence[AttemptSummary]
    # The Turn's Time used: from when it started on the server to its last attempt, so a forfeited Turn has one too.
    time_s: float
    # Only for a turn that ended in a chaos move, under Chaos rules with Legal counterparts asked for.
    legal_counterpart: LegalCounterpartSummary | None = Field(default=None, exclude_if=is_none)
    # Only for a turn that ended in a chaos move, with an evaluator, once the positions it needs are judged.
    chaos_gain: ChaosGain | None = Field(default=None, exclude_if=is_none)

    def log_shape(self) -> dict[str, Any]:
        """What the turn's last llm_attempt logs of the turn itself: its time."""
        return {"turn_time_s": self.time_s}


class LlmTurn(LlmTurnSummary):
    attempts: list[Attempt]
    thinking: str | None  # the thinking of the last try that answered
    reasoning: str | None  # the Reasoning of the last try: the one played, or the last before a Forfeit
    legal_counterpart: LegalCounterpart | None = Field(default=None, exclude_if=is_none)


class EvaluationEngine(BaseModel):
    """The engine a game's Evaluations come from, and the search it judges every position with, so numbers from
    different settings are never mixed up."""

    version: str  # e.g. "Stockfish 19"
    search: dict[str, int]  # e.g. {"depth": 16, "threads": 1, "hash_mb": 64}

    def log_shape(self) -> dict[str, Any]:
        """The engine as game_start logs it, the same as the API has it."""
        return self.model_dump(mode="json")


class Ply(BaseModel):
    """One ply of the game as played, for the page's move history: it shows any ply's position and animates into
    it without chess logic of its own (ADR 0001). The LLM turn that played it, if any, has the same ply number."""

    ply: int  # 1 for White's first move
    color: Color  # the side that moved
    move: str  # in UCI, with any promotion (e7e8q); a Spawn as a drop (Q@d5)
    written: str  # as in the Move record: standard SAN, or a chaos move in the LLM's own spelling
    fen_before: str
    fen_after: str
    check: bool  # whether the side to move after the ply is in check
    time_s: float  # the Time used on the move that made the ply
    # Only for a chaos move or spawn: its resolution, as its attempt has it, so a replay never resolves it again.
    resolution: Resolution | None = Field(default=None, exclude_if=is_none)
    # Only with an evaluator, and never for a position that ends the game.
    evaluation: Evaluation | None = Field(default=None, exclude_if=is_none)

    def log_shape(self) -> dict[str, Any]:
        """A human's or an Anchor's ply as human_move or anchor_move logs it, its move in SAN (ADR 0004)."""
        return {
            "color": self.color,
            "ply": self.ply,
            "move": self.written,
            "fen_after": self.fen_after,
            "time_s": self.time_s,
        }


class IllegalMoves(BaseModel):
    invalid: int
    illegal: int
    ambiguous: int


class LlmSideStats(BaseModel):
    """The totals of one LLM side. Under Enforced decoding the illegal-move metrics are None (ADR 0003)."""

    legal_move_streak: int | None
    illegal_moves: IllegalMoves | None
    recovered_turns: int | None
    notation_slips: int
    # Only under Chaos rules: the chaos moves played, spawns included, and the spawns among them.
    chaos_moves: int | None = Field(default=None, exclude_if=is_none)
    spawns: int | None = Field(default=None, exclude_if=is_none)


class Stats(BaseModel):
    """The totals of each side; a human's side has none (ADR 0004)."""

    white: LlmSideStats | None
    black: LlmSideStats | None

    def log_shape(self) -> dict[str, Any]:
        """The totals as game_end logs them, the same as the API has them."""
        return self.model_dump(mode="json")


class TimeUsed(BaseModel):
    """Each side's Time used: its finished moves, a forfeited Turn's included, to the millisecond."""

    white: float
    black: float

    def log_shape(self) -> dict[str, Any]:
        """Each side's Time used as game_end logs it, the same as the API has it."""
        return self.model_dump(mode="json")


class GameSettings(BaseModel):
    mode: ModeKey
    white: SideOut
    black: SideOut
    sampling: Sampling  # from the config file; empty means the models' defaults
    # Left out under Standard rules, so a Standard rules game reads as it did before Chaos rules existed.
    rules: RulesKey | None = Field(default=None, exclude_if=lambda rules: rules in (None, "standard"))
    max_attempts: int
    # Whether a chaos move's Legal counterpart is asked for: only under Chaos rules, left out under Standard rules.
    legal_counterpart: bool | None = Field(default=None, exclude_if=is_none)


class GameState(BaseModel):
    """What GameSession.state() returns: the game as the page shows it."""

    game_id: str
    fen: str
    pgn: str
    turn: Color
    human_legal_moves: list[str]
    last_move: str | None  # in UCI
    plies: list[Ply]  # every ply played, in order
    check: bool
    llm_turn: LlmTurn | None  # the last LLM turn
    llm_turns: list[LlmTurn]
    settings: GameSettings
    status: Literal["playing", "over"]
    result: GameResult | None
    end_reason: EndReason | None
    stats: Stats
    time_used: TimeUsed
    # How long the side to move had been on its move when the state was built. None once the game is over, and
    # while an LLM's Turn or an Anchor's move hasn't been asked for: their time only runs once it has.
    running_s: float | None
    # Only with an evaluator: the engine every ply's Evaluation comes from.
    evaluator: EvaluationEngine | None = Field(default=None, exclude_if=is_none)
