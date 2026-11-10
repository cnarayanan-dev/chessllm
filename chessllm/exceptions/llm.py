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


class ReplyDeclined(ChessLlmError):
    """A Hosted model declined to answer for its content (a refusal, not an error of the call). Like a call that
    times out, it gives no answer, so the turn it came in is a Forfeit (ADR 0013)."""

    code = "reply_declined"


class HostedModelFailed(ChessLlmError):
    """A Hosted model's provider failed for a reason that is not the model's play: it refuses the app's token or
    access, has no credit left, limits its use or is down, even after the client's own retries. No side loses: the
    game ends as an Aborted game (ADR 0013), and a batch stops."""

    code = "hosted_model_failed"
