"""The Tools (ADR 0011): four plain functions an LLM side may call during an attempt, none taking input from the LLM,
each answering about the current position. The ollama SDK builds their schemas from their names and docstrings."""

import chess
from ollama._utils import convert_function_to_tool

from chessllm.game.sides import ALL_TOOLS
from chessllm.game.tools import ToolPosition, bound_tools

# After 1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7: Black to move, a pawn down.
MOVES = ["e4", "e5", "Nf3", "Nc6", "Bc4", "Nf6", "Ng5", "d5", "exd5", "Nxd5", "Nxf7"]


def position(moves: list[str], color: str) -> ToolPosition:
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    return ToolPosition(board, moves, color)


def answers(moves: list[str], color: str) -> dict[str, str]:
    return {tool.__name__: tool() for tool in bound_tools(ALL_TOOLS, position(moves, color))}


def test_the_four_tools_take_no_input_and_their_schemas_come_from_their_docstrings():
    tools = bound_tools(ALL_TOOLS, position([], "white"))

    assert [tool.__name__ for tool in tools] == ["board", "move_history", "legal_moves", "material"]
    for tool in tools:
        schema = convert_function_to_tool(tool).function
        assert schema.parameters is not None and not schema.parameters.properties
        assert schema.description  # the docstring tells the LLM what the tool answers


def test_a_side_gets_only_its_own_tools():
    tools = bound_tools(frozenset({"material", "board"}), position([], "white"))

    assert [tool.__name__ for tool in tools] == ["board", "material"]


def test_board_is_a_diagram_with_files_and_ranks_the_fen_whose_move_castling_and_en_passant():
    board = answers(["e4", "c5", "e5", "d5"], "white")["board"]

    assert board == (
        "  a b c d e f g h\n"
        "8 r n b q k b n r 8\n"
        "7 p p . . p p p p 7\n"
        "6 . . . . . . . . 6\n"
        "5 . . p p P . . . 5\n"
        "4 . . . . . . . . 4\n"
        "3 . . . . . . . . 3\n"
        "2 P P P P . P P P 2\n"
        "1 R N B Q K B N R 1\n"
        "  a b c d e f g h\n"
        "Uppercase is White, lowercase Black, . an empty square.\n"
        "FEN: rnbqkbnr/pp2pppp/8/2ppP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3\n"
        "To move: White\n"
        "Castling rights: White O-O, O-O-O; Black O-O, O-O-O\n"
        "En passant: d6"
    )


def test_board_says_when_there_is_no_castling_or_en_passant():
    board = answers(MOVES + ["Kxf7"], "white")["board"]

    assert "To move: White" in board
    assert "Castling rights: White O-O, O-O-O; Black none" in board
    assert board.endswith("En passant: none")


def test_move_history_is_the_pgn_movetext():
    assert answers(MOVES, "black")["move_history"] == "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7"
    assert answers([], "white")["move_history"] == "(no moves yet)"


def test_legal_moves_are_every_legal_move_in_san_in_random_order():
    board = position(MOVES, "black").board
    legal = sorted(board.san(move) for move in board.legal_moves)
    [legal_moves] = [tool for tool in bound_tools(frozenset({"legal_moves"}), position(MOVES, "black"))]

    orders = {legal_moves() for _ in range(20)}

    assert all(sorted(order.split()) == legal for order in orders)
    assert len(orders) > 1


def test_material_gives_each_sides_pieces_and_points_and_the_balance_from_the_callers_side():
    material = answers(MOVES, "black")["material"]

    assert material == (
        "Points: pawn 1, knight 3, bishop 3, rook 5, queen 9.\n"
        "White: 7 pawns, 2 knights, 2 bishops, 2 rooks, 1 queen: 38 points\n"
        "Black: 6 pawns, 2 knights, 2 bishops, 2 rooks, 1 queen: 37 points\n"
        "Balance: you (Black) are 1 point down."
    )
    assert answers(MOVES, "white")["material"].endswith("Balance: you (White) are 1 point up.")
    assert answers(MOVES + ["Kxf7"], "black")["material"].endswith("Balance: you (Black) are 2 points up.")
    assert answers([], "white")["material"].endswith("Balance: even.")
