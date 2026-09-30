"""Exercise the Graph client's streaming boundary without network access."""

from __future__ import annotations

import asyncio
import gzip
import json
import zlib

import httpx
import pytest

from services.api import meta_client
from services.api.meta_client import (
    MetaGraphClient,
    MetaGraphOutcomeUnknown,
    MetaGraphReadError,
    MetaGraphRejected,
    MetaGraphTokenExpired,
    _MAX_GRAPH_RESPONSE_BYTES,
)


class GraphStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes, *, fail_after_body: bool = False) -> None:
        self.body = body
        self.fail_after_body = fail_after_body
        self.read_bytes = 0
        self.closed = False

    async def __aiter__(self):
        for start in range(0, len(self.body), 8192):
            chunk = self.body[start:start + 8192]
            self.read_bytes += len(chunk)
            yield chunk
        if self.fail_after_body:
            raise httpx.ReadError("upstream contained a synthetic-private-secret")

    async def aclose(self) -> None:
        self.closed = True


def run_graph(stream: GraphStream, *, headers=None, status=200, publishing=False):
    async def handler(request: httpx.Request):
        assert request.headers["accept-encoding"] == "identity"
        assert request.url.host == "graph.facebook.com"
        return httpx.Response(status, headers=headers, stream=stream)

    async def exercise():
        async with MetaGraphClient("123", "synthetic-private-secret", transport=httpx.MockTransport(handler)) as client:
            if publishing:
                return await client.publish_text("Synthetic fixture only")
            await client.verify_posts_read_access()

    return asyncio.run(exercise())


@pytest.mark.parametrize("length", [None, "1"])
def test_untrusted_stream_is_stopped_before_reading_unbounded_json(length) -> None:
    stream = GraphStream(b" " * (_MAX_GRAPH_RESPONSE_BYTES + 1024 * 1024))
    headers = {"content-length": length} if length else None
    with pytest.raises(MetaGraphReadError, match="2 MiB") as error:
        run_graph(stream, headers=headers)
    assert stream.closed
    assert stream.read_bytes <= _MAX_GRAPH_RESPONSE_BYTES + 64 * 1024
    assert stream.read_bytes < len(stream.body)
    assert "synthetic-private-secret" not in str(error.value)


def test_oversized_declared_length_is_rejected_without_reading_body() -> None:
    stream = GraphStream(b'{"data": []}')
    with pytest.raises(MetaGraphReadError, match="2 MiB"):
        run_graph(stream, headers={"content-length": str(_MAX_GRAPH_RESPONSE_BYTES + 1)})
    assert stream.closed and stream.read_bytes == 0


def test_exact_decoded_byte_limit_remains_valid_json() -> None:
    prefix, suffix = b'{"data":[],"padding":"', b'"}'
    payload = prefix + b"x" * (_MAX_GRAPH_RESPONSE_BYTES - len(prefix) - len(suffix)) + suffix
    assert len(payload) == _MAX_GRAPH_RESPONSE_BYTES
    stream = GraphStream(payload)
    run_graph(stream)
    assert stream.closed and stream.read_bytes == _MAX_GRAPH_RESPONSE_BYTES


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
def test_bounded_decompression_preserves_normal_graph_json(encoding, compress) -> None:
    payload = json.dumps({"data": [], "example": "Tiếng Việt"}, ensure_ascii=False).encode()
    stream = GraphStream(compress(payload))
    run_graph(stream, headers={"content-encoding": encoding})
    assert stream.closed


@pytest.mark.parametrize("encoding,compress", [("gzip", gzip.compress), ("deflate", zlib.compress)])
def test_small_compressed_response_cannot_expand_beyond_decoded_limit(encoding, compress) -> None:
    stream = GraphStream(compress(b"x" * (_MAX_GRAPH_RESPONSE_BYTES * 8)))
    assert len(stream.body) < _MAX_GRAPH_RESPONSE_BYTES
    with pytest.raises(MetaGraphReadError, match="2 MiB"):
        run_graph(stream, headers={"content-encoding": encoding})
    assert stream.closed


@pytest.mark.parametrize("body,encoding", [
    (b"not-gzip", "gzip"),
    (gzip.compress(b'{"data":[]}')[:-2], "gzip"),
    (gzip.compress(b'{"data":[]}') + gzip.compress(b"extra"), "gzip"),
    (b"compressed", "br"),
])
def test_invalid_or_unsupported_encoding_fails_without_partial_success(body, encoding) -> None:
    stream = GraphStream(body)
    with pytest.raises(MetaGraphReadError):
        run_graph(stream, headers={"content-encoding": encoding})
    assert stream.closed


@pytest.mark.parametrize("status,expected", [
    (200, MetaGraphOutcomeUnknown),
    (401, MetaGraphTokenExpired),
    (403, MetaGraphRejected),
])
def test_oversized_publish_response_keeps_outcome_and_rejection_semantics(status, expected) -> None:
    stream = GraphStream(b"unexpected")
    with pytest.raises(expected) as error:
        run_graph(stream, status=status, headers={"content-length": str(_MAX_GRAPH_RESPONSE_BYTES + 1)}, publishing=True)
    assert stream.closed and stream.read_bytes == 0
    assert "synthetic-private-secret" not in str(error.value)


@pytest.mark.parametrize("status", [302, 408, 500, 503])
def test_upstream_failure_does_not_buffer_or_follow_the_body(status) -> None:
    stream = GraphStream(b"not needed")
    with pytest.raises(MetaGraphOutcomeUnknown):
        run_graph(stream, status=status, headers={"location": "http://127.0.0.1/private"}, publishing=True)
    assert stream.closed and stream.read_bytes == 0


@pytest.mark.parametrize("status,expected", [(200, MetaGraphOutcomeUnknown), (403, MetaGraphRejected)])
def test_stream_failure_after_headers_is_closed_and_sanitized(status, expected) -> None:
    stream = GraphStream(b"partial", fail_after_body=True)
    with pytest.raises(expected) as error:
        run_graph(stream, status=status, publishing=True)
    assert stream.closed
    assert "synthetic-private-secret" not in str(error.value)


def test_unreadable_json_depth_returns_sanitized_read_error() -> None:
    stream = GraphStream(b"[" * 2000 + b"0" + b"]" * 2000)
    with pytest.raises(MetaGraphReadError):
        run_graph(stream)
    assert stream.closed


@pytest.mark.parametrize("publishing,expected", [(False, MetaGraphReadError), (True, MetaGraphOutcomeUnknown)])
def test_entire_stream_has_a_deadline_even_when_per_read_timeout_is_not_reached(monkeypatch, publishing, expected) -> None:
    class SlowStream(GraphStream):
        async def __aiter__(self):
            await asyncio.sleep(0.02)
            yield b'{"data": []}'

    monkeypatch.setattr(meta_client, "_GRAPH_REQUEST_DEADLINE_SECONDS", 0.001)
    stream = SlowStream(b"")
    with pytest.raises(expected):
        run_graph(stream, publishing=publishing)
    assert stream.closed
