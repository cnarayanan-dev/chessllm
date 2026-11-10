import threading
import time
from functools import partial

import pytest
from ollama import ListResponse, ResponseError, ShowResponse

from chessllm.exceptions import OllamaUnavailable
from chessllm.llm.models import LlmModel
from chessllm.llm.ollama_models import decision_models, missing_models, sampling_defaults

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


class PartialOllama:
    """Has only the models in PARAMETERS, answering for any other as Ollama does: a 404."""

    def show(self, model: str) -> ShowResponse:
        if model not in PARAMETERS:
            raise ResponseError(f"model '{model}' not found", 404)
        return FakeOllama().show(model)


class FailingOllama:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def show(self, model: str) -> ShowResponse:
        raise self.error


def test_the_models_ollama_doesnt_have_are_missing_in_the_order_given():
    asked = ["gemma3:12b", "qwen3.5:9b", "nonesuch:1b", "llama3:8b"]

    assert missing_models(asked, PartialOllama()) == ["gemma3:12b", "nonesuch:1b"]
    assert missing_models([], PartialOllama()) == []


def test_ollama_not_running_is_unavailable_not_a_missing_model():
    not_running = FailingOllama(ConnectionError("Failed to connect to Ollama. Please check that Ollama is running"))

    with pytest.raises(OllamaUnavailable, match=r"^Ollama isn't running: start it with `ollama serve`"):
        missing_models(["llama3:8b"], not_running)


def test_ollama_failing_otherwise_is_unavailable_with_its_error():
    with pytest.raises(OllamaUnavailable, match=r"^Ollama couldn't show llama3:8b: out of memory \(status code: 500\)"):
        missing_models(["llama3:8b"], FailingOllama(ResponseError("out of memory", 500)))


def test_with_ollama_stalled_the_models_are_unavailable_within_one_timeout(stalled_ollama):
    ollama = stalled_ollama({"qwen3.5:9b", "llama3:8b"})

    start = time.monotonic()
    with pytest.raises(OllamaUnavailable, match=r"^Ollama didn't show qwen3.5:9b within 0.3 s"):
        missing_models(["qwen3.5:9b", "llama3:8b"], ollama, timeout_s=0.3)

    assert time.monotonic() - start < 0.3 * 2  # the models are asked at once, not one after another


class ListingOllama:
    """Lists the models in CAPABILITIES and shows each with its capabilities, as Ollama does."""

    CAPABILITIES = {
        "d3:2b": ["decision", "vision"],
        "llama3:8b": ["completion"],
        "d1:2b": ["decision", "vision"],
        "qwen3.5:9b": ["completion", "vision", "tools", "thinking"],
    }

    def list(self) -> ListResponse:
        return ListResponse(models=[ListResponse.Model(model=name) for name in self.CAPABILITIES])

    def show(self, model: str) -> ShowResponse:
        return ShowResponse(model_info={}, capabilities=self.CAPABILITIES[model])


def test_the_decision_models_are_the_installed_models_with_the_decision_capability_in_the_order_listed():
    assert decision_models(ListingOllama()) == ["d3:2b", "d1:2b"]


def test_with_ollama_not_running_there_are_no_decision_models():
    class NotRunning(ListingOllama):
        def list(self) -> ListResponse:
            raise ConnectionError("Failed to connect to Ollama")

    assert decision_models(NotRunning()) == []


def test_a_model_ollama_cant_show_is_left_out_of_the_decision_models():
    class CantShowD3(ListingOllama):
        def show(self, model: str) -> ShowResponse:
            if model == "d3:2b":
                raise ResponseError("out of memory", 500)
            return super().show(model)

    assert decision_models(CantShowD3()) == ["d1:2b"]


def test_with_ollama_stalled_the_decision_models_are_none_within_one_timeout(stalled_ollama):
    class Stalled(ListingOllama):
        def __init__(self) -> None:
            self.stall = stalled_ollama(set(self.CAPABILITIES))

        def show(self, model: str) -> ShowResponse:
            self.stall.show(model)
            return super().show(model)

    start = time.monotonic()
    assert decision_models(Stalled(), timeout_s=0.3) == []

    assert time.monotonic() - start < 0.3 * 2
