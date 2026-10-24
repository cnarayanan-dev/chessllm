"""The request body of a Probe."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from chessllm.core.types import Color
from chessllm.game.prompt_library import unsaved
from chessllm.game.sides import PromptTemplate


class ProbeRequest(BaseModel):
    """Which past LLM turn of the current game to ask about, by its ply and the side's colour, and the Prompt template
    to ask with: by its ID in the Prompt library, or as the System prompt and Turn template text, saved or not, as the
    Prompt lab's dock has it. Text is recorded as unsaved (prompt_library.unsaved)."""

    model_config = ConfigDict(extra="forbid")

    ply: int = Field(ge=1)
    color: Color
    prompt_template_id: str | None = None
    system_prompt: str | None = None
    turn_template: str | None = None

    @model_validator(mode="after")
    def template_by_id_or_text(self) -> Self:
        text = (self.system_prompt, self.turn_template)
        if self.prompt_template_id is None and None in text:
            raise ValueError("a Probe needs a prompt_template_id, or both a system_prompt and a turn_template")
        if self.prompt_template_id is not None and text != (None, None):
            raise ValueError("a Probe takes a prompt_template_id or the text of one, not both")
        return self

    def unsaved(self) -> PromptTemplate | None:
        """The template the text makes, if the Probe was given text rather than an ID."""
        if self.system_prompt is None or self.turn_template is None:
            return None
        return unsaved(self.system_prompt, self.turn_template)
