from datetime import datetime, timedelta, timezone

import pytest

from services.research.privacy import (
    FACEBOOK_REDACTOR_VERSION,
    MAX_RAW_QUARANTINE,
    hold_comment_text,
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
