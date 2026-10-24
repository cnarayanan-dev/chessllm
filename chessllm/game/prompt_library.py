"""The Prompt library (ADR 0010): the default Prompt templates, as their files say now, and the saved ones, each a
JSON file in the library's folder, so saved prompts show up in git. A saved Prompt template never changes: saving an
edit makes a new one, and an old one is only hidden, left out of the list but still resolving for the games and probes
that played it. A default can be hidden too, as the Tools template is, which only the benchmark's commands can play
(ADR 0011)."""

import json
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import DefaultTemplate, check_prompt_template, default_template, text_version
from chessllm.game.sides import LISTED, LlmConstraints, PromptTemplate, TurnMemory

LLM_CONSTRAINTS: tuple[LlmConstraints, ...] = get_args(LlmConstraints)
TURN_MEMORIES: list[TurnMemory] = list(get_args(TurnMemory))
# The Turn memories whose turns show the position, which every default template but Moves fits.
SHOWING_THE_POSITION: list[TurnMemory] = [memory for memory in TURN_MEMORIES if memory != "chat_moves"]
UNSAVED = "unsaved"  # the ID of text not saved in the library, before the @ and its version


def unsaved(system_prompt: str, turn_template: str) -> PromptTemplate:
    """A Prompt template not saved in the library, as a Probe asks with it and records it: with no name, and the ID
    "unsaved" with a version from its text, e.g. "unsaved@1f0c2a9e", so an ID still means one text and probes with the
    same text are tallied together."""
    return PromptTemplate(f"{UNSAVED}@{text_version(system_prompt, turn_template)}", None, system_prompt, turn_template)


@dataclass(frozen=True)
class LibraryEntry:
    """A Prompt template of the library, with the LLM constraints it fits (check_prompt_template), and those it is
    the Default of under the Turn memories it fits (check_turn_memory): what a side under them plays when it asks for
    no template."""

    template: PromptTemplate
    fits: list[LlmConstraints]
    default_for: list[LlmConstraints]
    hidden: bool = False
    # A default template's own: chat_moves alone for Moves, every other for the rest; a saved one's, all of them.
    turn_memories: list[TurnMemory] = field(default_factory=lambda: list(TURN_MEMORIES))
    saved: bool = False  # saved in the library's folder, rather than a default: only a saved one can be hidden


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

    def save(
        self, name: str | None, system_prompt: str, turn_template: str, llm_constraints: LlmConstraints
    ) -> LibraryEntry:
        """Save a new Prompt template, written for a side under the LLM constraints, in a file of its own, and return
        it with its new ID: its name's (or "saved") and a random version, so saving the same text twice still makes
        two. It never changes an existing one. Raises InvalidSettings (check_prompt_template) if the side couldn't play
        it, and then writes nothing."""
        check_prompt_template(unsaved(system_prompt, turn_template), llm_constraints)
        slug = re.sub("[^a-z0-9]+", "-", (name or "").lower()).strip("-") or "saved"
        self._folder.mkdir(parents=True, exist_ok=True)
        while True:
            template = PromptTemplate(f"{slug}@{secrets.token_hex(4)}", name, system_prompt, turn_template)
            shape = {"id": template.id, "name": name, "hidden": False}
            shape |= {"system_prompt": system_prompt, "turn_template": turn_template}
            try:
                with (self._folder / f"{template.id}.json").open("x", encoding="utf-8") as file:
                    file.write(json.dumps(shape, indent=2, ensure_ascii=False) + "\n")
            except FileExistsError:  # the version taken: draw another
                continue
            return LibraryEntry(template, fits(template), default_for=[], saved=True)

    def hide(self, template_id: str) -> None:
        """Leave a saved Prompt template out of the list from now on; it still resolves for the games and probes that
        played it. Raises InvalidSettings if the library has no saved template with this ID: a default can't be
        hidden, as its file is the code's."""
        path = next((path for path in self._saved_files() if saved(path).template.id == template_id), None)
        if path is None:
            if any(entry.template.id == template_id for entry in default_entries()):
                refused = f"{template_id} is a default Prompt template: only a saved one can be hidden"
                raise InvalidSettings(refused, code="default_prompt_template")
            refused = f"The Prompt library has no Prompt template {template_id}"
            raise InvalidSettings(refused, code="unknown_prompt_template")
        shape = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(shape | {"hidden": True}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _all(self) -> list[LibraryEntry]:
        return default_entries() + [saved(path) for path in self._saved_files()]

    def _saved_files(self) -> list[Path]:
        return sorted(self._folder.glob("*.json"))


def default_entries() -> list[LibraryEntry]:
    """The default Prompt templates as their files say now: Default and Described without the Legal-move list, then
    with it, each followed by Moves, the Default under Turn memory chat_moves and fitting no other, and Tools, the
    Default of a side with Tools. Tools is hidden, as the app can't give a side Tools."""
    templates: dict[str, PromptTemplate] = {}
    kinds: dict[str, DefaultTemplate] = {}
    default_for: dict[str, list[LlmConstraints]] = {}
    for llm_constraints in sorted(LLM_CONSTRAINTS, key=lambda constraints: constraints in LISTED):
        for kind in get_args(DefaultTemplate):
            template = default_template(llm_constraints, kind)
            templates.setdefault(template.id, template)
            kinds[template.id] = kind
            default_for.setdefault(template.id, [])
            if kind in ("default", "moves"):
                default_for[template.id].append(llm_constraints)
    return [
        LibraryEntry(
            template,
            fits(template),
            default_for[template_id],
            hidden=kinds[template_id] == "tools",
            turn_memories=["chat_moves"] if kinds[template_id] == "moves" else SHOWING_THE_POSITION,
        )
        for template_id, template in templates.items()
    ]


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
    return LibraryEntry(template, fits(template), default_for=[], hidden=shape.get("hidden", False), saved=True)
