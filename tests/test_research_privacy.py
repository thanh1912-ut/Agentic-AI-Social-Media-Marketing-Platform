from datetime import datetime, timedelta, timezone

import pytest

from services.research.privacy import MAX_RAW_QUARANTINE, hold_comment_text, raw_quarantine_expiry


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
