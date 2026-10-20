"""Prompt builder: the system prompt from an editable file and the message for each turn."""

import random
from pathlib import Path
from string import Template
from typing import Literal

import chess

from chessllm.players import Message

# What the LLM is told after an illegal move: explained (the default), bare or hinted.
RetryFeedback = Literal["explained", "bare", "hinted"]
# Whether the LLM is shown the legal-move list, and whether Enforced decoding holds its move to the legal moves:
# free (neither, the default), listed (the list only), blind_enforced (enforced only) or listed_enforced (both).
LlmConstraints = Literal["free", "listed", "blind_enforced", "listed_enforced"]
# How the position is given in each turn's message: fen (the PGN and FEN, the default) or described (also the last
# move, where every piece stands and whether the LLM is in check, so it needn't decode the FEN).
PositionFormat = Literal["fen", "described"]
LISTED: set[LlmConstraints] = {"listed", "listed_enforced"}
ENFORCED: set[LlmConstraints] = {"blind_enforced", "listed_enforced"}

SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "system.txt"
LISTED_SYSTEM_PROMPT_FILE = Path(__file__).parent / "prompts" / "system_listed.txt"
SYSTEM_PROMPT_FILES: dict[LlmConstraints, Path] = {
    "free": SYSTEM_PROMPT_FILE,
    "listed": LISTED_SYSTEM_PROMPT_FILE,
    "blind_enforced": SYSTEM_PROMPT_FILE,
    "listed_enforced": LISTED_SYSTEM_PROMPT_FILE,
}

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


PIECE_NAMES = {
    chess.KING: ("King", "King"),
    chess.QUEEN: ("Queen", "Queens"),
    chess.ROOK: ("Rook", "Rooks"),
    chess.BISHOP: ("Bishop", "Bishops"),
    chess.KNIGHT: ("Knight", "Knights"),
    chess.PAWN: ("Pawn", "Pawns"),
}


def describe_position(board: chess.Board, last_move: str | None) -> str:
    """The position in words for the side to move: the last move, each side's pieces by square, and whether it is
    in check. Pieces of a kind are listed by file, then rank, so the text depends only on the position."""

    def pieces(color: chess.Color) -> str:
        kinds = []
        for piece_type, (one, many) in PIECE_NAMES.items():
            squares = sorted(board.pieces(piece_type, color), key=lambda square: (chess.square_file(square), square))
            if squares:
                kinds.append(f"{one if len(squares) == 1 else many} {', '.join(map(chess.square_name, squares))}")
        return "; ".join(kinds) or "none"

    mover, other = board.turn, not board.turn
    lines = [f"Last move: {last_move}"] if last_move else []
    lines.append(f"Your pieces ({chess.COLOR_NAMES[mover].capitalize()}): {pieces(mover)}")
    lines.append(f"Opponent's pieces ({chess.COLOR_NAMES[other].capitalize()}): {pieces(other)}")
    if board.is_check():
        lines.append("You are in check.")
    return "\n".join(lines)


def turn_messages(
    pgn: str,
    fen: str,
    llm_color: str,
    system_prompt_file: Path = SYSTEM_PROMPT_FILE,
    legal_moves: str | None = None,
    description: str | None = None,
) -> list[Message]:
    """A fresh prompt for one turn: the system prompt plus the game so far, with no earlier turns, the position's
    description under them when given, and then the legal moves (space-separated SAN) when given.

    The file is read every turn, so edits apply without restarting the app."""
    position = f"PGN: {pgn or NO_MOVES_YET}\nFEN: {fen}"
    if description is not None:
        position += f"\n{description}"
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


def cut_off_feedback(attempt: int, max_attempts: int) -> str:
    """The message after an answer cut off by the Thinking budget, the same at every Retry feedback level: there was
    no move to judge, so there is nothing to explain or hint at."""
    return (
        f"Your reply was cut off before it gave a move. Attempt {attempt} of {max_attempts}. "
        "Think more briefly and reply with a legal move."
    )
