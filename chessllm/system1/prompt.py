"""The Prompt templates of a System 1 model (ADR 0012): its System prompt is the question it is asked, its Turn template
the state it is given. The options are always the legal moves, so a Turn template never places them."""

from string import Template

from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import check_prompt_template, text_version
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.sides import PromptTemplate, System1Side

# The defaults' parts: the question, and the state, the FEN and where every piece stands, with the moves so far or
# without.
QUESTION = "Which move should $color play?"
MOVES_FEN_AND_DESCRIPTION = "Moves so far: $moves\nFEN: $fen\n$description"
FEN_AND_PIECES = "FEN: $fen\n$pieces"


def system1_template(kind: str, name: str, system_prompt: str, turn_template: str) -> PromptTemplate:
    """A System 1 Prompt template of the library's style: its ID is its kind, and a version from its text after an @,
    e.g. "system1@1f0c2a9e", so an ID always means one text (ADR 0010)."""
    return PromptTemplate(f"{kind}@{text_version(system_prompt, turn_template)}", name, system_prompt, turn_template)


# The default System 1 Prompt template: the question, and as the state the FEN, where every piece stands and the moves
# so far. Its ID is what the batch commands pick it by.
DEFAULT_TEMPLATE = system1_template("system1", "System 1", QUESTION, MOVES_FEN_AND_DESCRIPTION)
# The same without the moves so far, to measure whether the move history helps. It is a Player configuration of its
# own, as its text differs (ADR 0010).
POSITION_ONLY_TEMPLATE = system1_template("system1-position-only", "System 1, position only", QUESTION, FEN_AND_PIECES)
SYSTEM1_TEMPLATES: dict[str, PromptTemplate] = {
    template.id: template for template in (DEFAULT_TEMPLATE, POSITION_ONLY_TEMPLATE)
}


def side_template(side: System1Side) -> PromptTemplate:
    """The Prompt template the side plays with: its own, or else the default."""
    return side.prompt_template or DEFAULT_TEMPLATE


def check_system1_template(template: PromptTemplate) -> None:
    """Raises InvalidSettings, saying why, if a System 1 side can't play the template: a placeholder it doesn't know, a
    $ that starts none, or a Turn template that places $legal_moves, as the options are the legal moves and never in
    the state."""
    if "legal_moves" in Template(template.turn_template).get_identifiers():
        reason = f"Prompt template {template.id}: the Turn template places $legal_moves, but a System 1 model's options are the legal moves, never in the state"
        raise InvalidSettings(reason, code="invalid_prompt_template")
    check_prompt_template(template, "free")


def resolve_system1_template(template_id: str, library: PromptLibrary) -> PromptTemplate:
    """The Prompt template a new game's System 1 side asks for by its ID: one of the System 1 defaults, else a
    saved one of the Prompt library. Raises InvalidSettings (unknown_prompt_template) if the library has none, and
    (check_system1_template) if the side couldn't play it."""
    template = SYSTEM1_TEMPLATES.get(template_id) or library.template(template_id)
    if template is None:
        reason = f"The Prompt library has no Prompt template {template_id}"
        raise InvalidSettings(reason, code="unknown_prompt_template")
    check_system1_template(template)
    return template
