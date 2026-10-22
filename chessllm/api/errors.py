"""The API's error responses: the one table from each error a request can meet to its HTTP status.

A route raises the error and declares it in its OpenAPI responses with error_responses; the handlers that
register_error_handlers puts on the app turn it into an ErrorDetail. FastAPI's own 422 for a malformed request keeps
its own shape."""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chessllm.exceptions import (
    ChessLlmError,
    InvalidSamplingConfig,
    InvalidSettings,
    NoGameStarted,
    RefusedLlmTurn,
    RejectedHumanMove,
)

STATUSES: dict[type[ChessLlmError], int] = {
    InvalidSettings: 400,
    RejectedHumanMove: 400,
    NoGameStarted: 404,
    RefusedLlmTurn: 409,
    InvalidSamplingConfig: 500,
}


class ErrorDetail(BaseModel):
    """Why the API refused a request: the message to show, and its code (e.g. game_over), which says which refusal
    it is without parsing the message."""

    detail: str
    code: str


def error_responses(*errors: type[ChessLlmError]) -> dict[int | str, dict[str, Any]]:
    """A route's OpenAPI responses for the errors it can raise, each an ErrorDetail under its status."""
    return {STATUSES[error]: {"model": ErrorDetail, "description": error.__doc__} for error in errors}


def register_error_handlers(app: FastAPI) -> None:
    """Answer each error of the table with its status and an ErrorDetail."""
    for error, status in STATUSES.items():
        app.add_exception_handler(error, error_handler(status))


def error_handler(status: int) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def handle(request: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, ChessLlmError)  # registered only for the errors of the table
        return JSONResponse(ErrorDetail(detail=str(error), code=error.code).model_dump(), status_code=status)

    return handle
