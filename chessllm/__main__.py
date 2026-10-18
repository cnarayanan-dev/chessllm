"""Start the app locally: uv run python -m chessllm"""

import uvicorn

from chessllm.app import create_app
from chessllm.players import FirstLegalMovePlayer


def main() -> None:
    uvicorn.run(create_app(FirstLegalMovePlayer()), host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
