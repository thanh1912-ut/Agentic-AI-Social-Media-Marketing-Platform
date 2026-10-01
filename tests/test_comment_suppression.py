"""Synthetic suppression fixtures, not live collection/legal certification."""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from database.models import (Company, Membership, ResearchCommentCheckpoint, ResearchCommentPageReceipt,
                             ResearchCommentSuppression, ResearchCommentVersion, utcnow)
from services.research.comment_suppression import suppress_comment_tree
from services.worker import research_comments as worker
from tests.test_research_comment_quarantine import comment_sessions, item, page
from tests.test_public_facebook_comments import market_api, seed_public, persist

# Keep imported pytest fixtures visible to collection.
__all__ = ["comment_sessions", "market_api"]


async def suppress(sessions, seed, version_id):
    async with sessions() as db:
        await db.scalar(select(Company).where(Company.id == seed["company_id"]).with_for_update())
        from database.models import ResearchSource
        await db.scalar(select(ResearchSource).where(ResearchSource.id == seed["source_id"]).with_for_update())
        row = await db.get(ResearchCommentVersion, version_id)
        result = await suppress_comment_tree(db, version=row, actor_id=seed["user_id"], reason="subject_request")
        await db.commit()
        return result


def test_public_erasure_all_observations_and_edited_content_cannot_reimport(comment_sessions):
    async def exercise():
        seed, source = await seed_public(comment_sessions)
        observed = utcnow()
        await persist(seed, source, time=observed)
        await persist(seed, source, time=observed + timedelta(seconds=1))
        async with comment_sessions() as db:
            target = await db.scalar(select(ResearchCommentVersion).where(
                ResearchCommentVersion.company_id == seed["company_id"],
                ResearchCommentVersion.external_comment_id == "opaque-comment-one"))
            version_id = target.id
        result = await suppress(comment_sessions, seed, version_id)
        assert result.identities_suppressed == 1 and result.versions_erased == 2
        replay = await suppress(comment_sessions, seed, version_id)
        assert replay.suppression_id == result.suppression_id and replay.versions_erased == 0
        await persist(seed, source, time=observed + timedelta(seconds=2))
        async with comment_sessions() as db:
            rows = (await db.scalars(select(ResearchCommentVersion))).all()
            blocked = [row for row in rows if row.external_comment_id == "opaque-comment-one"]
            assert len(blocked) == 2 and all(row.status == "suppressed" for row in blocked)
            assert all(row.candidate_ciphertext is None and row.likes is None and row.published_at is None
                       and row.redaction_json == {"status": "suppressed"} for row in blocked)
            assert len([row for row in rows if row.external_comment_id == "opaque-comment-two"]) == 3
            assert len((await db.scalars(select(ResearchCommentSuppression))).all()) == 1
            receipts = (await db.scalars(select(ResearchCommentPageReceipt))).all()
            assert sum(row.suppressed_count for row in receipts) == 1
    asyncio.run(exercise())


def test_owned_replies_erased_and_inflight_root_page_cannot_restore_parent(comment_sessions):
    from tests.helpers.comment_frontier import seed_comment_frontier
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        async def prepare(checkpoint_id=None):
            return await worker.prepare_comment_page(checkpoint_id or seed["checkpoint_id"],
                company_id=seed["company_id"], decision_id=seed["decision_id"])
        await worker.commit_comment_page(await prepare(), page(item(seed, replies=2), next_cursor="NEXT"))
        async with comment_sessions() as db:
            child = await db.scalar(select(ResearchCommentCheckpoint).where(
                ResearchCommentCheckpoint.company_id == seed["company_id"],
                ResearchCommentCheckpoint.parent_key == "456_1"))
            child_id = child.id
        await worker.commit_comment_page(await prepare(child_id),
            page(item(seed, "456_2", parent="456_1", replies=1)))
        async with comment_sessions() as db:
            grandchild = await db.scalar(select(ResearchCommentCheckpoint).where(
                ResearchCommentCheckpoint.company_id == seed["company_id"],
                ResearchCommentCheckpoint.parent_key == "456_2"))
            grandchild_id = grandchild.id
        await worker.commit_comment_page(await prepare(grandchild_id),
            page(item(seed, "456_3", parent="456_2")))
        inflight = await prepare()
        async with comment_sessions() as db:
            root = await db.scalar(select(ResearchCommentVersion).where(
                ResearchCommentVersion.company_id == seed["company_id"],
                ResearchCommentVersion.external_comment_id == "456_1"))
            version_id = root.id
        result = await suppress(comment_sessions, seed, version_id)
        assert result.identities_suppressed == 3 and result.versions_erased == 3 and result.reply_edges_stopped == 2
        await worker.commit_comment_page(inflight, page(item(seed, text="Changed source body", replies=3)))
        with pytest.raises(worker.CommentCollectionHeld, match="frontier_unavailable"):
            await prepare(child_id)
        async with comment_sessions() as db:
            rows = (await db.scalars(select(ResearchCommentVersion))).all()
            assert len(rows) == 3 and all(row.candidate_ciphertext is None for row in rows)
            assert sum(row.suppressed_count for row in (await db.scalars(select(ResearchCommentPageReceipt))).all()) == 1
    asyncio.run(exercise())


