"""The sample games (docs/samples/): written by a command, the same on every run, so `git diff` shows what a refactor
step changed. No test compares them with the committed samples: they are checked by hand."""

import json

from scripts.sample_logs import write_samples

SAMPLE_GAMES = ["play-llm-standard", "llm-faceoff-chaos", "anchor-match-standard", "llm-faceoff-thinking-budget"]


def files(directory) -> dict[str, bytes]:
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def test_two_runs_write_the_same_files_byte_for_byte(tmp_path):
    write_samples(tmp_path / "first")
    write_samples(tmp_path / "second")

    assert files(tmp_path / "first") == files(tmp_path / "second")


def test_a_run_replaces_the_samples_of_the_run_before(tmp_path):
    stale = tmp_path / "api" / "renamed-sample.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")

    write_samples(tmp_path)

    assert not stale.exists()


def test_each_sample_game_is_logged_with_its_pgn_and_ends_as_scripted(tmp_path):
    write_samples(tmp_path)

    ends = {}
    for game in SAMPLE_GAMES:
        assert (tmp_path / "game-logs" / f"{game}.pgn").is_file()
        lines = (tmp_path / "game-logs" / f"{game}.jsonl").read_text(encoding="utf-8").splitlines()
        end = json.loads(lines[-1])
        ends[game] = (end["type"], end["reason"])
    assert ends == {
        "play-llm-standard": ("game_end", "checkmate"),
        "llm-faceoff-chaos": ("game_end", "king_capture"),
        "anchor-match-standard": ("game_end", "forfeit"),
        "llm-faceoff-thinking-budget": ("game_end", "forfeit"),
    }


def test_no_run_dependent_value_is_left_in_the_samples(tmp_path):
    write_samples(tmp_path / "samples")

    text = "\n".join(content.decode("utf-8") for content in files(tmp_path / "samples").values())
    assert str(tmp_path) not in text
    assert "/Users/" not in text and "/home/" not in text  # the prompt files are logged from the repo's root
