"""LLM faceoff: a Model player (an LLM or a System 1 model) plays each side, two different models or one model
against itself."""

from chessllm.game.modes.base import Mode

LLM_FACEOFF = Mode(
    key="llm_faceoff", name="LLM faceoff", sides={"human": 0, "model": 2, "anchor": 0}, unattended=True, rated=True
)
