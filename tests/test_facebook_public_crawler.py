"""Deterministic tests for policy-aware public Facebook Page parsing."""

from __future__ import annotations

import pytest

from services.research.facebook_public_crawler import (
    normalize_facebook_page_url,
    parse_public_facebook_page,
    read_public_facebook_page,
)
from services.research.web_crawler import CrawlError, FetchResult


PAGE_URL = "https://www.facebook.com/rival"


def test_normalize_facebook_page_url_rejects_groups_and_requires_profile_id() -> None:
    assert normalize_facebook_page_url("http://facebook.com/rival?fbclid=tracking") == "https://facebook.com/rival"
    assert normalize_facebook_page_url("https://facebook.com/profile.php?id=12345") == (
        "https://facebook.com/profile.php?id=12345"
    )
    with pytest.raises(CrawlError, match="nhóm Facebook"):
        normalize_facebook_page_url("https://www.facebook.com/groups/12345")
    with pytest.raises(CrawlError, match="Page ID dạng số"):
        normalize_facebook_page_url("https://www.facebook.com/profile.php")


def test_parse_public_page_keeps_post_provenance_and_approximate_counts() -> None:
    html = """<!doctype html><html><head>
      <meta property="og:title" content="Rival Page">
      <meta property="og:description" content="12K followers">
    </head><body><nav>Navigation should not be a post.</nav>
      <article data-post-id="post-42">
        <a href="/rival/posts/post-42?fbclid=tracking">Mau he moi</a>
        <p>Post body sentinel: giao hàng nhanh trong ngày.</p>
        <time datetime="2026-09-20T09:30:00+07:00">20 Sep</time>
        <span aria-label="1.2K reactions"></span>
        <span aria-label="3 comments"></span>
        <span aria-label="100+ shares"></span>
      </article>
      <script>window.fakePost = '<article><a href="/fake/posts/1">not a post</a></article>';</script>
      <form><article><a href="/rival/posts/private">not public post</a></article></form>
    </body></html>""".encode("utf-8")

    page = parse_public_facebook_page(PAGE_URL, html)

    assert page.name == "Rival Page"
    assert page.followers is None
    assert page.followers_raw == "12K"
    assert len(page.posts) == 1
    post = page.posts[0]
    assert post.url == "https://www.facebook.com/rival/posts/post-42"
    assert post.external_id == "post-42"
    assert "Post body sentinel" in post.text
    assert post.published_at is not None
    assert post.published_at.isoformat() == "2026-09-20T02:30:00+00:00"
    assert post.metrics == {"reactions": None, "comments": 3, "shares": None, "views": None}
    assert post.metric_provenance["reactions"]["raw"] == "1.2K"
    assert post.metric_provenance["reactions"]["precision"] == "approximate"
    assert post.metric_provenance["shares"]["raw"] == "100+"
    assert post.metric_provenance["shares"]["precision"] == "lower_bound"
    assert not post.content_truncated


def test_read_public_page_stops_before_content_when_robots_disallows() -> None:
    calls: list[str] = []

    def fetcher(url: str) -> FetchResult:
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResult(url, 200, "text/plain", b"User-agent: *\nDisallow: /")
        raise AssertionError("crawler must not fetch the Page after robots disallows it")

    with pytest.raises(CrawlError) as error:
        read_public_facebook_page(PAGE_URL, fetcher=fetcher)

    assert error.value.code == "blocked_robots"
    assert len(calls) == 1
    assert calls[0] == "https://www.facebook.com/robots.txt"


def test_read_public_page_distinguishes_login_wall_from_readable_page() -> None:
    calls: list[str] = []
    html = b"<html><head><title>Log in to Facebook</title></head><body>Log in to Facebook</body></html>"

    def fetcher(url: str) -> FetchResult:
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResult(url, 200, "text/plain", b"User-agent: *\nAllow: /")
        return FetchResult(url, 200, "text/html", html)

    with pytest.raises(CrawlError) as error:
        read_public_facebook_page(PAGE_URL, fetcher=fetcher)

    assert error.value.code == "login_required"
    assert calls == ["https://www.facebook.com/robots.txt", PAGE_URL]


def test_public_page_does_not_treat_verification_challenge_as_empty_success() -> None:
    html = b"<html><body>Security check: confirm it's you before continuing.</body></html>"
    with pytest.raises(CrawlError) as error:
        parse_public_facebook_page(PAGE_URL, html)
    assert error.value.code == "challenge_required"


def test_public_page_rate_limit_is_retryable() -> None:
    def fetcher(url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            return FetchResult(url, 200, "text/plain", b"User-agent: *\nAllow: /")
        return FetchResult(url, 429, "text/html", b"Too many requests")

    with pytest.raises(CrawlError) as error:
        read_public_facebook_page(PAGE_URL, fetcher=fetcher)

    assert error.value.code == "rate_limited"
    assert error.value.retryable is True
