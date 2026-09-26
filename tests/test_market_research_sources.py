"""Safety and extraction tests for user-submitted market research sources."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from services.api import meta_tokens
from services.api.meta_tokens import (
    TokenEncryptionUnavailable,
    decrypt_page_token,
    encrypt_page_token,
    token_fingerprint,
)
from services.research.web_crawler import (
    CrawlError,
    FetchResult,
    _feed_items,
    _pinned_request,
    canonicalize_url,
    crawl_public_site,
)


def test_source_urls_reject_credentials_secrets_and_private_networks() -> None:
    with pytest.raises(CrawlError, match="thông tin đăng nhập"):
        canonicalize_url("https://user:pass@example.com/")
    with pytest.raises(CrawlError, match="token"):
        canonicalize_url("https://example.com/?access_token=secret")
    with pytest.raises(CrawlError, match="riêng"):
        _pinned_request("http://127.0.0.1/admin")


def test_public_site_crawl_respects_robots_and_keeps_links_on_same_host() -> None:
    calls: list[str] = []

    def fetcher(url: str) -> FetchResult:
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FetchResult(url, 404, "text/plain", b"")
        if url == "https://example.com/":
            body = b'<html><head><title>Trang chu</title></head><body><p>Xu huong thi truong</p><a href="/tin">Tin</a><a href="https://other.example/news">External</a></body></html>'
            return FetchResult(url, 200, "text/html", body)
        return FetchResult(url, 200, "text/html", b"<html><title>Tin</title><main>Chu de dang chu y</main></html>")

    items = crawl_public_site("https://example.com", fetcher=fetcher)
    assert [item.url for item in items] == ["https://example.com/", "https://example.com/tin"]
    assert "Xu huong thi truong" in items[0].text
    assert "https://other.example/news" not in calls

    calls.clear()
    one_page = crawl_public_site("https://example.com", fetcher=fetcher, max_pages=1)
    assert len(one_page) == 1
    assert calls == ["https://example.com/robots.txt", "https://example.com/"]

    def disallowed(url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            return FetchResult(url, 200, "text/plain", b"User-agent: *\nDisallow: /")
        raise AssertionError("page fetch must stop when robots disallows it")

    with pytest.raises(CrawlError, match="không cho phép"):
        crawl_public_site("https://example.com/private", fetcher=disallowed)


def test_public_site_keeps_main_and_child_body_when_seo_description_exists() -> None:
    pages = {
        "https://example.com/": b'''<html><head><title>Home</title>
        <meta property="og:description" content="Root SEO summary."></head>
        <body><nav>Navigation noise</nav><main><h1>Root heading</h1>
        <p>ROOT_BODY_SENTINEL: shoppers now compare delivery speed before price.</p>
        <a href="/article">Article</a></main></body></html>''',
        "https://example.com/article": b'''<html><head><title>Article</title>
        <meta property="og:description" content="Child SEO summary."></head>
        <body><article><h1>Article heading</h1>
        <p>CHILD_BODY_SENTINEL: small sellers are adding same-day fulfillment.</p>
        </article></body></html>''',
    }

    def fetcher(url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            return FetchResult(url, 404, "text/plain", b"")
        return FetchResult(url, 200, "text/html", pages[url])

    items = crawl_public_site("https://example.com", fetcher=fetcher, max_pages=2)

    assert len(items) == 2
    assert "ROOT_BODY_SENTINEL" in items[0].text
    assert "Root SEO summary." in items[0].text
    assert "CHILD_BODY_SENTINEL" in items[1].text
    assert "Child SEO summary." in items[1].text
    assert "Navigation noise" not in items[0].text


def test_public_site_rejects_plain_text_content_after_reading_robots() -> None:
    def plain_text_site(url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            return FetchResult(url, 200, "text/plain", b"User-agent: *\nAllow: /")
        return FetchResult(url, 200, "text/plain", b"not an HTML or RSS source")

    with pytest.raises(CrawlError, match="HTML hoặc RSS/XML"):
        crawl_public_site("https://example.com", fetcher=plain_text_site)


def test_public_site_extracts_json_ld_without_author_or_executable_scripts() -> None:
    def structured_site(url: str) -> FetchResult:
        if url.endswith("/robots.txt"):
            return FetchResult(url, 404, "text/plain", b"")
        body = b'''<html><head><title>Demo shop</title>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product","name":"Tai khoan hoc truc tuyen",
         "description":"Goi dich vu hoc tap cho nguoi mua.","sku":"public-item-1",
         "offers":{"@type":"Offer","price":"125000","priceCurrency":"VND"},
         "author":{"@type":"Person","name":"Private Example"}}
        </script>
        <script>window.privateExample = "must not be collected";</script></head>
        <body><p>Public product summary.</p></body></html>'''
        return FetchResult(url, 200, "text/html", body)

    items = crawl_public_site("https://example.com", fetcher=structured_site, max_pages=1)

    assert len(items) == 1
    assert "Tai khoan hoc truc tuyen" in items[0].text
    assert "price: 125000" in items[0].text
    assert "priceCurrency: VND" in items[0].text
    assert "Private Example" not in items[0].text
    assert "window.privateExample" not in items[0].text


def test_feed_extraction_rejects_xml_entities_and_limits_to_safe_host() -> None:
    feed = FetchResult(
        "https://example.com/rss.xml", 200, "application/rss+xml",
        b"<rss><channel><item><title>Trend</title><link>https://example.com/post</link><description>Market text</description></item></channel></rss>",
    )
    items = _feed_items(feed)
    assert items[0].url == "https://example.com/post"
    assert items[0].text == "Market text"
    unsafe = FetchResult("https://example.com/rss.xml", 200, "application/xml", b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><x>&e;</x>")
    with pytest.raises(CrawlError, match="thực thể"):
        _feed_items(unsafe)
    utf16_unsafe = FetchResult(
        "https://example.com/rss.xml", 200, "application/xml",
        "<!DOCTYPE x [<!ENTITY e 'expanded'>]><x>&e;</x>".encode("utf-16"),
    )
    with pytest.raises(CrawlError, match="thực thể"):
        _feed_items(utf16_unsafe)


def test_page_tokens_are_encrypted_fingerprinted_and_key_rotation_is_supported(monkeypatch) -> None:
    current = Fernet.generate_key().decode("ascii")
    previous = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(meta_tokens, "settings", SimpleNamespace(
        meta_token_encryption_key=current,
        meta_token_encryption_key_previous="",
    ))
    ciphertext = encrypt_page_token("opaque-page-token-with-entropy")
    assert ciphertext != "opaque-page-token-with-entropy"
    assert decrypt_page_token(ciphertext) == "opaque-page-token-with-entropy"
    fingerprint = token_fingerprint("opaque-page-token-with-entropy")
    assert len(fingerprint) == 64

    old_ciphertext = Fernet(previous.encode("ascii")).encrypt(b"rotated-page-token").decode("ascii")
    monkeypatch.setattr(meta_tokens, "settings", SimpleNamespace(
        meta_token_encryption_key=current,
        meta_token_encryption_key_previous=previous,
    ))
    assert decrypt_page_token(old_ciphertext) == "rotated-page-token"

    monkeypatch.setattr(meta_tokens, "settings", SimpleNamespace(
        meta_token_encryption_key="",
        meta_token_encryption_key_previous="",
    ))
    with pytest.raises(TokenEncryptionUnavailable):
        encrypt_page_token("opaque-page-token-with-entropy")
