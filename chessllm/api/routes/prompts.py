"""The Prompt library: the Prompt templates a new game's LLM sides can play with (ADR 0010)."""

from fastapi import APIRouter

from chessllm.api.deps import PromptLibraryDep
from chessllm.api.schemas.prompts import PromptTemplateInfo

router = APIRouter()


@router.get("/api/prompt-templates")
def list_prompt_templates(library: PromptLibraryDep) -> list[PromptTemplateInfo]:
    """Every Prompt template that isn't hidden, the defaults first, each with the LLM constraints it fits. The New
    game sheet's Prompt picker offers a side those that fit its LLM constraints."""
    return [PromptTemplateInfo.of(entry) for entry in library.entries()]
