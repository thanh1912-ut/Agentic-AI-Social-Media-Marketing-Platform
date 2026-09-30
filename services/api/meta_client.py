"""Small, server-side client for one connected Facebook Page.

Only the Page token is accepted. Publishing failures without a definitive Meta
rejection are deliberately marked unknown so callers reconcile before retrying.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import quote, parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


_PAGE_ID = re.compile(r"[0-9]{1,32}\Z")
_POST_ID = re.compile(r"[0-9]{1,32}(?:_[0-9]{1,32})?\Z")
_VERSION = re.compile(r"v[1-9][0-9]{0,2}\.0\Z")
_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png"})


@dataclass(frozen=True, slots=True)
class MetaPage:
    id: str
    name: str
    picture_url: str | None = None


@dataclass(frozen=True, slots=True)
class MetaPublishedPost:
    external_post_id: str


@dataclass(frozen=True, slots=True)
class MetaPostMetrics:
    external_post_id: str
    reactions: int | None
    comments: int | None
    shares: int | None
    permalink_url: str | None
    created_time: datetime | None


@dataclass(frozen=True, slots=True)
class MetaPagePost:
    external_post_id: str
    message: str | None
    created_time: datetime | None
    permalink_url: str | None
    reactions: int | None
    comments: int | None
    shares: int | None
    link_url: str | None = None
    attachments: tuple[dict[str, str | None], ...] = ()
    attachment_metadata_status: str = "not_returned"


@dataclass(frozen=True, slots=True)
class MetaPagePostsPage:
    posts: tuple[MetaPagePost, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class MetaPublicPage:
    id: str
    name: str
    followers_count: int | None


class MetaGraphError(Exception):
    """Safe, token-free error base class."""


class MetaGraphRejected(MetaGraphError):
    """Meta explicitly rejected a request with a 4xx response."""

    def __init__(self, status_code: int, graph_code: int | None = None, graph_subcode: int | None = None):
        self.status_code = status_code
        self.graph_code = graph_code
        self.graph_subcode = graph_subcode
        self.retryable = status_code == 429
        detail = f"HTTP {status_code}"
        if graph_code is not None:
            detail += f", code {graph_code}"
        super().__init__(f"Meta Graph rejected request ({detail}).")


class MetaGraphTokenExpired(MetaGraphRejected):
    """Page token is expired, revoked, or otherwise invalid; reconnect it."""


class MetaPageIdentityMismatch(MetaGraphRejected):
    """The supplied token's /me identity is not the requested Page."""


class MetaPageTypeUnverified(MetaGraphRejected):
    """The token identity did not include a Page-specific category."""


class MetaGraphOutcomeUnknown(MetaGraphError):
    """A publish request may have succeeded; reconcile before any retry."""


class MetaGraphReadError(MetaGraphError):
    """A read failed without an explicit Graph 4xx rejection."""


