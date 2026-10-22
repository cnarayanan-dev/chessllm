"""Anchor match: an LLM plays an Anchor, run unattended in batches from the command line."""

from chessllm.game.modes.base import Mode

ANCHOR_MATCH = Mode(
    key="anchor_match", name="Anchor match", sides={"human": 0, "llm": 1, "anchor": 1}, unattended=True, rated=True
)
