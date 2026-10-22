"""The Maia-2 worker: answers move probabilities over stdin and stdout, one JSON object per line.

It runs in its own Python 3.12 environment with maia2 installed (see chessllm.engines.maia2_model): maia2 needs
Python < 3.13, and this project 3.13. So it imports nothing from chessllm.

On start it loads the rapid model (downloading it into --save-root the first time) on MPS, CUDA or the CPU and
writes {"version": ..., "ratings": [...]}. Then for each {"fen": ..., "move": <UCI>} it writes
{"probabilities": [...]}, one per rating, or {"error": ...}. Each rating r is given to Maia-2 as both the player's
and the opponent's rating, so the estimate needs no rating for the opponent."""

import argparse
import contextlib
import json
import sys
from importlib.metadata import version
from typing import Any

import torch
from maia2 import inference, model
from maia2.utils import mirror_move

# Maia-2 puts ratings in bins: under 1100, 100 wide up to 2000, and 2000 or over. One rating per bin, so 1000
# stands for "under 1100" and 2000 for "2000 or over".
RATINGS = list(range(1000, 2001, 100))
# A floor for a probability so small it rounds to 0 in float32, so its log stays finite.
MIN_PROBABILITY = 1e-12


def probabilities(maia: Any, prepared: Any, fen: str, move: str) -> list[float]:
    """The probability of move in fen at each rating, unrounded (inference_each rounds to 4 places)."""
    all_moves_dict, elo_dict, _ = prepared
    rows = [inference.preprocessing(fen, rating, rating, elo_dict, all_moves_dict) for rating in RATINGS]
    device = next(maia.parameters()).device
    boards = torch.stack([row[0] for row in rows]).to(device)
    elos = torch.tensor([row[1] for row in rows]).to(device)
    legal = torch.stack([row[3] for row in rows]).to(device)
    with torch.no_grad():
        logits, _, _ = maia(boards, elos, elos)
    # Maia-2 sees every position from White's side, so a Black move is looked up mirrored.
    index = all_moves_dict[mirror_move(move) if fen.split(" ")[1] == "b" else move]
    if not legal[0, index]:
        raise ValueError(f"{move} is not legal in {fen}")
    probs = logits.masked_fill(~legal.bool(), float("-inf")).softmax(dim=-1)[:, index]
    return [max(float(p), MIN_PROBABILITY) for p in probs.cpu().tolist()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-root", required=True)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):  # maia2 prints its progress; stdout is for answers only
        maia = model.from_pretrained("rapid", args.device, save_root=args.save_root)
        maia.eval()
    prepared = inference.prepare()
    described = f"maia2 {version('maia2')}, rapid model, opponent rated as the player"
    print(json.dumps({"version": described, "ratings": RATINGS}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        try:
            answer: dict[str, Any] = {"probabilities": probabilities(maia, prepared, request["fen"], request["move"])}
        except Exception as error:
            answer = {"error": f"{type(error).__name__}: {error}"}
        print(json.dumps(answer), flush=True)


if __name__ == "__main__":
    main()
