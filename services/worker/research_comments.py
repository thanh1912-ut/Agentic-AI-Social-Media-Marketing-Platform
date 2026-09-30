"""Bounded Meta comment/reply traversal with atomic checkpoints and quarantine.

No caller may bypass the scoped processing decision. Policy text, Page tokens
and public visibility are not treated as commenter consent. This module never
calls a model, publishes, or returns candidate plaintext to general APIs.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select

from database.models import (
    AuditEvent, Company, Job, Membership, MetaPageConnection, ResearchCommentCheckpoint, ResearchCommentPageReceipt,
    ResearchCommentProcessingDecision, ResearchCommentVersion, ResearchPrivacyPolicyRevision,
    ResearchSource, new_id, utcnow,
)
from database.job_fencing import JobLeaseLost, claim_job_fence, isolated_job_fence
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.meta_client import (
    MetaCommentsPage, MetaGraphClient, MetaGraphReadError, MetaGraphRejected, MetaGraphTokenExpired,
)
from services.api.meta_tokens import TokenEncryptionUnavailable, decrypt_page_token
from services.research.comment_quarantine import (
    COMMENT_REDACTOR_VERSION, CommentQuarantineUnavailable, encrypt_candidate, screen_comment_candidate,
)
from services.research.privacy import raw_quarantine_expiry
from .async_runtime import run_worker_coroutine
from .celery_app import celery_app


_COMMENT_ID = re.compile(r"[0-9]{1,32}(?:_[0-9]{1,32}){0,2}\Z")
_CURSOR = re.compile(r"[A-Za-z0-9_+/=.-]{1,2048}\Z")
BATCH_SECONDS = 300


class CommentCollectionHeld(RuntimeError):
    """Safe code only: never include a body, cursor, token or provider URL."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CommentPageWork:
    checkpoint_id: str
    decision_id: str
    company_id: str
    page_id: str = field(repr=False)
    post_id: str = field(repr=False)
    parent_key: str = field(repr=False)
    cursor: str | None = field(repr=False)
    token_ciphertext: str = field(repr=False)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _cursor_hash(cursor: str | None) -> str:
    return hashlib.sha256(json.dumps(cursor, ensure_ascii=True).encode()).hexdigest()


