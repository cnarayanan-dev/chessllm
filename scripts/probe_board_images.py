"""Offline probe: does showing a board image help small local vision LLMs propose legal moves?

Positions are sampled from the first attempts of LLM Turns in the game logs (Free, Standard rules sides), spread over
the opening, middlegame and endgame, with some where the side to move is in check. Each position is put to each model,
once per condition, with thinking off and the sampling from chessllm/llm/sampling.toml, as one first attempt (no Retry):

    text        the Turn's prompt exactly as the game builds it (chessllm.game.prompt.turn_messages: PGN + FEN)
    text+image  the same prompt, plus one line saying what the image is, with the board image on the user message
    image       the board image and a short instruction only: no PGN, no FEN

The answer is judged with the game's own chessllm.game.session.judge; a legal move not in exact SAN is a Notation slip, and an
illegal one is given an error kind (own piece on the target square, no such piece, king left in check, unreachable).

A perception check on the first --perception positions asks each model to list where the side to move's pieces are,
once from the image and once from the FEN, and scores the list against the real board.

Results go to a JSONL file, one line per call; a rerun skips calls already in it, so the probe can be resumed.

Run:
    uv run python -m scripts.probe_board_images --models gemma3:12b qwen3.5:9b --positions 60 --perception 20
    uv run python -m scripts.probe_board_images --models qwen3.8:latest --limit 15 --perception 0 --keep-alive 1m
    uv run python -m scripts.probe_board_images --summary
Not wired into the game."""

import argparse
import json
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from itertools import zip_longest
from pathlib import Path
from typing import Any, Literal

import chess
import chess.svg
import ollama
import resvg_py

from chessllm.game.chaos import CASTLE_RE
from chessllm.game.session import judge
from chessllm.logs.game_log import GAMES_DIR
from chessllm.llm.models import load_sampling
from chessllm.llm.ollama_player import OllamaPlayer
from chessllm.llm.players import Message
from chessllm.exceptions import LlmTimeout
from chessllm.game.prompt import turn_messages
from chessllm.cli.report import OPENING_PLIES, load_games

Condition = Literal["text", "text+image", "image"]
CONDITIONS: tuple[Condition, ...] = ("text", "text+image", "image")
PerceptionSource = Literal["image", "fen"]
# Stages of the game by ply, for spreading the sample. The logged games hardly ever trade down: no logged position is
# an endgame by chessllm/cli/report.py's material rule, so "late" (past ply 50) stands in for it.
PHASES = ("opening", "middlegame", "late")
RESULTS_FILE = Path(__file__).parent.parent / "docs" / "research" / "board-images-results.jsonl"
POSITIONS_FILE = RESULTS_FILE.with_name("board-images-positions.json")
IMAGE_SIZE = 512
TIMEOUT_S = 180.0

IMAGE_SYSTEM = """You are playing chess as {color} against a human playing {opponent}.
Each turn you get an image of the current board, seen from your side, with the files and ranks labelled.
Reply with your next move in SAN (e.g. Nf6, exd5, O-O, e8=Q).
The move must be legal in the current position."""
PERCEPTION_SCHEMA = {
    "type": "object",
    "properties": {"pieces": {"type": "array", "items": {"type": "string"}}},
    "required": ["pieces"],
}
PIECE_RE = re.compile(r"^([KQRBNP])?([a-h][1-8])$")


@dataclass(frozen=True)
class Position:
    fen: str
    pgn: str
    color: Literal["white", "black"]  # the side to move, the LLM's
    ply: int
    phase: str  # opening, middlegame or late (see stage)
    in_check: bool
    game: str  # the log file it came from


LATE_PLY = 50


def stage(ply: int) -> str:
    return "opening" if ply <= OPENING_PLIES else "middlegame" if ply <= LATE_PLY else "late"


