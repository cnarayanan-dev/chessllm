"""Play LLM: a human plays one side and an LLM the other."""

from chessllm.game.modes.base import Mode

# Its games don't count towards the Rating: the human's strength is unknown.
PLAY_LLM = Mode(
    key="play_llm", name="Play LLM", sides={"human": 1, "llm": 1, "anchor": 0}, unattended=False, rated=False
)
