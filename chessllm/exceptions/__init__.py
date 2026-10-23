"""The errors of chessllm, each a ChessLlmError with a code that says which refusal or failure it is. Every module
raises them from here; the API turns those a request can meet into its error responses (api/errors.py)."""


class ChessLlmError(Exception):
    """An error of chessllm itself. Its message says what went wrong; its code which kind of error it is, as the
    API's error responses give it."""

    code = "error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


# Imported after ChessLlmError, which each of them subclasses.
from chessllm.exceptions.config import InvalidSamplingConfig  # noqa: E402
from chessllm.exceptions.engines import AnchorUnavailable, Maia2Unavailable, StockfishUnavailable  # noqa: E402
from chessllm.exceptions.game import (  # noqa: E402
    InvalidSettings,
    NoGameStarted,
    RefusedAnchorTurn,
    RefusedLlmTurn,
    RefusedProbe,
    RejectedHumanMove,
)
from chessllm.exceptions.llm import LlmTimeout  # noqa: E402

__all__ = [
    "AnchorUnavailable",
    "ChessLlmError",
    "InvalidSamplingConfig",
    "InvalidSettings",
    "LlmTimeout",
    "Maia2Unavailable",
    "NoGameStarted",
    "RefusedAnchorTurn",
    "RefusedLlmTurn",
    "RefusedProbe",
    "RejectedHumanMove",
    "StockfishUnavailable",
]