def read_positions(games_dir: Path) -> list[Position]:
    """The position of every first attempt by a Free LLM side in a Standard rules game, each FEN once."""
    games, _ = load_games(games_dir)
    positions: dict[str, Position] = {}
    for game in games:
        if game.rules != "standard":
            continue
        for event in game.events:
            if event.get("type") != "llm_attempt" or int(event.get("attempt", 1)) != 1:
                continue
            color, fen, pgn = event.get("color"), event.get("fen"), event.get("pgn")
            if color not in ("white", "black") or not isinstance(fen, str) or not isinstance(pgn, str):
                continue
            if game.sides.get(color, {}).get("llm_constraints") != "free" or fen in positions:
                continue
            board = chess.Board(fen)
            if board.is_game_over():
                continue
            ply = int(event["ply"])
            positions[fen] = Position(fen, pgn, color, ply, stage(ply), board.is_check(), game.path.name)
    return list(positions.values())


def sample_positions(positions: Sequence[Position], count: int, in_check: int, seed: int = 0) -> list[Position]:
    """count positions: up to in_check where the side to move is in check, the rest spread evenly over the phases
    (topped up from the others when one runs short). Interleaved, so any prefix is spread too."""
    rng = random.Random(seed)
    checks = [p for p in positions if p.in_check]
    chosen_checks = rng.sample(checks, min(in_check, len(checks), count))
    rest = [p for p in positions if not p.in_check]
    by_phase = {name: [p for p in rest if p.phase == name] for name in PHASES}
    for pool in by_phase.values():
        rng.shuffle(pool)
    wanted = count - len(chosen_checks)
    picked: dict[str, list[Position]] = {name: [] for name in PHASES}
    while wanted > 0 and any(by_phase.values()):
        for name in PHASES:
            if wanted > 0 and by_phase[name]:
                picked[name].append(by_phase[name].pop())
                wanted -= 1
    groups = [chosen_checks, *picked.values()]
    return [p for row in zip_longest(*groups) for p in row if p is not None]


def render_png(fen: str, color: str, size: int = IMAGE_SIZE) -> bytes:
    """The board as a PNG, size × size, seen from color's side, with the files and ranks labelled."""
    board = chess.Board(fen)
    orientation = chess.WHITE if color == "white" else chess.BLACK
    svg = chess.svg.board(board, orientation=orientation, size=size, coordinates=True)
    return resvg_py.svg_to_bytes(svg_string=svg)


def png_size(png: bytes) -> tuple[int, int]:
    """Width and height from the PNG header."""
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def image_line(color: str) -> str:
    return f"Board image: the current position, seen from your side ({color.capitalize()} at the bottom)."


def move_messages(position: Position, condition: Condition) -> list[Message]:
    """The messages for one first attempt under the condition. The image itself goes on the last (user) message."""
    if condition == "text":
        return turn_messages(position.pgn, position.fen, position.color)
    if condition == "text+image":
        system, user = turn_messages(position.pgn, position.fen, position.color)
        return [system, Message("user", f"{user.content}\n{image_line(position.color)}")]
    opponent = "black" if position.color == "white" else "white"
    system_text = IMAGE_SYSTEM.format(color=position.color.capitalize(), opponent=opponent.capitalize())
    user_text = f"{image_line(position.color)}\n{position.color.capitalize()} to move."
    return [Message("system", system_text), Message("user", user_text)]


def perception_messages(position: Position, source: PerceptionSource) -> list[Message]:
    color = position.color.capitalize()
    ask = (
        f"List every {position.color} piece and the square it stands on, as the piece letter and the square "
        f"(K, Q, R, B, N, and P for pawns), e.g. Ke1, Pe2."
    )
    if source == "image":
        shown = f"The image shows a chess position, seen from {color}'s side ({color} at the bottom)."
    else:
        shown = f"FEN: {position.fen}"
    return [Message("user", f"{shown}\n{ask}")]


def with_image(
    chat: Callable[..., ollama.ChatResponse], image: bytes | None, keep_alive: str | None = None
) -> Callable[..., ollama.ChatResponse]:
    """A chat function for OllamaPlayer that attaches the image to the last message, so the request is otherwise
    exactly what the game sends."""

    def call(**request: Any) -> ollama.ChatResponse:
        messages = list(request["messages"])
        if image is not None:
            messages[-1] = messages[-1] | {"images": [image]}
        extra = {"keep_alive": keep_alive} if keep_alive is not None else {}
        return chat(**(request | {"messages": messages} | extra))

    return call


