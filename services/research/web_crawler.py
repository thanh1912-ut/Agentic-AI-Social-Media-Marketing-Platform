"""Small public-web collector with DNS pinning, redirect checks, and size limits."""

from __future__ import annotations

import gzip
import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .website_entities import extract_jsonld_entities, extract_microdata_entities, parse_public_count


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_PAGES_PER_SOURCE = 25
MAX_NORMALIZED_PAGE_TEXT = 100_000
MAX_REDIRECTS = 3
CRAWLER_AGENT = "AgenticMarketResearch/1.0"
SENSITIVE_QUERY_KEYS = {"access_token", "token", "api_key", "apikey", "key", "secret", "code", "auth"}
MAX_JSON_LD_SCRIPTS = 20
MAX_JSON_LD_SCRIPT_CHARS = 100_000
MAX_JSON_LD_NODES = 100
MAX_JSON_LD_TEXT_CHARS = 10_000
JSON_LD_CONTENT_TYPES = {
    "article", "blogposting", "collectionpage", "faqpage", "itemlist", "localbusiness",
    "newsarticle", "organization", "product", "service", "webpage", "website",
}


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
    entities: list[dict[str, object]] = field(default_factory=list)
    content_truncated: bool = False


@dataclass(slots=True)
class _DomElement:
    tag: str
    attrs: dict[str, str]
    children: list["_DomElement | str"] = field(default_factory=list)


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
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"} and "xml" not in content_type and not current.casefold().endswith((".xml", ".rss", ".atom", ".xml.gz")):
                raise CrawlError("source_content_type_unsupported", "Nguồn cần trả về HTML hoặc RSS/XML công khai.")
            return FetchResult(current, status, content_type, body)
        except CrawlError:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise CrawlError("source_fetch_failed", "Không tải được nội dung website.", retryable=True) from exc
    raise CrawlError("source_redirect_limit", "Website chuyển hướng quá nhiều lần.")


def _safe_fetch(url: str, fetcher=_pinned_request, *, sitemap_hints: list[str] | None = None) -> FetchResult:
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

        lines = robots.body.decode("utf-8", errors="replace").splitlines()
        parser = RobotFileParser(robots_url)
        parser.parse(lines)
        if sitemap_hints is not None:
            sitemap_hints.extend(
                line.split(":", 1)[1].strip()
                for line in lines
                if line.strip().casefold().startswith("sitemap:") and ":" in line
            )
        if not parser.can_fetch(CRAWLER_AGENT, current):
            raise CrawlError("robots_disallowed", "Website không cho phép crawler đọc link này.")
    elif robots.status not in {404, 410}:
        raise CrawlError("robots_unavailable", "Website chưa cho phép xác minh quy tắc thu thập.", retryable=True)
    page = fetcher(current)
    if page.status >= 500:
        raise CrawlError("source_server_error", "Website đang gặp lỗi tạm thời.", retryable=True)
    if page.status >= 400:
        raise CrawlError("source_http_error", f"Website trả về HTTP {page.status}.")
    if page.content_type not in {"text/html", "application/xhtml+xml"} and "xml" not in page.content_type and not page.url.casefold().endswith((".xml", ".rss", ".atom", ".xml.gz")):
        raise CrawlError("source_content_type_unsupported", "Nguồn cần trả về HTML hoặc RSS/XML công khai.")
    return page


