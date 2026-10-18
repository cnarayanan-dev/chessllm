"""Prompt builder: the system prompt from an editable file and the message for each turn."""

from pathlib import Path
from typing import Literal

from chessllm.players import Message

# What the LLM is told after an illegal move: explained (the default), bare or hinted.
RetryFeedback = Literal["explained", "bare", "hinted"]

SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "system.txt"


def turn_messages(pgn: str, fen: str, system_prompt_file: Path = SYSTEM_PROMPT_FILE) -> list[Message]:
    """A fresh prompt for one turn: the system prompt plus the game so far, with no earlier turns.

    The file is read every turn, so edits apply without restarting the app."""
    return [
        Message("system", system_prompt_file.read_text(encoding="utf-8")),
        Message("user", f"PGN: {pgn}\nFEN: {fen}"),
    ]


def retry_feedback(
    level: RetryFeedback, move: str, kind: str, attempt: int, max_attempts: int, legal_moves: list[str]
) -> str:
    """The message after an illegal move. Bare says only that the move was illegal, explained also names the kind
    of failure (never the answer), and hinted adds the legal moves in SAN."""
    if level == "bare":
        return f'Your move "{move}" is illegal. Attempt {attempt} of {max_attempts}. Try again.'
    explained = (
        f'Your move "{move}" is illegal in this position (kind: {kind} move). '
        f"Attempt {attempt} of {max_attempts}. Reply with a different legal move."
    )
    if level == "hinted":
        return f"{explained}\nLegal moves: {' '.join(legal_moves)}"
    return explained
