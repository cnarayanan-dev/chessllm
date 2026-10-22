"""Chaos rules: an LLM's rule-breaking or ambiguous move is played on the board anyway (ADR 0006). The resolver turns
the LLM's move text into a chaos move and applies it to the board; ChaosRules is what the rules change in a game.

python-chess only ever resolves legal moves, and `Board.push` mangles illegal ones, so a chaos move is
resolved here and applied by editing the board by hand."""

import re
from dataclasses import dataclass
from typing import Any

import chess

from chessllm.core.types import Color, RulesKey
from chessllm.exceptions import InvalidSettings
from chessllm.game.ending import GameEnd
from chessllm.game.records import AttemptResult, Resolution, ResolutionKind
from chessllm.game.sides import ENFORCED, AnchorSide, LlmSide

CASTLE_RE = re.compile(r"^[O0]-[O0](-[O0])?[+#]?$")


@dataclass(frozen=True)
class ResolvedMove:
    """How the resolver read a move, on python-chess squares and pieces. Its record, which the game log and the page
    get, is records.Resolution."""

    kind: ResolutionKind
    reason: str  # one line, e.g. "no bishop can reach d3 by its movement; c1 is nearest"
    from_square: chess.Square | None = None  # None for a spawn
    to_square: chess.Square | None = None
    piece: chess.Piece | None = None  # the piece that ends up on to_square, after any promotion
    rook: tuple[chess.Square, chess.Square] | None = None  # the rook's from and to in a castle
    move: chess.Move | None = None  # the legal move, for a legal resolution only

    def uci(self, board: chess.Board) -> str:
        """The resolved move in UCI, given the board it is played on: a spawn as a drop, e.g. "Q@d5", and a pawn
        that becomes another piece with its promotion. Only for a move that isn't invalid."""
        assert self.to_square is not None and self.piece is not None
        if self.from_square is None:
            return chess.Move(self.to_square, self.to_square, drop=self.piece.piece_type).uci()
        promotion = self.piece.piece_type if board.piece_type_at(self.from_square) != self.piece.piece_type else None
        return chess.Move(self.from_square, self.to_square, promotion).uci()

    def record(self) -> Resolution:
        def name(square: chess.Square | None) -> str | None:
            return chess.square_name(square) if square is not None else None

        return Resolution.model_validate({
            "kind": self.kind,
            "from": name(self.from_square),
            "to": name(self.to_square),
            "piece": self.piece.symbol() if self.piece else None,
            "rook": [chess.square_name(square) for square in self.rook] if self.rook else None,
            "reason": self.reason,
        })


def invalid(reason: str) -> ResolvedMove:
    return ResolvedMove("invalid", reason)


def fits(board: chess.Board, piece: chess.Piece, start: chess.Square, target: chess.Square) -> bool:
    """Whether the piece could reach the target by its movement pattern on an empty board.

    A pawn's diagonal step fits only when something stands on the target, as it is a capture."""
    df = chess.square_file(target) - chess.square_file(start)
    dr = chess.square_rank(target) - chess.square_rank(start)
    adf, adr = abs(df), abs(dr)
    match piece.piece_type:
        case chess.PAWN:
            forward = 1 if piece.color == chess.WHITE else -1
            home = 1 if piece.color == chess.WHITE else 6
            push = df == 0 and (dr == forward or (dr == 2 * forward and chess.square_rank(start) == home))
            return push or (adf == 1 and dr == forward and board.piece_at(target) is not None)
        case chess.KNIGHT:
            return {adf, adr} == {1, 2}
        case chess.BISHOP:
            return adf == adr != 0
        case chess.ROOK:
            return (adf == 0) != (adr == 0)
        case chess.QUEEN:
            return adf == adr != 0 or (adf == 0) != (adr == 0)
        case _:
            return max(adf, adr) == 1


def promoted(piece: chess.Piece, target: chess.Square, promotion: str | None) -> chess.Piece:
    """A pawn reaching the last rank becomes the named piece, or a queen if none (or a king) is named."""
    last = 7 if piece.color == chess.WHITE else 0
    if piece.piece_type != chess.PAWN or chess.square_rank(target) != last:
        return piece
    named = chess.Piece.from_symbol(promotion).piece_type if promotion else chess.QUEEN
    return chess.Piece(chess.QUEEN if named in (chess.PAWN, chess.KING) else named, piece.color)


def rook_squares(long: bool, rank: int) -> tuple[chess.Square, chess.Square]:
    """The corner a castling rook stands on and the square it goes to."""
    return chess.square(0 if long else 7, rank), chess.square(3 if long else 5, rank)