class _HTMLContentParser(HTMLParser):
    _SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form"}
    _DOM_SKIP = {"script", "style", "noscript", "svg", "iframe", "object", "canvas", "template"}
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
    _DOM_ATTRS = {
        "class", "id", "itemprop", "itemtype", "itemscope", "href", "src", "content",
        "datetime", "alt", "title", "aria-label", "data-product-id", "data-product_id",
        "data-product_permalink", "data-sku", "data-price", "data-currency",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.main_parts: list[str] = []
        self.article_parts: list[str] = []
        self.main_depth = 0
        self.article_depth = 0
        self.links: list[str] = []
        self.canonical: str | None = None
        self.published_at: datetime | None = None
        self.meta: dict[str, str] = {}
        self.json_ld_scripts: list[str] = []
        self._json_ld_buffer: list[str] = []
        self._json_ld_chars = 0
        self._capturing_json_ld = False
        self.microdata_items: list[dict[str, object]] = []
        self._microdata_scopes: list[dict[str, object]] = []
        self._microdata_frames: list[dict[str, object]] = []
        self.dom_root = _DomElement("document", {})
        self.dom_stack = [self.dom_root]
        self.dom_skip_tags: list[str] = []
        self.dom_node_count = 0
        self.dom_text_chars = 0
        self.dom_truncated = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.casefold(): value or "" for name, value in attrs}
        if tag in self._DOM_SKIP:
            self.dom_skip_tags.append(tag)
        elif not self.dom_skip_tags and not self.dom_truncated:
            if self.dom_node_count >= 50_000 or len(self.dom_stack) >= 300 or self.dom_text_chars >= 300_000:
                self.dom_truncated = True
            else:
                node = _DomElement(tag, {key: value for key, value in values.items() if key in self._DOM_ATTRS})
                self.dom_stack[-1].children.append(node)
                self.dom_node_count += 1
                if tag not in self._VOID:
                    self.dom_stack.append(node)
        if tag == "main":
            self.main_depth += 1
        elif tag == "article":
            self.article_depth += 1
        is_json_ld = tag == "script" and values.get("type", "").split(";", 1)[0].strip().casefold() == "application/ld+json"
        if is_json_ld:
            self._capturing_json_ld = True
            self._json_ld_buffer = []
            self._json_ld_chars = 0
        elif tag in self._SKIP:
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
        props = values.get("itemprop", "").split()
        frame: dict[str, object] = {"tag": tag}
        if "itemscope" in values:
            itemtype = values.get("itemtype", "").rstrip("/").rsplit("/", 1)[-1]
            node: dict[str, object] = {"@type": itemtype} if itemtype else {}
            if self._microdata_scopes:
                if props:
                    self._microdata_add(props, node)
            else:
                self.microdata_items.append(node)
            self._microdata_scopes.append(node)
            frame["scope"] = node
        elif props and self._microdata_scopes:
            attribute_value = (
                values.get("content") if tag == "meta" else
                values.get("src") if tag in {"img", "audio", "video", "source"} else
                values.get("href") if tag in {"a", "link", "area"} else
                values.get("datetime") if tag == "time" else None
            )
            if attribute_value:
                self._microdata_add(props, attribute_value)
            else:
                frame["props"] = props
                frame["buffer"] = []
        self._microdata_frames.append(frame)

    def _microdata_add(self, props: list[str], value: object) -> None:
        if not self._microdata_scopes:
            return
        scope = self._microdata_scopes[-1]
        for prop in props:
            existing = scope.get(prop)
            if existing is None:
                scope[prop] = value
            elif isinstance(existing, list):
                existing.append(value)
            else:
                scope[prop] = [existing, value]

    def _close_microdata_element(self, tag: str) -> None:
        matching = next((index for index in range(len(self._microdata_frames) - 1, -1, -1)
                         if self._microdata_frames[index]["tag"] == tag), None)
        if matching is None:
            return
        closed = self._microdata_frames[matching:]
        del self._microdata_frames[matching:]
        for frame in reversed(closed):
            props = frame.get("props")
            if isinstance(props, list):
                value = " ".join(" ".join(str(part).split()) for part in frame.get("buffer", []))
                if value:
                    self._microdata_add(props, value)
            scope = frame.get("scope")
            if scope is not None and self._microdata_scopes and self._microdata_scopes[-1] is scope:
                self._microdata_scopes.pop()

    def handle_endtag(self, tag: str) -> None:
        self._close_microdata_element(tag)
        if self.dom_skip_tags:
            matching_skip = next((index for index in range(len(self.dom_skip_tags) - 1, -1, -1)
                                  if self.dom_skip_tags[index] == tag), None)
            if matching_skip is not None:
                del self.dom_skip_tags[matching_skip:]
        elif tag not in self._VOID:
            matching_node = next((index for index in range(len(self.dom_stack) - 1, 0, -1)
                                  if self.dom_stack[index].tag == tag), None)
            if matching_node is not None:
                del self.dom_stack[matching_node:]
        if tag == "title":
            self.in_title = False
        if tag == "main" and self.main_depth:
            self.main_depth -= 1
        elif tag == "article" and self.article_depth:
            self.article_depth -= 1
        if tag == "script" and self._capturing_json_ld:
            script = "".join(self._json_ld_buffer).strip()
            if script and len(self.json_ld_scripts) < MAX_JSON_LD_SCRIPTS:
                self.json_ld_scripts.append(script)
            self._json_ld_buffer = []
            self._json_ld_chars = 0
            self._capturing_json_ld = False
            return
        if tag in self._SKIP and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.dom_skip_tags and not self.dom_truncated and data:
            remaining = 300_000 - self.dom_text_chars
            if remaining > 0:
                chunk = data[:remaining]
                self.dom_stack[-1].children.append(chunk)
                self.dom_text_chars += len(chunk)
            else:
                self.dom_truncated = True
        for frame in reversed(self._microdata_frames):
            buffer = frame.get("buffer")
            if isinstance(buffer, list):
                buffer.append(data)
                break
        if self._capturing_json_ld:
            remaining = MAX_JSON_LD_SCRIPT_CHARS - self._json_ld_chars
            if remaining > 0:
                chunk = data[:remaining]
                self._json_ld_buffer.append(chunk)
                self._json_ld_chars += len(chunk)
            return
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        elif self.skip_depth == 0:
            self.text_parts.append(text)
            if self.main_depth:
                self.main_parts.append(text)
            if self.article_depth:
                self.article_parts.append(text)


