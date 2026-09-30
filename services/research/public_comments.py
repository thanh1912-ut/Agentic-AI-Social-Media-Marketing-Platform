"""Signed-out comment candidates, pinned and encrypted for local Owner review.

The processing decision is source-scoped, not commenter consent or permission
for provider transmission. No personal author identity or raw response persists.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timezone

from sqlalchemy import select

from database.models import (
    Company, Membership, ResearchCommentCheckpoint, ResearchCommentPageReceipt,
    ResearchCommentProcessingDecision, ResearchCommentVersion, ResearchPrivacyPolicyRevision, ResearchSource, new_id, utcnow,
)
from services.research.comment_quarantine import (
    COMMENT_REDACTOR_VERSION, CommentQuarantineUnavailable, encrypt_candidate, screen_comment_candidate,
)
from services.research.facebook_cli_collector import ENGINE_VERSION, safe_comment_coverage, safe_reaction_breakdown
from services.research.privacy import raw_quarantine_expiry


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def active_public_comment_decision(db, source, *, expected_id=None, lock=False):
    current_source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == source.company_id, ResearchSource.id == source.id))
    if current_source is None:
        return None
    source = current_source
    company = await db.scalar(select(Company).where(Company.id == source.company_id))
    if (company is None or not company.page_id or company.page_connection_state != "active" or not source.active
            or source.source_type != "competitor_facebook_page" or source.collection_mode != "public_web"):
        return None
    q = select(ResearchCommentProcessingDecision).where(
        ResearchCommentProcessingDecision.company_id == source.company_id,
        ResearchCommentProcessingDecision.source_id == source.id,
    ).order_by(ResearchCommentProcessingDecision.created_at.desc(), ResearchCommentProcessingDecision.id.desc()).limit(1)
    decision = await db.scalar(q.with_for_update() if lock else q)
    policy = await db.scalar(select(ResearchPrivacyPolicyRevision).where(
        ResearchPrivacyPolicyRevision.company_id == source.company_id,
        ResearchPrivacyPolicyRevision.source_id == source.id,
    ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1))
    if (decision is None or (expected_id is not None and decision.id != expected_id)
            or decision.status != "active" or decision.scope != "local_comment_quarantine_v1"
            or not decision.assessment_reference.strip() or aware(decision.valid_until) <= utcnow()
            or policy is None or decision.policy_revision_id != policy.id
            or not policy.purpose.strip() or not policy.processing_basis_reference.strip()):
        return None
    owner = select(Membership.id).where(Membership.company_id == source.company_id,
                                      Membership.user_id == decision.assessed_by,
                                      Membership.is_active.is_(True), Membership.role == "owner")
    if not await db.scalar(owner.with_for_update() if lock else owner):
        return None
    try:
        encrypt_candidate("", binding={"scope": "configuration-validation"})
    except CommentQuarantineUnavailable:
        return None
    return decision


async def persist_public_comment_candidates(db, *, source, evidence, observation, post, decision_id):
    """Called in the same fenced transaction as the post observation."""
    coverage = safe_comment_coverage(post.get("comment_coverage"))
    if coverage["mode"] != "tier0_embedded":
        return
    decision = await active_public_comment_decision(db, source, expected_id=decision_id, lock=True)
    if decision is None:
        return  # Revoked/changed while the bounded external read was in flight.
    checkpoint = await db.scalar(select(ResearchCommentCheckpoint).where(
        ResearchCommentCheckpoint.company_id == source.company_id,
        ResearchCommentCheckpoint.observation_id == observation.id,
        ResearchCommentCheckpoint.parent_key == "root",
    ).with_for_update())
    if checkpoint is None:
        checkpoint = ResearchCommentCheckpoint(
            id=new_id(), company_id=source.company_id, source_id=source.id, evidence_id=evidence.id,
            observation_id=observation.id, evidence_version_id=observation.evidence_version_id,
            external_post_id=post.get("id") or "public:" + hashlib.sha256(evidence.canonical_url.encode()).hexdigest(),
            parent_key="root", status="partial", count_definition="tier0_embedded_post_comments",
            provider_reported_count=coverage["provider_reported_count"], pagination_exhausted=False,
            stop_reason=coverage["stop_reason"],
        )
        db.add(checkpoint)
        await db.flush()
    receipt_key = hashlib.sha256(b"facebook-cli-embedded-comments-v1").hexdigest()
    if await db.scalar(select(ResearchCommentPageReceipt.id).where(
        ResearchCommentPageReceipt.company_id == source.company_id,
        ResearchCommentPageReceipt.checkpoint_id == checkpoint.id,
        ResearchCommentPageReceipt.request_cursor_hash == receipt_key,
    )):
        return
    now = utcnow()
    comments = post.get("comment_records", [])
    identities = set()
    for c in comments:
        if c["id"] in identities:
            continue
        identities.add(c["id"])
        candidate = screen_comment_candidate(c["text"])
        fingerprint = hashlib.sha256(json.dumps({"text": candidate.text, "redactor": COMMENT_REDACTOR_VERSION,
            "truncated": c["text_truncated"], "likes": c["likes"], "reactions": c["reactions"],
            "reaction_breakdown": c["reaction_breakdown"], "reactions_raw": c["reactions_raw"],
            "reactions_precision": c["reactions_precision"],
            "replies": c["reply_count"]}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        binding = {"company_id": source.company_id, "source_id": source.id,
                   "observation_id": observation.id, "comment_id": c["id"]}
        db.add(ResearchCommentVersion(
            id=new_id(), company_id=source.company_id, source_id=source.id, evidence_id=evidence.id,
            observation_id=observation.id, evidence_version_id=observation.evidence_version_id,
            decision_id=decision.id, parent_key="root", external_comment_id=c["id"], content_hash=fingerprint,
            candidate_ciphertext=encrypt_candidate(candidate.text, binding=binding),
            redactor_version=COMMENT_REDACTOR_VERSION, redaction_json={**candidate.metadata,
                "author_alias": c["author_alias"], "author_identity_known": c["author_identity_known"],
                "alias_scope": "post_read_only", "reactions": c["reactions"],
                "reactions_raw": c["reactions_raw"], "reactions_precision": c["reactions_precision"],
                "reaction_breakdown": safe_reaction_breakdown(c["reaction_breakdown"]),
                "provenance": {"engine": "facebook-cli", "engine_version": ENGINE_VERSION,
                               "tier": 0, "locator": "post.comments", "adapter_version": "public-comments-v1"}},
            status="privacy_hold", content_truncated=c["text_truncated"], published_at=c["published_at"],
            likes=c["likes"], reply_count=c["reply_count"], captured_at=now,
            expires_at=min(raw_quarantine_expiry(now), aware(decision.valid_until)),
        ))
    checkpoint.received_count = len(identities)
    checkpoint.pages_processed = 1
    db.add(ResearchCommentPageReceipt(
        id=new_id(), company_id=source.company_id, checkpoint_id=checkpoint.id,
        request_cursor_hash=receipt_key, received_count=len(identities), withheld_private_count=0, captured_at=now,
    ))
