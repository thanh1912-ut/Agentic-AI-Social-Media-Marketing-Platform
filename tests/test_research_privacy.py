from datetime import datetime, timedelta, timezone

import pytest

from services.research.privacy import (
    FACEBOOK_REDACTOR_VERSION,
    MAX_RAW_QUARANTINE,
    hold_comment_text,
    protect_facebook_evidence,
    raw_quarantine_expiry,
    redact_facebook_text,
)


def test_raw_research_payload_quarantine_expires_within_24_hours() -> None:
    observed_at = datetime(2026, 9, 30, 10, 15, tzinfo=timezone.utc)

    assert MAX_RAW_QUARANTINE == timedelta(hours=24)
    assert raw_quarantine_expiry(observed_at) == datetime(2026, 10, 1, 10, 15, tzinfo=timezone.utc)


def test_raw_quarantine_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="stored_at.*timezone-aware"):
        raw_quarantine_expiry(datetime(2026, 9, 30, 10, 15))


def test_comment_text_is_withheld_but_count_is_preserved() -> None:
    comments, withheld_count = hold_comment_text([
        "Nhắn tôi tại private@example.test", "Địa chỉ và số điện thoại",
    ])

    assert comments == []
    assert withheld_count == 2


def test_facebook_text_masks_obvious_contacts_and_reports_incomplete_coverage() -> None:
    redacted, metadata = redact_facebook_text(
        "Liên hệ admin@example.invalid hoặc +84 901 234 567. "
        "Địa chỉ nhà riêng: 12/5 Đường Cá Nhân, Quận 1. Ngày 2026-09-30, giá 1 000 000 VND."
    )

    assert "admin@example.invalid" not in redacted
    assert "+84 901 234 567" not in redacted
    assert "12/5 Đường Cá Nhân" not in redacted
    assert "2026-09-30" in redacted
    assert "1 000 000 VND" in redacted
    assert metadata == {
        "redactor_version": FACEBOOK_REDACTOR_VERSION,
        "status": "pattern_redacted_review_incomplete",
        "redaction_count": 3,
        "redacted_fields": {"home_address": 1, "email": 1, "phone": 1},
        "limitations": ["names_not_detected", "not_anonymization", "manual_review_may_be_required"],
    }


def test_facebook_persistence_boundary_redacts_text_and_holds_comments_and_raw_payload() -> None:
    metrics = {"reactions": 3}
    title, text, safe_metrics, comments, raw_body = protect_facebook_evidence(
        title="Bài viết",
        text="Gọi 0901 234 567 hoặc gửi mail tới person@example.test",
        metrics=metrics,
        comments=["Tôi ở 12/5 Đường Cá Nhân, Quận 1"],
        raw_body=b"unredacted provider response",
    )

    assert title == "Bài viết"
    assert "0901 234 567" not in text
    assert "person@example.test" not in text
    assert comments == []
    assert raw_body is None
    assert safe_metrics["reactions"] == 3
    assert safe_metrics["comments_privacy"] == {
        "status": "privacy_hold",
        "withheld_text_count": 1,
    }
    assert safe_metrics["raw_payload_privacy"] == {"status": "not_retained"}
    assert safe_metrics["privacy_redaction"]["status"] == "pattern_redacted_review_incomplete"
    assert metrics == {"reactions": 3}
