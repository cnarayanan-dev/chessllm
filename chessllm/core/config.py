"""Every path and environment variable of the app, in one place.

Paths are taken from the project root, not the working directory, so the app reads its files and writes its game
logs to the project's games/ whichever folder it is started from. The project is installed editable (uv sync), so
the package directory is the one in the project."""

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).parent.parent  # chessllm/
PROJECT_ROOT = PACKAGE_DIR.parent

# One JSON Lines file per game, plus its PGN when it ends (ADR 0004), and its analysis file once analysed.
GAMES_DIR = PROJECT_ROOT / "games"
# The Markdown reports the benchmark's commands write, e.g. tools-experiment's tools-comparison-<date>.md.
REPORTS_DIR = PROJECT_ROOT / "reports"
# The sampling options every LLM side plays with; read at the start of every game.
SAMPLING_FILE = PACKAGE_DIR / "llm" / "sampling.toml"
# The outcome of the Move-quality validation (scripts/validate_move_quality.py).
VALIDATION_FILE = PACKAGE_DIR / "analytics" / "move_quality_validation.json"
# The system prompt templates, one per kind of LLM constraints.
PROMPTS_DIR = PACKAGE_DIR / "game" / "prompts"
# The Prompt library's saved Prompt templates, one JSON file each, kept in the repo so that their history is the
# project's (ADR 0010).
PROMPT_LIBRARY_DIR = PROJECT_ROOT / "prompt_library"
STATIC_DIR = PACKAGE_DIR / "static"
# The React app's build (frontend/, `pnpm build`), git-ignored. Its files are served under /static/dist/.
DIST_DIR = STATIC_DIR / "dist"

# How long Ollama gets to show a model; a stalled Ollama mustn't hang the New game sheet, which lists the models.
OLLAMA_SHOW_TIMEOUT_S = 3.0
# Long thinking can run for many minutes and still end without an answer, so a turn is cut off here.
OLLAMA_REPLY_TIMEOUT_S = 300.0

DRAGON_PATH_VARIABLE = "CHESSLLM_DRAGON"
STOCKFISH_PATH_VARIABLE = "CHESSLLM_STOCKFISH"


def dragon_path_from_environment() -> str | None:
    """The Dragon executable as CHESSLLM_DRAGON sets it, read when asked, so a change to the environment applies."""
    return os.environ.get(DRAGON_PATH_VARIABLE) or None


def stockfish_path_from_environment() -> str | None:
    """The Stockfish executable as CHESSLLM_STOCKFISH sets it, read when asked like Dragon's."""
    return os.environ.get(STOCKFISH_PATH_VARIABLE) or None


@dataclass(frozen=True)
class AppConfig:
    """The paths the app works with: the project's own, unless a test gives others."""

    games_dir: Path = GAMES_DIR
    sampling_file: Path = SAMPLING_FILE
    dist_dir: Path = DIST_DIR
    move_quality_validation: Path = VALIDATION_FILE
    static_dir: Path = STATIC_DIR
    prompt_library_dir: Path = PROMPT_LIBRARY_DIR
