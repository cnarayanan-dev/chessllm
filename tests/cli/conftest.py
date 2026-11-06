import pytest

import chessllm.llm.ollama_models
import chessllm.system1.http_model


@pytest.fixture(autouse=True)
def ollama_has_every_model(monkeypatch):
    """The commands check, before they play, that Ollama has the models (chessllm.cli.common.missing_models); here it
    has them all, so no test asks the real Ollama. A test of the check gives the command its own missing_models."""
    monkeypatch.setattr(chessllm.llm.ollama_models, "missing_models", lambda models: [])


@pytest.fixture(autouse=True)
def system1_server_has_every_model(monkeypatch):
    """The commands check, before they play, that a System 1 model's server has the model
    (chessllm.cli.common.system1_missing_models); here it has them all, so no test asks a real server."""
    monkeypatch.setattr(chessllm.system1.http_model, "missing_models", lambda base_url, models: [])
