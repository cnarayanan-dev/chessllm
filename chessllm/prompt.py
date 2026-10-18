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
