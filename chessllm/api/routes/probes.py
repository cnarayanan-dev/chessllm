"""Probes (ADR 0010): a past LLM turn of the current game asked again with any Prompt template, outside the game, and
the probes of any game, from its probe log."""

from typing import Annotated

from fastapi import APIRouter, Path

from chessllm.api.deps import ConfigDep, CurrentGame, PromptLibraryDep
from chessllm.api.errors import error_responses
from chessllm.api.schemas.probes import ProbeRequest
from chessllm.exceptions import InvalidSettings, NoGameStarted, NoLlmTurn, RefusedProbe
from chessllm.game.llm_turn.probe import Probe
from chessllm.game.prompt_library import PromptLibrary
from chessllm.game.sides import PromptTemplate
from chessllm.logs.probe_log import ProbeLog

router = APIRouter()

GameId = Annotated[str, Path(pattern="^[0-9a-f]{32}$")]


@router.post(
    "/api/games/current/probes",
    responses=error_responses(InvalidSettings, NoGameStarted, NoLlmTurn, RefusedProbe),
)
def probe_turn(request: ProbeRequest, session: CurrentGame, library: PromptLibraryDep) -> Probe:
    """Ask the LLM of a past turn of the current game about the position before it, with a fresh Prompt built from
    the template, by the side's model, thinking and sampling, in one call judged as an attempt. The probe is appended
    to the game's probe log; the game and its log are unchanged. Refused while an LLM turn runs."""
    return session.probe(request.ply, request.color, probe_template(request, library))


def probe_template(request: ProbeRequest, library: PromptLibrary) -> PromptTemplate | None:
    """The Prompt template a probe asks with: the unsaved text given, a template with no ID, the library's by its ID,
    or None for the one the game recorded for the side. Raises InvalidSettings (unknown_prompt_template) if the
    library has no such ID."""
    if request.system_prompt is not None and request.turn_template is not None:
        return PromptTemplate(id=None, name=None, system_prompt=request.system_prompt, turn_template=request.turn_template)
    if request.prompt_template_id is None:
        return None
    template = library.template(request.prompt_template_id)
    if template is None:
        refused = f"The Prompt library has no Prompt template {request.prompt_template_id} to probe with"
        raise InvalidSettings(refused, code="unknown_prompt_template")
    return template


@router.get("/api/games/{game_id}/probes")
def list_probes(game_id: GameId, config: ConfigDep) -> list[Probe]:
    """Every probe of the game, in the order asked, read from its probe log, so a game shows its probes again after
    a reload or a restart. None for a game never probed."""
    return ProbeLog(config.games_dir, game_id).probes()
