from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route

from services.api.request_limits import RequestBodyLimitMiddleware


def make_test_app(max_bytes: int) -> tuple[Starlette, list[int]]:
    accepted_sizes: list[int] = []

    async def accept(request: Request) -> JSONResponse:
        body = await request.body()
        accepted_sizes.append(len(body))
        return JSONResponse({"size": len(body), "content_length": request.headers.get("content-length")})

    app = Starlette(routes=[Route("/echo", accept, methods=["POST"])])
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=max_bytes)
    return app, accepted_sizes


def test_request_body_limit_allows_exact_limit_and_rejects_declared_oversize() -> None:
    app, accepted_sizes = make_test_app(8)
    with TestClient(app) as client:
        exact = client.post("/echo", content=b"12345678")
        rejected = client.post("/echo", content=b"123456789")

    assert exact.status_code == 200
    assert exact.json() == {"size": 8, "content_length": "8"}
    assert rejected.status_code == 413
    assert rejected.json()["error"]["code"] == "request_too_large"
    assert rejected.headers["X-Request-ID"] == rejected.json()["error"]["request_id"]
    assert accepted_sizes == [8]


def test_request_body_limit_counts_streamed_chunks_without_content_length() -> None:
    app, accepted_sizes = make_test_app(8)
    with TestClient(app) as client:
        response = client.post("/echo", content=iter([b"12345", b"6789"]))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"
    assert accepted_sizes == []
