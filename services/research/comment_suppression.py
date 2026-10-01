"""Erase local candidate bodies and prevent their re-import on later runs.

Callers hold the source lock in the same transaction as the operation. Collectors
check the ledger again when committing, never only before an external fetch.
The ledger contains restricted source IDs, not bodies or author identities.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from sqlalchemy import select, update

from database.models import MarketEvidence, ResearchCommentCheckpoint, ResearchCommentSuppression, ResearchCommentVersion, ResearchScreenedComment, new_id, utcnow


@dataclass(frozen=True)
class SuppressionResult:
    suppression_id: str
    identities_suppressed: int
    versions_erased: int
    reply_edges_stopped: int


async def post_key_hash(db, *, company_id: str, source_id: str, evidence_id: str) -> str:
    url = await db.scalar(select(MarketEvidence.canonical_url).where(
        MarketEvidence.company_id == company_id, MarketEvidence.source_id == source_id,
        MarketEvidence.id == evidence_id,
    ))
    if url is None:
        raise ValueError("suppression post is outside the requested tenant/source")
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def suppressed_ids(db, *, company_id: str, source_id: str, evidence_id: str) -> set[str]:
    key = await post_key_hash(db, company_id=company_id, source_id=source_id, evidence_id=evidence_id)
    return set((await db.scalars(select(ResearchCommentSuppression.external_comment_id).where(
        ResearchCommentSuppression.company_id == company_id,
        ResearchCommentSuppression.source_id == source_id,
        ResearchCommentSuppression.post_key_hash == key,
    ))).all())


async def suppress_comment_tree(db, *, version: ResearchCommentVersion, actor_id: str,
                                reason: str) -> SuppressionResult:
    """Root plus all known descendants across observations; cycle-safe CTE.

    The Owner's request removes all versions of these identities. Historical
    aggregate receipts remain observations of what was received, not assertions
    that all received content remains available. No source/network/AI call.
    """
    key = await post_key_hash(db, company_id=version.company_id, source_id=version.source_id,
                              evidence_id=version.evidence_id)
    scope = (ResearchCommentVersion.company_id == version.company_id,
             ResearchCommentVersion.source_id == version.source_id,
             ResearchCommentVersion.evidence_id == version.evidence_id)
    tree = select(ResearchCommentVersion.external_comment_id.label("comment_id")).where(
        *scope, ResearchCommentVersion.external_comment_id == version.external_comment_id,
    ).cte("suppressed_comment_tree", recursive=True)
    tree = tree.union(select(ResearchCommentVersion.external_comment_id).join(
        tree, ResearchCommentVersion.parent_key == tree.c.comment_id,
    ).where(*scope))
    identities = set((await db.scalars(select(tree.c.comment_id))).all())
    existing = (await db.scalars(select(ResearchCommentSuppression).where(
        ResearchCommentSuppression.company_id == version.company_id,
        ResearchCommentSuppression.source_id == version.source_id,
        ResearchCommentSuppression.post_key_hash == key,
        ResearchCommentSuppression.external_comment_id.in_(select(tree.c.comment_id)),
    ))).all()
    known = {row.external_comment_id: row.id for row in existing}
    now = utcnow()
    for identity in sorted(identities - known.keys()):
        entry_id = new_id()
        db.add(ResearchCommentSuppression(id=entry_id, company_id=version.company_id,
            source_id=version.source_id, post_key_hash=key, external_comment_id=identity,
            reason=reason, created_by=actor_id, created_at=now))
        known[identity] = entry_id
    await db.flush()
    erased = await db.execute(update(ResearchCommentVersion).where(
        *scope, ResearchCommentVersion.external_comment_id.in_(select(tree.c.comment_id)),
        ResearchCommentVersion.status != "suppressed",
    ).values(candidate_ciphertext=None, status="suppressed", redaction_json={"status": "suppressed"},
             likes=None, reply_count=None, published_at=None))
    stopped = await db.execute(update(ResearchCommentCheckpoint).where(
        ResearchCommentCheckpoint.company_id == version.company_id,
        ResearchCommentCheckpoint.source_id == version.source_id,
        ResearchCommentCheckpoint.evidence_id == version.evidence_id,
        ResearchCommentCheckpoint.parent_key.in_(select(tree.c.comment_id)),
        ResearchCommentCheckpoint.status != "suppressed",
    ).values(status="suppressed", cursor_after=None, stop_reason="comment_suppressed"))
    # Only batches actually using the erased identities are invalidated.
    # Topics can paraphrase any selected excerpt: remove the affected result
    # as a whole, rather than attempt unreliable substring redaction.
    batch_ids = (await db.scalars(select(ResearchScreenedComment.batch_id).where(
        ResearchScreenedComment.company_id == version.company_id,
        ResearchScreenedComment.source_id == version.source_id,
        ResearchScreenedComment.version_id.in_(select(ResearchCommentVersion.id).where(
            *scope, ResearchCommentVersion.external_comment_id.in_(select(tree.c.comment_id)))),
    ))).all()
    from .comment_analysis import erase_batches
    await erase_batches(db, company_id=version.company_id, source_id=version.source_id, batch_ids=batch_ids)
    return SuppressionResult(known[version.external_comment_id], len(identities), erased.rowcount, stopped.rowcount)
