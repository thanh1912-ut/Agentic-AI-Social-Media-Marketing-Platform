"""No-network contract tests for the Page Graph client."""

from __future__ import annotations

import asyncio
from datetime import timezone

import httpx
import pytest

from services.api.meta_client import (
    MetaGraphClient,
    MetaGraphOutcomeUnknown,
    MetaGraphReadError,
    MetaGraphRejected,
    MetaGraphTokenExpired,
    MetaPageIdentityMismatch,
    facebook_page_reference,
    safe_page_attachment_metadata,
    safe_external_link_url,
)


SECRET = "page-token-secret-must-not-leak"


def _run(awaitable):
    return asyncio.run(awaitable)


def test_verify_page_uses_bearer_header_and_returns_verified_identity() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https"
        assert request.url.host == "graph.facebook.com"
        assert SECRET not in str(request.url)
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        assert request.url.path == "/v26.0/me"
        assert request.url.params["fields"] == "id,name,picture"
        return httpx.Response(200, json={
            "id": "123", "name": " Trang của tôi ",
            "picture": {"data": {"url": "https://platform-lookaside.fbsbx.com/profile/photo.jpg?oh=signature&access_token=must-not-leak"}},
        })

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.verify_page()

    page = _run(exercise())
    assert (page.id, page.name) == ("123", "Trang của tôi")
    assert page.picture_url == "https://platform-lookaside.fbsbx.com/profile/photo.jpg?oh=signature"


def test_verify_page_discards_untrusted_avatar_hosts() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": "123", "name": "Trang của tôi",
            "picture": {"data": {"url": "https://attacker.example/avatar.png"}},
        })

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.verify_page()

    page = _run(exercise())
    assert page.picture_url is None


def test_verify_page_rejects_another_token_identity_without_exposing_it() -> None:
    async def handler(_request):
        return httpx.Response(200, json={"id": "999", "name": "Unrelated identity"})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            await client.verify_page()

    with pytest.raises(MetaPageIdentityMismatch) as error:
        _run(exercise())
    assert SECRET not in str(error.value)
    assert "999" not in str(error.value)


@pytest.mark.parametrize("records", [[], [{"id": "123_456"}]])
def test_onboarding_read_check_requires_only_post_ids(records) -> None:
    async def handler(request):
        assert request.url.path == "/v26.0/123/posts"
        assert dict(request.url.params) == {"fields": "id", "limit": "1"}
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        assert SECRET not in str(request.url)
        return httpx.Response(200, json={"data": records})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            await client.verify_posts_read_access()

    _run(exercise())


@pytest.mark.parametrize("payload", [{}, {"data": None}, {"data": [{"id": "999_456"}]}, {"data": [{"id": "123_1"}, {"id": "123_2"}]}])
def test_onboarding_read_check_rejects_invalid_or_out_of_scope_posts(payload) -> None:
    async def handler(_request):
        return httpx.Response(200, json=payload)

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            await client.verify_posts_read_access()

    with pytest.raises(MetaGraphReadError):
        _run(exercise())


@pytest.mark.parametrize(("url", "expected"), [
    ("https://www.facebook.com/thuonghieu", "thuonghieu"),
    ("https://facebook.com/pages/Thuong-Hieu/123456", "123456"),
    ("https://m.facebook.com/profile.php?id=123456", "123456"),
])
def test_facebook_page_reference_extracts_only_page_identity(url: str, expected: str) -> None:
    assert facebook_page_reference(url) == expected


@pytest.mark.parametrize("url", [
    "https://facebook.com/groups/123",
    "https://facebook.com/story.php?story_fbid=2&id=3",
    "https://evil.facebook.com/brand",
    "https://facebook.com/brand/posts/123",
])
def test_facebook_page_reference_rejects_non_page_urls(url: str) -> None:
    with pytest.raises(ValueError):
        facebook_page_reference(url)


