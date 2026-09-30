"""Small privacy-retention primitives shared by research workers and tests."""

from collections.abc import Sequence
from datetime import datetime, timedelta
import re


MAX_RAW_QUARANTINE = timedelta(hours=24)
FACEBOOK_REDACTOR_VERSION = "facebook-contact-patterns-v1"

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_CANDIDATE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")
_HOME_ADDRESS_RE = re.compile(
    r"\b(?:địa chỉ nhà riêng|địa chỉ nhà|nơi ở|nhà riêng)\s*[:：-]?\s*[^;\n.!?]{3,120}",
    re.IGNORECASE,
)


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
    safe_metrics = dict(metrics)

    previous_redaction = safe_metrics.get("privacy_redaction")
    if isinstance(previous_redaction, dict) and previous_redaction.get("redactor_version") == FACEBOOK_REDACTOR_VERSION:
        # Collectors may already have applied this same redactor. Preserve its
        # original counts and add any additional findings from this boundary.
        merged = dict(previous_redaction)
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
