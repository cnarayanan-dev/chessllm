from pydantic import BaseModel, ConfigDict

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
    saved: bool  # saved in the library rather than a default: only a saved one can be hidden

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
            saved=entry.saved,
        )


class NewPromptTemplate(BaseModel):
    """A Prompt template to save in the Prompt library as a new one: its name if it has one, its System prompt and its
    Turn template, and the LLM constraints of the side it is written for, which it must fit (check_prompt_template).
    There is no update: an edit is saved as a new Prompt template."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    system_prompt: str
    turn_template: str
    llm_constraints: LlmConstraints


class System1TemplateInfo(BaseModel):
    """A Prompt template a System 1 model can play with: its System prompt is the question it is asked, its Turn
    template the state it is given."""

    id: str
    name: str | None
    system_prompt: str
    turn_template: str


class System1Options(BaseModel):
    """What a new game's System 1 side is offered: the server a System 1 model is looked for at unless the game says
    another (the app's default), the System 1 models installed in Ollama there (none if it can't say), and the Prompt
    templates it can play with, the default first."""

    default_url: str
    models: list[str]
    templates: list[System1TemplateInfo]