def test_resolve_public_page_uses_app_reviewed_token_and_keeps_missing_followers_unknown() -> None:
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        assert SECRET not in str(request.url)
        nonlocal requests
        requests += 1
        if requests == 1:
            assert request.url.path == "/v26.0/brand-page"
            assert request.url.params["fields"] == "id,name"
            return httpx.Response(200, json={"id": "456", "name": "Trang đối thủ"})
        assert request.url.path == "/v26.0/456"
        assert request.url.params["fields"] == "followers_count"
        return httpx.Response(400, json={"error": {"code": 100}})

    async def exercise():
        async with MetaGraphClient("1", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.resolve_public_page("brand-page")

    page = _run(exercise())
    assert (page.id, page.name, page.followers_count) == ("456", "Trang đối thủ", None)
    assert requests == 2


def test_read_page_followers_and_post_media_views_use_current_page_metrics() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        assert SECRET not in str(request.url)
        if request.url.path == "/v26.0/123":
            assert request.url.params["fields"] == "followers_count"
            return httpx.Response(200, json={"followers_count": 4321})
        assert request.url.path == "/v26.0/123_456/insights"
        assert request.url.params["metric"] == "post_media_view"
        return httpx.Response(200, json={"data": [{
            "name": "post_media_view", "period": "lifetime", "values": [{"value": 9876}],
        }]})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            followers = await client.read_page_followers_count()
            views = await client.read_post_media_views("123_456")
            return followers, views

    assert _run(exercise()) == (4321, 9876)


def test_unavailable_post_media_views_remain_null_and_reject_other_page_posts() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{
            "name": "post_media_view", "period": "lifetime", "values": [{"value": None}],
        }]})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            assert await client.read_post_media_views("123_456") is None
            with pytest.raises(ValueError):
                await client.read_post_media_views("999_456")

    _run(exercise())


def test_text_and_photo_publish_require_post_ids() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {SECRET}"
        assert SECRET not in str(request.url)
        body = await request.aread()
        if request.url.path.endswith("/feed"):
            seen.append("text")
            assert b"message=Bai+viet+moi" in body
            return httpx.Response(200, json={"id": "123_456"})
        seen.append("photo")
        assert request.url.path == "/v26.0/123/photos"
        assert b'name="source"' in body
        assert b'name="caption"' in body
        assert b"picture bytes" in body
        return httpx.Response(200, json={"id": "789", "post_id": "123_790"})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            text_post = await client.publish_text("Bai viet moi")
            photo_post = await client.publish_photo("Anh moi", b"picture bytes", "image/png")
            return text_post, photo_post

    text_post, photo_post = _run(exercise())
    assert text_post.external_post_id == "123_456"
    assert photo_post.external_post_id == "123_790"
    assert seen == ["text", "photo"]


def test_photo_id_alone_is_not_mistaken_for_the_published_post() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "789"})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            await client.publish_photo("Caption", b"bytes", "image/jpeg")

    with pytest.raises(MetaGraphOutcomeUnknown, match="post ID is missing") as error:
        _run(exercise())
    assert SECRET not in str(error.value)


def test_read_post_metrics_only_returns_available_counts_and_valid_url() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v26.0/123_456"
        fields = request.url.params["fields"]
        assert "reactions.limit(0).summary(true)" in fields
        assert "comments.limit(0).summary(true)" in fields
        return httpx.Response(200, json={
            "id": "123_456",
            "reactions": {"summary": {"total_count": 12}},
            "comments": {"summary": {"total_count": 3}},
            "shares": {"count": 2},
            "permalink_url": "https://www.facebook.com/123/posts/456",
            "created_time": "2026-09-24T08:00:00+0000",
        })

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.read_post_metrics("123_456")

    metrics = _run(exercise())
    assert (metrics.reactions, metrics.comments, metrics.shares) == (12, 3, 2)
    assert metrics.created_time is not None and metrics.created_time.tzinfo == timezone.utc
    assert metrics.permalink_url == "https://www.facebook.com/123/posts/456"


def test_missing_metrics_remain_unavailable_not_zero() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "123_456", "permalink_url": "https://evil.example/path"})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.read_post_metrics("123_456")

    metrics = _run(exercise())
    assert metrics.reactions is None
    assert metrics.comments is None
    assert metrics.shares is None
    assert metrics.permalink_url is None


