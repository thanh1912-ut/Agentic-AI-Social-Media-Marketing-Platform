"""Small privacy-retention primitives shared by research workers and tests."""

from collections.abc import Sequence
from datetime import datetime, timedelta
import ipaddress
import re
from urllib.parse import urlsplit, urlunsplit

from .website_entities import parse_public_count


MAX_RAW_QUARANTINE = timedelta(hours=24)
FACEBOOK_REDACTOR_VERSION = "facebook-contact-patterns-v1"

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
_HOME_ADDRESS_RE = re.compile(
    r"\b(?:địa chỉ nhà riêng|địa chỉ nhà|nơi ở|nhà riêng)\s*[:：-]?\s*[^;\n.!?]{3,120}",
    re.IGNORECASE,
)
_METRIC_KEYS = {"reactions", "comments", "shares", "interactions", "views", "followers"}
_ATTACHMENT_KINDS = {"image", "video", "link", "other", "unknown"}
_ATTACHMENT_STATUSES = {"returned", "none_returned", "not_returned", "truncated"}
_PRECISIONS = {"exact", "approximate", "lower_bound"}
_REDACTION_LIMITATIONS = {"names_not_detected", "not_anonymization", "manual_review_may_be_required"}
_REDACTION_FIELD_KEYS = {"home_address", "email", "phone", "name", "person_handle"}
_MISSING_METRIC_REASONS = {
    "provider_value_ambiguous", "not_published", "ambiguous_public_value",
    "unparseable_public_value", "out_of_range", "unknown",
}
_ATTACHMENT_PROVIDER_TYPES = {
    "photo", "image", "video", "video_inline", "video_autoplay", "video_share",
    "album", "link", "share", "unknown",
}


def raw_quarantine_expiry(stored_at: datetime) -> datetime:
    """Return the hard expiry for raw research payloads kept for quarantine.

    Raw payloads are not retained as source-of-truth records. An aware timestamp
    is required so the scheduler can compare expiry consistently in UTC.
    """

    if stored_at.tzinfo is None or stored_at.utcoffset() is None:
        raise ValueError("stored_at must be timezone-aware")
    return stored_at + MAX_RAW_QUARANTINE


def hold_comment_text(comments: Sequence[str]) -> tuple[list[str], int]:
    """Return no commenter text while privacy processing is not approved."""

    return [], len(comments)


def _safe_public_url(value: object) -> str | None:
    """Keep a display-only public URL without credentials, query or fragment."""
    if not isinstance(value, str) or len(value) > 4096 or any(ord(char) < 32 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").casefold().rstrip(".")
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            return None
        if parsed.port not in {None, 80, 443} or host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path[:2048], "", ""))
    except ValueError:
        return None


def _safe_redaction_metadata(value: object, *, depth: int = 0) -> dict[str, object] | None:
    if not isinstance(value, dict) or depth > 1:
        return None
    result: dict[str, object] = {}
    version = value.get("redactor_version")
    if version == FACEBOOK_REDACTOR_VERSION:
        result["redactor_version"] = version
    status = value.get("status")
    if status == "pattern_redacted_review_incomplete":
        result["status"] = status
    count = value.get("redaction_count")
    if type(count) is int and 0 <= count <= 1_000_000:
        result["redaction_count"] = count
    fields = value.get("redacted_fields")
    if isinstance(fields, dict):
        safe_fields = {
            key: amount for key, amount in fields.items()
            if key in _REDACTION_FIELD_KEYS and type(amount) is int and 0 <= amount <= 1_000_000
        }
        if safe_fields:
            result["redacted_fields"] = safe_fields
    limitations = value.get("limitations")
    if isinstance(limitations, (list, tuple)):
        safe_limitations = [item for item in limitations if isinstance(item, str) and item in _REDACTION_LIMITATIONS]
        if safe_limitations:
            result["limitations"] = list(dict.fromkeys(safe_limitations))
    for key in ("content", "title"):
        nested = _safe_redaction_metadata(value.get(key), depth=depth + 1)
        if nested:
            result[key] = nested
    return result or None


