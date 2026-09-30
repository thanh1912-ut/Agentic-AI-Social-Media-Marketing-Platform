"""Native Graph transport tests for bounded comment/reply traversal, without network."""

import asyncio
from dataclasses import asdict

import httpx
import pytest

from services.api.meta_client import MetaGraphClient, MetaGraphReadError


TOKEN = "synthetic-comment-page-token"


def run(coroutine):
    return asyncio.run(coroutine)


def test_comment_pages_preserve_text_and_missing_counts_without_author_identity():
    seen = []

    async def handler(request):
        seen.append(request)
        assert request.url.path == "/v26.0/123_456/comments"
        assert "from" not in request.url.params["fields"]
        assert "attachment" not in request.url.params["fields"]
        assert request.url.params["filter"] == "toplevel"
        assert request.url.params["order"] == "chronological"
        assert TOKEN not in str(request.url)
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        if "after" not in request.url.params:
            return httpx.Response(200, json={
                "data": [{"id": "456_1", "message": "Nội dung " + "x" * 5000,
                          "created_time": "2026-10-01T00:00:00+0700", "like_count": 0, "comment_count": 2,
                          "from": {"id": "999", "name": "Never expose this author"}}],
                "summary": {"total_count": 2},
                "paging": {"next": f"https://graph.facebook.com/v26.0/123_456/comments?after=cursor-1&access_token={TOKEN}",
                           "cursors": {"after": "cursor-1"}},
            })
        assert request.url.params["after"] == "cursor-1"
        return httpx.Response(200, json={"data": [{"id": "456_2"}]})

    async def exercise():
        async with MetaGraphClient("123", TOKEN, transport=httpx.MockTransport(handler)) as client:
            first = await client.list_comments_page("123_456", limit=2)
            second = await client.list_comments_page("123_456", limit=2, after=first.next_cursor)
            return first, second

    first, second = run(exercise())
    assert len(seen) == 2
    assert first.pagination_exhausted is False
    assert first.provider_reported_count == 2
    assert first.comments[0].likes == 0  # Explicit likes, never called reactions.
    assert first.comments[0].reply_count == 2
    assert len(first.comments[0].message) > 4000
    assert first.comments[0].content_truncated is False
    assert "Never expose this author" not in str(asdict(first))
    assert "Nội dung" not in repr(first.comments[0])
    assert "456_1" not in repr(first.comments[0])
    assert second.comments[0].message is None
    assert second.comments[0].likes is None
    assert second.comments[0].reply_count is None
    assert second.provider_reported_count is None
    assert second.pagination_exhausted is True


def test_reply_edge_is_separate_and_private_hidden_records_are_withheld():
    async def handler(request):
        assert request.url.path == "/v26.0/456_1/comments"
        return httpx.Response(200, json={"data": [
            {"id": "456_10", "message": "Reply", "parent": {"id": "456_1"}},
            {"id": "456_11", "message": "Private", "is_private": True},
            {"id": "456_12", "message": "Hidden", "is_hidden": True},
        ]})

    async def exercise():
        async with MetaGraphClient("123", TOKEN, transport=httpx.MockTransport(handler)) as client:
            return await client.list_comments_page("123_456", parent_comment_id="456_1", limit=3)

    result = run(exercise())
    assert len(result.comments) == 1
    assert result.comments[0].root_post_id == "123_456"
    assert result.comments[0].parent_comment_id == "456_1"
    assert result.withheld_private_count == 2
    assert "Private" not in str(asdict(result)) and "Hidden" not in str(asdict(result))


@pytest.mark.parametrize("paging", [
    {"next": "http://127.0.0.1/private", "cursors": {"after": "next"}},
    {"next": "https://graph.facebook.com/v26.0/999/comments", "cursors": {"after": "next"}},
    {"next": "https://graph.facebook.com/v26.0/123_456/comments", "cursors": {}},
    {"next": "https://graph.facebook.com/v26.0/123_456/comments", "cursors": {"after": "current"}},
    {"next": "https://graph.facebook.com/v26.0/123_456/comments", "cursors": {"after": "https://127.0.0.1/"}},
])
def test_bad_or_stalled_pagination_is_not_called_complete(paging):
    async def handler(_request):
        return httpx.Response(200, json={"data": [], "paging": paging})

    async def exercise():
        async with MetaGraphClient("123", TOKEN, transport=httpx.MockTransport(handler)) as client:
            await client.list_comments_page("123_456", after="current")

    with pytest.raises(MetaGraphReadError) as error:
        run(exercise())
    assert TOKEN not in str(error.value)


@pytest.mark.parametrize("records", [
    None, [{"id": "../profile"}], [{"id": "1"}, {"id": "1"}],
    [{"id": "1", "parent": {"id": "999"}}], [{"id": "1", "message": {"private": "data"}}],
])
def test_invalid_comment_page_is_rejected_without_raw_content(records):
    async def handler(_request):
        return httpx.Response(200, json={"data": records})

    async def exercise():
        async with MetaGraphClient("123", TOKEN, transport=httpx.MockTransport(handler)) as client:
            await client.list_comments_page("123_456")

    with pytest.raises(MetaGraphReadError):
        run(exercise())


def test_comment_text_limit_is_explicit_not_silent():
    async def handler(_request):
        return httpx.Response(200, json={"data": [{"id": "456_1", "message": "x" * 20001}]})

    async def exercise():
        async with MetaGraphClient("123", TOKEN, transport=httpx.MockTransport(handler)) as client:
            return await client.list_comments_page("123_456")

    result = run(exercise())
    assert len(result.comments[0].message) == 20000
    assert result.comments[0].content_truncated is True


def test_500_top_level_comments_continue_by_cursor_without_claiming_reply_coverage():
    requests = 0

    async def handler(request):
        nonlocal requests
        requests += 1
        start = int(request.url.params.get("after", "0"))
        end = min(start + 100, 500)
        payload = {"data": [{"id": f"456_{index + 1}", "message": "Same caption", "comment_count": 1}
                            for index in range(start, end)], "summary": {"total_count": 500}}
        if end < 500:
            payload["paging"] = {"next": f"https://graph.facebook.com/v26.0/123_456/comments?after={end}",
                                 "cursors": {"after": str(end)}}
        return httpx.Response(200, json=payload)

    async def exercise():
        ids = []
        cursor = None
        async with MetaGraphClient("123", TOKEN, transport=httpx.MockTransport(handler)) as client:
            for _ in range(5):
                page = await client.list_comments_page("123_456", after=cursor)
                ids.extend(record.external_id for record in page.comments)
                cursor = page.next_cursor
            return ids, page

    ids, last = run(exercise())
    assert requests == 5 and len(ids) == len(set(ids)) == 500
    assert last.pagination_exhausted is True
    assert all(comment.reply_count == 1 for comment in last.comments)
    # Root exhaustion does not mean these 500 separate reply edges were read.
