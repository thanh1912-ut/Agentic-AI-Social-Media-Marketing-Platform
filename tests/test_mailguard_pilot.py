from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from services.api.content_reviews import (
    CONTENT_REVIEW_RULE_VERSION,
    _apply_semantic_review,
    _run_semantic_review,
    review_content,
)
from services.api.meta_schemas import MetaPublishIn
from services.api.pilot_schemas import CampaignPlanProposal, ContentSemanticReview, MailGuardEventIn


def test_content_review_blocks_absolute_promises_and_sensitive_requests() -> None:
    status, checks, summary = review_content(
        {"caption": "MailGuard bảo đảm an toàn tuyệt đối. Hãy gửi OTP để xác minh tài khoản."},
        [],
    )
    by_key = {check["key"]: check for check in checks}
    assert status == "blocked"
    assert by_key["absolute_claims"]["status"] == "blocking"
    assert by_key["sensitive_credentials"]["status"] == "blocking"
    assert CONTENT_REVIEW_RULE_VERSION == "mailguard-review-v1"
    assert "mục cần sửa" in summary


def test_content_review_applies_sensitive_credential_rule_to_cta_too() -> None:
    status, checks, _ = review_content(
        {"caption": "Nhận biết tin nhắn giả.", "cta": "Gửi OTP để được hỗ trợ."}, [],
    )
    by_key = {check["key"]: check for check in checks}
    assert status == "blocked"
    assert by_key["sensitive_credentials"]["status"] == "blocking"


def test_content_review_does_not_block_otp_safety_advice() -> None:
    status, checks, _ = review_content(
        {"caption": "Đừng bao giờ cung cấp OTP hoặc mật khẩu cho bất kỳ ai."},
        [],
    )
    by_key = {check["key"]: check for check in checks}
    assert status == "ready"
    assert by_key["sensitive_credentials"]["status"] == "pass"
    assert by_key["brand_voice"]["status"] == "warn"


def test_semantic_review_is_advisory_and_only_accepts_exact_draft_quotes() -> None:
    content = {"caption": "Kiểm tra tên miền trước khi bấm."}
    status, checks, _ = review_content(content, [])
    semantic = ContentSemanticReview.model_validate({
        "brand_voice": "needs_attention",
        "summary": "Cần bổ sung nguồn cho lời khẳng định.",
        "findings": [
            {"category": "unsupported_claim", "concern": "Câu cần kiểm chứng.", "quoted_text": "tên miền"},
            {"category": "other", "concern": "Mô hình đã nhầm câu.", "quoted_text": "Không có trong bài."},
        ],
    })
    final_status, checks, summary = _apply_semantic_review(checks, semantic, content["caption"])
    by_key = {check["key"]: check for check in checks}
    assert status == final_status == "ready"
    assert by_key["brand_voice"]["status"] == "warn"
    assert by_key["semantic_risks"]["status"] == "warn"
    assert "tên miền" in by_key["semantic_risks"]["evidence"][0]
    assert "Không có trong bài." not in str(by_key["semantic_risks"]["evidence"])
    assert "Owner" in summary


def test_semantic_review_uses_configured_adapter_without_live_provider(monkeypatch) -> None:
    import asyncio

    class FakeModel:
        def generate(self, *, system_prompt, input_payload, response_model):
            assert "untrusted data" in system_prompt
            assert input_payload["human_approval_required"] is True
            return response_model(
                brand_voice="aligned", summary="Phù hợp với hồ sơ đã xác nhận.", findings=[]
            ), object()

    monkeypatch.setattr("services.api.content_reviews.configured_structured_model", lambda: FakeModel())
    status, result = asyncio.run(_run_semantic_review(
        {"caption": "Lời khuyên an toàn."}, {"business_name": "MailGuard AI"},
    ))
    assert status == "completed"
    assert result is not None and result.brand_voice == "aligned"


def test_content_review_blocks_live_phishing_example_and_warns_on_duplicate() -> None:
    status, checks, _ = review_content(
        {"caption": "Ví dụ link lừa đảo: https://fake-bank-login.com/login"},
        [{"id": "old-post", "caption": "Ví dụ link lừa đảo: https://fake-bank-login.com/login"}],
    )
    by_key = {check["key"]: check for check in checks}
    assert status == "blocked"
    assert by_key["phishing_examples"]["status"] == "blocking"
    assert by_key["duplicate_content"]["status"] == "blocking"


def test_campaign_plan_requires_three_distinct_concepts_and_valid_dates() -> None:
    payload = {
        "campaign_name": "Cảnh giác link giả",
        "objective": "awareness",
        "topic": "Nhận diện link giả",
        "tone": "Gần gũi, không hù dọa",
        "audience": ["Sinh viên"],
        "key_message": "Kiểm tra người gửi và địa chỉ web trước khi bấm.",
        "start_date": "2026-10-01",
        "end_date": "2026-10-07",
        "pillars": ["education"],
        "concepts": [
            {"id": "one", "title": "A", "angle": "A", "hook": "A", "format": "text", "cta": "Tìm hiểu thêm"},
            {"id": "two", "title": "B", "angle": "B", "hook": "B", "format": "image", "cta": "Lưu bài"},
            {"id": "three", "title": "C", "angle": "C", "hook": "C", "format": "text", "cta": "Chia sẻ"},
        ],
    }
    proposal = CampaignPlanProposal.model_validate(payload)
    assert len(proposal.concepts) == 3
    assert proposal.start_date.isoformat() == "2026-10-01"
    with pytest.raises(ValidationError):
        CampaignPlanProposal.model_validate({**payload, "end_date": "2026-09-30"})


def test_mailguard_events_and_scheduled_publish_require_timezone() -> None:
    with pytest.raises(ValidationError):
        MailGuardEventIn(
            event_id="evt-1", event_type="signup_completed",
            occurred_at=datetime(2026, 9, 27), external_user_id="opaque-user-1",
        )
    with pytest.raises(ValidationError):
        MetaPublishIn(post_id="post-1", version=1, scheduled_at=datetime(2026, 9, 28))
    valid = MailGuardEventIn(
        event_id="evt-2", event_type="first_analysis_completed",
        occurred_at=datetime(2026, 9, 27, tzinfo=timezone.utc), external_user_id="opaque-user-1",
    )
    assert valid.event_type == "first_analysis_completed"
