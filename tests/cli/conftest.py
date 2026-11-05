import pytest

import chessllm.llm.ollama_models


@pytest.fixture(autouse=True)
def ollama_has_every_model(monkeypatch):
    """The commands check, before they play, that Ollama has the models (chessllm.cli.common.missing_models); here it
    has them all, so no test asks the real Ollama. A test of the check gives the command its own missing_models."""
    monkeypatch.setattr(chessllm.llm.ollama_models, "missing_models", lambda models: [])
