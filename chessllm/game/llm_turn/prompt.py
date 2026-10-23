"""Prompt builder: every Prompt is built from the side's Prompt template (ADR 0010), its System prompt and its Turn
template filled in for the game, then the Retry feedback after an illegal move. The default templates' System
prompts are editable files, read when a game starts: those of the templates that show the position, and under Turn
memory chat_moves those of the templates that give only the opponent's last move."""

import hashlib
import random
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Literal, get_args

import chess

from chessllm.core.config import PROMPTS_DIR
from chessllm.core.types import Color, opponent
from chessllm.exceptions import InvalidSettings
from chessllm.game.sides import LISTED, LlmConstraints, LlmSide, PromptTemplate, RetryFeedback, TurnMemory
from chessllm.llm.players import Message

SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system.txt"
LISTED_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_listed.txt"
# The System prompt file of the default Prompt templates for each kind of LLM constraints, as prompt_file logs it for
# a side playing one.
SYSTEM_PROMPT_FILES: dict[LlmConstraints, Path] = {
    "free": SYSTEM_PROMPT_FILE,
    "listed": LISTED_SYSTEM_PROMPT_FILE,
    "blind_enforced": SYSTEM_PROMPT_FILE,
    "listed_enforced": LISTED_SYSTEM_PROMPT_FILE,
}
MOVES_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_moves.txt"
LISTED_MOVES_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "system_moves_listed.txt"
# The System prompt file of the Moves default Prompt templates, played under Turn memory chat_moves, likewise.
MOVES_SYSTEM_PROMPT_FILES: dict[LlmConstraints, Path] = {
    "free": MOVES_SYSTEM_PROMPT_FILE,
    "listed": LISTED_MOVES_SYSTEM_PROMPT_FILE,
    "blind_enforced": MOVES_SYSTEM_PROMPT_FILE,
    "listed_enforced": LISTED_MOVES_SYSTEM_PROMPT_FILE,
}

# The example move shown in the system prompt for each colour the LLM can play: the first move of each side.
EXAMPLE_MOVES = {"white": [], "black": ["e4"]}
EXAMPLE_ANSWERS = {"white": "e4", "black": "e5"}
# The Moves templates' worked example goes on for a move more of each side, 1. e4 e5 2. Nf3 Nc6: the opponent's move
# and the LLM's answer.
EXAMPLE_NEXT_MOVES = {"white": "e5", "black": "Nf3"}
EXAMPLE_NEXT_ANSWERS = {"white": "Nf3", "black": "Nc6"}
NO_MOVES_YET = "(no moves yet)"
RECENT_PLIES = 10  # how many plies $recent_moves holds

# The placeholders of a System prompt: the two colours, and a worked example of a first move for the LLM's colour,
# then for the Moves templates the turn after it, each turn's message as chat_moves gives it.
SYSTEM_PLACEHOLDERS = (
    "color", "opponent", "example_pgn", "example_fen", "example_legal_moves", "example_move",
    "example_message", "example_next_message", "example_next_legal_moves", "example_next_move",
)
# The placeholders of a Turn template: the Move record, its last ten plies, the FEN, the position in words (the last
# move, where every piece stands and whether the LLM is in check), the last move, the Legal-move list, and the
# opponent's last move as a turn under chat_moves gives it ("Opponent played Nf6.").
TURN_PLACEHOLDERS = ("moves", "recent_moves", "fen", "description", "last_move", "legal_moves", "opponent_played")
# The placeholders that show the position, which a Turn template under chat_moves never places: there the LLM keeps
# track of the board itself.
POSITION_PLACEHOLDERS = ("moves", "recent_moves", "fen", "description")

# The parts of the default Turn templates, which send the messages sent before Prompt templates, byte for byte.
PGN_AND_FEN = "PGN: $moves\nFEN: $fen"
DESCRIPTION = "\n$description"
LEGAL_MOVES = "\nLegal moves: $legal_moves"
OPPONENT_PLAYED = "$opponent_played"

# The default Prompt templates that show the position, which --prompt-template chooses from: Default, the PGN and
# FEN, and Described, which adds where every piece stands.
PositionTemplate = Literal["default", "described"]
# Every default Prompt template: those two, and Moves, which gives only the opponent's last move, for chat_moves.
DefaultTemplate = Literal["default", "described", "moves"]


def default_template(llm_constraints: LlmConstraints, kind: DefaultTemplate = "default") -> PromptTemplate:
    """A default Prompt template for the LLM constraints, placing the Legal-move list under Listed. Its System prompt
    is read from its file now, so an edit to the file is played from the next game.

    Its ID is its kind, with "-listed" under Listed, and a version from its text after an @, e.g.
    "described-listed@1f0c2a9e": the files can be edited, and an ID always means one text (ADR 0010)."""
    listed = llm_constraints in LISTED
    system_prompt = default_system_prompt_file(llm_constraints, kind).read_text(encoding="utf-8")
    shown = OPPONENT_PLAYED if kind == "moves" else PGN_AND_FEN + (DESCRIPTION if kind == "described" else "")
    turn_template = shown + (LEGAL_MOVES if listed else "")
    version = hashlib.sha256(f"{system_prompt}\0{turn_template}".encode("utf-8")).hexdigest()[:8]
    return PromptTemplate(
        id=f"{kind}{'-listed' * listed}@{version}",
        name=f"{kind.capitalize()}{' listed' * listed}",
        system_prompt=system_prompt,
        turn_template=turn_template,
    )


