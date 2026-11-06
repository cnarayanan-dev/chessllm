"""The Prompt library: the Prompt templates a new game's LLM sides can play with, and probes ask with (ADR 0010);
saving one makes a new one, and an old one is only hidden."""

from fastapi import APIRouter

from chessllm.api.deps import PromptLibraryDep
from chessllm.api.errors import error_responses
from chessllm.api.schemas.prompts import NewPromptTemplate, PromptTemplateInfo, System1Options, System1TemplateInfo
from chessllm.core.config import SYSTEM1_DEFAULT_URL
from chessllm.exceptions import InvalidSettings
from chessllm.system1.prompt import SYSTEM1_TEMPLATES

router = APIRouter()


@router.get("/api/prompt-templates")
def list_prompt_templates(library: PromptLibraryDep) -> list[PromptTemplateInfo]:
    """Every Prompt template that isn't hidden, the defaults first, each with the LLM constraints it fits. The New
    game sheet's Prompt picker offers a side those that fit its LLM constraints."""
    return [PromptTemplateInfo.of(entry) for entry in library.entries()]


@router.get("/api/system1/options")
def system1_options() -> System1Options:
    """What a System 1 side is offered: the default server URL, and the Prompt templates it can play with, the default
    first. The New game sheet starts a System 1 side at the URL, and its Prompt picker offers the templates."""
    return System1Options(
        default_url=SYSTEM1_DEFAULT_URL,
        templates=[
            System1TemplateInfo(
                id=template.id,
                name=template.name,
                system_prompt=template.system_prompt,
                turn_template=template.turn_template,
            )
            for template in SYSTEM1_TEMPLATES.values()
        ],
    )


@router.post("/api/prompt-templates", responses=error_responses(InvalidSettings))
def save_prompt_template(new: NewPromptTemplate, library: PromptLibraryDep) -> PromptTemplateInfo:
    """Save a new Prompt template, with a new ID; a template its side couldn't play is refused, saying why, and nothing
    is written. An existing one never changes."""
    entry = library.save(new.name, new.system_prompt, new.turn_template, new.llm_constraints)
    return PromptTemplateInfo.of(entry)


@router.post("/api/prompt-templates/{template_id}/hide", responses=error_responses(InvalidSettings))
def hide_prompt_template(template_id: str, library: PromptLibraryDep) -> list[PromptTemplateInfo]:
    """Leave a saved Prompt template out of the list, and answer the list as it is now; the games and probes that
    played it still resolve it."""
    library.hide(template_id)
    return list_prompt_templates(library)
