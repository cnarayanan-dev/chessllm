"""The Prompt library: the Prompt templates a new game's LLM sides can play with (ADR 0010). A saved template never
changes: saving makes a new one, and an old one can only be hidden."""

from fastapi import APIRouter

from chessllm.api.deps import PromptLibraryDep
from chessllm.api.errors import error_responses
from chessllm.api.schemas.prompts import NewPromptTemplate, PromptTemplateInfo
from chessllm.exceptions import InvalidSettings

router = APIRouter()


@router.get("/api/prompt-templates")
def list_prompt_templates(library: PromptLibraryDep) -> list[PromptTemplateInfo]:
    """Every Prompt template that isn't hidden, the defaults first, each with the LLM constraints it fits. The New
    game sheet's Prompt picker offers a side those that fit its LLM constraints."""
    return [PromptTemplateInfo.of(entry) for entry in library.entries()]


@router.get("/api/prompt-templates/{template_id}", responses=error_responses(InvalidSettings))
def get_prompt_template(template_id: str, library: PromptLibraryDep) -> PromptTemplateInfo:
    """The Prompt template with this ID, hidden or not, as a game or probe that used it still resolves it."""
    return PromptTemplateInfo.of(library.entry(template_id))


@router.post("/api/prompt-templates", responses=error_responses(InvalidSettings))
def save_prompt_template(request: NewPromptTemplate, library: PromptLibraryDep) -> PromptTemplateInfo:
    """Save a new Prompt template, refused with the reason, and nothing written, if it doesn't fit the LLM
    constraints it is written for. Returns it with its new ID; there is no update: an edit is saved as another."""
    return PromptTemplateInfo.of(library.save(request.template(), request.llm_constraints))


@router.post("/api/prompt-templates/{template_id}/hide", responses=error_responses(InvalidSettings))
def hide_prompt_template(template_id: str, library: PromptLibraryDep) -> PromptTemplateInfo:
    """Leave a saved Prompt template out of the list, and return it; it still resolves for the games and probes that
    ask for it by its ID."""
    return PromptTemplateInfo.of(library.hide(template_id))
