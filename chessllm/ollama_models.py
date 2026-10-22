"""The sampling defaults of an Ollama model."""

import threading
from typing import Protocol

import ollama

from chessllm.models import SAMPLING_OPTIONS

# How long Ollama gets to show a model; a stalled Ollama mustn't hang the New game sheet, which lists the models.
TIMEOUT_S = 3.0


class OllamaClient(Protocol):
    def show(self, model: str) -> ollama.ShowResponse: ...


def sampling_defaults(model: str, client: OllamaClient | None = None, timeout_s: float = TIMEOUT_S) -> dict[str, float]:
    """The sampling options among the model's parameters, which Ollama gives one per line, e.g. "temperature   1".

    Raises if Ollama can't show the model, e.g. when it isn't installed or Ollama isn't running, and TimeoutError
    if it doesn't within timeout_s."""
    parameters = _show(client or ollama.Client(timeout=timeout_s), model, timeout_s).parameters
    sampling: dict[str, float] = {}
    for line in (parameters or "").splitlines():
        name, _, value = line.strip().partition(" ")
        if name in SAMPLING_OPTIONS:
            number = float(value)
            sampling[name] = int(number) if number.is_integer() and "." not in value else number
    return sampling


def _show(client: OllamaClient, model: str, timeout_s: float) -> ollama.ShowResponse:
    """client.show(model), given up on after timeout_s. The call runs on a daemon thread, so one that never returns
    is left behind without keeping the process from exiting."""
    result: list[ollama.ShowResponse] = []
    error: list[BaseException] = []

    def show() -> None:
        try:
            result.append(client.show(model))
        except BaseException as e:
            error.append(e)

    thread = threading.Thread(target=show, name=f"ollama show {model}", daemon=True)
    thread.start()
    thread.join(timeout_s)
    if error:
        raise error[0]
    if not result:
        raise TimeoutError(f"Ollama didn't show {model} within {timeout_s} s")
    return result[0]
