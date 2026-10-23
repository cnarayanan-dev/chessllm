"""The request body of a Probe."""

from pydantic import BaseModel, ConfigDict, Field

from chessllm.core.types import Color


class ProbeRequest(BaseModel):
    """Which past LLM turn of the current game to ask about, by its ply and the side's colour, and the Prompt template
    to ask with, by its ID in the Prompt library."""

    model_config = ConfigDict(extra="forbid")

    ply: int = Field(ge=1)
    color: Color
    prompt_template_id: str
