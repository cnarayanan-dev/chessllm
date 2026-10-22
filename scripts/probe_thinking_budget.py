"""Offline probe: which Thinking level and Thinking budget work best per model, from the 60 fixed positions.

The positions are the board-image study's frozen sample (docs/research/board-images-positions.json). Each is put to
each model once per condition and pass, as one first attempt (no Retry), by the game's own OllamaPlayer with the
sampling from chessllm/llm/sampling.toml, the Thinking budget's forced answer included (ADR 0007):

    conditions  thinking off, unbounded (thinking on, no budget), and budgets of 512, 1,024, 2,048 and 4,096 tokens;
                qwen3.8 at its medium level for "on", and also at xhigh with 2,048 and 4,096 (see grid)
    free             the Free prompt, no legal-move list: first-attempt legality
    listed_enforced  the Listed prompt and the legal moves as an enum: every answer is legal, scored by its
                     Stockfish centipawn loss as the game's analysis scores a played move

The answer is judged with the game's chessllm.game.session.judge. Each call's time limit is the game's for its budget.

Results go to a JSONL file, one line per call; a rerun skips calls already in it (a timeout included, an error not),
so the probe can be stopped and resumed, and run in chunks by model, condition and number of positions.

Run, one model at a time on an otherwise idle machine:
    uv run python -m scripts.probe_thinking_budget --models gemma4:26b --keep-alive 5m
    uv run python -m scripts.probe_thinking_budget --models qwen3.8:latest --conditions off medium --limit 20
    uv run python -m scripts.probe_thinking_budget --summary --write-note
Only recommends: not wired into the game, and no default changes."""

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self

import chess
import chess.engine
import ollama

from chessllm.analytics.analysis import mover_evaluations
from chessllm.engines.evaluator import Evaluator
from chessllm.game.session import CUT_OFF, BenchmarkLlmSide, HumanSide, Settings, judge
from chessllm.llm.models import LLM_MODELS, load_sampling
from chessllm.llm.ollama_player import OllamaPlayer, time_limit_s
from chessllm.exceptions import InvalidSettings, LlmTimeout
from chessllm.game.prompt import SYSTEM_PROMPT_FILES, LlmConstraints, turn_messages
from chessllm.engines.stockfish_evaluator import StockfishEvaluator
from scripts.probe_board_images import POSITIONS_FILE, Position

# Free for first-attempt legality; Listed enforced for move quality, since every answer is then a legal move.
Pass = Literal["free", "listed_enforced"]
PASSES: tuple[Pass, ...] = ("free", "listed_enforced")
RESULTS_FILE = Path(__file__).parent.parent / "docs" / "research" / "thinking-budget-results.jsonl"
NOTE_FILE = RESULTS_FILE.with_name("thinking-budget.md")
# --write-note puts the summary table between these two lines of the note.
NOTE_START = "<!-- budget-probe:start -->"
NOTE_END = "<!-- budget-probe:end -->"
# A move losing this much or more is a blunder, as the note's experiment plan counts it.
BLUNDER_CP = 200
BUDGETS = (512, 1024, 2048, 4096)
# qwen3.8's thinking on is sent as the level it means, medium, so the probe doesn't depend on Ollama's default.
ON_LEVELS = {"qwen3.8:latest": "medium"}
# xhigh only at the two largest budgets: unbounded it would run past the 300 s limit and the 8,192-token context
# (qwen3.8 spent ~12,800 tokens a move at xhigh in LLM Chess), and the small budgets would cut it as they cut
# medium, so they can't show what the level changes.
EXTRA_CONDITIONS = {"qwen3.8:latest": ("xhigh@2048", "xhigh@4096")}


