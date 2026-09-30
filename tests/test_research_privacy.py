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


def test_facebook_persistence_boundary_allowlists_nested_metrics_and_media_metadata() -> None:
    title, text, safe_metrics, comments, raw_body = protect_facebook_evidence(
        title="Public post",
        text="Public text",
        metrics={
            "reactions": 1200,
            "comments": True,
            "shares": 1.5,
            "comment_text": "Commenter's home address and phone",
            "authors": [{"name": "Private Person", "profile_url": "https://facebook.com/private-person"}],
            "raw_response": {"message": "unfiltered provider body"},
            "link_url": "https://news.example/story?email=person@example.test&token=signed#private",
            "attachments": [{
                "kind": "image", "provider_type": "photo", "title": "Private Person",
                "description": "Private address", "target_url": "https://cdn.example/item?access_token=secret",
                "author": "Private Person",
            }],
            "_provenance": {
                "reactions": {
                    "raw": "1.2K", "precision": "approximate", "locator": "facebook-cli/counts.reactions",
                },
                "shares": {"raw": "100+", "precision": "lower_bound", "locator": "facebook-cli/counts.shares"},
                "comments": {
                    "raw": "0901234567", "precision": "exact", "locator": "facebook-cli/counts.comments",
                },
                "views": {"raw": "1.2K", "precision": "approximate", "locator": "user_name01"},
            },
        },
        comments=[],
        raw_body=None,
    )

    assert title == "Public post"
    assert text == "Public text"
    assert comments == []
    assert raw_body is None
    assert safe_metrics["reactions"] == 1200
    assert "comments" not in safe_metrics  # bool is not a numeric count
    assert "shares" not in safe_metrics  # Facebook interaction counters must be integer counts
    assert "comment_text" not in safe_metrics
    assert "authors" not in safe_metrics
    assert "raw_response" not in safe_metrics
    assert safe_metrics["link_url"] == "https://news.example/story"
    assert safe_metrics["attachments"] == [{
        "kind": "image", "provider_type": "photo", "title": None,
        "description": None, "target_url": "https://cdn.example/item",
        "content_status": "metadata_only_privacy_hold",
    }]
    assert safe_metrics["_provenance"]["reactions"] == {
        "raw": "1.2K", "precision": "approximate", "locator": "facebook-cli/counts.reactions",
    }
    assert safe_metrics["_provenance"]["shares"] == {
        "raw": "100+", "precision": "lower_bound", "locator": "facebook-cli/counts.shares",
    }
    assert "raw" not in safe_metrics["_provenance"]["comments"]
    assert "views" not in safe_metrics["_provenance"]
    assert "0901234567" not in str(safe_metrics)
    assert "user_name01" not in str(safe_metrics)