def _nonnegative_count(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _summary_count(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    summary = value.get("summary")
    if not isinstance(summary, dict):
        return None
    return _nonnegative_count(summary.get("total_count"))


def _facebook_permalink(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or (host != "facebook.com" and not host.endswith(".facebook.com")):
            return None
        if parsed.username or parsed.password or parsed.port:
            return None
    except ValueError:
        return None
    return value


def safe_external_link_url(value: object) -> str | None:
    """Keep a provider-returned link safe to display; never fetch it here."""
    if not isinstance(value, str) or len(value) > 4096 or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
            return None
        if parsed.port not in {None, 80, 443}:
            return None
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            address = ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return None
        # Query parameters often contain signed media credentials or user-specific
        # tracking values. Keep the public destination path but never persist them.
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))[:2048]
    except ValueError:
        return None


def _attachment_items(value: object) -> tuple[tuple[dict[str, str | None], ...], str]:
    """Extract bounded attachment metadata only; binary/signed media URLs are excluded."""
    if not isinstance(value, dict) or not isinstance(value.get("data"), list):
        return (), "not_returned"
    source_items = value["data"]
    truncated = len(source_items) > 20
    items: list[dict[str, str | None]] = []
    for attachment in source_items[:20]:
        if not isinstance(attachment, dict):
            continue
        target = attachment.get("target")
        target_url = safe_external_link_url(attachment.get("url"))
        if target_url is None and isinstance(target, dict):
            target_url = safe_external_link_url(target.get("url"))
        media_type = attachment.get("media_type")
        provider_type = attachment.get("type")
        raw_kind = media_type if isinstance(media_type, str) else provider_type
        kind = "unknown"
        if isinstance(raw_kind, str):
            normalized = raw_kind.casefold()
            if "video" in normalized:
                kind = "video"
            elif "photo" in normalized or "image" in normalized:
                kind = "image"
            elif "link" in normalized or "share" in normalized or target_url:
                kind = "link"
            elif normalized:
                kind = "other"
        item = {
            "kind": kind,
            "provider_type": provider_type[:80] if isinstance(provider_type, str) else None,
            # Titles/descriptions are arbitrary post text and may identify people.
            # Keep this slice metadata-only until the source privacy pipeline exists.
            "title": None,
            "description": None,
            "target_url": target_url,
            "content_status": "metadata_only_privacy_hold",
        }
        items.append(item)
        nested = attachment.get("subattachments")
        nested_data = nested.get("data") if isinstance(nested, dict) else None
        if isinstance(nested_data, list):
            truncated = truncated or len(nested_data) > 20
            for child in nested_data[:20]:
                if not isinstance(child, dict):
                    continue
                child_target = child.get("target")
                child_url = safe_external_link_url(child.get("url"))
                if child_url is None and isinstance(child_target, dict):
                    child_url = safe_external_link_url(child_target.get("url"))
                child_type = child.get("media_type") or child.get("type")
                child_kind = "video" if isinstance(child_type, str) and "video" in child_type.casefold() else (
                    "image" if isinstance(child_type, str) and ("photo" in child_type.casefold() or "image" in child_type.casefold())
                    else "link" if child_url else "other"
                )
                items.append({
                    "kind": child_kind,
                    "provider_type": child.get("type")[:80] if isinstance(child.get("type"), str) else None,
                    "title": None,
                    "description": None,
                    "target_url": child_url,
                    "content_status": "metadata_only_privacy_hold",
                })
                if len(items) >= 100:
                    return tuple(items), "truncated"
        if len(items) >= 100:
            return tuple(items), "truncated"
    if truncated:
        return tuple(items), "truncated"
    if items:
        return tuple(items), "returned"
    return (), "none_returned" if not source_items else "not_returned"


def safe_page_attachment_metadata(value: object) -> list[dict[str, str | None]]:
    """Revalidate attachment DTOs at persistence/API trust boundaries.

    Provider titles and descriptions are arbitrary source text and may contain
    personal data. Keep them out until a reviewed privacy pipeline exists.
    """
    if not isinstance(value, (list, tuple)):
        return []
    allowed_kinds = {"image", "video", "link", "other", "unknown"}
    result: list[dict[str, str | None]] = []
    for item in value[:100]:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if not isinstance(kind, str) or kind not in allowed_kinds:
            kind = "unknown"
        provider_type = item.get("provider_type")
        result.append({
            "kind": kind,
            "provider_type": provider_type[:80] if isinstance(provider_type, str) else None,
            "title": None,
            "description": None,
            "target_url": safe_external_link_url(item.get("target_url")),
            "content_status": "metadata_only_privacy_hold",
        })
    return result


def _created_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _shares_count(value: object) -> int | None:
    return _nonnegative_count(value.get("count")) if isinstance(value, dict) else None


def _insight_count(payload: dict[str, object], metric_name: str) -> int | None:
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    for item in data:
        if not isinstance(item, dict) or item.get("name") != metric_name:
            continue
        values = item.get("values")
        if not isinstance(values, list) or not values or not isinstance(values[0], dict):
            return None
        return _nonnegative_count(values[0].get("value"))
    return None


def _valid_post_id(value: object, page_id: str) -> bool:
    return isinstance(value, str) and bool(_POST_ID.fullmatch(value)) and (
        "_" not in value or value.split("_", 1)[0] == page_id
    )


def facebook_page_reference(url: str) -> str:
    """Extract a Graph API Page identifier from a user-submitted Page URL."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold().rstrip(".")
    except ValueError as exc:
        raise ValueError("invalid Facebook Page URL") from exc
    if parsed.scheme not in {"http", "https"} or host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        raise ValueError("invalid Facebook Page URL")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if segments and segments[0].casefold() == "profile.php":
        ids = parse_qs(parsed.query).get("id", [])
        if len(ids) == 1 and _PAGE_ID.fullmatch(ids[0]):
            return ids[0]
        raise ValueError("invalid Facebook Page URL")
    if len(segments) >= 3 and segments[0].casefold() == "pages" and _PAGE_ID.fullmatch(segments[-1]):
        return segments[-1]
    if len(segments) != 1:
        raise ValueError("use the Facebook Page home URL")
    reference = segments[0]
    if reference.casefold() in {"groups", "watch", "story.php", "photo.php", "marketplace", "reel"}:
        raise ValueError("use the Facebook Page home URL")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", reference):
        raise ValueError("invalid Facebook Page URL")
    return reference


class MetaGraphClient:
    """One Page connection; close with ``aclose`` or ``async with``."""

    def __init__(
        self,
        page_id: str,
        page_access_token: str,
        graph_version: str = "v26.0",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not isinstance(page_id, str) or not _PAGE_ID.fullmatch(page_id):
            raise ValueError("invalid Page ID")
        if not isinstance(graph_version, str) or not _VERSION.fullmatch(graph_version):
            raise ValueError("invalid Graph API version")
        if not isinstance(page_access_token, str) or not page_access_token or any(
            character in page_access_token for character in "\r\n"
        ):
            raise ValueError("invalid Page access token")
        self.page_id = page_id
        self.graph_version = graph_version
        self._http = httpx.AsyncClient(
            base_url="https://graph.facebook.com",
            headers={"Authorization": f"Bearer {page_access_token}"},
            transport=transport,
            timeout=httpx.Timeout(15.0),
            follow_redirects=False,
            trust_env=False,
        )

    async def __aenter__(self) -> MetaGraphClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, *, publishing: bool, **kwargs: object) -> dict[str, object]:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.RequestError:
            if publishing:
                raise MetaGraphOutcomeUnknown("Meta publish outcome is unknown after a network failure.") from None
            raise MetaGraphReadError("Could not read from Meta Graph.") from None

        if response.status_code == 408 or response.status_code >= 500 or 300 <= response.status_code < 400:
            if publishing:
                raise MetaGraphOutcomeUnknown("Meta publish outcome is unknown after an upstream failure.")
            raise MetaGraphReadError("Could not read from Meta Graph.")
        if 400 <= response.status_code < 500:
            graph_code = None
            graph_subcode = None
            try:
                error = response.json().get("error")
                if isinstance(error, dict):
                    graph_code = error.get("code") if type(error.get("code")) is int else None
                    graph_subcode = error.get("error_subcode") if type(error.get("error_subcode")) is int else None
            except (ValueError, AttributeError):
                pass
            error_type = MetaGraphTokenExpired if response.status_code == 401 or graph_code == 190 else MetaGraphRejected
            raise error_type(response.status_code, graph_code, graph_subcode)

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            if publishing:
                raise MetaGraphOutcomeUnknown("Meta publish outcome is unknown after an invalid response.")
            raise MetaGraphReadError("Meta Graph returned an invalid response.")
        return payload

    async def verify_page(self) -> MetaPage:
        # A Page token's /me identity must match the user-supplied Page ID.
        # Reading /{page_id} alone can return public metadata with an unrelated token.
        payload = await self._request(
            "GET",
            f"/{self.graph_version}/me",
            publishing=False,
            params={"fields": "id,name,picture,category"},
        )
        page_id, name = payload.get("id"), payload.get("name")
        if page_id != self.page_id:
            raise MetaPageIdentityMismatch(403)
        if not isinstance(name, str) or not name.strip():
            raise MetaGraphReadError("Meta Graph returned an invalid Page name.")
        # A matching numeric identity and a /posts edge alone can also belong
        # to a personal User token. Require the Page-only field; a profile
        # rejects this field or cannot supply it. Do not guess the node type.
        category = payload.get("category")
        if not isinstance(category, str) or not category.strip():
            raise MetaPageTypeUnverified(403)
        picture = payload.get("picture")
        picture_data = picture.get("data") if isinstance(picture, dict) else None
        picture_url = picture_data.get("url") if isinstance(picture_data, dict) else None
        if not isinstance(picture_url, str):
            picture_url = None
        else:
            try:
                parsed = urlsplit(picture_url)
                host = (parsed.hostname or "").casefold().rstrip(".")
                allowed_host = (
                    host == "fbcdn.net" or host.endswith(".fbcdn.net")
                    or host == "fbsbx.com" or host.endswith(".fbsbx.com")
                )
                if parsed.scheme != "https" or not allowed_host or parsed.username or parsed.password:
                    picture_url = None
                else:
                    # Keep CDN signature parameters that make the avatar readable,
                    # but never expose API credentials through the workspace DTO.
                    forbidden_query_keys = {"access_token", "oauth_token", "token", "appsecret_proof"}
                    safe_query = urlencode([
                        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                        if key.casefold() not in forbidden_query_keys
                    ])
                    picture_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, safe_query, ""))[:2048]
            except ValueError:
                picture_url = None
        return MetaPage(id=page_id, name=name.strip(), picture_url=picture_url)

    async def verify_posts_read_access(self) -> None:
        """Check the posts edge without requiring media/metric field permissions.

        An empty Page can still be readable. Do not fetch comment text, media,
        metrics, or pagination during account activation.
        """
        payload = await self._request(
            "GET", f"/{self.graph_version}/{self.page_id}/posts", publishing=False,
            params={"fields": "id", "limit": 1},
        )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) > 1:
            raise MetaGraphReadError("Meta Graph returned an invalid Page posts access check.")
        if any(not isinstance(item, dict) or not _valid_post_id(item.get("id"), self.page_id) for item in data):
            raise MetaGraphReadError("Meta Graph returned a post outside the requested Page.")

    async def resolve_public_page(self, reference: str) -> MetaPublicPage:
        """Resolve a public Page with an app/user token approved for Page public access."""
        if not isinstance(reference, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", reference):
            raise ValueError("invalid public Page reference")
        payload = await self._request(
            "GET", f"/{self.graph_version}/{quote(reference, safe='')}", publishing=False,
            params={"fields": "id,name"},
        )
        page_id, name = payload.get("id"), payload.get("name")
        if not isinstance(page_id, str) or not _PAGE_ID.fullmatch(page_id) or not isinstance(name, str) or not name.strip():
            raise MetaGraphReadError("Meta Graph returned an invalid public Page identity.")
        followers_count = None
        try:
            details = await self._request(
                "GET", f"/{self.graph_version}/{page_id}", publishing=False,
                params={"fields": "followers_count"},
            )
            followers_count = _nonnegative_count(details.get("followers_count"))
        except MetaGraphTokenExpired:
            raise
        except MetaGraphRejected as error:
            if error.retryable:
                raise
        except MetaGraphReadError:
            pass
        return MetaPublicPage(id=page_id, name=name.strip(), followers_count=followers_count)

    async def read_page_followers_count(self) -> int | None:
        """Read a Page's current audience count when the token exposes it."""
        payload = await self._request(
            "GET", f"/{self.graph_version}/{self.page_id}", publishing=False,
            params={"fields": "followers_count"},
        )
        return _nonnegative_count(payload.get("followers_count"))

    async def read_post_media_views(self, external_post_id: str) -> int | None:
        """Read the current Page Insights view metric; unavailable values stay null."""
        if not _valid_post_id(external_post_id, self.page_id):
            raise ValueError("invalid external post ID for this Page")
        payload = await self._request(
            "GET", f"/{self.graph_version}/{external_post_id}/insights", publishing=False,
            params={"metric": "post_media_view"},
        )
        return _insight_count(payload, "post_media_view")

    async def publish_text(self, message: str) -> MetaPublishedPost:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("post message must not be empty")
        payload = await self._request(
            "POST", f"/{self.graph_version}/{self.page_id}/feed", publishing=True,
            data={"message": message},
        )
        post_id = payload.get("id")
        if not _valid_post_id(post_id, self.page_id):
            raise MetaGraphOutcomeUnknown("Meta publish outcome is unknown because the post ID is missing.")
        return MetaPublishedPost(external_post_id=post_id)

    async def publish_photo(self, message: str, image_bytes: bytes, mime_type: str) -> MetaPublishedPost:
        if not isinstance(message, str):
            raise ValueError("post message must be text")
        if not isinstance(image_bytes, bytes) or not image_bytes:
            raise ValueError("image must not be empty")
        if mime_type not in _IMAGE_MIME_TYPES:
            raise ValueError("unsupported image MIME type")
        extension = {"image/jpeg": "jpg", "image/png": "png"}[mime_type]
        payload = await self._request(
            "POST", f"/{self.graph_version}/{self.page_id}/photos", publishing=True,
            data={"caption": message, "published": "true"},
            files={"source": (f"photo.{extension}", image_bytes, mime_type)},
        )
        # A photo ID alone does not prove which feed post was published.
        post_id = payload.get("post_id")
        if not _valid_post_id(post_id, self.page_id):
            raise MetaGraphOutcomeUnknown("Meta photo publish outcome is unknown because the post ID is missing.")
        return MetaPublishedPost(external_post_id=post_id)

    async def read_post_metrics(self, external_post_id: str) -> MetaPostMetrics:
        if not _valid_post_id(external_post_id, self.page_id):
            raise ValueError("invalid external post ID for this Page")
        payload = await self._request(
            "GET", f"/{self.graph_version}/{external_post_id}", publishing=False,
            params={"fields": "id,permalink_url,created_time,reactions.limit(0).summary(true),comments.limit(0).summary(true),shares"},
        )
        if payload.get("id") != external_post_id:
            raise MetaGraphReadError("Meta Graph returned an unexpected post ID.")
        return MetaPostMetrics(
            external_post_id=external_post_id,
            reactions=_summary_count(payload.get("reactions")),
            comments=_summary_count(payload.get("comments")),
            shares=_shares_count(payload.get("shares")),
            permalink_url=_facebook_permalink(payload.get("permalink_url")),
            created_time=_created_time(payload.get("created_time")),
        )

    async def list_post_comments(self, external_post_id: str, limit: int = 50) -> tuple[str, ...]:
        """Return comment text only; author IDs and names are never requested."""
        if not _valid_post_id(external_post_id, self.page_id):
            raise ValueError("invalid external post ID for this Page")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        payload = await self._request(
            "GET", f"/{self.graph_version}/{external_post_id}/comments", publishing=False,
            params={"fields": "message", "limit": limit},
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise MetaGraphReadError("Meta Graph returned an invalid comments list.")
        return tuple(
            item["message"][:4000]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("message"), str) and item["message"].strip()
        )

    async def list_page_posts(self, limit: int = 25, after: str | None = None) -> MetaPagePostsPage:
        """List posts authored by this Page, including posts made outside this app."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if after is not None and (
            not isinstance(after, str) or not after or len(after) > 2048 or not after.isprintable()
        ):
            raise ValueError("invalid pagination cursor")
        stable_fields = (
            "id,message,created_time,permalink_url,reactions.limit(0).summary(true),"
            "comments.limit(0).summary(true),shares"
        )
        params: dict[str, str | int] = {
            "fields": (
                "id,message,created_time,permalink_url,link,"
                "attachments.limit(20){media_type,type,title,description,url,"
                "subattachments.limit(20){media_type,type,title,description,url}},"
                "reactions.limit(0).summary(true),comments.limit(0).summary(true),shares"
            ),
            "limit": limit,
        }
        if after is not None:
            params["after"] = after
        attachment_fields_requested = True
        try:
            payload = await self._request(
                "GET", f"/{self.graph_version}/{self.page_id}/posts", publishing=False, params=params,
            )
        except MetaGraphTokenExpired:
            raise
        except MetaGraphRejected as error:
            if error.retryable:
                raise
            # Field-level permissions/availability vary by Page and app review.
            # Keep text and metrics useful while truthfully marking media missing.
            attachment_fields_requested = False
            params["fields"] = stable_fields
            payload = await self._request(
                "GET", f"/{self.graph_version}/{self.page_id}/posts", publishing=False, params=params,
            )
        data = payload.get("data")
        if not isinstance(data, list):
            raise MetaGraphReadError("Meta Graph returned an invalid Page posts list.")
        posts: list[MetaPagePost] = []
        for item in data:
            if not isinstance(item, dict) or not _valid_post_id(item.get("id"), self.page_id):
                raise MetaGraphReadError("Meta Graph returned an invalid Page post.")
            message = item.get("message")
            attachment_data, attachment_status = (
                _attachment_items(item.get("attachments")) if attachment_fields_requested else ((), "not_returned")
            )
            posts.append(MetaPagePost(
                external_post_id=item["id"],
                message=message if isinstance(message, str) else None,
                created_time=_created_time(item.get("created_time")),
                permalink_url=_facebook_permalink(item.get("permalink_url")),
                reactions=_summary_count(item.get("reactions")),
                comments=_summary_count(item.get("comments")),
                shares=_shares_count(item.get("shares")),
                link_url=safe_external_link_url(item.get("link")),
                attachments=attachment_data,
                attachment_metadata_status=attachment_status,
            ))
        paging = payload.get("paging")
        cursor = None
        if isinstance(paging, dict) and isinstance(paging.get("next"), str):
            cursors = paging.get("cursors")
            if isinstance(cursors, dict):
                candidate = cursors.get("after")
                if isinstance(candidate, str) and candidate and len(candidate) <= 2048 and candidate.isprintable():
                    cursor = candidate
        return MetaPagePostsPage(posts=tuple(posts), next_cursor=cursor)