async def _context(db, checkpoint_id: str, company_id: str, decision_id: str, now: datetime):
    # Acquire the job fence first, before business row locks. It is asserted
    # again on flush/commit, including after an external read.
    await db.flush()
    company = await db.scalar(select(Company).where(Company.id == company_id).with_for_update())
    if company is None or not company.page_id or company.page_connection_state != "active":
        raise CommentCollectionHeld("page_connection_required")
    identity = await db.scalar(select(ResearchCommentCheckpoint).where(
        ResearchCommentCheckpoint.id == checkpoint_id, ResearchCommentCheckpoint.company_id == company_id,
    ))
    if identity is None:
        raise CommentCollectionHeld("comment_checkpoint_missing")
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.id == identity.source_id, ResearchSource.company_id == company_id,
    ).with_for_update())
    if source is None or not source.active or source.source_type != "owned_facebook_page":
        raise CommentCollectionHeld("comment_source_unavailable")
    checkpoint = await db.scalar(select(ResearchCommentCheckpoint).where(
        ResearchCommentCheckpoint.id == checkpoint_id, ResearchCommentCheckpoint.company_id == company_id,
    ).with_for_update())
    if checkpoint.status in {"suppressed", "error"}:
        raise CommentCollectionHeld("comment_frontier_unavailable")
    decision = await db.scalar(select(ResearchCommentProcessingDecision).where(
        ResearchCommentProcessingDecision.id == decision_id,
        ResearchCommentProcessingDecision.company_id == company_id,
        ResearchCommentProcessingDecision.source_id == source.id,
    ).with_for_update())
    latest_decision_id = await db.scalar(select(ResearchCommentProcessingDecision.id).where(
        ResearchCommentProcessingDecision.company_id == company_id,
        ResearchCommentProcessingDecision.source_id == source.id,
    ).order_by(ResearchCommentProcessingDecision.created_at.desc(), ResearchCommentProcessingDecision.id.desc()).limit(1))
    policy = await db.scalar(select(ResearchPrivacyPolicyRevision).where(
        ResearchPrivacyPolicyRevision.company_id == company_id, ResearchPrivacyPolicyRevision.source_id == source.id,
    ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1))
    if (decision is None or decision.id != latest_decision_id or decision.status != "active"
            or decision.scope != "local_comment_quarantine_v1"
            or not decision.assessment_reference.strip() or _aware(decision.valid_until) <= now
            or policy is None or policy.id != decision.policy_revision_id
            or not policy.purpose.strip() or not policy.processing_basis_reference.strip()):
        raise CommentCollectionHeld("comment_processing_decision_required")
    assessor = await db.scalar(select(Membership.id).where(
        Membership.company_id == company_id, Membership.user_id == decision.assessed_by,
        Membership.is_active.is_(True), Membership.role == "owner",
    ).with_for_update())
    if assessor is None:
        raise CommentCollectionHeld("comment_processing_decision_required")
    connection = await db.scalar(select(MetaPageConnection).where(
        MetaPageConnection.company_id == company_id, MetaPageConnection.id == source.connection_id,
    ).with_for_update())
    if (connection is None or connection.page_id != company.page_id or connection.status != "verified"
            or not connection.active or connection.verified_at is None or not connection.encrypted_token
            or not checkpoint.external_post_id.startswith(f"{company.page_id}_")):
        raise CommentCollectionHeld("page_needs_reconnect")
    if checkpoint.parent_key != "root":
        # Replies can only be queried for a parent actually received from the
        # same pinned post observation. An arbitrary inserted ID is not enough.
        parent = await db.scalar(select(ResearchCommentVersion.id).where(
            ResearchCommentVersion.company_id == company_id,
            ResearchCommentVersion.source_id == source.id,
            ResearchCommentVersion.observation_id == checkpoint.observation_id,
            ResearchCommentVersion.external_comment_id == checkpoint.parent_key,
        ).limit(1))
        if parent is None:
            raise CommentCollectionHeld("comment_parent_unverified")
    return checkpoint, decision, connection


async def prepare_comment_page(checkpoint_id: str, *, company_id: str, decision_id: str) -> CommentPageWork:
    async with SessionLocal() as db:
        checkpoint, decision, connection = await _context(db, checkpoint_id, company_id, decision_id, utcnow())
        if checkpoint.pagination_exhausted:
            raise CommentCollectionHeld("comment_edge_exhausted")
        return CommentPageWork(checkpoint.id, decision.id, company_id, connection.page_id,
                               checkpoint.external_post_id, checkpoint.parent_key,
                               checkpoint.cursor_after, connection.encrypted_token)


def _validate_page(work: CommentPageWork, page: MetaCommentsPage) -> None:
    if (len(page.comments) > 100 or type(page.withheld_private_count) is not int
            or not 0 <= page.withheld_private_count <= 100 or len(page.comments) + page.withheld_private_count > 100
            or (page.next_cursor is not None and (not _CURSOR.fullmatch(page.next_cursor) or page.next_cursor == work.cursor))
            or page.pagination_exhausted != (page.next_cursor is None)
            or (page.provider_reported_count is not None and
                (type(page.provider_reported_count) is not int or page.provider_reported_count < 0))):
        raise CommentCollectionHeld("comment_page_invalid")
    seen = set()
    for comment in page.comments:
        parent = None if work.parent_key == "root" else work.parent_key
        if (not isinstance(comment.external_id, str) or not _COMMENT_ID.fullmatch(comment.external_id) or comment.external_id in seen
                or comment.external_id == work.parent_key or comment.root_post_id != work.post_id
                or comment.parent_comment_id != parent):
            raise CommentCollectionHeld("comment_page_identity_mismatch")
        if (comment.message is not None and (not isinstance(comment.message, str) or len(comment.message) > 20_000)
                or type(comment.content_truncated) is not bool
                or (comment.created_time is not None and (not isinstance(comment.created_time, datetime)
                    or comment.created_time.tzinfo is None))):
            raise CommentCollectionHeld("comment_page_invalid")
        seen.add(comment.external_id)
        for count in (comment.likes, comment.reply_count):
            if count is not None and (type(count) is not int or count < 0):
                raise CommentCollectionHeld("comment_page_invalid")