def default_system_prompt_file(llm_constraints: LlmConstraints, kind: DefaultTemplate) -> Path:
    """The file of a default Prompt template's System prompt."""
    return (MOVES_SYSTEM_PROMPT_FILES if kind == "moves" else SYSTEM_PROMPT_FILES)[llm_constraints]


def side_template(side: LlmSide) -> PromptTemplate:
    """The Prompt template the side plays with: its own, or else the default for its LLM constraints and Turn
    memory, Moves under chat_moves and Default under the others."""
    kind: DefaultTemplate = "moves" if side.turn_memory == "chat_moves" else "default"
    return side.prompt_template or default_template(side.llm_constraints, kind)


def prompt_file(template: PromptTemplate, llm_constraints: LlmConstraints) -> Path | None:
    """The System prompt file of a default template as its files say now, as prompt_file logs it; None for any other
    template, whose System prompt no file holds."""
    for kind in get_args(DefaultTemplate):
        if template == default_template(llm_constraints, kind):
            return default_system_prompt_file(llm_constraints, kind)
    return None


def check_prompt_template(
    template: PromptTemplate, llm_constraints: LlmConstraints, turn_memory: TurnMemory = "fresh"
) -> None:
    """Raises InvalidSettings, saying why, if the template can't be played under the LLM constraints and Turn
    memory: a placeholder it doesn't know, a $ that starts none, a Turn template that places the Legal-move list
    when the constraints don't show it, or doesn't when they do, or one that doesn't add what the Turn memory says a
    turn adds: under chat_moves the opponent's last move ($opponent_played) and never the position, which the LLM
    keeps track of itself, and under the others never the opponent's move alone."""
    for part, text, known in (
        ("System prompt", template.system_prompt, SYSTEM_PLACEHOLDERS),
        ("Turn template", template.turn_template, TURN_PLACEHOLDERS),
    ):
        parsed = Template(text)
        if not parsed.is_valid():
            reason = f"the {part} has a $ that starts no placeholder; write $$ for a dollar sign"
            raise InvalidSettings(reason, code="invalid_prompt_template")
        unknown = [name for name in dict.fromkeys(parsed.get_identifiers()) if name not in known]
        if unknown:
            placeholders = "unknown placeholders" if len(unknown) > 1 else "an unknown placeholder"
            names = ", ".join(f"${name}" for name in unknown)
            raise InvalidSettings(f"the {part} has {placeholders}: {names}", code="invalid_prompt_template")
    places_list = "legal_moves" in Template(template.turn_template).get_identifiers()
    if llm_constraints in LISTED and not places_list:
        reason = f"the Turn template must place $legal_moves: {llm_constraints} shows the Legal-move list"
        raise InvalidSettings(reason, code="invalid_prompt_template")
    if llm_constraints not in LISTED and places_list:
        reason = (
            "the Turn template places $legal_moves, but only Listed and Listed enforced show the Legal-move list, "
            f"not {llm_constraints}"
        )
        raise InvalidSettings(reason, code="invalid_prompt_template")
    placed = Template(template.turn_template).get_identifiers()
    if turn_memory != "chat_moves":
        if "opponent_played" in placed:
            reason = f"the Turn template places $opponent_played, which only chat_moves gives, not {turn_memory}"
            raise InvalidSettings(reason, code="invalid_prompt_template")
        return
    if "opponent_played" not in placed:
        reason = "the Turn template must place $opponent_played: under chat_moves each turn adds the opponent's move"
        raise InvalidSettings(reason, code="invalid_prompt_template")
    if shown := [f"${name}" for name in dict.fromkeys(placed) if name in POSITION_PLACEHOLDERS]:
        reason = (
            f"the Turn template places {', '.join(shown)}, but under chat_moves a turn adds only the opponent's last "
            "move: the LLM keeps track of the board itself"
        )
        raise InvalidSettings(reason, code="invalid_prompt_template")


def system_prompt(llm_color: Color, system_prompt_file: Path = SYSTEM_PROMPT_FILE) -> str:
    """The System prompt in a file, filled in for the LLM playing llm_color."""
    return fill_system_prompt(system_prompt_file.read_text(encoding="utf-8"), llm_color)