def classify_illegal(board: chess.Board, written: str) -> str:
    """Why a move judged illegal can't be played: castling, own_piece_on_target, no_such_piece (no piece of that
    type, or the named from-square doesn't hold it), king_in_check (it would leave or keep its king in check) or
    unreachable (the piece exists but can't move there). "other" if the text can't be read as a move."""
    if CASTLE_RE.match(written):
        return "castling"
    san = chess.SAN_REGEX.match(written)
    if not san:
        return "other"
    letter, file, rank, target_name, _ = san.groups()
    target = chess.parse_square(target_name)
    on_target = board.piece_at(target)
    if on_target is not None and on_target.color == board.turn:
        return "own_piece_on_target"
    piece_type = chess.Piece.from_symbol(letter).piece_type if letter else chess.PAWN
    if file and rank:  # long form or UCI: the from-square must hold the mover's piece of that type
        start = chess.square("abcdefgh".index(file), int(rank) - 1)
        own = board.piece_at(start)
        if own is None or own.color != board.turn or (letter and own.piece_type != piece_type):
            return "no_such_piece"
        candidates = [start]
    else:
        candidates = [
            square
            for square in board.pieces(piece_type, board.turn)
            if (file is None or chess.square_file(square) == "abcdefgh".index(file))
            and (rank is None or chess.square_rank(square) == int(rank) - 1)
        ]
        if not candidates:
            return "no_such_piece"
    if any(m.from_square in candidates and m.to_square == target for m in board.pseudo_legal_moves):
        return "king_in_check"
    return "unreachable"


def own_pieces(board: chess.Board, color: chess.Color) -> set[str]:
    return {f"{piece.symbol().upper()}{chess.square_name(square)}" for square, piece in board.piece_map().items()
            if piece.color == color}


def score_pieces(board: chess.Board, listed: Sequence[str]) -> dict[str, Any]:
    """Precision and recall of the listed pieces (e.g. "Ke1", "Pe2", "e2") against the side to move's pieces."""
    truth = own_pieces(board, board.turn)
    predicted = set()
    for entry in listed:
        text = re.sub(r"[\s\-:]", "", str(entry))
        text = f"P{text}" if re.fullmatch(r"[a-h][1-8]", text) else text[:1].upper() + text[1:]
        match = PIECE_RE.match(text)
        if match:
            predicted.add(f"{match.group(1) or 'P'}{match.group(2)}")
        else:
            predicted.add(f"?{text}")
    hits = len(predicted & truth)
    return {
        "precision": hits / len(predicted) if predicted else 0.0,
        "recall": hits / len(truth),
        "exact": predicted == truth,
        "phantoms": sorted(predicted - truth),
        "missed": sorted(truth - predicted),
    }


def ask_move(
    chat: Callable[..., ollama.ChatResponse], model: str, position: Position, condition: Condition,
    sampling: dict[str, float], keep_alive: str | None = None,
) -> dict[str, Any]:
    """One first attempt, judged as the game judges it."""
    image = render_png(position.fen, position.color) if condition != "text" else None
    player = OllamaPlayer(model, thinking=False, chat=with_image(chat, image, keep_alive), sampling=sampling)
    record: dict[str, Any] = {"kind": "move", "model": model, "condition": condition, **asdict(position)}
    try:
        reply = player.reply(move_messages(position, condition))
    except LlmTimeout as timeout:
        return record | {"result": "timeout", "error": str(timeout)}
    except Exception as error:  # a failed call is recorded, not fatal to the probe
        return record | {"result": "error", "error": str(error)}
    board = chess.Board(position.fen)
    written, move, result = judge(board, reply.raw)
    san = board.san(move) if move is not None else None
    return record | {
        "raw": reply.raw, "move": written, "result": result, "san": san,
        "notation_slip": san is not None and written != san,
        "error_kind": None if move is not None else (classify_illegal(board, written) if result == "illegal" else result),
        "latency_s": reply.latency_s,
    }