def test_list_historical_page_posts_uses_cursor_without_following_next_url() -> None:
    requests = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        assert request.url.host == "graph.facebook.com"
        assert request.url.path == "/v26.0/123/posts"
        assert request.url.params["limit"] == "2"
        assert "attachments.limit(20)" in request.url.params["fields"]
        assert SECRET not in str(request.url)
        if requests == 1:
            assert "after" not in request.url.params
            return httpx.Response(200, json={
                "data": [{
                    "id": "123_100", "message": "Bài đăng trực tiếp trên fanpage",
                    "created_time": "2026-09-20T08:00:00+0000",
                    "permalink_url": "https://www.facebook.com/123/posts/100",
                    "link": "https://example.com/article?utm_source=facebook&access_token=leak#fragment",
                    "attachments": {"data": [{
                        "media_type": "photo", "type": "photo", "title": "Ảnh sản phẩm",
                        "description": "Hình minh họa", "url": "https://example.com/product?token=private",
                        "subattachments": {"data": [{
                            "media_type": "video", "type": "video_inline", "title": "Video hướng dẫn",
                            "url": "https://video.example/watch?v=123",
                        }]},
                    }]},
                    "reactions": {"summary": {"total_count": 10}},
                    "comments": {"summary": {"total_count": 2}},
                    "shares": {"count": 1},
                }],
                "paging": {
                    "cursors": {"after": "opaque-cursor"},
                    "next": f"https://graph.facebook.com/v26.0/123/posts?after=opaque-cursor&access_token={SECRET}",
                },
            })
        assert request.url.params["after"] == "opaque-cursor"
        return httpx.Response(200, json={"data": [{"id": "123_101"}], "paging": {"cursors": {"after": "last"}}})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            first = await client.list_page_posts(limit=2)
            second = await client.list_page_posts(limit=2, after=first.next_cursor)
            return first, second

    first, second = _run(exercise())
    assert first.next_cursor == "opaque-cursor"
    assert len(first.posts) == 1
    assert first.posts[0].external_post_id == "123_100"
    assert first.posts[0].message == "Bài đăng trực tiếp trên fanpage"
    assert first.posts[0].link_url == "https://example.com/article"
    assert first.posts[0].attachment_metadata_status == "returned"
    assert [item["kind"] for item in first.posts[0].attachments] == ["image", "video"]
    assert first.posts[0].attachments[0]["target_url"] == "https://example.com/product"
    assert first.posts[0].attachments[0]["title"] is None
    assert first.posts[0].attachments[0]["description"] is None
    assert first.posts[0].attachments[0]["content_status"] == "metadata_only_privacy_hold"
    assert (first.posts[0].reactions, first.posts[0].comments, first.posts[0].shares) == (10, 2, 1)
    assert second.posts[0].external_post_id == "123_101"
    assert second.posts[0].reactions is None
    assert second.next_cursor is None


def test_list_page_posts_rejects_bad_page_and_cursor() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "999_100"}]})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ValueError):
                await client.list_page_posts(limit=0)
            with pytest.raises(ValueError):
                await client.list_page_posts(after="\n")
            with pytest.raises(MetaGraphReadError):
                await client.list_page_posts()

    _run(exercise())


def test_list_page_posts_falls_back_when_attachment_fields_are_not_available() -> None:
    seen_fields: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        fields = request.url.params["fields"]
        seen_fields.append(fields)
        if "attachments" in fields:
            return httpx.Response(400, json={"error": {"code": 100, "message": "field unavailable"}})
        return httpx.Response(200, json={"data": [{"id": "123_456", "message": "Readable text"}]})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.list_page_posts()

    page = _run(exercise())
    assert len(seen_fields) == 2
    assert "attachments" in seen_fields[0] and "attachments" not in seen_fields[1]
    assert page.posts[0].message == "Readable text"
    assert page.posts[0].attachment_metadata_status == "not_returned"


