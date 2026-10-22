import threading
import time
from functools import partial

import pytest
from ollama import ShowResponse

from chessllm.models import LlmModel
from chessllm.ollama_models import sampling_defaults

PARAMETERS = {
    "qwen3.5:9b": "presence_penalty               1.5\ntemperature                    1\ntop_k                          20\ntop_p                          0.95",
    "llama3:8b": 'num_keep                       24\nstop                           "<|start_header_id|>"\nstop                           "<|eot_id|>"',
}


class FakeOllama:
    def show(self, model: str) -> ShowResponse:
        return ShowResponse(model_info={}, parameters=PARAMETERS[model])


class StalledOllama:
    """Never answers for the stalled models, until released."""

    def __init__(self, stalled: set[str]):
        self.stalled = stalled
        self.released = threading.Event()

    def show(self, model: str) -> ShowResponse:
        if model in self.stalled:
            self.released.wait()
        return FakeOllama().show(model)


@pytest.fixture
def stalled_ollama():
    """Makes a StalledOllama, released at teardown so no thread is left waiting on it."""
    clients: list[StalledOllama] = []

    def make(stalled: set[str]) -> StalledOllama:
        clients.append(StalledOllama(stalled))
        return clients[-1]

    yield make
    for client in clients:
        client.released.set()


def test_the_sampling_defaults_are_read_from_the_models_parameters():
    defaults = sampling_defaults("qwen3.5:9b", FakeOllama())

    assert defaults == {"presence_penalty": 1.5, "temperature": 1, "top_k": 20, "top_p": 0.95}


def test_parameters_that_arent_sampling_options_are_left_out():
    assert sampling_defaults("llama3:8b", FakeOllama()) == {}  # num_keep and stop aren't sampling options


def test_a_model_ollama_doesnt_answer_for_in_time_is_offered_without_sampling(scripted, stalled_ollama):
    ollama = stalled_ollama({"qwen3.5:9b"})
    models = [LlmModel("qwen3.5:9b", (False, True)), LlmModel("llama3:8b")]
    client, _ = scripted([], models=models, sampling_defaults=partial(sampling_defaults, client=ollama, timeout_s=0.2))

    start = time.monotonic()
    response = client.get("/api/models")

    assert time.monotonic() - start < 0.2 + 1
    assert response.json() == [
        {"name": "qwen3.5:9b", "thinking": True, "sampling": None},
        {"name": "llama3:8b", "thinking": False, "sampling": {}},
    ]


def test_with_ollama_stalled_the_models_are_offered_within_one_timeout(scripted, stalled_ollama):
    names = ["qwen3.5:9b", "llama3:8b"] * 3
    ollama = stalled_ollama(set(names))
    models = [LlmModel(name) for name in names]
    client, _ = scripted([], models=models, sampling_defaults=partial(sampling_defaults, client=ollama, timeout_s=0.5))

    start = time.monotonic()
    response = client.get("/api/models")

    assert time.monotonic() - start < 0.5 * 2  # the models are asked at once, not one after another
    assert [model["sampling"] for model in response.json()] == [None] * 6
