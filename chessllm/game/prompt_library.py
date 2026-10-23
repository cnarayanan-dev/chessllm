"""The Prompt library (ADR 0010): the default Prompt templates, as their files say now, and the saved ones, each a
JSON file in the library's folder, so saved prompts show up in git. A saved Prompt template never changes, and an
old one is only hidden: left out of the list, it still resolves for the games that play it."""

import json
import os
import re
import tempfile
from dataclasses import dataclass, replace
from itertools import count
from pathlib import Path
from typing import get_args

from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import (
    DefaultTemplate,
    check_prompt_template,
    default_template,
    side_template,
    template_version,
    tools_template,
)
from chessllm.game.sides import LISTED, LlmConstraints, LlmSide, PromptTemplate, TurnMemory

LLM_CONSTRAINTS: tuple[LlmConstraints, ...] = get_args(LlmConstraints)
TURN_MEMORIES: tuple[TurnMemory, ...] = get_args(TurnMemory)


@dataclass(frozen=True)
class LibraryEntry:
    """A Prompt template of the library, with the LLM constraints and the Turn memories it fits
    (check_prompt_template), and each pair of them it is the Default of: what a side under them plays when it asks
    for no template. A template fits every pair of the two: what the Turn memory asks of it and what the LLM
    constraints do are checked apart."""

    template: PromptTemplate
    fits: list[LlmConstraints]
    turn_memories: list[TurnMemory]
    default_for: list[tuple[LlmConstraints, TurnMemory]]
    hidden: bool = False
    path: Path | None = None  # the file of a saved one; None for a default one


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

    def entry(self, template_id: str) -> LibraryEntry:
        """The library's entry for the Prompt template with this ID, hidden or not. Raises InvalidSettings
        (unknown_prompt_template) if the library has none."""
        entry = next((entry for entry in self._all() if entry.template.id == template_id), None)
        if entry is None:
            refused = f"The Prompt library has no Prompt template {template_id}"
            raise InvalidSettings(refused, code="unknown_prompt_template")
        return entry

    def save(self, template: PromptTemplate, llm_constraints: LlmConstraints) -> LibraryEntry:
        """Save the template's text, with its name if it has one, as a new Prompt template written for the LLM
        constraints, and return it with its ID: the name's, or "saved", and a version from its text after an @, e.g.
        "terse@1f0c2a9e". The template's own ID is ignored, and no saved template or file is ever changed: the same
        name and text already in the library is returned as it is, shown again if it was hidden, and an ID or file
        name taken by another template is numbered on ("terse-2@1f0c2a9e").

        Raises InvalidSettings (invalid_prompt_template), saying why, if the template can't be played under the LLM
        constraints (check_prompt_template); nothing is written then."""
        check_prompt_template(template, llm_constraints)
        version = template_version(template.system_prompt, template.turn_template)
        slug = re.sub("[^a-z0-9]+", "-", (template.name or "").lower()).strip("-")[:40].strip("-") or "saved"
        taken = {entry.template.id: entry for entry in self._all()}
        for number in count(1):
            new = replace(template, id=f"{slug}{f'-{number}' if number > 1 else ''}@{version}")
            existing = taken.get(new.id)
            if existing is not None and existing.template == new:
                if existing.hidden and existing.path is not None:
                    self._write(existing.template, False, existing.path)
                return replace(existing, hidden=False)
            path = self._folder / f"{new.id}.json"
            if existing is None and self._write(new, False, path, new_file=True):
                return library_entry(new, default_for=[], path=path)
        raise AssertionError("unreachable: count() never ends")

    def hide(self, template_id: str) -> LibraryEntry:
        """Leave the saved Prompt template out of the list from now on, and return it. It still resolves for the games
        and probes that ask for it by its ID. Raises InvalidSettings if the library has no such template
        (unknown_prompt_template) or it is a default one (default_prompt_template), whose text is a file of the code."""
        entry = self.entry(template_id)
        if entry.path is None:
            refused = f"{entry.template.name} is a default Prompt template: only a saved one can be hidden"
            raise InvalidSettings(refused, code="default_prompt_template")
        self._write(entry.template, True, entry.path)
        return replace(entry, hidden=True)

    def _all(self) -> list[LibraryEntry]:
        return default_entries() + [saved(path) for path in sorted(self._folder.glob("*.json"))]

    def _write(self, template: PromptTemplate, hidden: bool, path: Path, new_file: bool = False) -> bool:
        """Write the template's file as saved() reads it, all at once through a temporary file, so a crash never
        leaves half a file. A new_file never replaces a file already there: False when its name is taken."""
        self._folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps(template.log_shape() | {"hidden": hidden}, indent=2, ensure_ascii=False) + "\n"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self._folder, suffix=".tmp", delete=False) as file:
            file.write(text)
        try:
            if not new_file:
                os.replace(file.name, path)
                return True
            try:
                os.link(file.name, path)  # refused if the name is taken, where a check then a write could race
            except FileExistsError:
                return False
            return True
        finally:
            Path(file.name).unlink(missing_ok=True)


def default_entries() -> list[LibraryEntry]:
    """The default Prompt templates as their files say now: Default, Described and Moves without the Legal-move list,
    then with it, then the Tools template. Each is the Default of the LLM constraints and Turn memories side_template
    plays it under: Default under fresh and chat_position, Moves under chat_moves."""
    templates: dict[str | None, PromptTemplate] = {}
    default_for: dict[str | None, list[tuple[LlmConstraints, TurnMemory]]] = {}
    for llm_constraints in sorted(LLM_CONSTRAINTS, key=lambda constraints: constraints in LISTED):
        for kind in get_args(DefaultTemplate):
            template = default_template(llm_constraints, kind)
            templates.setdefault(template.id, template)
            default_for.setdefault(template.id, [])
        for turn_memory in TURN_MEMORIES:
            default = side_template(LlmSide(llm_constraints=llm_constraints, turn_memory=turn_memory)).id
            default_for[default].append((llm_constraints, turn_memory))
    defaults = [library_entry(template, default_for[template_id]) for template_id, template in templates.items()]
    # The Tools template, the default of a side with Tools: hidden, as the app can't give a side tools to call
    # (ADR 0011), yet it resolves for a game that played it.
    return defaults + [library_entry(tools_template(), default_for=[], hidden=True)]


def library_entry(
    template: PromptTemplate,
    default_for: list[tuple[LlmConstraints, TurnMemory]],
    hidden: bool = False,
    path: Path | None = None,
) -> LibraryEntry:
    """The template's entry, with the LLM constraints and the Turn memories a side can play it under."""
    pairs = [
        (llm_constraints, turn_memory)
        for llm_constraints in LLM_CONSTRAINTS
        for turn_memory in TURN_MEMORIES
        if fits(template, llm_constraints, turn_memory)
    ]
    fitting = [llm_constraints for llm_constraints in LLM_CONSTRAINTS if llm_constraints in dict(pairs)]
    memories = [turn_memory for turn_memory in TURN_MEMORIES if turn_memory in {memory for _, memory in pairs}]
    return LibraryEntry(template, fitting, memories, default_for, hidden, path)


def fits(template: PromptTemplate, llm_constraints: LlmConstraints, turn_memory: TurnMemory) -> bool:
    """Whether a side can play the template under the LLM constraints and Turn memory."""
    try:
        check_prompt_template(template, llm_constraints, turn_memory)
    except InvalidSettings:
        return False
    return True


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
    return library_entry(template, default_for=[], hidden=shape.get("hidden", False), path=path)
