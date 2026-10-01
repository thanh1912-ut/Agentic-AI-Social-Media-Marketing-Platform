"""Pinned, reviewed excerpts for Gemini; never release collector output wholesale.

Operator assessment references are not consent or a legal certification. Only
explicitly selected/edited excerpts enter the provider contract. Quarantined
bodies, author aliases/IDs and engagement identities never enter that contract.
"""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta, timezone

from sqlalchemy import select, update

from database.models import (
    Company, Job, Membership, ResearchCommentAnalysisBatch, ResearchCommentVersion,
    ResearchPrivacyPolicyRevision, ResearchScreenedComment, ResearchSource, new_id, utcnow,
)
from services.agents.providers.comment_contracts import PrivacyApprovedCommentBatch, ScreenedComment
from .comment_decisions import active_local_comment_decision
from .comment_quarantine import decrypt_candidate, encrypt_candidate, screen_comment_candidate


class CommentAnalysisHeld(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def excerpt_binding(item):
    return {"scope": "screened-comment-v1", "company_id": item.company_id,
            "source_id": item.source_id, "batch_id": item.batch_id, "item_id": item.id}


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_screened_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 1500:
        raise CommentAnalysisHeld("comment_excerpt_invalid")
    if screen_comment_candidate(value).text != value:
        raise CommentAnalysisHeld("comment_excerpt_requires_redaction")


async def lock_source(db, company_id, source_id):
    # Fencing precedes business locks; suppression/review use this same order.
    await db.flush()
    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    source = await db.scalar(select(ResearchSource).where(ResearchSource.company_id == company_id,
        ResearchSource.id == source_id).with_for_update())
    if company is None or source is None:
        raise CommentAnalysisHeld("comment_source_missing")
    return source


async def create_screened_batch(db, *, company_id, source_id, actor_id, request):
    source = await lock_source(db, company_id, source_id)
    if not await db.scalar(select(Membership.id).where(Membership.company_id == company_id,
        Membership.user_id == actor_id, Membership.role == "owner", Membership.is_active.is_(True))):
        raise CommentAnalysisHeld("comment_owner_required")
    input_hash = text_hash(json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    existing = await db.scalar(select(ResearchCommentAnalysisBatch).where(
        ResearchCommentAnalysisBatch.company_id == company_id, ResearchCommentAnalysisBatch.source_id == source_id,
        ResearchCommentAnalysisBatch.request_key == request.request_key))
    if existing:
        if existing.input_hash != input_hash:
            raise CommentAnalysisHeld("comment_analysis_replay_conflict")
        job = await db.scalar(select(Job).where(Job.company_id == company_id,
            Job.idempotency_key == f"comment-analysis:{existing.id}"))
        if job is None:
            raise CommentAnalysisHeld("comment_analysis_job_missing")
        return existing, job, False
    decision = await active_local_comment_decision(db, source, expected_id=request.decision_id, lock=True)
    policy = await db.scalar(select(ResearchPrivacyPolicyRevision).where(
        ResearchPrivacyPolicyRevision.company_id == company_id, ResearchPrivacyPolicyRevision.source_id == source_id
    ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1))
    if decision is None or policy is None or policy.revision_no != request.policy_revision_no:
        raise CommentAnalysisHeld("comment_processing_context_changed")
    validate_screened_reference(request.provider_assessment_reference)
    now = utcnow()
    batch = ResearchCommentAnalysisBatch(id=new_id(), company_id=company_id, source_id=source_id,
        decision_id=decision.id, policy_revision_id=policy.id, request_key=request.request_key, input_hash=input_hash,
        assessed_by=actor_id, assessment_reference=request.provider_assessment_reference,
        created_at=now, provider_valid_until=min(aware(decision.valid_until), now + timedelta(days=30)),
        expires_at=now + timedelta(days=90), coverage_json={"selected_comments": len(request.comments),
            "selection_scope": "owner_screened_excerpts", "history_complete": False,
            "unselected_comments_sent": False, "author_identities_sent": False,
            "policy_revision_no": policy.revision_no, "parser": "screened-comment-v1"})
    rows = []
    for selected in request.comments:
        version = await db.scalar(select(ResearchCommentVersion).where(
            ResearchCommentVersion.company_id == company_id, ResearchCommentVersion.source_id == source_id,
            ResearchCommentVersion.id == selected.version_id))
        if (version is None or version.decision_id != decision.id or version.status != "privacy_hold"
                or not version.candidate_ciphertext or aware(version.expires_at) <= now):
            raise CommentAnalysisHeld("comment_selected_version_unavailable")
        if not await is_latest_version(db, version):
            raise CommentAnalysisHeld("comment_selected_version_stale")
        validate_screened_text(selected.text)
        original = decrypt_candidate(version.candidate_ciphertext, binding={"company_id": company_id,
            "source_id": source_id, "observation_id": version.observation_id, "comment_id": version.external_comment_id})
        item = ResearchScreenedComment(id=new_id(), company_id=company_id, source_id=source_id, batch_id=batch.id,
            version_id=version.id, excerpt_hash=text_hash(selected.text), source_content_hash=version.content_hash,
            content_edited=selected.text != original)
        item.excerpt_ciphertext = encrypt_candidate(selected.text, binding=excerpt_binding(item))
        rows.append(item)
    db.add(batch)
    await db.flush()
    db.add_all(rows)
    job = Job(company_id=company_id, created_by=actor_id, kind="research_comment_analysis",
        title="Phân tích lô bình luận đã kiểm tra", status="queued", progress=None,
        idempotency_key=f"comment-analysis:{batch.id}", result={"source_id": source_id, "batch_id": batch.id})
    db.add(job)
    await db.flush()
    return batch, job, True


def validate_screened_reference(value):
    if screen_comment_candidate(value).text != value:
        raise CommentAnalysisHeld("comment_assessment_reference_invalid")


async def is_latest_version(db, version):
    latest = await db.scalar(select(ResearchCommentVersion.id).where(
        ResearchCommentVersion.company_id == version.company_id,
        ResearchCommentVersion.source_id == version.source_id,
        ResearchCommentVersion.observation_id == version.observation_id,
        ResearchCommentVersion.external_comment_id == version.external_comment_id,
    ).order_by(ResearchCommentVersion.captured_at.desc(), ResearchCommentVersion.id.desc()).limit(1))
    return latest == version.id


async def approved_input(db, *, company_id, source_id, batch_id):
    source = await lock_source(db, company_id, source_id)
    batch = await db.scalar(select(ResearchCommentAnalysisBatch).where(
        ResearchCommentAnalysisBatch.id == batch_id, ResearchCommentAnalysisBatch.company_id == company_id,
        ResearchCommentAnalysisBatch.source_id == source_id).with_for_update())
    if batch is None or batch.status in {"suppressed", "expired"} or aware(batch.expires_at) <= utcnow():
        raise CommentAnalysisHeld("comment_analysis_unavailable")
    decision = await active_local_comment_decision(db, source, expected_id=batch.decision_id, lock=True)
    if decision is None or decision.policy_revision_id != batch.policy_revision_id or aware(batch.provider_valid_until) <= utcnow():
        raise CommentAnalysisHeld("comment_processing_context_changed")
    if not await db.scalar(select(Membership.id).where(Membership.company_id == company_id,
        Membership.user_id == batch.assessed_by, Membership.role == "owner", Membership.is_active.is_(True))):
        raise CommentAnalysisHeld("comment_assessor_unavailable")
    items = (await db.scalars(select(ResearchScreenedComment).where(
        ResearchScreenedComment.company_id == company_id, ResearchScreenedComment.batch_id == batch.id
    ).order_by(ResearchScreenedComment.id))).all()
    if not items or len(items) != batch.coverage_json.get("selected_comments"):
        raise CommentAnalysisHeld("comment_analysis_selection_changed")
    comments = []
    for item in items:
        version = await db.scalar(select(ResearchCommentVersion).where(
            ResearchCommentVersion.company_id == company_id, ResearchCommentVersion.source_id == source_id,
            ResearchCommentVersion.id == item.version_id))
        if (version is None or version.status == "suppressed" or version.content_hash != item.source_content_hash
                or not item.excerpt_ciphertext or not await is_latest_version(db, version)):
            raise CommentAnalysisHeld("comment_selected_version_stale")
        text = decrypt_candidate(item.excerpt_ciphertext, binding=excerpt_binding(item))
        validate_screened_text(text)
        if text_hash(text) != item.excerpt_hash:
            raise CommentAnalysisHeld("comment_analysis_selection_changed")
        comments.append(ScreenedComment(evidence_ref="comment_" + item.id, text=text))
    return batch, PrivacyApprovedCommentBatch(privacy_status="approved_for_provider", privacy_decision_id=batch.id,
        policy_version="screened-comment-v1", comments=comments)


async def erase_batches(db, *, company_id, source_id, batch_ids=None, status="suppressed"):
    query = select(ResearchCommentAnalysisBatch).where(
        ResearchCommentAnalysisBatch.company_id == company_id, ResearchCommentAnalysisBatch.source_id == source_id)
    if batch_ids is not None:
        query = query.where(ResearchCommentAnalysisBatch.id.in_(batch_ids))
    rows = (await db.scalars(query.with_for_update())).all()
    ids = [row.id for row in rows]
    for row in rows:
        row.result_json = None
        row.status = status
        row.error_code = "comment_data_erased" if status == "suppressed" else "comment_retention_expired"
    if ids:
        await db.execute(update(ResearchScreenedComment).where(ResearchScreenedComment.company_id == company_id,
            ResearchScreenedComment.batch_id.in_(ids)).values(excerpt_ciphertext=None))
    return len(ids)


async def purge_expired_screened_comments(db, now, *, limit=100):
    expired = (await db.execute(select(ResearchCommentAnalysisBatch.company_id, ResearchCommentAnalysisBatch.source_id,
        ResearchCommentAnalysisBatch.id).where(ResearchCommentAnalysisBatch.expires_at <= now,
            ResearchCommentAnalysisBatch.status.not_in(["expired", "suppressed"]))
        .order_by(ResearchCommentAnalysisBatch.expires_at).limit(limit))).all()
    for company_id, source_id, batch_id in expired:
        await lock_source(db, company_id, source_id)
        await erase_batches(db, company_id=company_id, source_id=source_id, batch_ids=[batch_id], status="expired")
    return len(expired)
