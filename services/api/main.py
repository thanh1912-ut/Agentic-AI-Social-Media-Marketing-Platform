"""FastAPI application entry point."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import auth, documents, jobs, workspaces
from .config import settings
from .db import create_schema
from .errors import ApiProblem, api_problem_handler, error_body


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_create_schema:
        await create_schema()
    yield


app = FastAPI(
    title="Agentic AI Social Media Marketing Platform API",
    version="0.1.0",
    description="Backend source of truth for tenant-scoped marketing workflows.",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "Authorization", "Idempotency-Key", "X-CSRF-Token"],
)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled request error request_id=%s path=%s", request_id, request.url.path)
        response = JSONResponse(
            status_code=500,
            content=error_body(ApiProblem(500, "internal_error", "Hệ thống gặp lỗi. Vui lòng thử lại.", retryable=True), request_id),
        )
    response.headers["X-Request-ID"] = request_id
    return response


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    field_errors = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", []) if part not in {"body", "query", "path", "header"}]
        field_errors.append({"field": ".".join(location) or "request", "message": "Giá trị không hợp lệ."})
    problem = ApiProblem(422, "validation_error", "Dữ liệu gửi lên chưa hợp lệ.", field_errors=field_errors)
    return JSONResponse(status_code=422, content=error_body(problem, getattr(request.state, "request_id", "req_unknown")))


app.add_exception_handler(ApiProblem, api_problem_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")


@app.get("/healthz", tags=["health"])
async def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/readyz", tags=["health"])
async def readyz():
    return {"status": "ready"}
