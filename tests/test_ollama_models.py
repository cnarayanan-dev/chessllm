from ollama import ListResponse, ShowResponse

from chessllm.models import InstalledModel
from chessllm.ollama_models import installed_chat_models

PARAMETERS = {
    "qwen3.5:9b": "presence_penalty               1.5\ntemperature                    1\ntop_k                          20\ntop_p                          0.95",
    "qwen3-embedding:0.6b": None,
    "llama3:8b": 'num_keep                       24\nstop                           "<|start_header_id|>"\nstop                           "<|eot_id|>"',
}
CAPABILITIES = {
    "qwen3.5:9b": ["completion", "vision", "tools", "thinking"],
    "qwen3-embedding:0.6b": ["tools", "thinking", "embedding"],
    "llama3:8b": ["completion"],
}


class FakeOllama:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    def list(self) -> ListResponse:
        return ListResponse(models=[ListResponse.Model(model=name) for name in self.names])

    def show(self, model: str) -> ShowResponse:
        return ShowResponse(model_info={}, parameters=PARAMETERS[model], capabilities=CAPABILITIES[model])


def test_embedding_models_are_left_out_and_each_models_sampling_defaults_are_read():
    client = FakeOllama(["qwen3.5:9b", "qwen3-embedding:0.6b", "llama3:8b"])

    assert installed_chat_models(client) == [
        InstalledModel("qwen3.5:9b", {"presence_penalty": 1.5, "temperature": 1, "top_k": 20, "top_p": 0.95}),
        InstalledModel("llama3:8b", {}),  # num_keep and stop aren't sampling options
    ]


def test_a_model_listed_twice_appears_once():
    client = FakeOllama(["llama3:8b", "llama3:8b"])

    assert [model.name for model in installed_chat_models(client)] == ["llama3:8b"]
