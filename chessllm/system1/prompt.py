"""The Prompt templates of a System 1 model (ADR 0012): its System prompt is the question it is asked, its Turn template
the state it is given. The options are always the legal moves, so a Turn template never places them."""

from string import Template

from chessllm.exceptions import InvalidSettings
from chessllm.game.llm_turn.prompt import check_prompt_template, text_version
from chessllm.game.sides import PromptTemplate, System1Side

# The default's parts: the question, and the state, the moves so far, the FEN and where every piece stands.
QUESTION = "Which move should $color play?"
MOVES_FEN_AND_DESCRIPTION = "Moves so far: $moves\nFEN: $fen\n$description"


def system1_template(kind: str, name: str, system_prompt: str, turn_template: str) -> PromptTemplate:
    """A System 1 Prompt template of the library's style: its ID is its kind, and a version from its text after an @,
    e.g. "system1@1f0c2a9e", so an ID always means one text (ADR 0010)."""
    return PromptTemplate(f"{kind}@{text_version(system_prompt, turn_template)}", name, system_prompt, turn_template)


# The default System 1 Prompt template: the question, and as the state the FEN, where every piece stands and the moves
# so far. Its ID is what the batch commands pick it by.
DEFAULT_TEMPLATE = system1_template("system1", "System 1", QUESTION, MOVES_FEN_AND_DESCRIPTION)
SYSTEM1_TEMPLATES: dict[str, PromptTemplate] = {DEFAULT_TEMPLATE.id: DEFAULT_TEMPLATE}


def side_template(side: System1Side) -> PromptTemplate:
    """The Prompt template the side plays with: its own, or else the default."""
    return side.prompt_template or DEFAULT_TEMPLATE


def check_system1_template(template: PromptTemplate) -> None:
    """Raises InvalidSettings, saying why, if a System 1 side can't play the template: a placeholder it doesn't know, a
    $ that starts none, or a Turn template that places $legal_moves, as the options are the legal moves and never in
    the state."""
    if "legal_moves" in Template(template.turn_template).get_identifiers():
        reason = "the Turn template places $legal_moves, but a System 1 model's options are the legal moves, never in the state"
        raise InvalidSettings(reason, code="invalid_prompt_template")
    check_prompt_template(template, "free")