def _page_text(parser: _HTMLContentParser) -> tuple[str, bool]:
    """Prefer article/main text and use metadata only as distinct supporting text."""

    def normalize(value: str) -> str:
        return " ".join(value.split())

    primary = normalize(" ".join(parser.article_parts) or " ".join(parser.main_parts) or " ".join(parser.text_parts))
    fragments: list[str] = []

    def append_distinct(value: str, label: str | None = None) -> None:
        normalized = normalize(value)
        if not normalized:
            return
        folded = normalized.casefold()
        for fragment in fragments:
            existing = fragment.casefold()
            if folded == existing or (min(len(folded), len(existing)) >= 12 and (folded in existing or existing in folded)):
                return
        fragments.append(f"{label}: {normalized}" if label else normalized)

    append_distinct(primary)
    append_distinct(parser.meta.get("og:description", ""))
    append_distinct(parser.meta.get("description", ""))
    structured_text = _json_ld_summary(parser.json_ld_scripts)
    for line in structured_text.splitlines():
        label, separator, value = line.partition(": ")
        if separator:
            append_distinct(value, label)
        else:
            append_distinct(line)
    text = " ".join(fragments)
    return text[:MAX_NORMALIZED_PAGE_TEXT], len(text) > MAX_NORMALIZED_PAGE_TEXT


def _json_ld_nodes(value: object):
    """Walk only bounded JSON-LD graph/list nodes; never execute page scripts."""
    pending = [value]
    visited = 0
    while pending and visited < MAX_JSON_LD_NODES:
        current = pending.pop()
        if isinstance(current, list):
            pending.extend(reversed(current[:MAX_JSON_LD_NODES - visited]))
            continue
        if not isinstance(current, dict):
            continue
        visited += 1
        yield current
        for key in ("@graph", "itemListElement", "item"):
            child = current.get(key)
            if isinstance(child, (dict, list)):
                pending.append(child)


def _json_ld_scalar(value: object) -> str:
    if isinstance(value, str):
        return " ".join(value.split())[:1200]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        parts = [_json_ld_scalar(item) for item in value[:20]]
        return ", ".join(part for part in parts if part)[:1200]
    return ""


def _json_ld_summary(scripts: list[str]) -> str:
    """Extract public product/article facts while omitting author and account fields."""
    output: list[str] = []
    output_chars = 0
    for script in scripts[:MAX_JSON_LD_SCRIPTS]:
        try:
            document = json.loads(script)
        except (json.JSONDecodeError, RecursionError):
            continue
        for node in _json_ld_nodes(document):
            raw_types = node.get("@type")
            types = raw_types if isinstance(raw_types, list) else [raw_types]
            type_names = [
                str(value).rsplit("/", 1)[-1].rsplit(":", 1)[-1].casefold()
                for value in types if isinstance(value, str)
            ]
            relevant_types = [value for value in type_names if value in JSON_LD_CONTENT_TYPES]
            if not relevant_types:
                continue
            fields: list[str] = []
            for key, label in (
                ("name", "name"), ("headline", "headline"), ("description", "description"),
                ("articleBody", "content"), ("keywords", "keywords"), ("category", "category"),
                ("sku", "SKU"), ("datePublished", "published"), ("dateModified", "updated"),
            ):
                value = _json_ld_scalar(node.get(key))
                if value:
                    fields.append(f"{label}: {value}")
            for key, label, nested_keys in (
                ("brand", "brand", ("name",)),
                ("offers", "offer", ("price", "priceCurrency", "availability")),
                ("aggregateRating", "rating", ("ratingValue", "reviewCount", "ratingCount")),
            ):
                nested = node.get(key)
                nested_items = nested if isinstance(nested, list) else [nested]
                for nested_item in nested_items[:10]:
                    if isinstance(nested_item, str):
                        value = _json_ld_scalar(nested_item)
                        if value and key == "brand":
                            fields.append(f"{label}: {value}")
                        continue
                    if not isinstance(nested_item, dict):
                        continue
                    nested_values = [
                        f"{nested_key}: {value}"
                        for nested_key in nested_keys
                        if (value := _json_ld_scalar(nested_item.get(nested_key)))
                    ]
                    rendered = "; ".join(nested_values)
                    if rendered:
                        fields.append(f"{label}: {rendered}")
            if fields:
                line = "JSON-LD " + "/".join(relevant_types) + " — " + "; ".join(fields)
                remaining = MAX_JSON_LD_TEXT_CHARS - output_chars
                if remaining <= 0:
                    return "\n".join(output)
                output.append(line[:remaining])
                output_chars += min(len(line), remaining)
    return "\n".join(output)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _feed_items(result: FetchResult) -> list[WebItem]:
    root = _xml_root(result)
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
            url=urljoin(result.url, link), title=title[:1000], text=" ".join(text.split())[:MAX_NORMALIZED_PAGE_TEXT],
            published_at=_parse_datetime(fields.get("pubdate") or fields.get("published") or fields.get("updated") or fields.get("lastmod")),
            raw_body=result.body, content_type=result.content_type, entities=[],
            content_truncated=len(" ".join(text.split())) > MAX_NORMALIZED_PAGE_TEXT,
        ))
    return found


