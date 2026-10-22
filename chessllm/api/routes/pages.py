"""The React app's pages, from its build, refused when the build was made for a different API."""

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse

from chessllm.api.deps import ConfigDep
from chessllm.core.config import AppConfig

# The fingerprint of the API description the build's types (frontend/src/api/schema.ts) were made from.
BUILD_FINGERPRINT_FILE = "api-fingerprint.txt"

router = APIRouter()


def api_fingerprint(description: dict[str, Any]) -> str:
    """The sha256 of an OpenAPI description, written canonically, so that the same API always gives the same one."""
    canonical = json.dumps(description, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@router.get("/", include_in_schema=False, response_model=None)
@router.get("/analytics", include_in_schema=False, response_model=None)
def page(config: ConfigDep, request: Request) -> FileResponse | PlainTextResponse:
    """The React app, from its build: the game at /, the analytics page at /analytics.

    A build made for a different API is refused rather than left to break in the browser."""
    dist_dir = config.dist_dir
    index = dist_dir / "index.html"
    if not index.is_file():
        return PlainTextResponse(
            f"The frontend isn't built: {index} is missing. Run `pnpm install && pnpm build` in frontend/, "
            "then reload this page.",
            status_code=503,
        )
    built_for = build_fingerprint(config)
    # Taken from the app's own description, which FastAPI builds once, on first use, with every route in it.
    running = api_fingerprint(request.app.openapi())
    if built_for != running:
        return PlainTextResponse(
            f"The frontend build in {dist_dir} was made for a different API (fingerprint {built_for or 'missing'}) "
            f"than the one running (fingerprint {running}). Run `pnpm install && pnpm build` in frontend/, "
            "then reload this page. If the API itself changed, run `uv run python -m scripts.generate_api_types` "
            "first.",
            status_code=503,
        )
    return FileResponse(index)


def build_fingerprint(config: AppConfig) -> str | None:
    try:
        return (config.dist_dir / BUILD_FINGERPRINT_FILE).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