def _safe_metric_provenance(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    safe: dict[str, object] = {}
    for metric_name in _METRIC_KEYS:
        item = value.get(metric_name)
        if not isinstance(item, dict):
            continue
        locator = item.get("locator")
        if not isinstance(locator, str) or locator not in {"aria-label", f"facebook-cli/counts.{metric_name}"}:
            continue
        provenance: dict[str, object] = {}
        raw = item.get("raw")
        parsed = parse_public_count(raw)
        # A long bare integer is ambiguous with a phone/account number. The
        # normalized metric stays available, but its source string is withheld.
        digits = re.sub(r"\D", "", raw) if isinstance(raw, str) else ""
        if parsed.precision in _PRECISIONS and not (parsed.precision == "exact" and len(digits) >= 10):
            provenance["raw"] = parsed.raw
            provenance["precision"] = parsed.precision
        precision = item.get("precision")
        if isinstance(precision, str) and precision in _PRECISIONS:
            provenance["precision"] = precision
        missing = item.get("missing_reason")
        if isinstance(missing, str) and missing in _MISSING_METRIC_REASONS:
            provenance["missing_reason"] = missing
        provenance["locator"] = locator
        if provenance:
            safe[metric_name] = provenance
    return safe or None


def _safe_attachments(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, (list, tuple)):
        return None
    result: list[dict[str, object]] = []
    for item in value[:100]:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        kind = kind if isinstance(kind, str) and kind in _ATTACHMENT_KINDS else "unknown"
        provider_type = item.get("provider_type")
        safe_provider_type = (
            provider_type if isinstance(provider_type, str) and provider_type in _ATTACHMENT_PROVIDER_TYPES else None
        )
        result.append({
            "kind": kind,
            "provider_type": safe_provider_type,
            "title": None,
            "description": None,
            "target_url": _safe_public_url(item.get("target_url")),
            "content_status": "metadata_only_privacy_hold",
        })
    return result


def _safe_facebook_metrics(metrics: dict[str, object]) -> dict[str, object]:
    """Allow only bounded research measures and display-safe provenance fields."""
    result: dict[str, object] = {}
    for key in _METRIC_KEYS:
        if key not in metrics:
            continue
        value = metrics.get(key)
        if value is None:
            result[key] = None
        elif type(value) is int and 0 <= value <= 2**63 - 1:
            result[key] = value
    for key in ("privacy_redaction", "title_privacy_redaction"):
        safe = _safe_redaction_metadata(metrics.get(key))
        if safe:
            result[key] = safe
    provenance = _safe_metric_provenance(metrics.get("_provenance"))
    if provenance:
        result["_provenance"] = provenance
    link_url = _safe_public_url(metrics.get("link_url"))
    if link_url:
        result["link_url"] = link_url
    attachments = _safe_attachments(metrics.get("attachments"))
    if attachments is not None:
        result["attachments"] = attachments
    attachment_status = metrics.get("attachment_metadata_status")
    if isinstance(attachment_status, str) and attachment_status in _ATTACHMENT_STATUSES:
        result["attachment_metadata_status"] = attachment_status
    if type(metrics.get("content_truncated")) is bool:
        result["content_truncated"] = metrics["content_truncated"]
    comments_privacy = metrics.get("comments_privacy")
    if isinstance(comments_privacy, dict) and comments_privacy.get("status") == "privacy_hold":
        withheld_count = comments_privacy.get("withheld_text_count")
        if type(withheld_count) is int and 0 <= withheld_count <= 1_000_000:
            result["comments_privacy"] = {"status": "privacy_hold", "withheld_text_count": withheld_count}
    if isinstance(metrics.get("raw_payload_privacy"), dict) and metrics["raw_payload_privacy"].get("status") == "not_retained":
        result["raw_payload_privacy"] = {"status": "not_retained"}
    return result


def redact_facebook_text(value: str) -> tuple[str, dict[str, object]]:
    """Mask obvious contact details in Facebook text without claiming anonymity.

    This intentionally does not try to guess names or guarantee that all
    personal data is detected. Comment bodies and media remain on privacy hold
    until their separate processing controls are approved.
    """

    text = value
    address_matches = 0
    email_matches = 0
    phone_matches = 0
    text, address_matches = _HOME_ADDRESS_RE.subn("[đã ẩn địa chỉ nhà]", text)
    text, email_matches = _EMAIL_RE.subn("[đã ẩn email]", text)

    def redact_phone(match: re.Match[str]) -> str:
        nonlocal phone_matches
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        is_local_number = digits.startswith("0") and 9 <= len(digits) <= 11
        is_country_code_number = digits.startswith("84") and 11 <= len(digits) <= 12
        is_explicit_international = candidate.lstrip().startswith("+") and 8 <= len(digits) <= 15
        if is_local_number or is_country_code_number or is_explicit_international:
            phone_matches += 1
            return "[đã ẩn số điện thoại]"
        return candidate

    text = _PHONE_CANDIDATE_RE.sub(redact_phone, text)
    return text, {
        "redactor_version": FACEBOOK_REDACTOR_VERSION,
        "status": "pattern_redacted_review_incomplete",
        "redaction_count": address_matches + email_matches + phone_matches,
        "redacted_fields": {
            "home_address": address_matches,
            "email": email_matches,
            "phone": phone_matches,
        },
        "limitations": ["names_not_detected", "not_anonymization", "manual_review_may_be_required"],
    }


def protect_facebook_evidence(
    *,
    title: str,
    text: str,
    metrics: dict[str, object],
    comments: Sequence[str],
    raw_body: bytes | None,
) -> tuple[str, str, dict[str, object], list[str], None]:
    """Apply the Facebook storage boundary even when a collector forgot to.

    This is defense in depth, not a legal-basis check or anonymization. Facebook
    evidence may keep only pattern-redacted post text and public metrics here;
    comment bodies and raw responses stay out of persistent storage.
    """

    safe_title, title_redaction = redact_facebook_text(title)
    safe_text, text_redaction = redact_facebook_text(text)
    safe_metrics = _safe_facebook_metrics(metrics)

    previous_redaction = safe_metrics.get("privacy_redaction")
    if isinstance(previous_redaction, dict) and previous_redaction.get("redactor_version") == FACEBOOK_REDACTOR_VERSION:
        # Collectors may already have applied this same redactor. Preserve its
        # original counts and add any additional findings from this boundary.
        merged = dict(safe_metrics.get("privacy_redaction") or previous_redaction)
        previous_fields = previous_redaction.get("redacted_fields")
        current_fields = text_redaction.get("redacted_fields")
        if isinstance(previous_fields, dict) and isinstance(current_fields, dict):
            merged["redacted_fields"] = {
                key: int(previous_fields.get(key, 0)) + int(current_fields.get(key, 0))
                for key in {**previous_fields, **current_fields}
            }
        merged["redaction_count"] = (
            int(previous_redaction.get("redaction_count", 0))
            + int(text_redaction["redaction_count"])
        )
        safe_metrics["privacy_redaction"] = merged
    else:
        safe_metrics["privacy_redaction"] = text_redaction

    if int(title_redaction["redaction_count"]) > 0:
        safe_metrics["title_privacy_redaction"] = title_redaction
    if comments:
        safe_metrics["comments_privacy"] = {
            "status": "privacy_hold",
            "withheld_text_count": len(comments),
        }
    if raw_body is not None:
        safe_metrics["raw_payload_privacy"] = {"status": "not_retained"}

    # Do not persist comment text or raw HTML/provider payloads from Facebook,
    # even if a future adapter accidentally passes them through.
    return safe_title, safe_text, safe_metrics, [], None
