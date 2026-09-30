"""Synthetic-only comment fixture. Never activate its assessment on live data."""

from datetime import timedelta
import uuid

from sqlalchemy import select

from database.models import (
    Company, Membership, MetaPageConnection, MetaPageGroup, ResearchCommentCheckpoint,
    ResearchCommentProcessingDecision, ResearchPrivacyPolicyRevision, ResearchSource, User, new_id, utcnow,
)
from services.worker import research_tasks
from services.api.meta_tokens import encrypt_page_token, token_fingerprint


async def seed_comment_frontier(sessions):
    marker = uuid.uuid4().hex
    user_id, company_id, group_id, source_id, connection_id, policy_id, decision_id = (new_id() for _ in range(7))
    now = utcnow()
    async with sessions() as db:
        db.add(User(id=user_id, email=f"comment-fixture-{marker}@example.invalid", full_name="Synthetic fixture",
                    password_hash="not-a-login"))
        db.add(Company(id=company_id, name="Synthetic comment fixture", slug=f"comment-fixture-{marker}",
                       page_id=f"8{int(marker[:12], 16)}", page_connection_state="active"))
        await db.flush()
        company = await db.get(Company, company_id)
        page_id = company.page_id
        db.add(Membership(company_id=company_id, user_id=user_id, role="owner", is_active=True))
        db.add(MetaPageGroup(id=group_id, company_id=company_id, name="Research", industry="fixture", region="fixture"))
        await db.flush()
        db.add(MetaPageConnection(id=connection_id, company_id=company_id, group_id=group_id,
                                 page_id=page_id, encrypted_token=encrypt_page_token("synthetic-test-token"),
                                 token_fingerprint=token_fingerprint("synthetic-test-token"), status="verified",
                                 active=True, verified_at=now))
        await db.flush()
        db.add(ResearchSource(id=source_id, company_id=company_id, group_id=group_id, connection_id=connection_id,
                              source_type="owned_facebook_page", name="Synthetic comments", active=True,
                              url=f"https://www.facebook.com/{page_id}", normalized_url=f"https://www.facebook.com/{page_id}",
                              status="active", schedule_enabled=False, created_by=user_id))
        await db.flush()
        db.add(ResearchPrivacyPolicyRevision(id=policy_id, company_id=company_id, source_id=source_id,
                                            revision_no=1, purpose="Synthetic pagination test",
                                            processing_basis_reference="fixture only; no real personal data",
                                            policy_version="fixture-v1", requested_retention_days=90, configured_by=user_id))
        await db.flush()
        db.add(ResearchCommentProcessingDecision(id=decision_id, company_id=company_id, source_id=source_id,
                                                 policy_revision_id=policy_id, status="active", assessed_by=user_id,
                                                 assessment_reference="Synthetic test ONLY; not a live legal assessment",
                                                 created_at=now, valid_until=now + timedelta(days=1)))
        await db.commit()
    async with sessions() as db:
        source = await db.get(ResearchSource, source_id)
    post_id = f"{page_id}_456"
    await research_tasks._persist_evidence(company_id=company_id, group_id=group_id, source=source,
                                          url=f"https://www.facebook.com/{page_id}/posts/456", title="Synthetic post",
                                          text="Synthetic company post", published_at=now, metrics={"comments": 7},
                                          comments=[], raw_body=None, observed_at=now, page_id=page_id,
                                          external_post_id=post_id)
    async with sessions() as db:
        checkpoint = await db.scalar(select(ResearchCommentCheckpoint).where(
            ResearchCommentCheckpoint.company_id == company_id, ResearchCommentCheckpoint.source_id == source_id,
        ))
        return {"company_id": company_id, "source_id": source_id, "group_id": group_id,
                "user_id": user_id, "decision_id": decision_id, "policy_id": policy_id,
                "connection_id": connection_id, "post_id": post_id, "checkpoint_id": checkpoint.id,
                "observation_id": checkpoint.observation_id}
