"""The Tools an LLM side may call during an attempt (ADR 0011): plain functions of the current position, registered by
@tool. None takes input from the LLM: each is bound to the turn's position (bound_tools) and handed to the LLM player
without parameters, and the ollama SDK builds its schema from its name and docstring, which is what the LLM is told
the tool answers."""

import random
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

import chess

from chessllm.core.types import Color
from chessllm.game.llm_turn.prompt import NO_MOVES_YET, move_record
from chessllm.game.sides import TOOL_NAMES, ToolName


@dataclass(frozen=True)
class ToolPosition:
    """What the tools answer about: the position to move in, every ply that led to it as written in the Move record,
    and the colour of the side asking."""

    board: chess.Board
    moves: Sequence[str]
    color: Color


TOOLS: dict[str, Callable[[ToolPosition], str]] = {}


def tool(function: Callable[[ToolPosition], str]) -> Callable[[ToolPosition], str]:
    """Register a tool under its function's name, one of the ToolNames."""
    assert function.__name__ in TOOL_NAMES, f"{function.__name__} is no ToolName"
    TOOLS[function.__name__] = function
    return function


def bound_tools(names: Collection[ToolName], position: ToolPosition) -> list[Callable[[], str]]:
    """The side's tools, in the order of TOOL_NAMES, each bound to the position: a function without parameters, with
    the tool's name and docstring, as the ollama SDK takes it."""
    return [bind(TOOLS[name], position) for name in TOOL_NAMES if name in names]


def bind(function: Callable[[ToolPosition], str], position: ToolPosition) -> Callable[[], str]:
    """The tool answering about position, without parameters, under the tool's own name and docstring."""

    def bound() -> str:
        return function(position)

    # Not functools.wraps: its __wrapped__ would give the SDK the unbound signature, position and all.
    bound.__name__ = bound.__qualname__ = function.__name__
    bound.__doc__ = function.__doc__
    return bound


@tool
def board(position: ToolPosition) -> str:
    """The current position: a diagram of the board with its files and ranks, the FEN, whose move it is, each side's
    castling rights and the en passant square."""
    on_board = position.board
    files = "  " + " ".join(chess.FILE_NAMES)
    ranks = []
    for rank in reversed(range(8)):
        squares = (on_board.piece_at(chess.square(file, rank)) for file in range(8))
        row = " ".join(piece.symbol() if piece else "." for piece in squares)
        ranks.append(f"{rank + 1} {row} {rank + 1}")

    def castling(color: chess.Color) -> str:
        sides = [
            castle
            for castle, has_right in (
                ("O-O", on_board.has_kingside_castling_rights(color)),
                ("O-O-O", on_board.has_queenside_castling_rights(color)),
            )
            if has_right
        ]
        return ", ".join(sides) or "none"

    # The en passant square as the FEN gives it: only when an en passant capture is legal.
    ep_square = on_board.ep_square if on_board.has_legal_en_passant() else None
    en_passant = chess.square_name(ep_square) if ep_square is not None else None
    return "\n".join(
        [
            files,
            *ranks,
            files,
            "Uppercase is White, lowercase Black, . an empty square.",
            f"FEN: {on_board.fen()}",
            f"To move: {chess.COLOR_NAMES[on_board.turn].capitalize()}",
            f"Castling rights: White {castling(chess.WHITE)}; Black {castling(chess.BLACK)}",
            f"En passant: {en_passant or 'none'}",
        ]
    )


@tool
def move_history(position: ToolPosition) -> str:
    """The moves of the game so far, as PGN movetext."""
    return move_record(position.moves) or NO_MOVES_YET


@tool
def legal_moves(position: ToolPosition) -> str:
    """Every legal move in the current position, in SAN. Their order is random and means nothing."""
    on_board = position.board
    moves = [on_board.san(move) for move in on_board.legal_moves]
    random.shuffle(moves)
    return " ".join(moves)


# The points of each kind of piece, the King counting none.
POINTS = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


@tool
def material(position: ToolPosition) -> str:
    """Each side's pieces and their points (pawn 1, knight 3, bishop 3, rook 5, queen 9), and the balance from your
    side."""
    on_board = position.board

    def pieces(color: chess.Color) -> tuple[str, int]:
        counts = {piece_type: len(on_board.pieces(piece_type, color)) for piece_type in POINTS}
        named = [
            f"{count} {chess.piece_name(piece_type)}{'s' * (count != 1)}"
            for piece_type, count in counts.items()
            if count
        ]
        return ", ".join(named) or "no pieces but the King", sum(POINTS[kind] * count for kind, count in counts.items())

    (white, white_points), (black, black_points) = pieces(chess.WHITE), pieces(chess.BLACK)
    balance = white_points - black_points if position.color == "white" else black_points - white_points
    points = f"{abs(balance)} point{'s' * (abs(balance) != 1)}"
    you = f"you ({position.color.capitalize()})"
    return "\n".join(
        [
            "Points: pawn 1, knight 3, bishop 3, rook 5, queen 9.",
            f"White: {white}: {white_points} points",
            f"Black: {black}: {black_points} points",
            f"Balance: {you} are {points} {'up' if balance > 0 else 'down'}." if balance else "Balance: even.",
        ]
    )

