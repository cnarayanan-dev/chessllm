"""The Dragon adapter of the Anchor port, against a fake UCI engine that offers Dragon's options and records the
commands it is sent. The real Dragon is played in tests/live/test_dragon_live.py."""

import sys

import chess
import pytest

from chessllm.engines.anchors import AnchorUnavailable, DragonAnchor

FAKE_ENGINE = '''
import sys

log = open(sys.argv[1], "a")
options = sys.argv[2:]
for line in sys.stdin:
    line = line.strip()
    log.write(line + "\\n")
    log.flush()
    if line == "uci":
        print("id name Fake Dragon")
        for option in options:
            print(option)
        print("uciok")
    elif line == "isready":
        print("readyok")
    elif line.startswith("go"):
        print("bestmove e7e5")
    elif line == "quit":
        break
    sys.stdout.flush()
'''

# Defaults other than the values wanted, as python-chess only sends an option that differs from its default.
DRAGON_OPTIONS = [
    "option name Threads type spin default 4 min 1 max 64",
    "option name Skill type spin default 25 min 1 max 25",
    "option name Auto Skill type check default true",
    "option name Personality type combo default Default var Default var Aggressive var Defensive",
]


def fake_engine(tmp_path, options: list[str]):
    """An executable fake engine offering the given UCI options, and the file it records its commands in."""
    script, commands = tmp_path / "fake_engine.py", tmp_path / "commands.txt"
    script.write_text(FAKE_ENGINE)
    executable = tmp_path / "fake-dragon"
    quoted = " ".join(f"'{option}'" for option in options)
    executable.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "{commands}" {quoted}\n')
    executable.chmod(0o755)
    return executable, commands


def test_dragon_plays_at_its_skill_with_one_thread_auto_skill_off_and_its_default_personality(tmp_path):
    executable, commands = fake_engine(tmp_path, DRAGON_OPTIONS)
    board = chess.Board()
    board.push_san("e4")

    anchor = DragonAnchor(executable, skill=3, rosetta=False)
    move = anchor.move(board)
    anchor.close()

    assert move == chess.Move.from_uci("e7e5")
    sent = commands.read_text().splitlines()
    assert {"setoption name Skill value 3", "setoption name Threads value 1", "setoption name Auto Skill value false"} <= set(sent)
    assert not any("Personality" in command for command in sent)
    assert sent[-1] == "quit"


def test_an_engine_without_dragons_options_is_refused(tmp_path):
    executable, _ = fake_engine(tmp_path, DRAGON_OPTIONS[:1])

    with pytest.raises(AnchorUnavailable, match="doesn't look like Dragon: it has no Skill, Auto Skill option"):
        DragonAnchor(executable, skill=1, rosetta=False)
