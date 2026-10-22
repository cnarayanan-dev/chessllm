"""The Modes, looked up by the key the API and the game log give them."""

from chessllm.core.types import ModeKey
from chessllm.game.modes.anchor_match import ANCHOR_MATCH
from chessllm.game.modes.base import Mode
from chessllm.game.modes.llm_faceoff import LLM_FACEOFF
from chessllm.game.modes.play_llm import PLAY_LLM

MODES: dict[ModeKey, Mode] = {"play_llm": PLAY_LLM, "llm_faceoff": LLM_FACEOFF, "anchor_match": ANCHOR_MATCH}


def mode_named(key: object) -> Mode | None:
    """The Mode with this key, e.g. a game log's, or None if none has it."""
    return next((mode for mode in MODES.values() if mode.key == key), None)


__all__ = ["ANCHOR_MATCH", "LLM_FACEOFF", "MODES", "PLAY_LLM", "Mode", "mode_named"]
