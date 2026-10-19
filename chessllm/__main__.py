"""Start the app locally: uv run python -m chessllm"""

import uvicorn

from chessllm.app import create_app
from chessllm.game import Settings
from chessllm.ollama_models import sampling_defaults
from chessllm.ollama_player import OllamaPlayer


def player_for(settings: Settings) -> OllamaPlayer:
    """The LLM player of one game, built when the game starts."""
    return OllamaPlayer(settings.model, settings.thinking, sampling=settings.sampling)


def main() -> None:
    uvicorn.run(create_app(player_for, sampling_defaults=sampling_defaults), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