def test_suppression_api_csrf_roles_cross_tenant_and_reconnect_independence(market_api, monkeypatch):
    from types import SimpleNamespace
    from database.models import User
    from services.api.security import create_access_token
    from services.research import comment_quarantine
    from services.worker import research_tasks
    client, sessions, key = market_api
    monkeypatch.setattr(comment_quarantine, "settings", SimpleNamespace(
        meta_token_encryption_key=key, meta_token_encryption_key_previous=""))
    monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
    seed, source = asyncio.run(seed_public(sessions))
    evidence_id = asyncio.run(persist(seed, source))
    async def details():
        async with sessions() as db:
            row = await db.scalar(select(ResearchCommentVersion).where(
                ResearchCommentVersion.company_id == seed["company_id"]))
            return row.id, create_access_token(await db.get(User, seed["user_id"]))[0]
    version_id, token = asyncio.run(details())
    base = f"/api/v1/workspaces/{seed['company_id']}/market-research/sources/{source.id}"
    client.cookies.set("agentic_access", token)
    headers = {}
    url = base + f"/comments/{version_id}/suppress"
    body = {"reason": "subject_request"}
    assert client.post(url, headers=headers, json=body).status_code == 403
    client.cookies.set("agentic_csrf", "synthetic-csrf")
    headers["X-CSRF-Token"] = "synthetic-csrf"
    async def set_role(value):
        async with sessions() as db:
            member = await db.scalar(select(Membership).where(Membership.company_id == seed["company_id"]))
            member.role = value
            await db.commit()
    for role in ("viewer", "editor"):
        asyncio.run(set_role(role))
        assert client.post(url, headers=headers, json=body).status_code == 403
    asyncio.run(set_role("owner"))
    other, _ = asyncio.run(seed_public(sessions))
    assert client.post(url.replace(source.id, other["source_id"]), headers=headers, json=body).status_code == 404
    async def disconnected():
        async with sessions() as db:
            company = await db.get(Company, seed["company_id"])
            company.page_connection_state = "needs_reconnect"
            await db.commit()
    asyncio.run(disconnected())
    result = client.post(url, headers=headers, json=body)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store, private"
    assert result.json()["versions_erased"] == 1
    assert not any(value in result.text for value in ("opaque-comment", "Synthetic question", "external_comment_id"))
    assert client.post(url, headers=headers, json=body).json()["versions_erased"] == 0
    after = client.get(base + f"/posts/{evidence_id}/comments", headers=headers)
    assert after.status_code == 200 and after.json()["suppressed_comments_count"] == 1


def test_exported_deletion_ledger_reapplies_to_older_data_without_bodies(comment_sessions):
    from sqlalchemy import delete
    from services.research.comment_deletion_ledger import apply_deletion_ledger, export_deletion_ledger
    async def exercise():
        seed, source = await seed_public(comment_sessions)
        await persist(seed, source)
        async with comment_sessions() as db:
            target = await db.scalar(select(ResearchCommentVersion).where(
                ResearchCommentVersion.company_id == seed["company_id"],
                ResearchCommentVersion.external_comment_id == "opaque-comment-one"))
            snapshot = {column.name: getattr(target, column.name) for column in target.__table__.columns}
            version_id = target.id
        await suppress(comment_sessions, seed, version_id)
        async with comment_sessions() as db:
            records = [record async for record in export_deletion_ledger(db)]
            assert not any(term in records[0].model_dump_json() for term in ("candidate_ciphertext", "author_alias", "comment text"))
            await db.execute(delete(ResearchCommentSuppression))
            target = await db.get(ResearchCommentVersion, version_id)
            for key, value in snapshot.items():
                setattr(target, key, value)
            await db.commit()
        async with comment_sessions() as db:
            result = await apply_deletion_ledger(db, records)
            await db.commit()
            assert result["inserted"] == 1 and result["versions_erased"] == 1
            assert (await db.get(ResearchCommentVersion, version_id)).candidate_ciphertext is None
            replay = await apply_deletion_ledger(db, records)
            await db.commit()
            assert replay["inserted"] == 0 and replay["versions_erased"] == 0
    asyncio.run(exercise())
