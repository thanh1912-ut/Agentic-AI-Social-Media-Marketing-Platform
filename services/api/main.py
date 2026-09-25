"""FastAPI application entry point."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import analytics, auth, brand_profiles, campaign_workflows, documents, jobs, market_research, media, meta, workspaces
from .config import settings
from .db import create_schema, engine
from .errors import ApiProblem, api_problem_handler, error_body
from .request_limits import RequestBodyLimitMiddleware
from .storage import storage_ready


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    rate_limiter = Redis.from_url(settings.redis_url) if settings.rate_limits_enabled else None
    response_cache = Redis.from_url(
        settings.redis_cache_url, decode_responses=True,
        socket_connect_timeout=2, socket_timeout=2,
    )
    app.state.rate_limiter = rate_limiter
    app.state.response_cache = response_cache
    try:
        if settings.auto_create_schema:
            await create_schema()
        yield
    finally:
        if rate_limiter is not None:
            await rate_limiter.aclose()
        await response_cache.aclose()


app = FastAPI(
    title="Agentic AI Social Media Marketing Platform API",
    version="0.1.0",
    description="Backend source of truth for tenant-scoped marketing workflows.",
    openapi_url=None if settings.app_env.casefold() in {"prod", "production"} else "/api/openapi.json",
    docs_url=None if settings.app_env.casefold() in {"prod", "production"} else "/api/docs",
    redoc_url=None if settings.app_env.casefold() in {"prod", "production"} else "/api/redoc",
    lifespan=lifespan,
)

app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)


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


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-CSRF-Token"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))


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
app.include_router(media.router, prefix="/api/v1")
app.include_router(brand_profiles.router, prefix="/api/v1")
app.include_router(campaign_workflows.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(meta.router, prefix="/api/v1")
app.include_router(market_research.router, prefix="/api/v1")


@app.get("/healthz", tags=["health"])
async def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/readyz", tags=["health"])
async def readyz():
    components = {"database": False, "redis": False, "cache": False, "object_storage": False}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        components["database"] = True
    except Exception:
        pass
    redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await redis.ping()
        components["redis"] = True
    except Exception:
        pass
    finally:
        await redis.aclose()
    cache = Redis.from_url(settings.redis_cache_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await cache.ping()
        components["cache"] = True
    except Exception:
        pass
    finally:
        await cache.aclose()
    try:
        components["object_storage"] = await storage_ready()
    except Exception:
        pass
    ready = components["database"] and components["redis"] and components["object_storage"]
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "dependencies": components},
    )
