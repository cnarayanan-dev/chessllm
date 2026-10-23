"""The Prompt library (ADR 0010): the default Prompt templates, as their files say now, and the saved ones, each a
JSON file in the library's folder, so saved prompts show up in git. A saved Prompt template never changes, and an
old one is only hidden: left out of the list, it still resolves for the games that play it."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import DefaultTemplate, check_prompt_template, default_template, tools_template
from chessllm.game.sides import LISTED, LlmConstraints, PromptTemplate

LLM_CONSTRAINTS: tuple[LlmConstraints, ...] = get_args(LlmConstraints)


@dataclass(frozen=True)
class LibraryEntry:
    """A Prompt template of the library, with the LLM constraints it fits (check_prompt_template), and those it is
    the Default of: what a side under them plays when it asks for no template."""

    template: PromptTemplate
    fits: list[LlmConstraints]
    default_for: list[LlmConstraints]
    hidden: bool = False


class PromptLibrary:
    """The library over its folder, read at every call, so a file added or edited by hand shows at once. A missing
    folder holds no saved template."""

    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def entries(self) -> list[LibraryEntry]:
        """Every Prompt template that isn't hidden: the defaults first, then the saved ones by file name."""
        return [entry for entry in self._all() if not entry.hidden]

    def template(self, template_id: str) -> PromptTemplate | None:
        """The Prompt template with this ID, hidden or not; None if the library has none."""
        return next((entry.template for entry in self._all() if entry.template.id == template_id), None)

    def resolve(self, template_id: str, color: str) -> PromptTemplate:
        """The Prompt template a new game's LLM side (color) asks for by its ID. Raises InvalidSettings
        (unknown_prompt_template) if the library has none."""
        template = self.template(template_id)
        if template is None:
            refused = f"The Prompt library has no Prompt template {template_id}: the LLM side ({color}) can't play it"
            raise InvalidSettings(refused, code="unknown_prompt_template")
        return template

    def _all(self) -> list[LibraryEntry]:
        return default_entries() + [saved(path) for path in sorted(self._folder.glob("*.json"))]


def default_entries() -> list[LibraryEntry]:
    """The default Prompt templates as their files say now: Default, Described and Moves without the Legal-move list,
    then with it, then the Tools template. Moves fits no LLM constraints here, where fits is for fresh Turn memory, the
    only one the app plays: it is played under chat_moves, as that Turn memory's default (side_template)."""
    templates: dict[str, PromptTemplate] = {}
    default_for: dict[str, list[LlmConstraints]] = {}
    for llm_constraints in sorted(LLM_CONSTRAINTS, key=lambda constraints: constraints in LISTED):
        for kind in get_args(DefaultTemplate):
            template = default_template(llm_constraints, kind)
            templates.setdefault(template.id, template)
            default_for.setdefault(template.id, [])
            if kind == "default":
                default_for[template.id].append(llm_constraints)
    defaults = [
        LibraryEntry(template, fits(template), default_for[template_id]) for template_id, template in templates.items()
    ]
    # The Tools template, the default of a side with Tools: hidden, as the app can't give a side tools to call
    # (ADR 0011), yet it resolves for a game that played it.
    tools = tools_template()
    return defaults + [LibraryEntry(tools, fits(tools), default_for=[], hidden=True)]


def fits(template: PromptTemplate) -> list[LlmConstraints]:
    """The LLM constraints a side can play the template under."""
    fitting = []
    for llm_constraints in LLM_CONSTRAINTS:
        try:
            check_prompt_template(template, llm_constraints)
        except InvalidSettings:
            continue
        fitting.append(llm_constraints)
    return fitting


def saved(path: Path) -> LibraryEntry:
    """A saved Prompt template from its file: its ID, its name if it has one, whether it is hidden, its System prompt
    and its Turn template."""
    shape = json.loads(path.read_text(encoding="utf-8"))
    template = PromptTemplate(
        id=shape["id"],
        name=shape.get("name"),
        system_prompt=shape["system_prompt"],
        turn_template=shape["turn_template"],
    )
    return LibraryEntry(template, fits(template), default_for=[], hidden=shape.get("hidden", False))
