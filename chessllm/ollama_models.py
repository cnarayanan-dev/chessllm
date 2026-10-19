"""The sampling defaults of an Ollama model."""

from typing import Protocol

import ollama

from chessllm.models import SAMPLING_OPTIONS


class OllamaClient(Protocol):
    def show(self, model: str) -> ollama.ShowResponse: ...


def sampling_defaults(model: str, client: OllamaClient | None = None) -> dict[str, float]:
    """The sampling options among the model's parameters, which Ollama gives one per line, e.g. "temperature   1".

    Raises if Ollama can't show the model, e.g. when it isn't installed or Ollama isn't running."""
    parameters = (client or ollama.Client()).show(model).parameters
    sampling: dict[str, float] = {}
    for line in (parameters or "").splitlines():
        name, _, value = line.strip().partition(" ")
        if name in SAMPLING_OPTIONS:
            number = float(value)
            sampling[name] = int(number) if number.is_integer() and "." not in value else number
    return sampling
