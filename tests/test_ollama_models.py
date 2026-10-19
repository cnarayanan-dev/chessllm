from ollama import ShowResponse

from chessllm.ollama_models import sampling_defaults

PARAMETERS = {
    "qwen3.5:9b": "presence_penalty               1.5\ntemperature                    1\ntop_k                          20\ntop_p                          0.95",
    "llama3:8b": 'num_keep                       24\nstop                           "<|start_header_id|>"\nstop                           "<|eot_id|>"',
}


class FakeOllama:
    def show(self, model: str) -> ShowResponse:
        return ShowResponse(model_info={}, parameters=PARAMETERS[model])


def test_the_sampling_defaults_are_read_from_the_models_parameters():
    defaults = sampling_defaults("qwen3.5:9b", FakeOllama())

    assert defaults == {"presence_penalty": 1.5, "temperature": 1, "top_k": 20, "top_p": 0.95}


def test_parameters_that_arent_sampling_options_are_left_out():
    assert sampling_defaults("llama3:8b", FakeOllama()) == {}  # num_keep and stop aren't sampling options
