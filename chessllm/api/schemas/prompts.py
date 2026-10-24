from pydantic import BaseModel

from chessllm.game.prompt_library import LibraryEntry
from chessllm.game.sides import LlmConstraints, TurnMemory


class PromptTemplateInfo(BaseModel):
    """A Prompt template of the Prompt library, with the LLM constraints and the Turn memories a side can play it
    under, and the LLM constraints it is the Default of under those Turn memories: what a side under them plays when
    its new game asks for no template."""

    id: str
    name: str | None
    system_prompt: str
    turn_template: str
    fits: list[LlmConstraints]
    turn_memories: list[TurnMemory]
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
            turn_memories=entry.turn_memories,
            default_for=entry.default_for,
        )
