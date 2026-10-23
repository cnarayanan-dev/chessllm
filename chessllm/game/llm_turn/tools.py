"""The Tools an LLM side may call during its Turn (ADR 0011), each answering about the position it is to move in.

They are methods of PositionTools, registered by the tool decorator. None takes input from the LLM: bound to a turn's
position, each is a function of no arguments, from whose name and docstring the ollama SDK builds the tool's schema,
so the docstrings are written for the LLM."""

import random
from collections.abc import Callable, Sequence

import chess

from chessllm.core.types import Color
from chessllm.game.llm_turn.prompt import NO_MOVES_YET, move_record
from chessllm.game.sides import TOOLS, Tool

# The tools, by name, in the order registered: every one of TOOLS.
REGISTERED: dict[Tool, Callable[..., str]] = {}

# The points of each piece the material tool counts, in the order it lists them; kings aren't counted.
POINTS = {chess.QUEEN: 9, chess.ROOK: 5, chess.BISHOP: 3, chess.KNIGHT: 3, chess.PAWN: 1}
POINTS_LINE = "Points: P 1, N 3, B 3, R 5, Q 9 (kings not counted)"


def tool(method: Callable[..., str]) -> Callable[..., str]:
    """Register a method of PositionTools as the Tool of its name."""
    assert method.__name__ in TOOLS, f"no tool {method.__name__}"
    REGISTERED[method.__name__] = method
    return method


class PositionTools:
    """The Tools answering about one position: the board the LLM side at color is to move in, and every ply that led
    to it as written in the Move record."""

    def __init__(self, board: chess.Board, moves: Sequence[str], color: Color) -> None:
        self._board = board.copy()
        self._moves = list(moves)
        self._color = color

    def functions(self, tools: frozenset[Tool]) -> tuple[Callable[[], str], ...]:
        """The tools given, bound to this position, in the order of TOOLS."""
        return tuple(getattr(self, name) for name in REGISTERED if name in tools)

    @tool
    def board(self) -> str:
        """The current position: a diagram of the board with its files and ranks, the FEN, whose move it is, the
        castling rights and the en passant square."""
        board = self._board
        rows = []
        for rank in range(7, -1, -1):
            pieces = (board.piece_at(chess.square(file, rank)) for file in range(8))
            rows.append(f"{rank + 1}  " + " ".join(piece.symbol() if piece else "." for piece in pieces))
        castling = [
            f"{chess.COLOR_NAMES[color].capitalize()} {', '.join(rights)}"
            for color in chess.COLORS
            if (rights := castling_rights(board, color))
        ]
        # As the FEN gives it: only when an en passant capture is legal.
        en_passant = board.ep_square if board.has_legal_en_passant() else None
        en_passant_square = chess.square_name(en_passant) if en_passant is not None else "none"
        return "\n".join(
            [
                *rows,
                "   a b c d e f g h",
                "Uppercase is White, lowercase Black, . an empty square.",
                f"FEN: {board.fen()}",
                f"To move: {chess.COLOR_NAMES[board.turn].capitalize()}",
                f"Castling rights: {'; '.join(castling) or 'none'}",
                f"En passant: {en_passant_square}",
            ]
        )

    @tool
    def move_history(self) -> str:
        """The moves of the game so far, as PGN movetext."""
        return move_record(self._moves) or NO_MOVES_YET

    @tool
    def legal_moves(self) -> str:
        """Every legal move in the current position, in SAN, separated by spaces. The order is random and means
        nothing."""
        moves = [self._board.san(move) for move in self._board.legal_moves]
        random.shuffle(moves)
        return " ".join(moves)

    @tool
    def material(self) -> str:
        """Each side's pieces and their points, and the material balance from your side."""
        totals = {color: points(self._board, color) for color in chess.COLORS}
        mine = self._color == "white"
        balance = totals[mine] - totals[not mine]
        you = f"for you ({self._color.capitalize()})"
        return "\n".join(
            [
                POINTS_LINE,
                *(
                    f"{chess.COLOR_NAMES[color].capitalize()}: {pieces(self._board, color)} = {totals[color]} points"
                    for color in chess.COLORS
                ),
                f"Balance: {f'{balance:+d}' if balance else '0, even,'} {you}",
            ]
        )


def castling_rights(board: chess.Board, color: chess.Color) -> list[str]:
    """The castlings color still has the right to, though perhaps not now: O-O, O-O-O or both."""
    sides = (
        ("O-O", board.has_kingside_castling_rights(color)),
        ("O-O-O", board.has_queenside_castling_rights(color)),
    )
    return [castling for castling, right in sides if right]


def pieces(board: chess.Board, color: chess.Color) -> str:
    """color's pieces but the king, most valuable first, e.g. "Q, 2 R, 8 P"; "none" when it has only its king."""
    counted = []
    for piece_type in POINTS:
        count = len(board.pieces(piece_type, color))
        symbol = chess.piece_symbol(piece_type).upper()
        if count:
            counted.append(symbol if count == 1 else f"{count} {symbol}")
    return ", ".join(counted) or "none"


def points(board: chess.Board, color: chess.Color) -> int:
    return sum(value * len(board.pieces(piece_type, color)) for piece_type, value in POINTS.items())
