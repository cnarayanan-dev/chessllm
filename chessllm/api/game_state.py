"""The API's response models of the game's state: what GameSession.state() returns, as the page gets it. Every state
the API returns is validated against them, so a field missing here is dropped from the response.

They move to the game, as its state records, with ADR 0008."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from chessllm.core.types import Color, GameResult, Sampling
from chessllm.game.chaos import ResolutionKind
from chessllm.game.session import AnchorSide, AppAttemptResult, HumanSide, LlmSide, Mode, Rules
from chessllm.llm.players import MessageRole

SideOut = Annotated[HumanSide | LlmSide | AnchorSide, Field(discriminator="player")]


def is_none(value: object) -> bool:
    return value is None


class Resolution(BaseModel):
    """How the resolver read an LLM's move under Chaos rules (ADR 0006), so a replay never resolves it again."""

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


class Attempt(BaseModel):
    """One try of an LLM turn, as the game log has it. Most fields are None until the LLM has answered."""

    move: str | None  # the move as written, or the raw reply if it isn't the move schema
    san: str | None  # the move's standard SAN, when it is legal
    notation_slip: bool
    result: AppAttemptResult | None
    feedback_sent: str | None  # the retry feedback this try answers, None on the first
    raw_reply: str | None
    thinking: str | None  # the Thinking, with thinking on
    reasoning: str | None  # the Reasoning in the answer, with thinking off
    error: str | None  # why the call failed or timed out
    latency_s: float | None
    prompt: list[PromptMessage] | None = None  # the messages sent for this try; None in games from before it was kept
    # Only under Chaos rules, and only when there was a move to resolve; a chaos move or spawn was played.
    resolution: Resolution | None = Field(None, exclude_if=is_none)


class LlmTurn(BaseModel):
    ply: int
    color: Color
    attempts: list[Attempt]
    thinking: str | None  # the thinking of the last try that answered
    reasoning: str | None  # the Reasoning of the last try: the one played, or the last before a Forfeit


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
    # Only for a chaos move or spawn: its resolution, as its attempt has it, so a replay never resolves it again.
    resolution: Resolution | None = Field(None, exclude_if=is_none)


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
    chaos_moves: int | None = Field(None, exclude_if=is_none)
    spawns: int | None = Field(None, exclude_if=is_none)


class Stats(BaseModel):
    """The totals of each side; a human's side has none (ADR 0004)."""

    white: LlmSideStats | None
    black: LlmSideStats | None


class GameSettings(BaseModel):
    mode: Mode
    white: SideOut
    black: SideOut
    sampling: Sampling  # from the config file; empty means the models' defaults
    # Left out under Standard rules, so a Standard rules game reads as it did before Chaos rules existed.
    rules: Rules | None = Field(None, exclude_if=lambda rules: rules in (None, "standard"))
    max_attempts: int


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
    end_reason: str | None  # one of session.EndReason
    stats: Stats
