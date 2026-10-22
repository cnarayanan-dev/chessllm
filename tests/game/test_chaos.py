import chess
import pytest

from chessllm.game.chaos import ResolvedMove, apply, resolve

START = chess.STARTING_FEN
ONLY_THE_C1_BISHOP = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQK1NR w KQkq - 0 1"
EMPTY_B1 = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/R1BQKBNR w KQkq - 0 1"
WHITE_IN_CHECK = "rnb1kbnr/pppp1ppp/8/4p3/5P1q/8/PPPPP1PP/RNBQKBNR w KQkq - 0 1"
PAWN_ON_A7 = "4k3/P7/8/8/8/8/8/4K3 w - - 0 1"
BARE_KINGS = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
NO_WHITE_QUEEN = "rnb1kbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 0 1"
ROOK_BEHIND_PAWN = "4k3/8/8/8/8/8/4P3/4R1K1 w - - 0 1"


def sq(name: str) -> chess.Square:
    return chess.parse_square(name)


def played(fen: str, text: str) -> tuple[ResolvedMove, chess.Board]:
    board = chess.Board(fen)
    resolution = resolve(board, text)
    return resolution, apply(board, resolution)


def summary(resolution: ResolvedMove) -> tuple[str, str | None, str | None, str | None]:
    """The kind, from, to and piece symbol of a resolution."""

    def name(square: chess.Square | None) -> str | None:
        return None if square is None else chess.square_name(square)

    piece = None if resolution.piece is None else resolution.piece.symbol()
    return resolution.kind, name(resolution.from_square), name(resolution.to_square), piece


RESOLVED = [
        (START, "e4", ("legal", "e2", "e4", "P")),
        (ONLY_THE_C1_BISHOP, "Bd3", ("chaos", "c1", "d3", "B")),  # a bishop moving like a knight
        # The blocked a1 rook fits the movement pattern, so it beats the nearer c3 rook.
        ("4k3/8/8/8/8/2R5/P7/R3K3 w - - 0 1", "Ra4", ("chaos", "a1", "a4", "R")),
        (START, "e2e5", ("chaos", "e2", "e5", "P")),
        (START, "Nxe2", ("chaos", "g1", "e2", "N")),  # capturing its own pawn
        (WHITE_IN_CHECK, "a3", ("chaos", "a2", "a3", "P")),  # ignoring check; the empty a3 doesn't call the b2 pawn
        (ROOK_BEHIND_PAWN, "Rxe8", ("chaos", "e1", "e8", "R")),  # jumps its pawn to take the king
        # Both knights fit and stand two squares away: the first in a1→h8 order moves.
        ("rnbqkbnr/pppppppp/8/8/8/5N2/PPP1PPPP/RNBQKB1R w KQkq - 0 1", "Nd2", ("chaos", "b1", "d2", "N")),
        # The file hint beats the g4 rook, which is nearer and fits the movement pattern.
        ("4k3/8/8/8/6R1/8/8/R6K w - - 0 1", "Rad4", ("chaos", "a1", "d4", "R")),
        (NO_WHITE_QUEEN, "Qh5", ("spawn", None, "h5", "Q")),
        # The from-square holds the mover's bishop, so the bishop moves whatever the letter says.
        ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKNBR w KQkq - 0 1", "Ng1f3", ("chaos", "g1", "f3", "B")),
        (EMPTY_B1, "Nb1c3", ("chaos", "g1", "c3", "N")),  # empty from-square: the other knight moves
        (START, "Qe7e5", ("chaos", "d1", "e5", "Q")),  # the opponent's piece on e7 is not taken over
        (PAWN_ON_A7, "b8", ("chaos", "a7", "b8", "Q")),  # auto-queens
        (PAWN_ON_A7, "b8=N", ("chaos", "a7", "b8", "N")),
        (PAWN_ON_A7, "a7a8", ("chaos", "a7", "a8", "Q")),
        (START, "O-O", ("chaos", "e1", "g1", "K")),
        (BARE_KINGS, "O-O-O", ("chaos", "e1", "c1", "K")),
]


@pytest.mark.parametrize(("fen", "text", "expected"), RESOLVED)
def test_resolves_the_move(fen, text, expected):
    assert summary(resolve(chess.Board(fen), text)) == expected


@pytest.mark.parametrize(("fen", "text", "expected"), [case for case in RESOLVED if case[2][0] != "legal"])
def test_applying_a_chaos_move_flips_the_side_clears_en_passant_and_cleans_castling_rights(fen, text, expected):
    board = chess.Board(fen)

    after = apply(board, resolve(board, text))

    assert after.turn != board.turn
    assert after.ep_square is None
    assert after.castling_rights == after.clean_castling_rights()


@pytest.mark.parametrize(
    ("fen", "text"),
    [
        (BARE_KINGS.replace("4K3", "8"), "Ke2"),  # a king is never spawned
        (BARE_KINGS.replace("4K3", "8"), "O-O"),
        (START, "e7e5"),  # pure UCI from the opponent's piece
        (EMPTY_B1, "b1c3"),  # pure UCI from an empty square
        ("4k3/8/8/8/8/5N2/8/4K3 w - - 0 1", "Nf3"),  # the only knight already stands on f3
        (START, "I'll play the Sicilian!"),
        (START, "Qz9"),
        (START, "--"),
        (START, ""),
    ],
)
def test_invalid_moves_leave_the_board_unchanged(fen, text):
    resolution, after = played(fen, text)
    assert resolution.kind == "invalid"
    assert (resolution.from_square, resolution.to_square, resolution.piece) == (None, None, None)
    assert resolution.reason
    assert after.fen() == fen


