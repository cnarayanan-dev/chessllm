from pydantic import BaseModel

from chessllm.game.prompt_library import LibraryEntry
from chessllm.game.sides import LlmConstraints


class PromptTemplateInfo(BaseModel):
    """A Prompt template of the Prompt library, with the LLM constraints a side can play it under, and those it is
    the Default of: what a side under them plays when its new game asks for no template."""

    id: str
    name: str | None
    system_prompt: str
    turn_template: str
    fits: list[LlmConstraints]
    default_for: list[LlmConstraints]

    @classmethod
    def of(cls, entry: LibraryEntry) -> "PromptTemplateInfo":
        template = entry.template
        return cls(
            id=template.id,
            name=template.name,
            system_prompt=template.system_prompt,
            turn_template=template.turn_template,
            fits=entry.fits,
            default_for=entry.default_for,
        )
