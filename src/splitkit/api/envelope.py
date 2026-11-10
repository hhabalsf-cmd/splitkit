"""Uniform {success, data, error} responses and exception handlers."""

from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("splitkit.api")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def finite(x: float) -> float | None:
    """JSON has no NaN/Infinity; report undefined values (e.g. lift over a 0 baseline) as null."""
    return x if math.isfinite(x) else None


def ok(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse({"success": True, "data": data, "error": None}, status_code=status)


def fail(status: int, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"success": False, "data": None, "error": message}, status_code=status, headers=headers)


def _describe_validation(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
        parts.append(f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg", "invalid")))
    return "; ".join(parts) or "invalid request"


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return fail(exc.status, exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return fail(422, _describe_validation(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return fail(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return fail(500, "internal server error")
