"""Stable error envelope and request correlation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass
class ApiProblem(Exception):
    status_code: int
    code: str
    message: str
    field_errors: list[dict[str, str]] | None = None
    details: dict[str, Any] | None = None
    retryable: bool = False


def error_body(problem: ApiProblem, request_id: str) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": problem.code,
        "message": problem.message,
        "field_errors": problem.field_errors or [],
        "request_id": request_id,
        "retryable": problem.retryable,
    }
    if problem.details:
        error["details"] = problem.details
    return {"error": error}


async def api_problem_handler(request: Request, exc: ApiProblem) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(status_code=exc.status_code, content=error_body(exc, request_id))

