"""Anchor match: a Model player (an LLM or a System 1 model) plays an Anchor, run unattended in batches from the
command line."""

from chessllm.game.modes.base import Mode

ANCHOR_MATCH = Mode(
    key="anchor_match", name="Anchor match", sides={"human": 0, "model": 1, "anchor": 1}, unattended=True, rated=True
)
