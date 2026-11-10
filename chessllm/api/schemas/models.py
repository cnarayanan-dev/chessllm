from pydantic import BaseModel, Field

from chessllm.core.types import Sampling


class ModelInfo(BaseModel):
    """A model the game can be played against, with the sampling it would play at."""

    name: str
    thinking: bool
    sampling: Sampling | None  # None when Ollama can't show the model, and for a Hosted model, whose sampling is its provider's
    # Whether it is a Hosted model (ADR 0013): run on a provider's servers, with no sampling, Thinking level, Thinking
    # budget or Tools. Left out for a local model.
    hosted: bool = Field(default=False, exclude_if=lambda hosted: not hosted)