def _xml_root(result: FetchResult) -> ET.Element:
    body = result.body
    if result.url.casefold().endswith(".gz"):
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as stream:
                body = stream.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, EOFError) as exc:
            raise CrawlError("source_xml_invalid", "Không giải nén được sitemap.") from exc
        if len(body) > MAX_RESPONSE_BYTES:
            raise CrawlError("source_too_large", "Sitemap đã giải nén vượt giới hạn dung lượng.")
    # XML may use UTF-16/32. Remove NUL bytes before checking DTD/entity syntax.
    markup = body.upper().replace(b"\x00", b"")
    if b"<!DOCTYPE" in markup or b"<!ENTITY" in markup:
        raise CrawlError("source_xml_unsafe", "Tệp XML có khai báo thực thể không được hỗ trợ.")
    try:
        return ET.fromstring(body)
    except ET.ParseError as exc:
        raise CrawlError("source_xml_invalid", "Không đọc được nội dung XML của website.") from exc


def _site_host(value: str) -> str:
    host = (urlsplit(value).hostname or "").casefold().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _discovered_url(value: str, base: str) -> str | None:
    try:
        normalized = canonicalize_url(urljoin(base, value))
    except CrawlError:
        return None
    parsed = urlsplit(normalized)
    tracking = {"fbclid", "gclid", "dclid", "msclkid", "ref_src"}
    query = [
        (key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in tracking and not key.casefold().startswith("utm_")
    ]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), ""))


def _sitemap_urls(
    sitemap_hints: list[str], root_url: str, *, fetcher, maximum_sitemaps: int = 50,
    maximum_candidates: int = 5000,
) -> list[str]:
    root_host = _site_host(root_url)
    pending: deque[str] = deque()
    for hint in sitemap_hints or [urljoin(root_url, "/sitemap.xml")]:
        candidate = _discovered_url(hint, root_url)
        if candidate and _site_host(candidate) == root_host:
            pending.append(candidate)
    seen_sitemaps: set[str] = set()
    seen_pages: set[str] = set()
    pages: list[str] = []
    while pending and len(seen_sitemaps) < maximum_sitemaps and len(pages) < maximum_candidates:
        sitemap_url = pending.popleft()
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        try:
            result = _safe_fetch(sitemap_url, fetcher)
            if result.status >= 400 or _site_host(result.url) != root_host:
                continue
            document = _xml_root(result)
        except Exception:
            # Broken optional sitemap data does not prevent the normal HTML crawl.
            continue
        root_name = document.tag.rsplit("}", 1)[-1].casefold()
        for element in document.iter():
            local_name = element.tag.rsplit("}", 1)[-1].casefold()
            if local_name != "loc" or not element.text:
                continue
            candidate = _discovered_url(element.text.strip(), result.url)
            if not candidate or _site_host(candidate) != root_host:
                continue
            if root_name == "sitemapindex" and candidate not in seen_sitemaps:
                if len(seen_sitemaps) + len(pending) < maximum_sitemaps:
                    pending.append(candidate)
            elif candidate not in seen_pages:
                seen_pages.add(candidate)
                pages.append(candidate)
                if len(pages) >= maximum_candidates:
                    break
    return pages


def crawl_public_site(
    url: str,
    *,
    fetcher=_pinned_request,
    max_pages: int = MAX_PAGES_PER_SOURCE,
) -> list[WebItem]:
    """Read a bounded same-site frontier discovered from HTML and sitemap data."""
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES_PER_SOURCE:
        raise ValueError(f"max_pages must be between 1 and {MAX_PAGES_PER_SOURCE}")
    start = canonicalize_url(url)
    sitemap_hints: list[str] = []
    first = _safe_fetch(start, fetcher, sitemap_hints=sitemap_hints)
    if "xml" in first.content_type or first.content_type.endswith("rss") or first.url.casefold().endswith((".xml", ".rss", ".atom", ".xml.gz")):
        if max_pages > 1:
            root_name = _xml_root(first).tag.rsplit("}", 1)[-1].casefold()
            if root_name in {"sitemapindex", "urlset"}:
                page_urls = _sitemap_urls([first.url], start, fetcher=fetcher)[:max_pages]
                return _crawl_discovered_pages(page_urls, first, start, max_pages, fetcher)
        items = _feed_items(first)
        return [item for item in items if _site_host(item.url) == _site_host(start)][:max_pages]

    root_item, root_parser = _html_item(first)
    root_url = first.url
    root_host = _site_host(start)
    if _site_host(root_url) != root_host:
        raise CrawlError("source_cross_host_redirect", "Website chuyển hướng sang host ngoài phạm vi nguồn đã nhập.")
    items = [root_item]
    if max_pages <= 1:
        return [item for item in items if item.text or item.entities]

    sitemap_urls = _sitemap_urls(sitemap_hints, root_url, fetcher=fetcher)
    frontier: deque[tuple[str, int]] = deque()
    seen = {root_url, root_item.url}
    for candidate in sitemap_urls:
        if candidate not in seen and _site_host(candidate) == root_host:
            seen.add(candidate)
            frontier.append((candidate, 1))
            if len(frontier) >= 5000:
                break
    for href in root_parser.links:
        candidate = _discovered_url(href, root_url)
        if candidate and candidate not in seen and _site_host(candidate) == root_host and len(frontier) < 5000:
            seen.add(candidate)
            frontier.append((candidate, 1))

    expanded = 0
    while frontier and len(items) < max_pages and expanded < 5000:
        link, depth = frontier.popleft()
        expanded += 1
        if depth > 6:
            continue
        try:
            page = _safe_fetch(link, fetcher)
        except CrawlError:
            continue
        if _site_host(page.url) != root_host or "html" not in page.content_type:
            continue
        item, page_parser = _html_item(page)
        if item.url in {current.url for current in items}:
            continue
        items.append(item)
        if depth >= 6:
            continue
        for href in page_parser.links:
            candidate = _discovered_url(href, page.url)
            if candidate and candidate not in seen and _site_host(candidate) == root_host and len(frontier) < 5000:
                seen.add(candidate)
                frontier.append((candidate, depth + 1))
    return [item for item in items if item.text or item.entities]


