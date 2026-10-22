from chessllm.exceptions import ChessLlmError


class LlmTimeout(ChessLlmError):
    """The model gave no answer within the time limit, so the call was cancelled."""

    code = "llm_timeout"

    def __init__(self, timeout_s: float) -> None:
        super().__init__(f"no answer within {timeout_s:g}s")
        self.timeout_s = timeout_s