def ask_perception(
    client: ollama.Client, model: str, position: Position, source: PerceptionSource, sampling: dict[str, float],
    keep_alive: str | None = None,
) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in perception_messages(position, source)]
    if source == "image":
        messages[-1]["images"] = [render_png(position.fen, position.color)]
    record: dict[str, Any] = {"kind": "perception", "model": model, "condition": source, **asdict(position)}
    try:
        response = client.chat(
            model=model, messages=messages, think=False, format=PERCEPTION_SCHEMA, options=sampling or None,
            keep_alive=keep_alive,
        )
        listed = json.loads(response.message.content or "{}").get("pieces", [])
    except Exception as error:
        return record | {"error": str(error)}
    return record | {"listed": listed, **score_pieces(chess.Board(position.fen), listed)}


def frozen_sample(args: argparse.Namespace) -> list[Position]:
    """The sample, drawn once and kept in the positions file: the logs grow while games run, so a fresh draw later
    would not be the same positions."""
    if args.positions_file.exists():
        return [Position(**row) for row in json.loads(args.positions_file.read_text(encoding="utf-8"))]
    positions = sample_positions(read_positions(args.games_dir), args.positions, args.in_check, args.seed)
    args.positions_file.parent.mkdir(parents=True, exist_ok=True)
    args.positions_file.write_text(json.dumps([asdict(p) for p in positions], indent=1) + "\n", encoding="utf-8")
    return positions


def done_keys(path: Path) -> set[tuple[str, str, str, str]]:
    if not path.exists():
        return set()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["kind"], r["model"], r["condition"], r["fen"]) for r in rows if r.get("result") not in ("timeout", "error")}


