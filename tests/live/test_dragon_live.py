"""Live tests against the real Komodo Dragon 1, under Rosetta 2 on Apple silicon.

Excluded from the default run; run them with `pytest -m dragon`. Skipped when CHESSLLM_DRAGON doesn't name the
Dragon executable (from dragon.zip at komodochess.com)."""

import io
import json
import os
from pathlib import Path

import chess
import chess.pgn
import pytest

from tests.conftest import Raw, ScriptedPlayer

from chessllm.cli.anchor_match import main
from chessllm.core.config import DRAGON_PATH_VARIABLE
from chessllm.engines.anchors import DragonAnchor

pytestmark = pytest.mark.dragon


@pytest.fixture(scope="module")
def dragon_path() -> Path:
    path = os.environ.get(DRAGON_PATH_VARIABLE)
    if not path or not Path(path).expanduser().is_file():
        pytest.skip(f"Dragon isn't installed: set {DRAGON_PATH_VARIABLE} to the Dragon executable")
    return Path(path).expanduser()


def test_dragon_at_skill_1_plays_a_few_legal_moves(dragon_path):
    anchor = DragonAnchor(dragon_path, skill=1)
    board = chess.Board()
    try:
        for _ in range(8):
            move = anchor.move(board)
            assert board.is_legal(move)
            board.push(move)
    finally:
        anchor.close()


def test_the_command_plays_dragon_and_writes_the_log_and_pgn(dragon_path, tmp_path):
    games_dir = tmp_path / "games"
    player = ScriptedPlayer([Raw("no move")] * 4)  # the LLM forfeits its first turn, after Dragon's first move

    code = main(
        ["--skill", "1", "--color", "black", "--dragon", str(dragon_path), "--games-dir", str(games_dir)],
        player_for=player.for_settings,
        sampling_file=tmp_path / "no-sampling.toml",
    )

    assert code == 0
    [log] = games_dir.glob("*.jsonl")
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert events[0]["white"] == {"player": "anchor", "engine": "dragon", "skill": 1}
    assert events[1]["type"] == "anchor_move"
    assert (events[-1]["result"], events[-1]["reason"]) == ("1-0", "forfeit")
    game = chess.pgn.read_game(io.StringIO(log.with_suffix(".pgn").read_text(encoding="utf-8")))
    assert game is not None and game.headers["White"] == "Dragon (Skill 1)"
