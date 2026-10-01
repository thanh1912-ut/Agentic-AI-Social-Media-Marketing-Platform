"""Validate local review scope for owned Meta and signed-out public Pages.

This is never consent or permission to transmit candidates to an AI provider.
Caller locks company/source before enabling decision/connection row locks.
"""
from datetime import timezone
from sqlalchemy import select
from database.models import Company, Membership, MetaPageConnection, ResearchCommentProcessingDecision, ResearchPrivacyPolicyRevision, ResearchSource, utcnow
from .comment_quarantine import CommentQuarantineUnavailable, encrypt_candidate


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def active_local_comment_decision(db, source, *, expected_id=None, lock=False, public_only=False):
    source = await db.scalar(select(ResearchSource).where(
        ResearchSource.company_id == source.company_id, ResearchSource.id == source.id))
    if source is None:
        return None
    company = await db.scalar(select(Company).where(Company.id == source.company_id))
    public = source.source_type == "competitor_facebook_page" and source.collection_mode == "public_web"
    owned = source.source_type == "owned_facebook_page"
    if company is None or not company.page_id or company.page_connection_state != "active" or not source.active or not (public or owned) or (public_only and not public):
        return None
    query = select(ResearchCommentProcessingDecision).where(
        ResearchCommentProcessingDecision.company_id == source.company_id,
        ResearchCommentProcessingDecision.source_id == source.id,
    ).order_by(ResearchCommentProcessingDecision.created_at.desc(), ResearchCommentProcessingDecision.id.desc()).limit(1)
    decision = await db.scalar(query.with_for_update() if lock else query)
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
        Membership.user_id == decision.assessed_by, Membership.is_active.is_(True), Membership.role == "owner")
    if not await db.scalar(owner.with_for_update() if lock else owner):
        return None
    if owned:
        connection = select(MetaPageConnection.id).where(MetaPageConnection.company_id == company.id,
            MetaPageConnection.id == source.connection_id, MetaPageConnection.page_id == company.page_id,
            MetaPageConnection.status == "verified", MetaPageConnection.active.is_(True),
            MetaPageConnection.verified_at.is_not(None), MetaPageConnection.encrypted_token.is_not(None))
        if not await db.scalar(connection.with_for_update() if lock else connection):
            return None
    try:
        encrypt_candidate("", binding={"scope": "configuration-validation"})
    except CommentQuarantineUnavailable:
        return None
    return decision
