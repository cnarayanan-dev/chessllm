"""The request body of a Probe."""

from pydantic import BaseModel, ConfigDict, Field

from chessllm.core.types import Color


class ProbeRequest(BaseModel):
    """The past LLM turn of the current game to probe, by its ply and colour, and the Prompt template to ask with, by
    its ID in the Prompt library; none for the one the game recorded for the side, whether or not the library still
    has it."""

    model_config = ConfigDict(extra="forbid")

    ply: int = Field(ge=1)
    color: Color
    prompt_template_id: str | None = None