async def commit_comment_page(work: CommentPageWork, page: MetaCommentsPage) -> bool:
    """Commit all bodies, reply edges and progress, or commit none of them.

    Returns False for a delivery whose cursor already has a committed receipt.
    Overlapping pages do not inflate received_count. The observed message is
    immutable; an edit creates a new fingerprint/version even within a run.
    """
    _validate_page(work, page)
    now = utcnow()
    async with SessionLocal() as db:
        checkpoint, decision, connection = await _context(
            db, work.checkpoint_id, work.company_id, work.decision_id, now,
        )
        if connection.page_id != work.page_id or connection.encrypted_token != work.token_ciphertext:
            raise CommentCollectionHeld("comment_connection_changed")
        receipt = await db.scalar(select(ResearchCommentPageReceipt.id).where(
            ResearchCommentPageReceipt.company_id == work.company_id,
            ResearchCommentPageReceipt.checkpoint_id == work.checkpoint_id,
            ResearchCommentPageReceipt.request_cursor_hash == _cursor_hash(work.cursor),
        ))
        if receipt is not None:
            return False
        if checkpoint.cursor_after != work.cursor or checkpoint.pagination_exhausted:
            raise CommentCollectionHeld("comment_cursor_stale")
        if page.next_cursor is not None and await db.scalar(select(ResearchCommentPageReceipt.id).where(
            ResearchCommentPageReceipt.company_id == work.company_id,
            ResearchCommentPageReceipt.checkpoint_id == work.checkpoint_id,
            ResearchCommentPageReceipt.request_cursor_hash == _cursor_hash(page.next_cursor),
        )):
            raise CommentCollectionHeld("comment_cursor_cycle")
        if checkpoint.external_post_id != work.post_id or checkpoint.parent_key != work.parent_key:
            raise CommentCollectionHeld("comment_page_identity_mismatch")
        expires_at = min(raw_quarantine_expiry(now), _aware(decision.valid_until))
        new_identities = 0
        for comment in page.comments:
            candidate = screen_comment_candidate(comment.message or "")
            fingerprint = hashlib.sha256(json.dumps({
                "text": candidate.text, "truncated": comment.content_truncated,
                "redactor": COMMENT_REDACTOR_VERSION,
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            existing = (await db.scalars(select(ResearchCommentVersion).where(
                ResearchCommentVersion.company_id == work.company_id,
                ResearchCommentVersion.observation_id == checkpoint.observation_id,
                ResearchCommentVersion.external_comment_id == comment.external_id,
            ))).all()
            # A comment seen on two different parent edges is ambiguous. Do not
            # attach another parent's content/replies to this edge.
            if any(row.parent_key != checkpoint.parent_key for row in existing):
                raise CommentCollectionHeld("comment_parent_conflict")
            if not any(row.content_hash == fingerprint for row in existing):
                binding = {"company_id": work.company_id, "source_id": checkpoint.source_id,
                           "observation_id": checkpoint.observation_id, "comment_id": comment.external_id}
                db.add(ResearchCommentVersion(
                    **{key: getattr(checkpoint, key) for key in (
                        "company_id", "source_id", "evidence_id", "observation_id", "evidence_version_id", "parent_key",
                    )},
                    decision_id=decision.id, external_comment_id=comment.external_id, content_hash=fingerprint,
                    candidate_ciphertext=encrypt_candidate(candidate.text, binding=binding),
                    redactor_version=COMMENT_REDACTOR_VERSION, redaction_json=candidate.metadata,
                    content_truncated=comment.content_truncated, published_at=comment.created_time,
                    likes=comment.likes, reply_count=comment.reply_count,
                    captured_at=now, expires_at=expires_at,
                ))
            new_identities += int(not existing)
            if comment.reply_count is None or comment.reply_count > 0:
                child = await db.scalar(select(ResearchCommentCheckpoint.id).where(
                    ResearchCommentCheckpoint.company_id == work.company_id,
                    ResearchCommentCheckpoint.observation_id == checkpoint.observation_id,
                    ResearchCommentCheckpoint.parent_key == comment.external_id,
                ))
                if child is None:
                    db.add(ResearchCommentCheckpoint(
                        **{key: getattr(checkpoint, key) for key in (
                            "company_id", "source_id", "evidence_id", "observation_id", "evidence_version_id", "external_post_id",
                        )}, parent_key=comment.external_id, status="queued", stop_reason=None,
                        provider_reported_count=comment.reply_count, count_definition="comment_replies_summary",
                    ))
        db.add(ResearchCommentPageReceipt(
            company_id=work.company_id, checkpoint_id=checkpoint.id,
            request_cursor_hash=_cursor_hash(work.cursor), received_count=len(page.comments),
            withheld_private_count=page.withheld_private_count, captured_at=now,
        ))
        checkpoint.received_count += new_identities
        checkpoint.pages_processed += 1
        checkpoint.provider_reported_count = page.provider_reported_count
        checkpoint.cursor_after = page.next_cursor
        checkpoint.pagination_exhausted = page.pagination_exhausted
        checkpoint.status = "completed" if page.pagination_exhausted else "partial"
        checkpoint.stop_reason = "provider_edge_exhausted" if page.pagination_exhausted else "next_cursor_available"
        await db.commit()
    return True


async def collect_comment_page(checkpoint_id: str, *, company_id: str, decision_id: str, limit: int = 100) -> bool:
    """Read one fixed, verified edge. Callers own the durable job/batch budget."""
    work = await prepare_comment_page(checkpoint_id, company_id=company_id, decision_id=decision_id)
    try:
        async with MetaGraphClient(work.page_id, decrypt_page_token(work.token_ciphertext), settings.meta_graph_version) as client:
            page = await client.list_comments_page(work.post_id, parent_comment_id=(
                None if work.parent_key == "root" else work.parent_key
            ), limit=max(1, min(limit, 100)), after=work.cursor)
    except MetaGraphTokenExpired:
        await _expire_comment_connection(work)
        raise
    return await commit_comment_page(work, page)


async def purge_expired_comment_quarantine(db, now: datetime, *, limit: int = 100) -> int:
    """Erase only expired candidate ciphertext; retain a restricted tombstone.

    Does not select arbitrary sources or touch user-authored posts. Plaintext
    is never reconstructed during cleanup. Source purge also cascades these
    rows through their pinned evidence/observation foreign keys.
    """
    rows = (await db.scalars(select(ResearchCommentVersion).join(ResearchCommentProcessingDecision, (
        ResearchCommentProcessingDecision.company_id == ResearchCommentVersion.company_id
    ) & (ResearchCommentProcessingDecision.id == ResearchCommentVersion.decision_id)).where(
        ResearchCommentVersion.candidate_ciphertext.is_not(None), or_(
            ResearchCommentVersion.expires_at <= now, ResearchCommentProcessingDecision.status != "active",
            ResearchCommentProcessingDecision.valid_until <= now,
        ),
    ).order_by(ResearchCommentVersion.expires_at).limit(limit).with_for_update(skip_locked=True))).all()
    for row in rows:
        row.candidate_ciphertext = None
        row.status = "expired"
    companies = {row.company_id for row in rows}
    for company_id in companies:
        db.add(AuditEvent(company_id=company_id, actor_user_id=None, action="research.comment_quarantine.expired",
                          entity_type="research_comment_quarantine", entity_id=company_id,
                          metadata_json={"removed_candidates": sum(row.company_id == company_id for row in rows),
                                         "scope": "expired_or_revoked_local_ciphertext"}))
    await db.flush()
    return len(rows)


async def comment_frontier_coverage(db, *, company_id: str, observation_id: str) -> dict[str, object]:
    rows = (await db.scalars(select(ResearchCommentCheckpoint).where(
        ResearchCommentCheckpoint.company_id == company_id,
        ResearchCommentCheckpoint.observation_id == observation_id,
    ))).all()
    versions = await db.scalar(select(func.count(func.distinct(ResearchCommentVersion.external_comment_id))).where(
        ResearchCommentVersion.company_id == company_id, ResearchCommentVersion.observation_id == observation_id,
    ))
    receipts = select(ResearchCommentPageReceipt).join(ResearchCommentCheckpoint, (
        ResearchCommentCheckpoint.company_id == ResearchCommentPageReceipt.company_id
    ) & (ResearchCommentCheckpoint.id == ResearchCommentPageReceipt.checkpoint_id)).where(
        ResearchCommentCheckpoint.company_id == company_id,
        ResearchCommentCheckpoint.observation_id == observation_id,
    )
    withheld = sum(row.withheld_private_count for row in (await db.scalars(receipts)).all())
    return {
        "received_unique_comments": int(versions or 0), "edge_count": len(rows),
        "pending_edges": sum(not row.pagination_exhausted for row in rows),
        "accessible_edges_exhausted": bool(rows) and all(row.pagination_exhausted for row in rows),
        "withheld_private_count": withheld, "history_complete": False,
        "content_status": "privacy_hold", "coverage_scope": "provider_accessible_edges_only",
    }


async def enqueue_comment_batches(db, now: datetime) -> int:
    """Recover configured work without dispatching or granting processing rights.

    No active decisions are created on deploy or from policy notes. The source
    lock serializes concurrent schedulers; PostgreSQL idempotency is the second
    guard. This workflow does not toggle the source's 12-hour schedule intent.
    """
    sources = (await db.scalars(select(ResearchSource).join(Company, Company.id == ResearchSource.company_id).where(
        ResearchSource.source_type == "owned_facebook_page", ResearchSource.active.is_(True),
        Company.page_connection_state == "active",
    ).order_by(ResearchSource.id).limit(100).with_for_update(of=ResearchSource, skip_locked=True))).all()
    count = 0
    for source in sources:
        decision = await db.scalar(select(ResearchCommentProcessingDecision).where(
            ResearchCommentProcessingDecision.company_id == source.company_id,
            ResearchCommentProcessingDecision.source_id == source.id,
        ).order_by(ResearchCommentProcessingDecision.created_at.desc(), ResearchCommentProcessingDecision.id.desc()).limit(1))
        if decision is None or decision.status != "active" or _aware(decision.valid_until) <= now:
            continue
        policy_id = await db.scalar(select(ResearchPrivacyPolicyRevision.id).where(
            ResearchPrivacyPolicyRevision.company_id == source.company_id,
            ResearchPrivacyPolicyRevision.source_id == source.id,
        ).order_by(ResearchPrivacyPolicyRevision.revision_no.desc()).limit(1))
        if policy_id != decision.policy_revision_id:
            continue
        active = await db.scalar(select(Job.id).where(
            Job.company_id == source.company_id, Job.kind == "research_comments", Job.status.in_(["queued", "running"]),
            Job.result["source_id"].as_string() == source.id,
        ).limit(1))
        if active is not None:
            continue
        checkpoint = await db.scalar(select(ResearchCommentCheckpoint).where(
            ResearchCommentCheckpoint.company_id == source.company_id,
            ResearchCommentCheckpoint.source_id == source.id, ResearchCommentCheckpoint.pagination_exhausted.is_(False),
            ResearchCommentCheckpoint.status.in_(["privacy_hold", "queued", "partial"]),
        ).order_by(ResearchCommentCheckpoint.created_at, ResearchCommentCheckpoint.id).limit(1))
        if checkpoint is None:
            continue
        key = f"research-comments:{decision.id}:{checkpoint.id}"
        if await db.scalar(select(Job.id).where(Job.company_id == source.company_id, Job.idempotency_key == key)):
            continue
        db.add(Job(
            company_id=source.company_id, created_by=decision.assessed_by, kind="research_comments",
            title="Thu thập bình luận và replies vào vùng xử lý riêng tư", status="queued", progress=None,
            idempotency_key=key, result={"source_id": source.id, "decision_id": decision.id,
                                       "batches_completed": 0, "content_status": "privacy_hold"},
        ))
        count += 1
    if count:
        await db.flush()
    return count


async def _next_checkpoint(db, company_id: str, source_id: str):
    return await db.scalar(select(ResearchCommentCheckpoint).where(
        ResearchCommentCheckpoint.company_id == company_id, ResearchCommentCheckpoint.source_id == source_id,
        ResearchCommentCheckpoint.pagination_exhausted.is_(False),
        ResearchCommentCheckpoint.status.in_(["privacy_hold", "queued", "partial"]),
    ).order_by(ResearchCommentCheckpoint.created_at, ResearchCommentCheckpoint.id).limit(1))


async def _claim_comment_job(job_id: str) -> tuple[str, str, str] | None:
    async with SessionLocal() as db:
        job = await db.scalar(select(Job).where(Job.id == job_id, Job.kind == "research_comments").with_for_update())
        if job is None or job.status != "queued":
            return None
        if job.attempts >= settings.max_job_attempts:
            job.status = "failed"
            job.finished_at = utcnow()
            job.lease_until = None
            job.error = {"code": "comment_retry_limit", "message": "Lô bình luận đã hết số lần thử tự động.",
                         "retryable": False}
            await db.commit()
            return None
        retry_at = (job.result or {}).get("retry_not_before")
        if isinstance(retry_at, str):
            try:
                if _aware(datetime.fromisoformat(retry_at)) > utcnow():
                    return None
            except ValueError:
                return None
        from .page_gate import block_job_without_active_page
        if await block_job_without_active_page(db, job):
            await db.commit()
            return None
        source_id, decision_id = (job.result or {}).get("source_id"), (job.result or {}).get("decision_id")
        if not isinstance(source_id, str) or not isinstance(decision_id, str):
            job.status = "failed"
            job.error = {"code": "comment_job_context_missing", "message": "Thiếu ngữ cảnh xử lý bình luận."}
            job.finished_at = utcnow()
            await db.commit()
            return None
        token = new_id()
        job.status = "running"
        job.claim_token = token
        job.attempts += 1
        job.started_at = job.started_at or utcnow()
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        await db.commit()
        claim_job_fence(job_id, token)
        return job.company_id, source_id, decision_id


async def _finish_comment_batch(job_id: str, *, code: str | None = None, retryable: bool = False) -> None:
    async with SessionLocal() as db:
        await db.flush()
        job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if job is None:
            return
        result = dict(job.result or {})
        checkpoint = await _next_checkpoint(db, job.company_id, result["source_id"])
        continuation = code is None and checkpoint is not None
        retry = retryable and job.attempts < settings.max_job_attempts
        job.status = "queued" if continuation or retry else "failed" if code else "succeeded"
        job.error = {"code": code, "message": "Thu thập bình luận chưa hoàn tất; dữ liệu đã lưu vẫn được giữ.",
                     "retryable": retry} if code else None
        result["content_status"] = "privacy_hold"
        result["continuation_pending"] = continuation or retry
        result["batches_completed"] = int(result.get("batches_completed", 0)) + int(code is None)
        job.result = result
        job.finished_at = None if continuation or retry else utcnow()
        # Checkpoint success is progress, not a failed attempt. Normal backfill
        # may require hundreds of deliveries without exhausting three retries.
        if continuation:
            job.attempts = 0
        if retry:
            job.lease_until = utcnow() + timedelta(seconds=min(30 * job.attempts, 120))
            result["retry_not_before"] = job.lease_until.isoformat()
        else:
            result.pop("retry_not_before", None)
        job.result = result
        job.claim_token = new_id()  # Revoke before returning to durable queue.
        if not retry:
            job.lease_until = None
        # No flush after the transition. FencedAsyncSession asserts against
        # the database's previous running token, then atomically commits the
        # queued/terminal status and its revoked token.
        await db.commit()


async def _expire_comment_connection(work: CommentPageWork) -> None:
    async with SessionLocal() as db:
        await db.flush()
        company = await db.scalar(select(Company).where(Company.id == work.company_id).with_for_update())
        checkpoint = await db.scalar(select(ResearchCommentCheckpoint).where(
            ResearchCommentCheckpoint.id == work.checkpoint_id, ResearchCommentCheckpoint.company_id == work.company_id,
        ))
        if checkpoint is None:
            raise CommentCollectionHeld("comment_checkpoint_missing")
        source = await db.scalar(select(ResearchSource).where(
            ResearchSource.company_id == work.company_id, ResearchSource.id == checkpoint.source_id,
        ).with_for_update())
        if company is not None and source is not None:
            connection = await db.scalar(select(MetaPageConnection).where(
                MetaPageConnection.company_id == work.company_id, MetaPageConnection.id == source.connection_id,
            ).with_for_update())
            if connection is not None:
                if connection.encrypted_token != work.token_ciphertext or connection.page_id != work.page_id:
                    raise CommentCollectionHeld("comment_connection_changed")
                connection.status = "needs_reconnect"
                connection.last_error_code = "token_expired"
                company.page_connection_state = "needs_reconnect"
                await db.commit()


@isolated_job_fence
async def research_comments_task_async(job_id: str) -> None:
    context = await _claim_comment_job(job_id)
    if context is None:
        return
    company_id, source_id, decision_id = context
    deadline, received, requests = time.monotonic() + BATCH_SECONDS, 0, 0
    try:
        while received < 500 and requests < 20 and time.monotonic() < deadline:
            async with SessionLocal() as db:
                checkpoint = await _next_checkpoint(db, company_id, source_id)
                if checkpoint is None:
                    break
                checkpoint_id, cursor_hash = checkpoint.id, _cursor_hash(checkpoint.cursor_after)
            async with asyncio.timeout(max(0.001, deadline - time.monotonic())):
                await collect_comment_page(checkpoint_id, company_id=company_id, decision_id=decision_id,
                                           limit=min(100, 500 - received))
            requests += 1
            async with SessionLocal() as db:
                receipt = await db.scalar(select(ResearchCommentPageReceipt).where(
                    ResearchCommentPageReceipt.company_id == company_id,
                    ResearchCommentPageReceipt.checkpoint_id == checkpoint_id,
                    ResearchCommentPageReceipt.request_cursor_hash == cursor_hash,
                ))
                received += receipt.received_count + receipt.withheld_private_count if receipt else 0
        await _finish_comment_batch(job_id)
    except JobLeaseLost:
        return
    except CommentCollectionHeld as error:
        await _finish_comment_batch(job_id, code=error.code)
    except CommentQuarantineUnavailable:
        await _finish_comment_batch(job_id, code="comment_quarantine_unavailable")
    except TokenEncryptionUnavailable:
        await _finish_comment_batch(job_id, code="page_token_unavailable")
    except MetaGraphTokenExpired:
        await _finish_comment_batch(job_id, code="page_needs_reconnect")
    except MetaGraphRejected as error:
        await _finish_comment_batch(job_id, code="meta_comment_rate_limited" if error.retryable else "meta_comment_access_denied",
                                    retryable=error.retryable)
    except MetaGraphReadError:
        await _finish_comment_batch(job_id, code="meta_comment_read_failed", retryable=True)
    except TimeoutError:
        # A budget boundary keeps already committed pages and retries only the
        # uncommitted cursor on the next bounded delivery.
        await _finish_comment_batch(job_id, code="meta_comment_timeout" if requests == 0 else None,
                                    retryable=requests == 0)


@celery_app.task(name="services.worker.research_comments.research_comments_task", acks_late=True,
                 reject_on_worker_lost=True)
def research_comments_task(job_id: str) -> None:
    run_worker_coroutine(research_comments_task_async(job_id))
