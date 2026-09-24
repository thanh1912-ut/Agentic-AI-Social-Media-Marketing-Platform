"""Small, server-side client for one connected Facebook Page.

Only the Page token is accepted. Publishing failures without a definitive Meta
rejection are deliberately marked unknown so callers reconcile before retrying.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import httpx


_PAGE_ID = re.compile(r"[0-9]{1,32}\Z")
_POST_ID = re.compile(r"[0-9]{1,32}(?:_[0-9]{1,32})?\Z")
_VERSION = re.compile(r"v[1-9][0-9]{0,2}\.0\Z")
_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png"})


@dataclass(frozen=True, slots=True)
class MetaPage:
    id: str
    name: str


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


@dataclass(frozen=True, slots=True)
class MetaPagePostsPage:
    posts: tuple[MetaPagePost, ...]
    next_cursor: str | None


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


def _valid_post_id(value: object, page_id: str) -> bool:
    return isinstance(value, str) and bool(_POST_ID.fullmatch(value)) and (
        "_" not in value or value.split("_", 1)[0] == page_id
    )


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
        payload = await self._request(
            "GET",
            f"/{self.graph_version}/{self.page_id}",
            publishing=False,
            params={"fields": "id,name"},
        )
        page_id, name = payload.get("id"), payload.get("name")
        if page_id != self.page_id or not isinstance(name, str) or not name.strip():
            raise MetaGraphReadError("Meta Graph returned an invalid Page identity.")
        return MetaPage(id=page_id, name=name.strip())

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

    async def list_page_posts(self, limit: int = 25, after: str | None = None) -> MetaPagePostsPage:
        """List posts authored by this Page, including posts made outside this app."""
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if after is not None and (
            not isinstance(after, str) or not after or len(after) > 2048 or not after.isprintable()
        ):
            raise ValueError("invalid pagination cursor")
        params: dict[str, str | int] = {
            "fields": "id,message,created_time,permalink_url,reactions.limit(0).summary(true),comments.limit(0).summary(true),shares",
            "limit": limit,
        }
        if after is not None:
            params["after"] = after
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
            posts.append(MetaPagePost(
                external_post_id=item["id"],
                message=message if isinstance(message, str) else None,
                created_time=_created_time(item.get("created_time")),
                permalink_url=_facebook_permalink(item.get("permalink_url")),
                reactions=_summary_count(item.get("reactions")),
                comments=_summary_count(item.get("comments")),
                shares=_shares_count(item.get("shares")),
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
