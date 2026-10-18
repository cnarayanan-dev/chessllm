"""The installed models the game can be played against, and the sampling settings from the config file."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

SAMPLING_FILE = Path(__file__).parent / "sampling.toml"

# The Ollama options that change how a model samples its reply. Others (num_ctx, stop, ...) aren't sampling.
SAMPLING_OPTIONS = frozenset(
    {
        "temperature",
        "top_k",
        "top_p",
        "min_p",
        "typical_p",
        "repeat_penalty",
        "repeat_last_n",
        "presence_penalty",
        "frequency_penalty",
        "seed",
        "mirostat",
        "mirostat_tau",
        "mirostat_eta",
    }
)


@dataclass(frozen=True)
class InstalledModel:
    name: str
    sampling: dict[str, float] = field(default_factory=dict)  # the model's own defaults


def load_sampling(path: Path = SAMPLING_FILE) -> dict[str, float]:
    """The sampling options set in the config file. Empty (or no file) means the model's own defaults.

    The file is read at the start of every game, so edits apply to the next game without restarting the app."""
    if not path.exists():
        return {}
    sampling = tomllib.loads(path.read_text(encoding="utf-8"))
    unknown = sorted(set(sampling) - SAMPLING_OPTIONS)
    if unknown:
        raise ValueError(f"{path.name}: unknown sampling options {', '.join(unknown)}")
    not_numbers = sorted(name for name, value in sampling.items() if type(value) not in (int, float))
    if not_numbers:
        raise ValueError(f"{path.name}: sampling options must be numbers: {', '.join(not_numbers)}")
    return sampling