def fill_system_prompt(text: str, llm_color: Color) -> str:
    """A System prompt filled in for the LLM playing llm_color ("white" or "black"): $color and $opponent are the two
    colours, and $example_pgn, $example_fen, $example_legal_moves and $example_move make up a worked example of a
    first move for that colour. The Moves templates' example gives that turn's message as chat_moves does
    ($example_message), then the next turn's, its Legal-move list and its move ($example_next_...)."""
    board = chess.Board()
    for san in EXAMPLE_MOVES[llm_color]:
        board.push_san(san)
    next_board = board.copy()
    next_board.push_san(EXAMPLE_ANSWERS[llm_color])
    next_board.push_san(EXAMPLE_NEXT_MOVES[llm_color])
    return Template(text).substitute(
        color=llm_color.capitalize(),
        opponent=opponent(llm_color).capitalize(),
        example_pgn=chess.Board().variation_san(board.move_stack) or NO_MOVES_YET,
        example_fen=board.fen(),
        example_legal_moves=shuffled_legal_moves(board),
        example_move=EXAMPLE_ANSWERS[llm_color],
        example_message=opponent_played(EXAMPLE_MOVES[llm_color], llm_color),
        example_next_message=opponent_played([EXAMPLE_NEXT_MOVES[llm_color]], llm_color),
        example_next_legal_moves=shuffled_legal_moves(next_board),
        example_next_move=EXAMPLE_NEXT_ANSWERS[llm_color],
    )


def shuffled_legal_moves(board: chess.Board) -> str:
    """The legal moves of an example position in SAN, in a random order: the prompt says the order is random, and a
    fixed seed keeps it stable."""
    legal_moves = [board.san(move) for move in board.legal_moves]
    random.Random(0).shuffle(legal_moves)
    return " ".join(legal_moves)


def opponent_played(moves: Sequence[str], llm_color: Color) -> str:
    """What a turn under chat_moves adds: the opponent's last move of the plies so far, e.g. "Opponent played Nf6.",
    or at White's first turn, before any move, that it plays White and moves first."""
    if not moves:
        return f"You play {llm_color.capitalize()}. Make the first move."
    return f"Opponent played {moves[-1]}."


def move_record(moves: Sequence[str], first_ply: int = 1) -> str:
    """Plies as PGN movetext, each as written, e.g. "1. e4 e5". first_ply is the number of the first (1 for White's
    first move), so plies from the middle of a game keep their move numbers, e.g. "3... Nc6 4. Bb5"."""
    numbered = []
    for ply, written in enumerate(moves, start=first_ply):
        number = (ply + 1) // 2
        if ply % 2 == 1:
            numbered.append(f"{number}. {written}")
        else:
            numbered.append(f"{number}... {written}" if ply == first_ply else written)
    return " ".join(numbered)


@dataclass(frozen=True)
class TurnPosition:
    """What a Turn template is filled in with: the position to move in, every ply that led to it as written in the
    Move record, and the Legal-move list (space-separated SAN) as shown, under Listed only."""

    board: chess.Board
    moves: Sequence[str]
    legal_moves: str | None = None


def turn_message(template: PromptTemplate, position: TurnPosition) -> str:
    """A turn's message: the side's Turn template filled in for the position. The template has been checked
    (check_prompt_template), so it places the Legal-move list exactly when the position has one."""
    moves, board = position.moves, position.board
    last_move = moves[-1] if moves else None
    recent_from = max(len(moves) - RECENT_PLIES, 0)
    values: dict[str, Callable[[], str | None]] = {
        "moves": lambda: move_record(moves) or NO_MOVES_YET,
        "recent_moves": lambda: move_record(moves[recent_from:], recent_from + 1) or NO_MOVES_YET,
        "fen": board.fen,
        "description": lambda: describe_position(board, last_move),
        "last_move": lambda: last_move or NO_MOVES_YET,
        "legal_moves": lambda: position.legal_moves,
        "opponent_played": lambda: opponent_played(moves, "white" if board.turn == chess.WHITE else "black"),
    }
    parsed = Template(template.turn_template)
    # Only the placeholders the template places are worked out.
    return parsed.substitute({name: values[name]() for name in parsed.get_identifiers()})


def fresh_prompt(template: PromptTemplate, llm_color: Color, position: TurnPosition) -> list[Message]:
    """A fresh Prompt for one turn, with no earlier turns: the System prompt, then the turn's message."""
    return [
        Message("system", fill_system_prompt(template.system_prompt, llm_color)),
        Message("user", turn_message(template, position)),
    ]


def record_moves(pgn: str) -> list[str]:
    """The plies of a Move record as written, e.g. ["e4", "e5"] for "1. e4 e5": move_record undone, for positions
    taken from game logs."""
    return [token for token in pgn.split() if not re.fullmatch(r"\d+\.(\.\.)?", token)]


def turn_messages(
    pgn: str, fen: str, llm_color: Color, llm_constraints: LlmConstraints = "free", legal_moves: str | None = None
) -> list[Message]:
    """A fresh Prompt with the Default template for a position given by its Move record and FEN, with the Legal-move
    list under Listed: for the research scripts, which take their positions from game logs."""
    position = TurnPosition(chess.Board(fen), record_moves(pgn), legal_moves)
    return fresh_prompt(default_template(llm_constraints), llm_color, position)


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