def test_list_page_posts_marks_attachment_metadata_truncated_at_provider_budget() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{
            "id": "123_456", "attachments": {"data": [
                {"media_type": "photo", "type": "photo", "title": f"Photo {index}"}
                for index in range(21)
            ]},
        }]})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.list_page_posts()

    post = _run(exercise()).posts[0]
    assert len(post.attachments) == 20
    assert post.attachment_metadata_status == "truncated"


def test_list_post_comments_requests_text_without_author_identity() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v26.0/123_456/comments"
        assert request.url.params["fields"] == "message"
        assert request.url.params["limit"] == "2"
        return httpx.Response(200, json={"data": [
            {"message": "Nội dung bình luận", "from": {"id": "private-user", "name": "Tên riêng"}},
            {"message": "  "},
        ]})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            return await client.list_post_comments("123_456", limit=2)

    assert _run(exercise()) == ("Nội dung bình luận",)


@pytest.mark.parametrize("value", [
    "javascript:alert(1)",
    "https://user:pass@example.com/",
    "http://127.0.0.1/private",
    "https://localhost/private",
])
def test_attachment_links_reject_non_web_or_local_targets(value: str) -> None:
    assert safe_external_link_url(value) is None


def test_attachment_links_strip_credentials_and_fragments() -> None:
    assert safe_external_link_url("https://example.com/path?token=secret&lang=vi#section") == (
        "https://example.com/path"
    )


def test_persisted_attachment_metadata_discards_free_text_and_revalidates_fields() -> None:
    item = safe_page_attachment_metadata([{
        "kind": [], "provider_type": "x" * 100, "title": "person@example.com",
        "description": "202-555-0198", "target_url": "https://example.com/item?sig=private",
        "content_status": "unexpected",
    }])[0]
    assert item == {
        "kind": "unknown", "provider_type": "x" * 80, "title": None, "description": None,
        "target_url": "https://example.com/item", "content_status": "metadata_only_privacy_hold",
    }


@pytest.mark.parametrize("status,code,expected", [
    (400, 190, MetaGraphTokenExpired),
    (401, None, MetaGraphTokenExpired),
    (403, 200, MetaGraphRejected),
    (429, 4, MetaGraphRejected),
])
def test_explicit_graph_4xx_are_sanitized_rejections(status: int, code: int | None, expected: type) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {
            "code": code, "message": f"Graph rejected {SECRET}", "error_subcode": 463,
        }})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            await client.publish_text("Hello")

    with pytest.raises(expected) as error:
        _run(exercise())
    assert error.value.status_code == status
    assert SECRET not in str(error.value)
    assert SECRET not in repr(error.value)


@pytest.mark.parametrize("status", [408, 500, 503, 302])
def test_publish_upstream_failure_is_ambiguous(status: int) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": {"message": SECRET}})

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            await client.publish_text("Hello")

    with pytest.raises(MetaGraphOutcomeUnknown) as error:
        _run(exercise())
    assert SECRET not in str(error.value)


def test_publish_network_timeout_is_ambiguous_but_get_failure_is_read_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"request failed with {SECRET}", request=request)

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(MetaGraphOutcomeUnknown) as published:
                await client.publish_text("Hello")
            with pytest.raises(MetaGraphReadError) as read:
                await client.verify_page()
            return published.value, read.value

    published, read = _run(exercise())
    assert SECRET not in str(published)
    assert SECRET not in str(read)


def test_invalid_ids_and_version_are_rejected_before_request() -> None:
    with pytest.raises(ValueError):
        MetaGraphClient("../123", SECRET)
    with pytest.raises(ValueError):
        MetaGraphClient("123", SECRET, graph_version="v26.0/evil")

    async def exercise():
        async with MetaGraphClient("123", SECRET, transport=httpx.MockTransport(lambda _r: httpx.Response(200))) as client:
            with pytest.raises(ValueError):
                await client.read_post_metrics("999_456")
            with pytest.raises(ValueError):
                await client.read_post_metrics("123_456/insights")
            with pytest.raises(ValueError):
                await client.publish_text("")

    _run(exercise())