def castle(board: chess.Board, long: bool) -> ResolvedMove:
    """An illegal castle: the king goes to c or g on its back rank, and the corner rook, if there, to d or f."""
    color = board.turn
    rank = 0 if color == chess.WHITE else 7
    king_to = chess.square(2 if long else 6, rank)
    corner, rook_to = rook_squares(long, rank)
    king = board.king(color)
    side = "O-O-O" if long else "O-O"
    if king is None:
        return invalid(f"{side} without a king; a king is never spawned")
    rook = (corner, rook_to) if board.piece_at(corner) == chess.Piece(chess.ROOK, color) else None
    if king == king_to and not rook:
        return invalid(f"{side}, but the king already stands on {chess.square_name(king_to)} and no rook is in the corner")
    rook_note = f", rook {chess.square_name(corner)}→{chess.square_name(rook_to)}" if rook else ", no rook in the corner"
    return ResolvedMove(
        "chaos",
        f"illegal {side}: king {chess.square_name(king)}→{chess.square_name(king_to)}{rook_note}",
        king,
        king_to,
        chess.Piece(chess.KING, color),
        rook,
    )


def by_type(
    board: chess.Board,
    piece_type: chess.PieceType,
    target: chess.Square,
    file_hint: int | None,
    rank_hint: int | None,
    promotion: str | None,
) -> ResolvedMove:
    """Steps 2 to 5 of ADR 0006: a hint, then the movement pattern, then distance pick the mover's piece of
    this type; with none on the board, one spawns."""
    color = board.turn
    name = chess.piece_name(piece_type)
    target_name = chess.square_name(target)
    on_board = list(board.pieces(piece_type, color))
    if not on_board:
        if piece_type == chess.KING:
            return invalid("no king on the board, and a king is never spawned")
        piece = promoted(chess.Piece(piece_type, color), target, promotion)
        return ResolvedMove("spawn", f"no {name} on the board; one appears on {target_name}", None, target, piece)
    candidates = [s for s in on_board if s != target]
    if not candidates:
        return invalid(f"the only {name} already stands on {target_name}")

    notes = []
    hinted = [
        s
        for s in candidates
        if (file_hint is None or chess.square_file(s) == file_hint)
        and (rank_hint is None or chess.square_rank(s) == rank_hint)
    ]
    if hinted and len(hinted) < len(candidates):
        candidates = hinted
        notes.append("picked by the hint")
    fitting = [s for s in candidates if fits(board, chess.Piece(piece_type, color), s, target)]
    if fitting:
        candidates = fitting
    nearest = min(chess.square_distance(s, target) for s in candidates)
    start = min(s for s in candidates if chess.square_distance(s, target) == nearest)
    if not fitting:
        reason = f"no {name} can reach {target_name} by its movement; {chess.square_name(start)} is nearest"
    elif len(fitting) > 1:
        reason = f"{name}s that can reach {target_name}: {', '.join(chess.square_name(s) for s in fitting)}; "
        reason += f"{chess.square_name(start)} is nearest"
    else:
        reason = f"the {name} on {chess.square_name(start)} moves"
    if sum(chess.square_distance(s, target) == nearest for s in candidates) > 1:
        notes.append("tie broken a1→h8")
    piece = promoted(chess.Piece(piece_type, color), target, promotion)
    return ResolvedMove("chaos", "; ".join([reason, *notes]), start, target, piece)


def resolve(board: chess.Board, text: str) -> ResolvedMove:
    """Resolve the LLM's move text: legal as python-chess reads it, else a chaos move or spawn, else invalid."""
    try:
        move = board.parse_san(text)
    except (chess.AmbiguousMoveError, chess.IllegalMoveError):
        pass
    except chess.InvalidMoveError:
        return invalid("not a move in any notation")
    else:
        if not move:
            return invalid("a null move")
        piece = board.piece_at(move.from_square)
        assert piece is not None
        if move.promotion:
            piece = chess.Piece(move.promotion, piece.color)
        rook = None
        if board.is_castling(move):
            long = chess.square_file(move.to_square) < chess.square_file(move.from_square)
            rook = rook_squares(long, chess.square_rank(move.from_square))
        return ResolvedMove("legal", "a legal move", move.from_square, move.to_square, piece, rook, move)

    if castling := CASTLE_RE.match(text):
        return castle(board, long=bool(castling.group(1)))
    san = chess.SAN_REGEX.match(text)
    if not san:
        return invalid("not a move this resolver can read")
    letter, file, rank, target_name, promotion = san.groups()
    named = chess.Piece.from_symbol(letter).piece_type if letter else None
    target = chess.parse_square(target_name)
    promotion = promotion.lstrip("=") if promotion else None
    file_hint = "abcdefgh".index(file) if file else None
    rank_hint = int(rank) - 1 if rank else None
    if file_hint is not None and rank_hint is not None:  # a from-square: trusted if it holds the mover's own piece
        start = chess.square(file_hint, rank_hint)
        own = board.piece_at(start)
        if own and own.color == board.turn:
            if start == target:
                return invalid(f"from and to are both {target_name}")
            ignored = f" (the {chess.piece_name(named)} letter is ignored)" if named and named != own.piece_type else ""
            reason = f"the {chess.piece_name(own.piece_type)} on {chess.square_name(start)} moves{ignored}"
            return ResolvedMove("chaos", reason, start, target, promoted(own, target, promotion))
        if named is None:
            whose = "the opponent's piece" if own else "an empty square"
            return invalid(f"UCI from {whose} on {chess.square_name(start)} names no piece type")
        file_hint = rank_hint = None
    return by_type(board, named or chess.PAWN, target, file_hint, rank_hint, promotion)


