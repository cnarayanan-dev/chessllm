from pydantic import BaseModel

from chessllm.core.types import Sampling


class ModelInfo(BaseModel):
    """A model the game can be played against, with the sampling it would play at."""

    name: str
    thinking: bool
    sampling: Sampling | None  # None when Ollama can't show the model
