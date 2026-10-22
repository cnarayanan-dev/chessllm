"""Analyse the finished games: each one's analysis file (chessllm.analytics.analysis), with the Move-quality estimate
from Maia-2 and centipawn loss and accuracy from Stockfish.

Run:
    uv run analyse-games          # every finished game in games/ without an analysis file
    uv run analyse-games --all    # re-analyse every finished game
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from chessllm.analytics.analysis import analyse_games
from chessllm.engines.evaluator import Evaluator
from chessllm.exceptions import Maia2Unavailable, StockfishUnavailable
from chessllm.engines.move_model import MoveModel
from chessllm.core.config import GAMES_DIR


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="analyse-games",
        description="Analyse every finished game without an analysis file: its Move-quality estimate (Maia-2), "
        "and centipawn loss and accuracy (Stockfish). An engine that can't start is skipped.",
    )
    parser.add_argument("--games-dir", type=Path, default=GAMES_DIR, help="where the game logs are (default: the project's games/)")
    parser.add_argument("--all", action="store_true", help="re-analyse every finished game, replacing its analysis")
    args = parser.parse_args(argv)
    from chessllm.engines.maia2_model import Maia2MoveModel
    from chessllm.engines.stockfish_evaluator import StockfishEvaluator

    with Maia2MoveModel() as maia2, StockfishEvaluator() as stockfish:
        move_model: MoveModel | None = maia2
        evaluator: Evaluator | None = stockfish
        try:
            print(f"Move-quality estimate: {maia2.version}")
        except Maia2Unavailable as error:
            print(f"skipping the Move-quality estimate: {error}")
            move_model = None
        try:
            print(f"centipawn loss and accuracy: {stockfish.version}")
        except StockfishUnavailable as error:
            print(f"skipping centipawn loss and accuracy: {error}")
            evaluator = None
        if move_model is None and evaluator is None:
            parser.exit(1, "neither Maia-2 nor Stockfish can start, so there is nothing to analyse with\n")
        for path in analyse_games(args.games_dir, move_model, evaluator, reanalyse=args.all):
            print(f"analysed {path}")


if __name__ == "__main__":
    main()
