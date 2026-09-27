"""Bounded public Facebook Page reader.

This collector honors Facebook robots.txt, rejects cross-host redirects, and
never authenticates or executes page JavaScript. A blocked response is a
collection outcome, not a reason to switch to another access method.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .web_crawler import (
    CrawlError,
    FetchResult,
    _pinned_request,
    _safe_fetch,
    canonicalize_url,
)
from .website_entities import parse_public_count


FACEBOOK_HOSTS = frozenset({"facebook.com", "www.facebook.com", "m.facebook.com"})
FACEBOOK_PARSER_VERSION = "facebook-public-v1"
MAX_POSTS_PER_PAGE = 50
MAX_POST_TEXT = 12_000
MAX_HTML_NODES = 50_000
MAX_HTML_TEXT = 300_000
MAX_ARTICLES = 200
_SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "form", "nav", "footer"}
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_COUNT_LABELS = {
    "reactions": r"(?:reactions?|likes?|cảm xúc|lượt thích)",
    "comments": r"(?:comments?|bình luận)",
    "shares": r"(?:shares?|lượt chia sẻ)",
    "views": r"(?:views?|lượt xem)",
}
_COUNT_PATTERN = re.compile(
    r"(?<![\w])(?P<count>[\d][\d.,]*(?:\s*(?:k|m|b|nghìn|ngàn|triệu|\+))?)\s*(?P<label>"
    + "|".join(f"(?:{label})" for label in _COUNT_LABELS.values())
    + r")(?!\w)",
    re.IGNORECASE,
)
_POST_PATH_MARKERS = ("/posts/", "/permalink/", "/photos/", "/videos/", "/reel/", "/watch/")
_AUTH_TEXT = (
    "log in to facebook", "log into facebook", "đăng nhập facebook",
    "create new account", "you must log in", "đăng nhập để xem",
)
_CHALLENGE_TEXT = (
    "security check", "confirm it's you", "unusual activity", "enter the code",
    "captcha", "checkpoint required", "xác minh danh tính",
)


@dataclass(slots=True)
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list["_Node | str"] = field(default_factory=list)


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("document", {})
        self.stack = [self.root]
        self.skip_depth = 0
        self.node_count = 0
        self.text_count = 0
        self.truncated = False
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth or self.truncated:
            return
        if self.node_count >= MAX_HTML_NODES or len(self.stack) >= 250:
            self.truncated = True
            return
        allowed = {"role", "href", "datetime", "aria-label", "data-post-id", "data-id", "data-ft",
                   "data-pagelet", "data-testid", "property", "name", "content", "itemprop", "itemtype"}
        node = _Node(tag, {key: value[:2048] for key, value in values.items() if key in allowed})
        self.stack[-1].children.append(node)
        self.node_count += 1
        if tag not in _VOID_TAGS:
            self.stack.append(node)
        if tag == "title":
            self.in_title = True
        key = (values.get("property") or values.get("name") or "").casefold()
        if key and values.get("content"):
            self.meta[key] = values["content"][:2000]

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        matching = next((i for i in range(len(self.stack) - 1, 0, -1) if self.stack[i].tag == tag), None)
        if matching is not None:
            del self.stack[matching:]
        if tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip_depth or not data or self.truncated:
            return
        remaining = MAX_HTML_TEXT - self.text_count
        if remaining <= 0:
            self.truncated = True
            return
        chunk = data[:remaining]
        self.stack[-1].children.append(chunk)
        self.text_count += len(chunk)
        if self.in_title:
            self.title_parts.append(" ".join(chunk.split()))


@dataclass(frozen=True, slots=True)
class PublicFacebookPost:
    url: str
    external_id: str | None
    text: str
    published_at: datetime | None
    metrics: dict[str, int | None]
    metric_provenance: dict[str, dict[str, Any]]
    content_truncated: bool


@dataclass(frozen=True, slots=True)
class PublicFacebookPage:
    final_url: str
    name: str | None
    followers: int | None
    followers_raw: str | None
    posts: list[PublicFacebookPost]
    coverage: dict[str, Any]
    parser_version: str = FACEBOOK_PARSER_VERSION


def normalize_facebook_page_url(value: str) -> str:
    canonical = canonicalize_url(value)
    parsed = urlsplit(canonical)
    host = (parsed.hostname or "").casefold()
    if host not in FACEBOOK_HOSTS:
        raise CrawlError("facebook_url_required", "Nguồn cần là liên kết HTTPS công khai của facebook.com.")
    path = parsed.path.casefold()
    if path.startswith("/groups/"):
        raise CrawlError("facebook_page_required", "Nguồn này là nhóm Facebook; chỉ nhận đường dẫn Fanpage.")
    if any(segment in path for segment in ("/events/", "/marketplace/")):
        raise CrawlError("facebook_page_required", "Hãy nhập liên kết trang chủ Fanpage, không phải sự kiện hoặc Marketplace.")
    safe_query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                  if key.casefold() == "id" and path == "/profile.php"]
    if path == "/profile.php" and (
        len(safe_query) != 1 or not re.fullmatch(r"\d{1,32}", safe_query[0][1])
    ):
        raise CrawlError("invalid_facebook_page_url", "Link profile.php cần có Page ID dạng số.")
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", urlencode(safe_query), ""))


def _facebook_fetch(url: str) -> FetchResult:
    parsed = urlsplit(canonicalize_url(url))
    if (parsed.hostname or "").casefold() not in FACEBOOK_HOSTS or parsed.scheme != "https":
        raise CrawlError("source_host_out_of_scope", "Yêu cầu nằm ngoài host Facebook đã cho phép.")
    return _pinned_request(url, allowed_hosts=set(FACEBOOK_HOSTS))


def _text(node: _Node) -> str:
    parts: list[str] = []
    pending: list[_Node | str] = list(reversed(node.children))
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
        else:
            pending.extend(reversed(item.children))
    return " ".join(" ".join(parts).split())


def _nodes(root: _Node):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(child for child in reversed(node.children) if isinstance(child, _Node))


def _safe_post_url(href: str, base_url: str) -> str | None:
    try:
        canonical = canonicalize_url(urljoin(base_url, href))
    except CrawlError:
        return None
    parsed = urlsplit(canonical)
    if (parsed.hostname or "").casefold() not in FACEBOOK_HOSTS or parsed.scheme != "https":
        return None
    path = parsed.path.casefold()
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if not any(marker in path for marker in _POST_PATH_MARKERS) and not (
        path.endswith(("story.php", "photo.php", "video.php")) and query
    ):
        return None
    keep = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.casefold() in {"story_fbid", "fbid", "id", "substory_index"}]
    return urlunsplit(("https", parsed.netloc, parsed.path, urlencode(keep), ""))


def _post_id(article: _Node, permalink: str) -> str | None:
    for node in _nodes(article):
        for key in ("data-post-id", "data-id"):
            value = node.attrs.get(key, "").strip()
            if value and re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", value):
                return value
        raw = node.attrs.get("data-ft", "")
        if 0 < len(raw) <= 10_000:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                for key in ("top_level_post_id", "mf_story_key", "story_fbid"):
                    value = payload.get(key)
                    if isinstance(value, (str, int)) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,255}", str(value)):
                        return str(value)
    return None


def _metrics(article: _Node) -> tuple[dict[str, int | None], dict[str, dict[str, Any]]]:
    values: dict[str, int | None] = {key: None for key in _COUNT_LABELS}
    provenance: dict[str, dict[str, Any]] = {
        key: {"raw": None, "precision": None, "missing_reason": "not_published", "locator": None}
        for key in _COUNT_LABELS
    }
    for node in _nodes(article):
        label = node.attrs.get("aria-label", "")
        for match in _COUNT_PATTERN.finditer(label):
            raw_label = match.group("label").casefold()
            metric = next((key for key, pattern in _COUNT_LABELS.items()
                           if re.fullmatch(pattern, raw_label, re.IGNORECASE)), None)
            if metric and provenance[metric]["raw"] is None:
                parsed = parse_public_count(match.group("count"))
                values[metric] = parsed.value
                provenance[metric] = {
                    "raw": parsed.raw, "precision": parsed.precision,
                    "missing_reason": parsed.missing_reason if parsed.value is None else None,
                    "locator": "aria-label",
                }
    return values, provenance


def parse_public_facebook_page(url: str, body: bytes) -> PublicFacebookPage:
    parser = _PageParser()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
        parser.close()
    except Exception as error:
        raise CrawlError("facebook_parse_failed", "Không phân tích được HTML công khai của Fanpage.") from error
    page_name = parser.meta.get("og:title") or " ".join(parser.title_parts).strip() or None
    page_text = _text(parser.root).casefold()
    if any(phrase in (page_name or "").casefold() for phrase in _AUTH_TEXT) or any(
        phrase in page_text for phrase in _AUTH_TEXT
    ):
        raise CrawlError("login_required", "Facebook chỉ trả trang đăng nhập; không đọc được nội dung công khai.")
    if any(phrase in page_text for phrase in _CHALLENGE_TEXT):
        raise CrawlError("challenge_required", "Facebook yêu cầu xác minh; crawler không vượt qua bước này.")

    articles = [node for node in _nodes(parser.root)
                if node.tag == "article" or node.attrs.get("role", "").casefold() == "article"]
    posts: list[PublicFacebookPost] = []
    seen_urls: set[str] = set()
    for article in articles[:MAX_ARTICLES]:
        nodes = list(_nodes(article))
        permalink = next((
            resolved for node in nodes
            if node.tag == "a" and node.attrs.get("href")
            for resolved in [_safe_post_url(node.attrs["href"], url)]
            if resolved
        ), None)
        if not permalink or permalink in seen_urls:
            continue
        seen_urls.add(permalink)
        whole_text = _text(article)
        if not whole_text:
            continue
        published_at = None
        for node in nodes:
            raw_datetime = node.attrs.get("datetime")
            if node.tag == "time" and raw_datetime:
                try:
                    parsed = datetime.fromisoformat(raw_datetime.replace("Z", "+00:00"))
                    published_at = parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
                    break
                except ValueError:
                    pass
        metrics, metric_provenance = _metrics(article)
        truncated = len(whole_text) > MAX_POST_TEXT
        posts.append(PublicFacebookPost(
            url=permalink, external_id=_post_id(article, permalink),
            text=whole_text[:MAX_POST_TEXT], published_at=published_at,
            metrics=metrics, metric_provenance=metric_provenance, content_truncated=truncated,
        ))
        if len(posts) >= MAX_POSTS_PER_PAGE:
            break
    followers = None
    followers_raw = None
    for key, value in parser.meta.items():
        if key in {"og:description", "description"}:
            match = re.search(r"([\d.,]+\s*(?:k|m|b|nghìn|ngàn|triệu|\+)?)\s*(?:followers?|người theo dõi)", value, re.IGNORECASE)
            if match:
                parsed = parse_public_count(match.group(1))
                followers, followers_raw = parsed.value, parsed.raw
                break
    return PublicFacebookPage(
        final_url=url, name=page_name, followers=followers, followers_raw=followers_raw, posts=posts,
        coverage={
            "posts_seen": len(posts), "items_saved": 0, "posts_truncated": parser.truncated,
            "followers_missing_reason": None if followers is not None else "not_published_or_not_parseable",
            "rendering": "http_only",
            # One returned Page document cannot establish full feed coverage.
            "coverage": "partial",
            "coverage_reason": "single_page_http_snapshot" if not parser.truncated else "html_parser_budget_reached",
        },
    )


def read_public_facebook_page(
    url: str, *, fetcher=_facebook_fetch, request_gate: Callable[[], None] | None = None,
) -> tuple[FetchResult, PublicFacebookPage]:
    """Fetch only after the shared crawler confirms robots permits the URL."""
    normalized = normalize_facebook_page_url(url)
    def gated_fetch(target: str) -> FetchResult:
        if request_gate is not None:
            request_gate()
        return fetcher(target)
    try:
        page = _safe_fetch(
            normalized, fetcher=gated_fetch, allowed_error_statuses={401, 403, 429},
        )
    except CrawlError as error:
        if error.code == "robots_disallowed":
            raise CrawlError("blocked_robots", "robots.txt của Facebook không cho phép crawler đọc Fanpage.") from error
        raise
    if page.status == 429:
        raise CrawlError("rate_limited", "Facebook đang giới hạn yêu cầu; hãy thử lại sau.", retryable=True)
    if page.status in {401, 403}:
        raise CrawlError("access_denied", "Facebook không cho phép đọc nội dung Fanpage này.")
    if page.status >= 400:
        raise CrawlError("facebook_http_error", f"Facebook trả về HTTP {page.status}.", retryable=page.status >= 500)
    result = parse_public_facebook_page(page.url, page.body)
    return page, PublicFacebookPage(
        final_url=page.url, name=result.name, followers=result.followers,
        followers_raw=result.followers_raw, posts=result.posts, coverage=result.coverage,
    )
