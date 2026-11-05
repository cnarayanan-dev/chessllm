from chessllm.exceptions import ChessLlmError


class LlmTimeout(ChessLlmError):
    """The model gave no answer within the time limit, so the call was cancelled."""

    code = "llm_timeout"

    def __init__(self, timeout_s: float) -> None:
        super().__init__(f"no answer within {timeout_s:g}s")
        self.timeout_s = timeout_s


class OllamaUnavailable(ChessLlmError):
    """Ollama can't be asked which models it has: it isn't running, didn't answer in time, or failed."""

    code = "ollama_unavailable"
