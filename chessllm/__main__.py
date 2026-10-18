"""Start the app locally: uv run python -m chessllm"""

import uvicorn

from chessllm.app import create_app
from chessllm.game import Settings
from chessllm.ollama_player import OllamaPlayer


def main() -> None:
    settings = Settings()
    uvicorn.run(create_app(OllamaPlayer(settings.model), settings), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