@dataclass(frozen=True)
class Condition:
    """Thinking off, or on (at a Thinking level when given), with a Thinking budget or unbounded. Its label is
    "off", "on", "medium" or "xhigh", with "@" and the budget when there is one, e.g. "on@1024"."""

    thinking: bool
    level: str | None
    budget: int | None

    @classmethod
    def parse(cls, label: str) -> Self:
        name, _, budget = label.partition("@")
        if name == "off":
            return cls(False, None, int(budget) if budget else None)
        return cls(True, None if name == "on" else name, int(budget) if budget else None)

    @property
    def label(self) -> str:
        name = "off" if not self.thinking else self.level or "on"
        return name if self.budget is None else f"{name}@{self.budget}"

    @property
    def think(self) -> bool | str:
        """The thinking sent to Ollama, as a game's side sends it."""
        return self.level if self.level is not None else self.thinking

    def side(self, model: str, llm_constraints: LlmConstraints = "free") -> BenchmarkLlmSide:
        return BenchmarkLlmSide(
            model=model, thinking=self.thinking, llm_constraints=llm_constraints, thinking_level=self.level,
            thinking_budget=self.budget,
        )


def grid(model: str) -> list[Condition]:
    """The conditions a model is probed under: thinking off, unbounded, and each budget, plus any extra ones."""
    on = ON_LEVELS.get(model, "on")
    labels = ["off", on, *(f"{on}@{budget}" for budget in BUDGETS), *EXTRA_CONDITIONS.get(model, ())]
    return [Condition.parse(label) for label in labels]


def condition_problem(model: str, condition: Condition) -> str | None:
    """Why the model can't be played under the condition, as the game's settings check says it, or None."""
    try:
        Settings(white=HumanSide(), black=condition.side(model)).check(LLM_MODELS)
    except InvalidSettings as problem:
        return str(problem).replace(f"{model} (black)", model)  # no colour in a probe
    return None


def listed_moves(fen: str) -> list[str]:
    """The legal moves in SAN in a random order, as Listed shows them, but seeded by the position, so every
    condition is shown the same list and the conditions stay paired."""
    board = chess.Board(fen)
    moves = [board.san(move) for move in board.legal_moves]
    random.Random(fen).shuffle(moves)
    return moves


def speed(model: str) -> float | None:
    return next((m.tokens_per_s for m in LLM_MODELS if m.name == model), None)


def ask(
    chat: Callable[..., ollama.ChatResponse], model: str, index: int, position: Position, condition: Condition,
    pass_: Pass, evaluator: Evaluator, sampling: dict[str, float],
) -> dict[str, Any]:
    """One first attempt, made by the game's player, judged as the game judges it; under Listed enforced its move
    is scored by its centipawn loss, as the game's analysis scores a played move."""
    limit = time_limit_s(condition.budget, speed(model))
    player = OllamaPlayer(model, condition.think, chat=chat, timeout_s=limit, sampling=sampling,
                          budget=condition.budget)
    shown = listed_moves(position.fen) if pass_ == "listed_enforced" else None
    messages = turn_messages(position.pgn, position.fen, position.color, SYSTEM_PROMPT_FILES[pass_],
                             " ".join(shown) if shown is not None else None)
    record: dict[str, Any] = {
        "model": model, "condition": condition.label, "level": condition.think, "budget": condition.budget,
        "pass": pass_, "position": index, "fen": position.fen, "phase": position.phase, "in_check": position.in_check,
        "raw": None, "move": None, "result": None, "centipawn_loss": None, "evaluation_before": None,
        "evaluation_after": None, "thinking_tokens": None, "answer_tokens": None, "prompt_tokens": None,
        "stop_reason": None, "forced": False, "latency_s": None, "time_limit_s": limit,
    }
    try:
        reply = player.reply(messages, shown)
    except LlmTimeout:
        return record | {"result": "timeout"}
    except Exception as error:  # a failed call is recorded, not fatal to the probe, and asked again on a rerun
        return record | {"result": "error", "error": str(error)}
    board = chess.Board(position.fen)
    written, move, result = judge(board, reply.raw)
    if result == "invalid" and reply.forced and reply.stop_reason == "length":
        result = CUT_OFF  # the forced answer ran out of tokens too, as the game counts it
    record |= {
        "raw": reply.raw, "move": written, "result": result, "thinking_tokens": reply.thinking_tokens,
        "answer_tokens": reply.answer_tokens, "prompt_tokens": reply.prompt_tokens, "stop_reason": reply.stop_reason,
        "forced": reply.forced, "latency_s": reply.latency_s,
    }
    if move is not None and pass_ == "listed_enforced":
        evaluations = mover_evaluations(position.fen, move.uci(), evaluator)
        if evaluations is not None:
            before, after = evaluations
            record |= {"centipawn_loss": max(0, before - after), "evaluation_before": before, "evaluation_after": after}
    return record


