"""The models the game can be played against, and the sampling settings from the config file."""

import tomllib
from dataclasses import dataclass
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
class LlmModel:
    name: str  # the Ollama model name
    thinking: bool  # whether it can think before it answers (Ollama's "thinking" capability)


# The models offered in the settings modal. Their thinking was checked on 2026-10-19 against the capabilities
# `ollama show` reports and the Ollama library (ollama.com/library/qwen3.5, ollama.com/library/llama3,
# ollama.com/library/gemma3).
LLM_MODELS = [
    LlmModel("qwen3.5:9b", thinking=True),  # Qwen 3.5, 9.7B parameters
    LlmModel("qwen3.8:latest", thinking=True),  # Qwen 3.8, 27.8B parameters
    LlmModel("llama3:8b", thinking=False),  # Llama 3, 8B parameters
    LlmModel("gemma3:12b", thinking=False),  # Gemma 3, 11.8B parameters
]


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
