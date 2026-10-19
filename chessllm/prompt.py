"""Prompt builder: the system prompt from an editable file and the message for each turn."""

import random
from pathlib import Path
from string import Template
from typing import Literal

import chess

from chessllm.players import Message

# What the LLM is told after an illegal move: explained (the default), bare or hinted.
RetryFeedback = Literal["explained", "bare", "hinted"]
# Whether the LLM is shown the legal-move list: free (no list, the default) or listed.
LlmConstraints = Literal["free", "listed"]

SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "system.txt"
LISTED_SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "system_listed.txt"
SYSTEM_PROMPT_FILES: dict[LlmConstraints, Path] = {"free": SYSTEM_PROMPT_FILE, "listed": LISTED_SYSTEM_PROMPT_FILE}

# The example move shown in the system prompt for each colour the LLM can play: the first move of each side.
EXAMPLE_MOVES = {"white": [], "black": ["e4"]}
EXAMPLE_ANSWERS = {"white": "e4", "black": "e5"}
NO_MOVES_YET = "(no moves yet)"


def system_prompt(llm_color: str, system_prompt_file: Path = SYSTEM_PROMPT_FILE) -> str:
    """The system prompt for the LLM playing llm_color ("white" or "black").

    The file is a template: $color and $opponent are the two colours, and $example_pgn, $example_fen,
    $example_legal_moves and $example_move make up a worked example of a first move for that colour."""
    board = chess.Board()
    for san in EXAMPLE_MOVES[llm_color]:
        board.push_san(san)
    legal_moves = [board.san(move) for move in board.legal_moves]
    random.Random(0).shuffle(legal_moves)  # the prompt says the order is random; a fixed seed keeps it stable
    opponent = "black" if llm_color == "white" else "white"
    return Template(system_prompt_file.read_text(encoding="utf-8")).substitute(
        color=llm_color.capitalize(),
        opponent=opponent.capitalize(),
        example_pgn=chess.Board().variation_san(board.move_stack) or NO_MOVES_YET,
        example_fen=board.fen(),
        example_legal_moves=" ".join(legal_moves),
        example_move=EXAMPLE_ANSWERS[llm_color],
    )


def turn_messages(
    pgn: str, fen: str, llm_color: str, system_prompt_file: Path = SYSTEM_PROMPT_FILE, legal_moves: str | None = None
) -> list[Message]:
    """A fresh prompt for one turn: the system prompt plus the game so far, with no earlier turns, and the
    legal moves (space-separated SAN) under them when given.

    The file is read every turn, so edits apply without restarting the app."""
    position = f"PGN: {pgn or NO_MOVES_YET}\nFEN: {fen}"
    if legal_moves is not None:
        position += f"\nLegal moves: {legal_moves}"
    return [Message("system", system_prompt(llm_color, system_prompt_file)), Message("user", position)]


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