def apply(board: chess.Board, resolution: ResolvedMove) -> chess.Board:
    """The board after the resolved move; an invalid move leaves it unchanged. Chaos moves and spawns are
    applied by hand, never through `push`."""
    if resolution.kind == "invalid":
        return board.copy()
    if resolution.kind == "legal":
        assert resolution.move is not None
        after = board.copy()
        after.push(resolution.move)
        return after
    assert resolution.to_square is not None and resolution.piece is not None
    after = board.copy(stack=False)
    mover = after.turn
    moving = after.piece_at(resolution.from_square) if resolution.from_square is not None else resolution.piece
    assert moving is not None
    captures = after.piece_at(resolution.to_square) is not None
    rook_piece = None
    if resolution.rook:
        rook_piece = after.remove_piece_at(resolution.rook[0])
        captures = captures or after.piece_at(resolution.rook[1]) is not None
    if resolution.from_square is not None:
        after.remove_piece_at(resolution.from_square)
    after.set_piece_at(resolution.to_square, resolution.piece)  # captures anything, own pieces and kings included
    if resolution.rook and rook_piece:
        after.set_piece_at(resolution.rook[1], rook_piece)
    after.turn = not mover
    after.ep_square = None
    after.castling_rights = after.clean_castling_rights()
    after.halfmove_clock = 0 if moving.piece_type == chess.PAWN or captures else after.halfmove_clock + 1
    if mover == chess.BLACK:
        after.fullmove_number += 1
    return after


class ChaosRules:
    """Chaos rules, for every LLM in the game: a rule-breaking or ambiguous move is resolved and played at its first
    attempt, the game can end in a King capture or a King left in check, and its games are counted apart, unrated."""

    key: RulesKey = "chaos"
    rated = False
    plays_illegal_moves = True

    def check_anchor(self, anchor: AnchorSide) -> None:
        if anchor.engine != "stockfish":
            why = "it alone copes with chaos positions"
            raise InvalidSettings(f"Only Stockfish can be the Anchor under Chaos rules: {why}")

    def check_llm(self, color: Color, side: LlmSide) -> None:
        if side.llm_constraints in ENFORCED:
            wanted = "Chaos rules need every LLM under Free or Listed"
            raise InvalidSettings(f"{wanted}, not {side.model} ({color}) under {side.llm_constraints}")

    def resolve(self, board: chess.Board, written: str, result: AttemptResult) -> ResolvedMove | None:
        """A rule-breaking or ambiguous move is resolved, and a legal one too; badly formed notation never is, nor
        an answer cut off before it gave a move."""
        return resolve(board, written) if result not in ("invalid", "cut_off") else None

    def end(self, board: chess.Board) -> GameEnd | None:
        """King capture comes first: python-chess would go on judging a position with a king missing. Then a chaos
        move that leaves the mover's own king in check loses at once, before the opponent has to take the king."""
        mover = not board.turn
        if board.king(board.turn) is None or board.king(mover) is None:
            # The side left with a king wins: normally the mover, unless it took its own king with a chaos move.
            winner = mover if board.king(mover) is not None else board.turn
            return GameEnd("1-0" if winner == chess.WHITE else "0-1", "king_capture")
        if board.was_into_check():  # only a chaos move can leave the mover's king attacked
            return GameEnd("0-1" if mover == chess.WHITE else "1-0", "king_left_in_check")
        return None

    def chaos_counts(self, chaos_moves: int, spawns: int) -> tuple[int | None, int | None]:
        return chaos_moves, spawns

    def attempt_log_shape(self, shape: dict[str, Any]) -> dict[str, Any]:
        """The resolution is always there, null when there was no move to resolve."""
        shape.setdefault("resolution", None)
        return shape

    def game_start_fields(self) -> dict[str, Any]:
        return {"rules": self.key}

    def game_end_fields(self, plies: int, first_chaos_ply: int | None) -> dict[str, Any]:
        """The plies played from the first chaos move on, by any side."""
        return {"chaos_plies": plies - first_chaos_ply + 1 if first_chaos_ply else 0}

    def pgn_headers(self) -> dict[str, str]:
        return {"Rules": "Chaos"}


CHAOS = ChaosRules()
