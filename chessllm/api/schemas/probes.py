"""The request body of a Probe."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from chessllm.core.types import Color


class ProbeRequest(BaseModel):
    """The past LLM turn of the current game to probe, by its ply and colour, and the Prompt template to ask with: by
    its ID in the Prompt library, or as text not saved yet, a System prompt and a Turn template; neither for the one
    the game recorded for the side, whether or not the library still has it."""

    model_config = ConfigDict(extra="forbid")

    ply: int = Field(ge=1)
    color: Color
    prompt_template_id: str | None = None
    system_prompt: str | None = None
    turn_template: str | None = None

    @model_validator(mode="after")
    def one_template(self) -> Self:
        """Unsaved text comes as both parts, and never with an ID."""
        unsaved = (self.system_prompt is not None, self.turn_template is not None)
        if unsaved[0] != unsaved[1]:
            raise ValueError("unsaved text takes both a system_prompt and a turn_template")
        if unsaved[0] and self.prompt_template_id is not None:
            raise ValueError("a probe asks with a prompt_template_id or with unsaved text, not both")
        return self
