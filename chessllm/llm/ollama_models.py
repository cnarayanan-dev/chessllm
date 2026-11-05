"""What Ollama shows of its models: their sampling defaults, and which of them it doesn't have."""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import ollama

from chessllm.core.config import OLLAMA_SHOW_TIMEOUT_S
from chessllm.core.types import Sampling
from chessllm.exceptions import OllamaUnavailable
from chessllm.llm.models import SAMPLING_OPTIONS


class OllamaClient(Protocol):
    def show(self, model: str) -> ollama.ShowResponse: ...


def sampling_defaults(model: str, client: OllamaClient | None = None, timeout_s: float = OLLAMA_SHOW_TIMEOUT_S) -> Sampling:
    """The sampling options among the model's parameters, which Ollama gives one per line, e.g. "temperature   1".

    Raises if Ollama can't show the model, e.g. when it isn't installed or Ollama isn't running, and TimeoutError
    if it doesn't within timeout_s."""
    parameters = _show(client or ollama.Client(timeout=timeout_s), model, timeout_s).parameters
    sampling: Sampling = {}
    for line in (parameters or "").splitlines():
        name, _, value = line.strip().partition(" ")
        if name in SAMPLING_OPTIONS:
            number = float(value)
            sampling[name] = int(number) if number.is_integer() and "." not in value else number
    return sampling


def missing_models(
    models: list[str], client: OllamaClient | None = None, timeout_s: float = OLLAMA_SHOW_TIMEOUT_S
) -> list[str]:
    """The models Ollama doesn't have, in the order given: those it answers a 404 for. They are asked at once, so a
    stalled Ollama holds them up for one timeout, not one per model.

    Raises OllamaUnavailable if Ollama can't say: it isn't running, doesn't answer within timeout_s, or fails."""
    if not models:
        return []
    ask = client or ollama.Client(timeout=timeout_s)

    def has(model: str) -> bool:
        try:
            _show(ask, model, timeout_s)
        except ollama.ResponseError as error:
            if error.status_code == 404:
                return False
            raise OllamaUnavailable(f"Ollama couldn't show {model}: {error}") from error
        except ConnectionError as error:
            raise OllamaUnavailable("Ollama isn't running: start it with `ollama serve` or the Ollama app") from error
        except TimeoutError as error:
            raise OllamaUnavailable(str(error)) from error
        return True

    with ThreadPoolExecutor(len(models)) as pool:
        found = list(pool.map(has, models))
    return [model for model, there in zip(models, found, strict=True) if not there]


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
