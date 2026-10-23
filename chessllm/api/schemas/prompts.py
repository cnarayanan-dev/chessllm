from pydantic import BaseModel, ConfigDict, field_validator

from chessllm.game.prompt_library import LibraryEntry
from chessllm.game.sides import LlmConstraints, PromptTemplate, TurnMemory


class DefaultFor(BaseModel):
    """LLM constraints and a Turn memory a Prompt template is the Default of."""

    llm_constraints: LlmConstraints
    turn_memory: TurnMemory


class PromptTemplateInfo(BaseModel):
    """A Prompt template of the Prompt library, with the LLM constraints and the Turn memories a side can play it
    under, any of the one with any of the other, and each pair of them it is the Default of: what a side under them
    plays when its new game asks for no template. Saved if the human saved it (only a saved one can be hidden), and
    hidden if it is left out of the list."""

    id: str
    name: str | None
    system_prompt: str
    turn_template: str
    fits: list[LlmConstraints]
    turn_memories: list[TurnMemory]
    default_for: list[DefaultFor]
    saved: bool
    hidden: bool

    @classmethod
    def of(cls, entry: LibraryEntry) -> "PromptTemplateInfo":
        template = entry.template
        assert template.id is not None  # every template of the library has its ID
        return cls(
            id=template.id,
            name=template.name,
            system_prompt=template.system_prompt,
            turn_template=template.turn_template,
            fits=entry.fits,
            turn_memories=entry.turn_memories,
            default_for=[
                DefaultFor(llm_constraints=llm_constraints, turn_memory=turn_memory)
                for llm_constraints, turn_memory in entry.default_for
            ],
            saved=entry.path is not None,
            hidden=entry.hidden,
        )


class NewPromptTemplate(BaseModel):
    """A Prompt template to save in the Prompt library: its text, its name if any, and the LLM constraints it is
    written for, which it must fit. The library gives it its ID."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    system_prompt: str
    turn_template: str
    llm_constraints: LlmConstraints

    @field_validator("name")
    @classmethod
    def no_blank_name(cls, name: str | None) -> str | None:
        """A name of only spaces is no name."""
        return name.strip() or None if name is not None else None

    def template(self) -> PromptTemplate:
        return PromptTemplate(id=None, name=self.name, system_prompt=self.system_prompt, turn_template=self.turn_template)
