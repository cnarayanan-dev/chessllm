"""The installed Ollama models that can chat, with their sampling defaults."""

from typing import Protocol

import ollama

from chessllm.models import SAMPLING_OPTIONS, InstalledModel


class OllamaClient(Protocol):
    def list(self) -> ollama.ListResponse: ...

    def show(self, model: str) -> ollama.ShowResponse: ...


def installed_chat_models(client: OllamaClient | None = None) -> list[InstalledModel]:
    """Every installed model that can complete a chat, so embedding-only models are left out."""
    client = client or ollama.Client()
    models: dict[str, InstalledModel] = {}
    for listed in client.list().models:
        name = listed.model
        if name is None or name in models:
            continue
        shown = client.show(name)
        if "completion" in (shown.capabilities or []):
            models[name] = InstalledModel(name, sampling_defaults(shown.parameters))
    return list(models.values())


def sampling_defaults(parameters: str | None) -> dict[str, float]:
    """The sampling options among a model's parameters, given one per line, e.g. "temperature   1"."""
    sampling: dict[str, float] = {}
    for line in (parameters or "").splitlines():
        name, _, value = line.strip().partition(" ")
        if name in SAMPLING_OPTIONS:
            number = float(value)
            sampling[name] = int(number) if number.is_integer() and "." not in value else number
    return sampling