def test_the_reason_names_the_rule_that_picked_the_piece():
    resolution = resolve(chess.Board(ONLY_THE_C1_BISHOP), "Bd3")
    assert resolution.reason == "no bishop can reach d3 by its movement; c1 is nearest"
    assert "\n" not in resolution.reason


def test_a_legal_move_is_played_as_usual():
    resolution, after = played(START, "Nf3")
    assert resolution.move == chess.Move.from_uci("g1f3")
    assert after.fen() == "rnbqkbnr/pppppppp/8/8/8/5N2/PPPPPPPP/RNBQKB1R b KQkq - 1 1"


def test_a_legal_castle_names_the_rook_move():
    resolution, after = played("4k3/8/8/8/8/8/8/4K2R w K - 0 1", "O-O")
    assert resolution.kind == "legal"
    assert resolution.rook == (sq("h1"), sq("f1"))
    assert after.board_fen() == "4k3/8/8/8/8/8/8/5RK1"


def test_a_chaos_move_captures_whatever_stands_on_the_target():
    _, after = played(START, "Nxe2")
    assert after.board_fen() == "rnbqkbnr/pppppppp/8/8/8/8/PPPPNPPP/RNBQKB1R"


def test_a_chaos_move_jumps_over_pieces_in_the_way():
    _, after = played(START, "e2e5")
    assert after.board_fen() == "rnbqkbnr/pppppppp/8/4P3/8/8/PPPP1PPP/RNBQKBNR"


def test_a_spawn_adds_a_piece_and_moves_nothing():
    _, after = played(NO_WHITE_QUEEN, "Qh5")
    assert after.board_fen() == "rnb1kbnr/pppp1ppp/8/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR"


def test_a_chaos_move_can_take_the_king():
    _, after = played(ROOK_BEHIND_PAWN, "Rxe8")
    assert after.king(chess.BLACK) is None
    assert after.turn == chess.BLACK


def test_a_king_left_in_check_by_a_chaos_move_can_be_taken():
    _, after = played(WHITE_IN_CHECK, "a3")
    resolution, after = played(after.fen(), "Qxe1")
    assert resolution.kind == "legal"  # python-chess calls taking a king left in check legal
    assert after.king(chess.WHITE) is None


def test_an_illegal_castle_moves_the_corner_rook_and_captures():
    resolution, after = played(START, "O-O")
    assert resolution.rook == (sq("h1"), sq("f1"))
    assert after.board_fen() == "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQ1RK1"
    assert after.castling_rights == chess.BB_A8 | chess.BB_H8  # White's king left e1


def test_an_illegal_castle_with_the_king_already_in_place_still_moves_the_rook():
    resolution, after = played("4k3/8/8/8/8/8/8/6KR w - - 0 1", "O-O")
    assert resolution.kind == "chaos"
    assert after.board_fen() == "4k3/8/8/8/8/8/8/5RK1"


def test_an_illegal_castle_without_a_corner_rook_moves_only_the_king():
    resolution, after = played(BARE_KINGS, "O-O-O")
    assert resolution.rook is None
    assert after.board_fen() == "4k3/8/8/8/8/8/8/2K5"


@pytest.mark.parametrize(("text", "piece"), [("b8", chess.QUEEN), ("b8=N", chess.KNIGHT)])
def test_a_pawn_reaching_the_last_rank_promotes(text, piece):
    _, after = played(PAWN_ON_A7, text)
    assert after.piece_at(sq("b8")) == chess.Piece(piece, chess.WHITE)
    assert after.piece_at(sq("a7")) is None


def test_after_a_chaos_move_the_side_flips_en_passant_clears_and_clocks_advance():
    after_e4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    _, after = played(after_e4, "Bb4")  # the f8 bishop jumps its own e7 pawn
    assert after.turn == chess.WHITE
    assert after.ep_square is None
    assert (after.halfmove_clock, after.fullmove_number) == (1, 2)


def test_a_pawn_chaos_move_or_a_capture_resets_the_halfmove_clock():
    _, after = played("4k3/8/8/8/8/8/P7/4K3 w - - 7 30", "a2a5")
    assert (after.halfmove_clock, after.fullmove_number) == (0, 30)


def test_castling_rights_follow_where_kings_and_rooks_stand():
    _, after = played(START, "Rh5")  # the h1 rook jumps its own pawn
    assert after.castling_rights == chess.BB_A1 | chess.BB_A8 | chess.BB_H8


def test_chaos_moves_never_go_through_push(monkeypatch):
    def refuse(*_):
        raise AssertionError("push used for a chaos move")

    board = chess.Board()
    resolution = resolve(board, "e2e5")
    monkeypatch.setattr(chess.Board, "push", refuse)
    apply(board, resolution)