Key = tuple[str, str, str, str]  # model, condition label, pass, FEN


def done_keys(path: Path) -> set[Key]:
    """The calls already in the results file. A timeout is the condition's outcome, so it stays done; an error
    (e.g. Ollama not running) is asked again."""
    if not path.exists():
        return set()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {(r["model"], r["condition"], r["pass"], r["fen"]) for r in rows if r["result"] != "error"}


def pending(
    models: Sequence[str], conditions: Sequence[Condition] | None, positions: Sequence[Position],
    passes: Sequence[Pass], done: set[Key],
) -> Iterator[tuple[str, int, Position, Condition, Pass]]:
    """The calls still to make, model by model, then position by position, so a run stopped anywhere leaves every
    condition on the same positions. conditions None is each model's grid."""
    for model in models:
        for index, position in enumerate(positions):
            for condition in conditions if conditions is not None else grid(model):
                for pass_ in passes:
                    if (model, condition.label, pass_, position.fen) not in done:
                        yield model, index, position, condition, pass_


def percentile(values: Sequence[float], share: float) -> float:
    """The nearest-rank percentile, e.g. share 0.9 for p90."""
    ranked = sorted(values)
    return ranked[max(0, math.ceil(share * len(ranked)) - 1)]


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def summary(every: Sequence[dict[str, Any]]) -> str:
    """The table per model and condition. Legality counts every Free call that ended, so a timeout or cut-off
    answer is no legal move; centipawn loss is over Listed enforced moves; tokens, forced share and time are over
    both passes, a timeout counting at its time limit. An error (no call made) counts nowhere."""
    # A rerun asks again after an error; the latest row for each call counts.
    latest = {(r["model"], r["condition"], r["pass"], r["fen"]): r for r in every}.values()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in latest:
        if row["result"] != "error":
            groups[(row["model"], row["condition"])].append(row)

    def order(key: tuple[str, str]) -> tuple[str, int, str]:
        labels = [c.label for c in grid(key[0])]
        return key[0], labels.index(key[1]) if key[1] in labels else len(labels), key[1]

    lines = [
        "| Model | Condition | Free: legal first attempt | Listed enforced: mean centipawn loss (moves) | "
        f"Blunders (≥{BLUNDER_CP} cp) | Thinking tokens median / p90 | Forced | Median time (s) | Timeouts and cut-offs |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for key in sorted(groups, key=order):
        group = groups[key]
        free = [r for r in group if r["pass"] == "free"]
        legal = sum(r["result"] == "legal" for r in free)
        losses = [r["centipawn_loss"] for r in group if r["pass"] == "listed_enforced" and r["centipawn_loss"] is not None]
        quality = f"{statistics.mean(losses):.0f} ({len(losses)})" if losses else "-"
        tokens = [r["thinking_tokens"] for r in group if r["thinking_tokens"] is not None]
        spent = f"{statistics.median(tokens):.0f} / {percentile(tokens, 0.9):.0f}" if tokens else "-"
        answered = [r for r in group if r["result"] != "timeout"]
        times = [r["time_limit_s"] if r["result"] == "timeout" else r["latency_s"] for r in group]
        lines.append(
            f"| {key[0]} | {key[1]} | {legal}/{len(free)} ({percent(legal, len(free))}) | {quality} | "
            f"{sum(loss >= BLUNDER_CP for loss in losses)} | {spent} | "
            f"{percent(sum(bool(r['forced']) for r in answered), len(answered))} | {statistics.median(times):.1f} | "
            f"{sum(r['result'] in ('timeout', CUT_OFF) for r in group)} |"
        )
    return "\n".join(lines)


def into_note(note: str, table: str) -> str:
    """The note with the table between its probe markers, in place of what was there."""
    start, end = note.index(NOTE_START) + len(NOTE_START), note.index(NOTE_END)
    return f"{note[:start]}\n{table}\n{note[end:]}"


def load_positions(path: Path = POSITIONS_FILE) -> list[Position]:
    """The board-image study's frozen positions, in their order (interleaved, so any first N are spread too)."""
    return [Position(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


class CachedEvaluator:
    """The evaluator, asked once per position: every condition plays the same 60, and often the same moves."""

    def __init__(self, evaluator: Evaluator) -> None:
        self._evaluator = evaluator
        self._scores: dict[str, chess.engine.Score] = {}

    @property
    def version(self) -> str:
        return self._evaluator.version

    @property
    def search(self) -> dict[str, int]:
        return self._evaluator.search

    def evaluate(self, fen: str) -> chess.engine.Score:
        if fen not in self._scores:
            self._scores[fen] = self._evaluator.evaluate(fen)
        return self._scores[fen]


def with_keep_alive(chat: Callable[..., ollama.ChatResponse], keep_alive: str | None) -> Callable[..., ollama.ChatResponse]:
    """A chat function for OllamaPlayer that adds Ollama's keep_alive, so the request is otherwise the game's."""

    def call(**request: Any) -> ollama.ChatResponse:
        return chat(**(request | ({"keep_alive": keep_alive} if keep_alive is not None else {})))

    return call


def run(args: argparse.Namespace, evaluator: Evaluator) -> None:
    positions = load_positions(args.positions_file)
    positions = positions[: args.limit] if args.limit else positions
    conditions = [Condition.parse(label) for label in args.conditions] if args.conditions else None
    # Every model and condition is checked by the game's settings check before the first call.
    for model in args.models:
        for condition in conditions if conditions is not None else grid(model):
            problem = condition_problem(model, condition)
            if problem is not None:
                raise SystemExit(f"{condition.label}: {problem}")
    sampling = load_sampling()
    scored = CachedEvaluator(evaluator)
    clients: dict[float, ollama.Client] = {}
    done = done_keys(args.out)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a", encoding="utf-8") as out:
        for model, index, position, condition, pass_ in pending(args.models, conditions, positions, args.passes, done):
            limit = time_limit_s(condition.budget, speed(model))
            client = clients.setdefault(limit, ollama.Client(timeout=limit))
            chat = with_keep_alive(client.chat, args.keep_alive)
            row = ask(chat, model, index, position, condition, pass_, scored, sampling)
            out.write(json.dumps(row) + "\n")
            out.flush()
            shown = f"{row['result']} {row['move']} cp {row['centipawn_loss']} tokens {row['thinking_tokens']}"
            forced = " forced" if row["forced"] else ""
            print(f"{model} #{index + 1} {condition.label}/{pass_}: {shown}{forced} {row['latency_s'] or 0:.0f} s",
                  file=sys.stderr)


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--models", nargs="+", default=[])
    p.add_argument("--conditions", nargs="+", default=None,
                   help='labels such as off, on, on@1024, medium@3072, xhigh@4096; default each model\'s grid')
    p.add_argument("--passes", nargs="+", choices=PASSES, default=list(PASSES))
    p.add_argument("--limit", type=int, default=0, help="only the first N positions (still spread)")
    p.add_argument("--keep-alive", default=None, help="Ollama keep_alive for these calls, e.g. 5m")
    p.add_argument("--out", type=Path, default=RESULTS_FILE)
    p.add_argument("--positions-file", type=Path, default=POSITIONS_FILE)
    p.add_argument("--summary", action="store_true", help="only print the table from --out")
    p.add_argument("--write-note", type=Path, nargs="?", const=NOTE_FILE, default=None,
                   help="also put the table into the thinking-budget note (or the note given)")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.models:
        with StockfishEvaluator() as evaluator:
            run(args, evaluator)
    if args.summary or args.models or args.write_note:
        table = summary(read_rows(args.out))
        print(table)
        if args.write_note:
            args.write_note.write_text(into_note(args.write_note.read_text(encoding="utf-8"), table), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
