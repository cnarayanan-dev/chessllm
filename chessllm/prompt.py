"""Prompt builder: the system prompt from an editable file and the message for each turn."""

from pathlib import Path

from chessllm.players import Message

SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "system.txt"


def turn_messages(pgn: str, fen: str, system_prompt_file: Path = SYSTEM_PROMPT_FILE) -> list[Message]:
    """A fresh prompt for one turn: the system prompt plus the game so far, with no earlier turns.

    The file is read every turn, so edits apply without restarting the app."""
    return [
        Message("system", system_prompt_file.read_text(encoding="utf-8")),
        Message("user", f"PGN: {pgn}\nFEN: {fen}"),
    ]


def retry_feedback(move: str, kind: str, attempt: int, max_attempts: int) -> str:
    """The explained retry feedback: the rejected move and the kind of failure, never the answer."""
    return (
        f'Your move "{move}" is illegal in this position (kind: {kind} move). '
        f"Attempt {attempt} of {max_attempts}. Reply with a different legal move."
    )
