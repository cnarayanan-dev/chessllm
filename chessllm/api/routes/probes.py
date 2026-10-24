"""Probes (ADR 0010): the LLM of a side asked again about one of its past turns with any Prompt template, outside the
game, and a game's probes listed from its probe log."""

from fastapi import APIRouter

from chessllm.api.deps import ConfigDep, CurrentGame, PromptLibraryDep
from chessllm.api.errors import error_responses
from chessllm.api.schemas.probes import ProbeRequest
from chessllm.exceptions import InvalidSettings, NoGameStarted, RefusedProbe
from chessllm.game.llm_turn.probe import Probe
from chessllm.logs.probe_log import probes_of

router = APIRouter()


@router.post("/api/games/current/probes", responses=error_responses(InvalidSettings, NoGameStarted, RefusedProbe))
def ask_probe(request: ProbeRequest, session: CurrentGame, library: PromptLibraryDep) -> Probe:
    """Ask a Probe about a past LLM turn of the current game, with a Prompt template of the library or unsaved text, and
    append it to the game's probe log. Refused while an LLM turn runs; a turn asked for while a probe runs waits for
    it."""
    template = request.unsaved()
    if template is None:
        assert request.prompt_template_id is not None  # ProbeRequest takes an ID or text
        template = library.resolve(request.prompt_template_id, request.color)
    return session.probe(request.ply, request.color, template)


@router.get("/api/games/{game_id}/probes")
def list_probes(game_id: str, config: ConfigDep) -> list[Probe]:
    """A game's Probes, in the order they were asked, read from its probe log: a reopened game shows them again, and a
    game the games folder doesn't hold has none."""
    return probes_of(config.games_dir, game_id)