def run(args: argparse.Namespace) -> None:
    positions = frozen_sample(args)
    positions = positions[: args.limit] if args.limit else positions
    sampling = load_sampling()
    client = ollama.Client(timeout=args.timeout)
    done = done_keys(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    phases = Counter(p.phase for p in positions)
    print(f"{len(positions)} positions: {dict(phases)}, {sum(p.in_check for p in positions)} in check", file=sys.stderr)
    with args.out.open("a", encoding="utf-8") as out:
        for model in args.models:
            for index, position in enumerate(positions):
                jobs: list[tuple[str, str]] = [("move", c) for c in args.conditions]
                if index < args.perception:
                    jobs += [("perception", "image"), ("perception", "fen")]
                for kind, condition in jobs:
                    if (kind, model, condition, position.fen) in done:
                        continue
                    if kind == "move":
                        row = ask_move(client.chat, model, position, condition, sampling, args.keep_alive)  # type: ignore[arg-type]
                        shown = f"{row.get('result')} {row.get('move')} {row.get('error_kind') or ''}"
                    else:
                        row = ask_perception(client, model, position, condition, sampling, args.keep_alive)  # type: ignore[arg-type]
                        shown = f"recall {row.get('recall', 0):.2f} precision {row.get('precision', 0):.2f}"
                    out.write(json.dumps(row) + "\n")
                    out.flush()
                    print(f"{model} #{index + 1} {kind}/{condition}: {shown}", file=sys.stderr)


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def summary(path: Path) -> str:
    every = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    # A rerun asks again after a timeout or error; the latest row for each call counts.
    rows = list({(r["kind"], r["model"], r["condition"], r["fen"]): r for r in every}.values())
    moves = defaultdict(list)
    for row in rows:
        if row["kind"] == "move":
            moves[(row["model"], row["condition"])].append(row)
    lines = [
        "| Model | Condition | n | Legal first attempt | Own piece on target | No such piece | Unreachable | "
        "King in check | Invalid/other | Notation slips | Latency median / mean (s) | No answer |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (model, condition), group in sorted(moves.items()):
        answered = [r for r in group if r["result"] not in ("timeout", "error")]
        n = len(answered)
        kinds = Counter(r["error_kind"] for r in answered if r["result"] != "legal")
        legal = sum(r["result"] == "legal" for r in answered)
        slips = sum(bool(r.get("notation_slip")) for r in answered)
        latencies = [r["latency_s"] for r in answered]
        latency = f"{statistics.median(latencies):.1f} / {statistics.mean(latencies):.1f}" if latencies else "-"
        other = kinds["invalid"] + kinds["ambiguous"] + kinds["other"] + kinds["castling"]
        lines.append(
            f"| {model} | {condition} | {n} | {legal} ({percent(legal, n)}) | {kinds['own_piece_on_target']} | "
            f"{kinds['no_such_piece']} | {kinds['unreachable']} | {kinds['king_in_check']} | {other} | {slips} | "
            f"{latency} | {len(group) - n} |"
        )
    lines += ["", "Legal first attempt by phase and check:", "",
              "| Model | Condition | opening | middlegame | late | in check |", "|---|---|---|---|---|---|"]
    for (model, condition), group in sorted(moves.items()):
        answered = [r for r in group if r["result"] not in ("timeout", "error")]
        cells = []
        for test in [lambda r, p=p: r["phase"] == p and not r["in_check"] for p in PHASES] + [lambda r: r["in_check"]]:
            part = [r for r in answered if test(r)]
            legal = sum(r["result"] == "legal" for r in part)
            cells.append(f"{legal}/{len(part)}")
        lines.append(f"| {model} | {condition} | " + " | ".join(cells) + " |")
    lines += ["", "Paired against text (same positions): image condition legal where text was not / the reverse:", ""]
    for model in sorted({m for m, _ in moves}):
        text = {r["fen"]: r["result"] == "legal" for r in moves.get((model, "text"), []) if "raw" in r}
        for condition in ("text+image", "image"):
            shown = {r["fen"]: r["result"] == "legal" for r in moves.get((model, condition), []) if "raw" in r}
            both = text.keys() & shown.keys()
            gained = sum(shown[f] and not text[f] for f in both)
            lost = sum(text[f] and not shown[f] for f in both)
            lines.append(f"- {model} {condition}: +{gained} / -{lost} of {len(both)}")
    perceptions = defaultdict(list)
    for row in rows:
        if row["kind"] == "perception" and "recall" in row:
            perceptions[(row["model"], row["condition"])].append(row)
    if perceptions:
        lines += ["", "| Model | Pieces read from | n | Recall | Precision | Exact | Phantoms per position |",
                  "|---|---|---|---|---|---|---|"]
        for (model, source), group in sorted(perceptions.items()):
            n = len(group)
            lines.append(
                f"| {model} | {source} | {n} | {statistics.mean(r['recall'] for r in group):.0%} | "
                f"{statistics.mean(r['precision'] for r in group):.0%} | {percent(sum(r['exact'] for r in group), n)} | "
                f"{statistics.mean(len(r['phantoms']) for r in group):.1f} |"
            )
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=[])
    p.add_argument("--conditions", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    p.add_argument("--positions", type=int, default=60, help="positions to sample")
    p.add_argument("--in-check", type=int, default=8, help="how many of them have the side to move in check")
    p.add_argument("--limit", type=int, default=0, help="only the first N sampled positions (still spread)")
    p.add_argument("--perception", type=int, default=20, help="perception check on the first N positions")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--timeout", type=float, default=TIMEOUT_S, help="seconds before a call counts as no answer")
    p.add_argument("--keep-alive", default=None, help="Ollama keep_alive for these calls, e.g. 1m")
    p.add_argument("--games-dir", type=Path, default=GAMES_DIR)
    p.add_argument("--out", type=Path, default=RESULTS_FILE)
    p.add_argument("--positions-file", type=Path, default=POSITIONS_FILE, help="the frozen sample, made if missing")
    p.add_argument("--images-dir", type=Path, default=None, help="also save the sampled boards as PNGs here")
    p.add_argument("--summary", action="store_true", help="only print the tables from --out")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.images_dir:
        args.images_dir.mkdir(parents=True, exist_ok=True)
        positions = frozen_sample(args)
        for index, position in enumerate(positions, start=1):
            name = f"{index:02d}-{position.phase}{'-check' if position.in_check else ''}.png"
            (args.images_dir / name).write_bytes(render_png(position.fen, position.color))
    if args.models:
        run(args)
    if args.summary or args.models:
        print(summary(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
