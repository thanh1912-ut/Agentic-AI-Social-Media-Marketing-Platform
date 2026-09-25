"""Small public-web collector with DNS pinning, redirect checks, and size limits."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGES_PER_SOURCE = 25
MAX_REDIRECTS = 3
CRAWLER_AGENT = "AgenticMarketResearch/1.0"
SENSITIVE_QUERY_KEYS = {"access_token", "token", "api_key", "apikey", "key", "secret", "code", "auth"}


class CrawlError(ValueError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes


@dataclass(frozen=True, slots=True)
class WebItem:
    url: str
    title: str
    text: str
    published_at: datetime | None
    raw_body: bytes
    content_type: str


def canonicalize_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise CrawlError("invalid_source_url", "Link nguồn quá dài hoặc không hợp lệ.")
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as exc:
        raise CrawlError("invalid_source_url", "Link nguồn không hợp lệ.") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise CrawlError("invalid_source_url", "Nguồn web cần là link HTTP hoặc HTTPS công khai.")
    if parsed.username or parsed.password or port not in {None, 80, 443}:
        raise CrawlError("invalid_source_url", "Link có thông tin đăng nhập hoặc cổng mạng không được hỗ trợ.")
    if any(key.casefold() in SENSITIVE_QUERY_KEYS for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
        raise CrawlError("sensitive_source_url", "Hãy bỏ token hoặc mã bí mật khỏi link nguồn.")
    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if not host:
        raise CrawlError("invalid_source_url", "Tên máy chủ trong link không hợp lệ.")
    scheme = parsed.scheme.lower()
    netloc = f"{host}:{port}" if port and port != (443 if scheme == "https" else 80) else host
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _public_addresses(host: str, port: int) -> list[tuple[int, int, int, tuple]]:
    try:
        literal = ipaddress.ip_address(host)
        records = [(socket.AF_INET6 if literal.version == 6 else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP,
                    "", (str(literal), port, 0, 0) if literal.version == 6 else (str(literal), port))]
    except ValueError:
        try:
            records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
        except OSError as exc:
            raise CrawlError("source_dns_failed", "Không tìm thấy địa chỉ của website.", retryable=True) from exc
    if not records:
        raise CrawlError("source_dns_failed", "Không tìm thấy địa chỉ của website.", retryable=True)
    checked: list[tuple[int, int, int, tuple]] = []
    for family, socktype, proto, _canonname, sockaddr in records:
        try:
            address = ipaddress.ip_address(sockaddr[0])
        except ValueError as exc:
            raise CrawlError("source_address_rejected", "Website phân giải tới địa chỉ mạng không hợp lệ.") from exc
        if not address.is_global:
            raise CrawlError("source_address_rejected", "Website phân giải tới mạng riêng hoặc địa chỉ không công khai.")
        checked.append((family, socktype, proto, sockaddr))
    return checked


def _pinned_request(url: str, *, timeout: float = 12.0) -> FetchResult:
    current = canonicalize_url(url)
    for redirect in range(MAX_REDIRECTS + 1):
        parsed = urlsplit(current)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        address = _public_addresses(host, port)[0]
        family, socktype, proto, sockaddr = address
        raw = socket.socket(family, socktype, proto)
        raw.settimeout(timeout)
        try:
            raw.connect(sockaddr)
            sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host) if parsed.scheme == "https" else raw
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
            connection.sock = sock
            path = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
            connection.request("GET", path, headers={
                "Host": parsed.netloc,
                "User-Agent": CRAWLER_AGENT,
                "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.1",
                "Accept-Encoding": "identity",
                "Connection": "close",
            })
            response = connection.getresponse()
            status = response.status
            headers = {name.casefold(): value for name, value in response.getheaders()}
            if status in {301, 302, 303, 307, 308}:
                location = headers.get("location")
                connection.close()
                if not location or redirect >= MAX_REDIRECTS:
                    raise CrawlError("source_redirect_limit", "Website chuyển hướng quá nhiều lần.")
                target = canonicalize_url(urljoin(current, location))
                if parsed.scheme == "https" and urlsplit(target).scheme != "https":
                    raise CrawlError("source_downgrade_blocked", "Không theo chuyển hướng từ HTTPS xuống HTTP.")
                current = target
                continue
            content_length = headers.get("content-length")
            if content_length and int(content_length) > MAX_RESPONSE_BYTES:
                connection.close()
                raise CrawlError("source_too_large", "Trang web vượt giới hạn dung lượng cho một lần đọc.")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            connection.close()
            if len(body) > MAX_RESPONSE_BYTES:
                raise CrawlError("source_too_large", "Trang web vượt giới hạn dung lượng cho một lần đọc.")
            if status >= 500:
                raise CrawlError("source_server_error", "Website đang gặp lỗi tạm thời.", retryable=True)
            content_type = headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip().lower()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"} and "xml" not in content_type and not current.casefold().endswith((".xml", ".rss", ".atom")):
                raise CrawlError("source_content_type_unsupported", "Nguồn cần trả về HTML hoặc RSS/XML công khai.")
            return FetchResult(current, status, content_type, body)
        except CrawlError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise CrawlError("source_fetch_failed", "Không tải được nội dung website.", retryable=True) from exc
    raise CrawlError("source_redirect_limit", "Website chuyển hướng quá nhiều lần.")


def _safe_fetch(url: str, fetcher=_pinned_request) -> FetchResult:
    current = canonicalize_url(url)
    parsed = urlsplit(current)
    if not parsed.hostname:
        raise CrawlError("invalid_source_url", "Link website không hợp lệ.")
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        robots = fetcher(robots_url)
    except CrawlError as exc:
        # A broken robots endpoint is treated conservatively as unavailable.
        raise CrawlError("robots_unavailable", "Chưa xác minh được quy tắc thu thập của website.", retryable=exc.retryable) from exc
    if robots.status == 200:
        from urllib.robotparser import RobotFileParser

        parser = RobotFileParser(robots_url)
        parser.parse(robots.body.decode("utf-8", errors="replace").splitlines())
        if not parser.can_fetch(CRAWLER_AGENT, current):
            raise CrawlError("robots_disallowed", "Website không cho phép crawler đọc link này.")
    elif robots.status not in {404, 410}:
        raise CrawlError("robots_unavailable", "Website chưa cho phép xác minh quy tắc thu thập.", retryable=True)
    page = fetcher(current)
    if page.status >= 500:
        raise CrawlError("source_server_error", "Website đang gặp lỗi tạm thời.", retryable=True)
    if page.status >= 400:
        raise CrawlError("source_http_error", f"Website trả về HTTP {page.status}.")
    if page.content_type not in {"text/html", "application/xhtml+xml"} and "xml" not in page.content_type and not page.url.casefold().endswith((".xml", ".rss", ".atom")):
        raise CrawlError("source_content_type_unsupported", "Nguồn cần trả về HTML hoặc RSS/XML công khai.")
    return page


class _HTMLContentParser(HTMLParser):
    _SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.canonical: str | None = None
        self.published_at: datetime | None = None
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        if tag in self._SKIP:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if self.skip_depth == 0:
            if tag == "a" and values.get("href"):
                self.links.append(values["href"])
            if tag == "link" and "canonical" in values.get("rel", "").casefold():
                self.canonical = values.get("href") or None
            key = values.get("property") or values.get("name") or ""
            content = values.get("content", "")
            if key and content:
                self.meta[key.casefold()] = content
            if tag == "time" and values.get("datetime"):
                self.published_at = _parse_datetime(values["datetime"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in self._SKIP and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        elif self.skip_depth == 0:
            self.text_parts.append(text)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _feed_items(result: FetchResult) -> list[WebItem]:
    # XML permits UTF-16/32 byte encodings; remove NUL bytes before checking so
    # a DTD cannot bypass this guard by interleaving zero bytes between letters.
    markup = result.body.upper().replace(b"\x00", b"")
    if b"<!DOCTYPE" in markup or b"<!ENTITY" in markup:
        raise CrawlError("source_xml_unsafe", "Tệp XML có khai báo thực thể không được hỗ trợ.")
    try:
        root = ET.fromstring(result.body)
    except ET.ParseError as exc:
        raise CrawlError("source_xml_invalid", "Không đọc được RSS/sitemap của website.") from exc
    found: list[WebItem] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].casefold()
        if tag not in {"item", "entry", "url"}:
            continue
        fields: dict[str, str] = {}
        for child in list(element):
            key = child.tag.rsplit("}", 1)[-1].casefold()
            value = (child.attrib.get("href") or "".join(child.itertext()).strip()) if key == "link" else "".join(child.itertext()).strip()
            if value:
                fields[key] = value
        link = fields.get("link") or fields.get("loc") or fields.get("guid")
        if not link:
            continue
        title = fields.get("title") or ""
        text = fields.get("description") or fields.get("summary") or fields.get("content") or title
        if tag == "url":
            text = title
        found.append(WebItem(
            url=urljoin(result.url, link), title=title[:1000], text=" ".join(text.split())[:12000],
            published_at=_parse_datetime(fields.get("pubdate") or fields.get("published") or fields.get("updated") or fields.get("lastmod")),
            raw_body=result.body, content_type=result.content_type,
        ))
    return found


def crawl_public_site(
    url: str,
    *,
    fetcher=_pinned_request,
    max_pages: int = MAX_PAGES_PER_SOURCE,
) -> list[WebItem]:
    """Read an explicitly submitted public site and a bounded set of its links."""
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES_PER_SOURCE:
        raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_PER_SOURCE}")
    start = canonicalize_url(url)
    root = urlsplit(start)
    first = _safe_fetch(start, fetcher)
    if "xml" in first.content_type or first.content_type.endswith("rss") or first.url.casefold().endswith((".xml", ".rss", ".atom")):
        items = _feed_items(first)
        return [item for item in items if (urlsplit(canonicalize_url(item.url)).hostname or "").casefold() == (root.hostname or "").casefold()][:max_pages]

    parser = _HTMLContentParser()
    try:
        parser.feed(first.body.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise CrawlError("source_html_invalid", "Không trích xuất được nội dung trang web.") from exc
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.title_parts)
    text = parser.meta.get("og:description") or " ".join(parser.text_parts)
    canonical = urljoin(first.url, parser.canonical) if parser.canonical else first.url
    items = [WebItem(
        url=canonicalize_url(canonical), title=title[:1000], text=" ".join(text.split())[:12000],
        published_at=_parse_datetime(parser.meta.get("article:published_time")) or parser.published_at,
        raw_body=first.body, content_type=first.content_type,
    )]
    seen = {items[0].url}
    discovered: list[str] = []
    for href in parser.links:
        if len(discovered) >= max_pages - 1:
            break
        target = urljoin(first.url, href)
        try:
            normalized = canonicalize_url(target)
        except CrawlError:
            continue
        parsed = urlsplit(normalized)
        if (parsed.hostname or "").casefold() != (root.hostname or "").casefold() or normalized in seen:
            continue
        seen.add(normalized)
        discovered.append(normalized)
    for link in discovered:
        try:
            page = _safe_fetch(link, fetcher)
        except CrawlError:
            continue
        if "html" not in page.content_type:
            continue
        page_parser = _HTMLContentParser()
        page_parser.feed(page.body.decode("utf-8", errors="replace"))
        page_title = page_parser.meta.get("og:title") or " ".join(page_parser.title_parts)
        page_text = page_parser.meta.get("og:description") or " ".join(page_parser.text_parts)
        page_url = urljoin(page.url, page_parser.canonical) if page_parser.canonical else page.url
        items.append(WebItem(
            url=canonicalize_url(page_url), title=page_title[:1000], text=" ".join(page_text.split())[:12000],
            published_at=_parse_datetime(page_parser.meta.get("article:published_time")) or page_parser.published_at,
            raw_body=page.body, content_type=page.content_type,
        ))
    return [item for item in items if item.text]