def _merge_structured_entities(
    jsonld_entities: list[dict[str, object]], microdata_entities: list[dict[str, object]],
    dom_entities: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Keep structured data first and retain conflicting DOM values as evidence."""
    output = list(jsonld_entities)
    comparable = ("title", "sku", "description", "content", "category", "brand", "offers")
    for candidate in [*microdata_entities, *(dom_entities or [])]:
        identity = (candidate.get("kind"), candidate.get("identity_url"))
        existing = next((entity for entity in output
                         if (entity.get("kind"), entity.get("identity_url")) == identity), None)
        if existing is None:
            output.append(candidate)
            continue
        conflicts = existing.setdefault("extraction_conflicts", [])
        if not isinstance(conflicts, list):
            conflicts = []
            existing["extraction_conflicts"] = conflicts
        for field_name in comparable:
            preferred = existing.get(field_name)
            alternate = candidate.get(field_name)
            if alternate is None or alternate == preferred:
                continue
            conflicts.append({
                "field": field_name,
                "preferred_value": preferred,
                "preferred_method": existing.get("extraction_method", "json_ld"),
                "alternate_value": alternate,
                "alternate_method": candidate.get("extraction_method", "dom"),
            })
    return output


def _dom_walk(root: _DomElement, *, limit: int = 5000):
    pending: list[tuple[_DomElement, bool, int]] = [(root, False, 0)]
    visited = 0
    while pending and visited < limit:
        node, in_deleted_price, depth = pending.pop()
        visited += 1
        yield node, in_deleted_price
        if depth >= 12:
            continue
        deleted = in_deleted_price or node.tag in {"del", "s", "strike"}
        pending.extend((child, deleted, depth + 1) for child in reversed(node.children) if isinstance(child, _DomElement))


def _dom_text(root: _DomElement, *, maximum: int = 20_000) -> str:
    pending: list[_DomElement | str] = [root]
    pieces: list[str] = []
    length = 0
    visited = 0
    while pending and length < maximum and visited < 5000:
        current = pending.pop()
        visited += 1
        if isinstance(current, str):
            text = " ".join(current.split())
            if text:
                clipped = text[:maximum - length]
                pieces.append(clipped)
                length += len(clipped)
        else:
            pending.extend(reversed(current.children))
    return " ".join(pieces)


def _dom_classes(node: _DomElement) -> set[str]:
    return {value.casefold() for value in node.attrs.get("class", "").split()}


_PRODUCT_CONTAINER_CLASSES = {
    "product", "product-card", "product-item", "product-detail", "product-info", "product-box",
    "product-small", "woocommerce-product",
}
_NESTED_PRODUCT_BOUNDARY_CLASSES = {"product-card", "product-item", "product-small"}


def _dom_product_walk(root: _DomElement, *, limit: int = 5000):
    """Walk one product subtree without absorbing nested related product cards."""
    pending: list[tuple[_DomElement, bool, int]] = [(root, False, 0)]
    visited = 0
    while pending and visited < limit:
        node, deleted, depth = pending.pop()
        visited += 1
        yield node, deleted
        if depth >= 12:
            continue
        next_deleted = deleted or node.tag in {"del", "s", "strike"}
        child_nodes = [child for child in node.children if isinstance(child, _DomElement)]
        for child in reversed(child_nodes):
            if _dom_classes(child).intersection(_NESTED_PRODUCT_BOUNDARY_CLASSES):
                continue
            pending.append((child, next_deleted, depth + 1))


_VISIBLE_PRICE = re.compile(r"(?<![\w])([0-9][0-9\s.,]*[0-9]|[0-9])\s*(VND|VNĐ|₫|đ|USD|EUR|€|\$)?", re.I)


def _visible_price(text: str) -> dict[str, object] | None:
    compact = " ".join(text.replace("\xa0", " ").split())
    if not compact:
        return None
    if re.search(r"\b(liên hệ|contact|request a quote|quote)\b", compact, re.I):
        return {"price_kind": "contact", "price": None, "currency": None, "raw": compact[:160]}
    if re.search(r"\b(miễn phí|free)\b", compact, re.I):
        return {"price_kind": "free", "price": None, "currency": None, "raw": compact[:160]}
    match = _VISIBLE_PRICE.search(compact)
    if not match:
        return None
    raw_number = re.sub(r"\s+", "", match.group(1))
    suffix = (match.group(2) or "").casefold()
    prefix = compact[max(0, match.start() - 4):match.start()].casefold()
    currency = "VND" if suffix in {"vnd", "vnđ", "₫", "đ"} else (
        "USD" if suffix == "usd" or "us$" in prefix else
        "EUR" if suffix in {"eur", "€"} else None
    )
    if suffix == "$" and not currency:
        return {"price_kind": "ambiguous", "price": None, "currency": None, "raw": compact[:160]}
    if not currency and any(separator in raw_number for separator in ".,\\"):
        return {"price_kind": "ambiguous", "price": None, "currency": None, "raw": compact[:160]}
    try:
        if currency == "VND":
            normalized = raw_number.replace(",", "").replace(".", "")
        elif "," in raw_number and "." in raw_number:
            decimal_mark = "." if raw_number.rfind(".") > raw_number.rfind(",") else ","
            thousands_mark = "," if decimal_mark == "." else "."
            normalized = raw_number.replace(thousands_mark, "").replace(decimal_mark, ".")
        elif "," in raw_number or "." in raw_number:
            separator = "," if "," in raw_number else "."
            suffix_digits = len(raw_number.rsplit(separator, 1)[1])
            normalized = raw_number.replace(separator, "") if suffix_digits == 3 else raw_number.replace(separator, ".")
        else:
            normalized = raw_number
        amount = Decimal(normalized)
        if amount < 0 or amount > Decimal("999999999999999999.999999"):
            return None
    except (InvalidOperation, ValueError):
        return None
    return {"price_kind": "exact", "price": format(amount, "f"), "currency": currency, "raw": compact[:160]}


def _dom_product_entities(root: _DomElement, page_url: str, page_title: str = "") -> list[dict[str, object]]:
    containers = [
        node for node, _deleted in _dom_walk(root)
        if _dom_classes(node).intersection(_PRODUCT_CONTAINER_CLASSES)
    ]
    output: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for container in containers[:100]:
        descendants = list(_dom_product_walk(container, limit=2500))
        title_node = next((node for node, _ in descendants
                           if _dom_classes(node).intersection({
                               "product_title", "product-title", "product_name", "product-name",
                               "woocommerce-loop-product__title",
                           }) and _dom_text(node, maximum=1000)), None)
        has_product_title = title_node is not None
        if title_node is None:
            title_node = next((node for node, _ in descendants
                               if node.tag in {"h1", "h2", "h3"} and _dom_text(node, maximum=1000)), None)
        name = _dom_text(title_node, maximum=1000) if title_node else ""
        if not name:
            continue
        classes = _dom_classes(container)
        if "product-info" in classes and not (
            title_node is not None and (title_node.tag == "h1" or "product_title" in _dom_classes(title_node))
        ):
            continue
        if "product-info" in classes and page_title and name.casefold() != page_title.casefold():
            continue
        is_detail = (title_node is not None and title_node.tag == "h1") or bool(
            classes.intersection({"single-product", "product-detail"})
        )
        is_card = bool(classes.intersection({
            "product-small", "product-card", "product-item", "product-box", "woocommerce-product",
        }))
        has_product_value = any(
            _dom_classes(node).intersection({"price", "amount", "product-price", "current-price"})
            or node.attrs.get("itemprop") == "price" or node.attrs.get("data-price")
            for node, _ in descendants
        )
        # Generic wrappers such as a related-products carousel often carry a
        # `product` class too. Only use their first heading when it is a real
        # product title or the container is itself one product card/detail.
        if not (has_product_title or is_detail or is_card or has_product_value):
            continue
        if page_title and name.casefold() != page_title.casefold() and not (has_product_title or is_detail or is_card):
            continue
        product_url = container.attrs.get("data-product_permalink") or container.attrs.get("data-product_id")
        if product_url and product_url.isdigit():
            product_url = None
        if title_node is not None and title_node.tag == "h1":
            product_url = page_url
        elif not product_url:
            product_url = next((node.attrs.get("href") for node, _ in descendants
                                if node.tag == "a" and node.attrs.get("href")), None)
        identity_url = urljoin(page_url, product_url) if product_url else page_url
        if _site_host(identity_url) != _site_host(page_url):
            identity_url = page_url
        identity = (identity_url, name.casefold())
        if identity in seen:
            continue
        seen.add(identity)

        price_nodes = [(node, deleted) for node, deleted in descendants
                       if _dom_classes(node).intersection({"price", "amount", "product-price", "current-price"})
                       or node.attrs.get("itemprop") == "price" or node.attrs.get("data-price")]
        # Prefer innermost marked price elements so a wrapper and its amount child do not double-count.
        leaves = []
        marked_ids = {id(node) for node, _ in price_nodes}
        for node, deleted in price_nodes:
            descendant_ids = {id(child) for child, _ in _dom_walk(node, limit=1000)}
            if any(candidate_id != id(node) and candidate_id in descendant_ids for candidate_id in marked_ids):
                continue
            text = node.attrs.get("content") or node.attrs.get("data-price") or _dom_text(node, maximum=1000)
            parsed = _visible_price(text)
            if parsed:
                leaves.append((parsed, deleted, " ." + " ".join(sorted(_dom_classes(node))) if _dom_classes(node) else node.tag))
        unique_prices: list[tuple[dict[str, object], bool, str]] = []
        seen_prices: set[tuple[object, object, object, bool]] = set()
        for parsed, deleted, locator in leaves:
            key = (parsed.get("price_kind"), parsed.get("price"), parsed.get("raw"), deleted)
            if key not in seen_prices:
                seen_prices.add(key)
                unique_prices.append((parsed, deleted, locator))
        current_prices = [entry for entry in unique_prices if not entry[1]]
        original_prices = [entry for entry in unique_prices if entry[1]]
        if not current_prices:
            current_prices = unique_prices
        has_explicit_variant_group = any(
            _dom_classes(node).intersection({
                "variations", "product-variations", "variation", "variation-select",
                "variable-items-wrapper", "isures-radio-variable",
            })
            for node, _ in descendants
        )
        variants_truncated = len(current_prices) > 1 and not has_explicit_variant_group
        if variants_truncated:
            raw_candidates = "; ".join(str(entry[0].get("raw") or "") for entry in current_prices[:10])[:500]
            current_prices = [({"price_kind": "ambiguous", "price": None, "currency": None,
                               "raw": raw_candidates}, False, "ambiguous DOM price candidates")]
        offers: list[dict[str, object]] = []
        original = original_prices[0][0].get("price") if original_prices else None
        for index, (price, _deleted, locator) in enumerate(current_prices[:100]):
            provenance = {
                "value": price.get("raw"), "raw_value": price.get("raw"), "source_url": page_url,
                "method": "dom", "locator": locator,
            }
            if original is not None and index == 0:
                provenance["original_price_raw"] = original_prices[0][0].get("raw")
            offers.append({
                "identity": f"dom-offer-{index + 1}", "price_kind": price["price_kind"],
                "price": price.get("price"), "original_price": original if index == 0 else None,
                "low_price": None, "high_price": None, "currency": price.get("currency"),
                "availability": None, "billing_unit": None, "seller": None, "url": identity_url,
                "price_provenance": provenance,
            })
        whole_text = _dom_text(container, maximum=20_000)
        sold_text = whole_text if is_detail else " ".join(
            _dom_text(node, maximum=200) for node, _ in descendants
            if _dom_classes(node).intersection({"sold-count", "sales-count", "product-sold-count"})
        )
        review_text = whole_text if is_detail else " ".join(
            _dom_text(node, maximum=200) for node, _ in descendants
            if _dom_classes(node).intersection({"review-count", "rating-count", "woocommerce-review-link"})
        )
        sold_match = re.search(r"([\d.,]+\s*(?:k|m|nghìn|ngàn|triệu|\+)?)\s*(?:đã bán|sold|purchases?)\b", sold_text, re.I)
        review_match = re.search(r"([\d.,]+\s*(?:k|m|nghìn|ngàn|triệu|\+)?)\s*(?:đánh giá|reviews?)\b", review_text, re.I)
        sold = parse_public_count(sold_match.group(1)) if sold_match else parse_public_count(None)
        review = parse_public_count(review_match.group(1)) if review_match else parse_public_count(None)
        sku_node = next((node for node, _ in descendants
                         if _dom_classes(node).intersection({"sku", "product-sku"}) and _dom_text(node, maximum=200)), None)
        brand_node = next((node for node, _ in descendants
                           if _dom_classes(node).intersection({"brand", "product-brand"}) and _dom_text(node, maximum=300)), None)
        description_node = next((node for node, _ in descendants
                                 if _dom_classes(node).intersection({"short-description", "product-short-description", "product-description"})
                                 and _dom_text(node, maximum=MAX_NORMALIZED_PAGE_TEXT)), None) if is_detail else None
        category_node = next((node for node, _ in descendants
                              if _dom_classes(node).intersection({"category", "product-category", "posted_in"})
                              and _dom_text(node, maximum=300)), None)
        availability_node = next((node for node, _ in descendants
                                  if _dom_classes(node).intersection({"stock", "availability", "product-availability"})
                                  and _dom_text(node, maximum=200)), None)
        images = [urljoin(identity_url, node.attrs.get("src", "")) for node, _ in descendants
                  if node.tag == "img" and node.attrs.get("src")][:20]
        description = _dom_text(description_node, maximum=MAX_NORMALIZED_PAGE_TEXT) if description_node else None
        sku = _dom_text(sku_node, maximum=200) if sku_node else container.attrs.get("data-sku")
        brand = _dom_text(brand_node, maximum=300) if brand_node else None
        category = _dom_text(category_node, maximum=300) if category_node else None
        availability = _dom_text(availability_node, maximum=200) if availability_node else None
        for offer in offers:
            offer["availability"] = availability
        if availability and not offers:
            offers.append({
                "identity": "dom-offer-1", "price_kind": "unknown", "price": None,
                "original_price": None, "low_price": None, "high_price": None,
                "currency": None, "availability": availability, "billing_unit": None,
                "seller": None, "url": identity_url,
                "price_provenance": {"value": None, "raw_value": None, "source_url": page_url,
                                     "method": "dom", "locator": "product availability selector"},
            })
        output.append({
            "kind": "product", "identity_url": identity_url, "title": name,
            "category": category, "brand": brand, "sku": sku, "description": description or "",
            "attributes": {}, "image_urls": images, "offers": offers,
            "rating_value": None, "review_count": review.value, "review_count_raw": review.raw or None,
            "sold_count": sold.value, "sold_count_lower_bound": sold.lower_bound,
            "sold_count_raw": sold.raw or None, "sold_precision": sold.precision,
            "sold_missing_reason": sold.missing_reason, "review_count_precision": review.precision,
            "field_provenance": {
                "title": {"value": name, "raw_value": name, "source_url": page_url,
                          "method": "dom", "locator": "product title selector"},
                "description": {"value": description, "raw_value": description, "source_url": page_url,
                                "method": "dom", "locator": "product description selector"},
            },
            "extraction_method": "dom",
            "dom_container_classes": sorted(classes), "variants_truncated": variants_truncated,
        })
    return output


def _html_item(page: FetchResult) -> tuple[WebItem, _HTMLContentParser]:
    parser = _HTMLContentParser()
    try:
        parser.feed(page.body.decode("utf-8", errors="replace"))
    except Exception as exc:
        raise CrawlError("source_html_invalid", "Không trích xuất được nội dung trang web.") from exc
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.title_parts)
    text, content_truncated = _page_text(parser)
    page_url = page.url
    canonical = _discovered_url(parser.canonical, page.url) if parser.canonical else page.url
    if canonical and _site_host(canonical) == _site_host(page.url):
        page_url = canonical
    published_at = _parse_datetime(parser.meta.get("article:published_time")) or parser.published_at
    entities = _merge_structured_entities(
        extract_jsonld_entities(parser.json_ld_scripts, page_url),
        extract_microdata_entities(parser.microdata_items, page_url),
        _dom_product_entities(parser.dom_root, page_url, title),
    )
    if parser.article_parts:
        article_text = " ".join(" ".join(parser.article_parts).split())
        existing_article = next((entity for entity in entities if entity["kind"] == "article"), None)
        if existing_article is None:
            entities.append({
                "kind": "article", "identity_url": page_url, "title": title[:1000],
                "content": article_text[:MAX_NORMALIZED_PAGE_TEXT],
                "content_truncated": len(article_text) > MAX_NORMALIZED_PAGE_TEXT,
                "category": None, "published_at": published_at.isoformat() if published_at else None,
                "updated_at": None, "extraction_method": "html_article",
                "field_provenance": {
                    "title": {"value": title[:1000], "raw_value": title, "source_url": page_url,
                              "method": "html_article", "locator": "article heading / document title"},
                    "content": {"value": article_text[:MAX_NORMALIZED_PAGE_TEXT], "raw_value": article_text[:MAX_NORMALIZED_PAGE_TEXT],
                                "source_url": page_url, "method": "html_article", "locator": "article"},
                },
            })
        elif len(article_text) > len(str(existing_article.get("content") or "")):
            existing_article["content"] = article_text[:MAX_NORMALIZED_PAGE_TEXT]
            existing_article["content_truncated"] = len(article_text) > MAX_NORMALIZED_PAGE_TEXT
            existing_article["field_provenance"]["content"] = {
                "value": article_text[:MAX_NORMALIZED_PAGE_TEXT],
                "raw_value": article_text[:MAX_NORMALIZED_PAGE_TEXT], "source_url": page_url,
                "method": "html_article", "locator": "article",
            }
    return WebItem(
        url=page_url, title=title[:1000], text=text,
        published_at=published_at, raw_body=page.body, content_type=page.content_type,
        entities=entities, content_truncated=content_truncated,
    ), parser


def _crawl_discovered_pages(
    urls: list[str], first: FetchResult, source_url: str, max_pages: int, fetcher,
) -> list[WebItem]:
    root_host = _site_host(source_url)
    items: list[WebItem] = []
    for page_url in urls:
        if len(items) >= max_pages:
            break
        if _site_host(page_url) != root_host:
            continue
        try:
            page = first if page_url == first.url else _safe_fetch(page_url, fetcher)
        except CrawlError:
            continue
        if _site_host(page.url) != root_host or "html" not in page.content_type:
            continue
        item, _parser = _html_item(page)
        if item.text or item.entities:
            items.append(item)
    return items
