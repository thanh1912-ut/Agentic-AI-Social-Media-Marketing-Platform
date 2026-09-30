from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
import asyncio

from cryptography.fernet import Fernet, InvalidToken
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.models import (
    Base, Company, Job, MetaPageConnection, ResearchCommentCheckpoint, ResearchCommentPageReceipt, ResearchCommentProcessingDecision,
    ResearchCommentVersion, ResearchPrivacyPolicyRevision, utcnow,
)
from services.api import meta_tokens
from services.api.meta_client import MetaComment, MetaCommentsPage
from services.research import comment_quarantine as quarantine
from services.worker import research_comments as comments, research_tasks
from tests.helpers.comment_frontier import seed_comment_frontier


@pytest.fixture
def comment_sessions(monkeypatch, tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'comments.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    secret = Fernet.generate_key().decode("ascii")
    cfg = SimpleNamespace(meta_token_encryption_key=secret, meta_token_encryption_key_previous="")
    monkeypatch.setattr(meta_tokens, "settings", cfg)
    monkeypatch.setattr(quarantine, "settings", cfg)
    monkeypatch.setattr(comments, "SessionLocal", sessions)
    monkeypatch.setattr(research_tasks, "SessionLocal", sessions)
    monkeypatch.setattr(comments, "settings", SimpleNamespace(meta_graph_version="v26.0", job_lease_minutes=5,
                                                             max_job_attempts=3))

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(setup())
    yield sessions
    asyncio.run(engine.dispose())


def item(seed, external_id="456_1", *, text="Synthetic question", parent=None, replies=0, likes=None):
    return MetaComment(external_id, seed["post_id"], parent, text, utcnow(), likes, replies, False)


def page(*items, next_cursor=None, total=None, withheld=0):
    return MetaCommentsPage(tuple(items), next_cursor, total, withheld, next_cursor is None)


def test_candidate_masks_patterns_but_stays_held_and_encrypts_in_separate_domain(comment_sessions):
    candidate = quarantine.screen_comment_candidate(
        "Gửi tới person@example.invalid, 0901 234 567. @private_handle Họ tên: Người Kiểm Thử; câu hỏi?"
    )
    assert not any(value in candidate.text for value in ("person@example.invalid", "0901 234 567", "@private_handle", "Người Kiểm Thử"))
    assert candidate.metadata["status"] == "privacy_hold"
    assert "unlabelled_names_not_detected" in candidate.metadata["limitations"]
    assert "private_handle" not in repr(candidate)
    binding = {"company_id": "synthetic-one", "observation_id": "synthetic-observation"}
    encrypted = quarantine.encrypt_candidate(candidate.text, binding=binding)
    assert candidate.text not in encrypted
    assert quarantine.decrypt_candidate(encrypted, binding=binding) == candidate.text
    with pytest.raises(quarantine.CommentQuarantineUnavailable):
        quarantine.decrypt_candidate(encrypted, binding={**binding, "company_id": "other-company"})
    with pytest.raises(InvalidToken):
        meta_tokens._fernet().decrypt(encrypted.encode())


def test_cursor_replay_overlap_edit_and_reply_coverage_are_atomic(comment_sessions):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        first = page(item(seed, text="person@example.invalid", replies=1), next_cursor="CURSOR_1", total=3, withheld=1)
        assert await comments.commit_comment_page(work, first)
        assert not await comments.commit_comment_page(work, first)
        second_work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        assert await comments.commit_comment_page(second_work, page(item(seed, text="person@example.invalid", replies=1),
                                                                  item(seed, "456_2", text="Edited later", likes=0), total=3))
        async with comment_sessions() as db:
            rows = (await db.scalars(select(ResearchCommentVersion))).all()
            assert len(rows) == 2
            assert all(row.status == "privacy_hold" and row.candidate_ciphertext for row in rows)
            assert all(row.expires_at - row.captured_at <= timedelta(hours=24) for row in rows)
            assert sorted(row.likes for row in rows if row.likes is not None) == [0]
            assert any(row.likes is None for row in rows)
            root = await db.get(ResearchCommentCheckpoint, seed["checkpoint_id"])
            assert root.received_count == 2 and root.pages_processed == 2 and root.pagination_exhausted
            child = await db.scalar(select(ResearchCommentCheckpoint).where(ResearchCommentCheckpoint.parent_key == "456_1"))
            coverage = await comments.comment_frontier_coverage(db, company_id=seed["company_id"], observation_id=seed["observation_id"])
            assert coverage["pending_edges"] == 1 and coverage["history_complete"] is False
            assert coverage["withheld_private_count"] == 1 and coverage["received_unique_comments"] == 2
        reply_work = await comments.prepare_comment_page(child.id, company_id=seed["company_id"], decision_id=seed["decision_id"])
        assert await comments.commit_comment_page(reply_work, page(item(seed, "456_3", parent="456_1", text="Synthetic reply"), total=1))
        async with comment_sessions() as db:
            coverage = await comments.comment_frontier_coverage(db, company_id=seed["company_id"], observation_id=seed["observation_id"])
            assert coverage["accessible_edges_exhausted"] and coverage["received_unique_comments"] == 3
            assert coverage["history_complete"] is False  # Hidden/deleted/provider omissions are not proven.
            assert len((await db.scalars(select(ResearchCommentPageReceipt))).all()) == 3
    asyncio.run(exercise())


def test_policy_change_revocation_stale_cursor_and_invalid_parent_cannot_commit(comment_sessions):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        with pytest.raises(comments.CommentCollectionHeld, match="identity_mismatch"):
            await comments.commit_comment_page(work, page(item(seed, parent="other-post-parent")))
        with pytest.raises(comments.CommentCollectionHeld, match="identity_mismatch"):
            await comments.commit_comment_page(work, page(replace(item(seed), root_post_id="999_888")))
        async with comment_sessions() as db:
            assert not (await db.scalars(select(ResearchCommentVersion))).all()
            assert not (await db.scalars(select(ResearchCommentPageReceipt))).all()
            db.add(ResearchPrivacyPolicyRevision(company_id=seed["company_id"], source_id=seed["source_id"], revision_no=2,
                                                 purpose="Changed purpose", processing_basis_reference="fixture", policy_version="v2",
                                                 configured_by=seed["user_id"]))
            await db.commit()
        with pytest.raises(comments.CommentCollectionHeld, match="decision_required"):
            await comments.commit_comment_page(work, page(item(seed)))
        async with comment_sessions() as db:
            assert not (await db.scalars(select(ResearchCommentVersion))).all()
    asyncio.run(exercise())


def test_cursor_cycles_fail_without_advancing_or_reinflating_counts(comment_sessions):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        def prepare():
            return comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        await comments.commit_comment_page(await prepare(), page(item(seed), next_cursor="A"))
        await comments.commit_comment_page(await prepare(), page(item(seed, "456_2"), next_cursor="B"))
        with pytest.raises(comments.CommentCollectionHeld, match="cursor_cycle"):
            await comments.commit_comment_page(await prepare(), page(item(seed, "456_3"), next_cursor="A"))
        async with comment_sessions() as db:
            checkpoint = await db.get(ResearchCommentCheckpoint, seed["checkpoint_id"])
            assert checkpoint.received_count == 2 and checkpoint.cursor_after == "B"
            assert len((await db.scalars(select(ResearchCommentVersion))).all()) == 2
    asyncio.run(exercise())


def test_expired_quarantine_removes_ciphertext_only_and_does_not_resurrect_on_replay(comment_sessions):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        received = page(item(seed))
        await comments.commit_comment_page(work, received)
        async with comment_sessions() as db:
            row = await db.scalar(select(ResearchCommentVersion))
            old_fingerprint = row.content_hash
            assert await comments.purge_expired_comment_quarantine(db, utcnow()) == 0
            assert await comments.purge_expired_comment_quarantine(db, utcnow() + timedelta(days=2)) == 1
            await db.commit()
        assert not await comments.commit_comment_page(work, received)
        async with comment_sessions() as db:
            row = await db.scalar(select(ResearchCommentVersion))
            assert row.candidate_ciphertext is None and row.status == "expired" and row.content_hash == old_fingerprint
    asyncio.run(exercise())


def test_batch_task_claim_and_duplicate_delivery_do_not_call_provider_or_duplicate_records(comment_sessions, monkeypatch):
    calls = []
    class SyntheticMetaClient:
        def __init__(self, *args):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def list_comments_page(self, post_id, **kwargs):
            calls.append(kwargs)
            return MetaCommentsPage((MetaComment("456_1", post_id, None, "Synthetic question", utcnow(), None, 0, False),),
                                    None, 1, 0, True)
    monkeypatch.setattr(comments, "MetaGraphClient", SyntheticMetaClient)
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        async with comment_sessions() as db:
            assert await comments.enqueue_comment_batches(db, utcnow()) == 1
            await db.commit()
            assert await comments.enqueue_comment_batches(db, utcnow()) == 0
            job = await db.scalar(select(Job).where(Job.kind == "research_comments"))
        await comments.research_comments_task_async(job.id)
        await comments.research_comments_task_async(job.id)
        async with comment_sessions() as db:
            saved = await db.get(Job, job.id)
            assert saved.status == "succeeded" and saved.result["content_status"] == "privacy_hold"
            assert len((await db.scalars(select(ResearchCommentVersion))).all()) == 1
            assert len(calls) == 1 and calls[0]["parent_comment_id"] is None
            assert await comments.enqueue_comment_batches(db, utcnow()) == 0
            decision = await db.get(ResearchCommentProcessingDecision, seed["decision_id"])
            decision.status = "revoked"
            await db.commit()
        with pytest.raises(comments.CommentCollectionHeld, match="decision_required"):
            await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
    asyncio.run(exercise())


def test_missing_key_rolls_back_all_candidates_receipts_and_cursor(comment_sessions, monkeypatch):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        monkeypatch.setattr(quarantine, "settings", SimpleNamespace(meta_token_encryption_key="", meta_token_encryption_key_previous=""))
        with pytest.raises(quarantine.CommentQuarantineUnavailable):
            await comments.commit_comment_page(work, page(item(seed), next_cursor="NEXT"))
        async with comment_sessions() as db:
            root = await db.get(ResearchCommentCheckpoint, seed["checkpoint_id"])
            assert root.cursor_after is None and root.pages_processed == 0
            assert not (await db.scalars(select(ResearchCommentVersion))).all()
            assert not (await db.scalars(select(ResearchCommentPageReceipt))).all()
    asyncio.run(exercise())


def test_an_expired_old_token_does_not_invalidate_a_new_connection(comment_sessions):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        async with comment_sessions() as db:
            connection = await db.get(MetaPageConnection, seed["connection_id"])
            connection.encrypted_token = meta_tokens.encrypt_page_token("new-synthetic-token")
            await db.commit()
        with pytest.raises(comments.CommentCollectionHeld, match="connection_changed"):
            await comments._expire_comment_connection(work)
        async with comment_sessions() as db:
            company = await db.get(Company, seed["company_id"])
            assert company.page_connection_state == "active"
        new_work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        await comments._expire_comment_connection(new_work)
        async with comment_sessions() as db:
            assert (await db.get(Company, seed["company_id"])).page_connection_state == "needs_reconnect"
    asyncio.run(exercise())


def test_revocation_erases_quarantine_before_ttl_without_returning_plaintext(comment_sessions):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        work = await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
        await comments.commit_comment_page(work, page(item(seed)))
        async with comment_sessions() as db:
            decision = await db.get(ResearchCommentProcessingDecision, seed["decision_id"])
            decision.status = "revoked"
            await db.commit()
            assert await comments.purge_expired_comment_quarantine(db, utcnow()) == 1
            await db.commit()
            version = await db.scalar(select(ResearchCommentVersion))
            assert version.candidate_ciphertext is None and version.status == "expired"
    asyncio.run(exercise())


def test_newer_revoked_decision_never_falls_back_to_older_active_assessment(comment_sessions):
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        async with comment_sessions() as db:
            db.add(ResearchCommentProcessingDecision(company_id=seed["company_id"], source_id=seed["source_id"],
                                                     policy_revision_id=seed["policy_id"], status="revoked",
                                                     assessed_by=seed["user_id"], assessment_reference="Synthetic revocation",
                                                     created_at=utcnow(), valid_until=utcnow() + timedelta(days=1)))
            await db.commit()
            assert await comments.enqueue_comment_batches(db, utcnow()) == 0
        with pytest.raises(comments.CommentCollectionHeld, match="decision_required"):
            await comments.prepare_comment_page(seed["checkpoint_id"], company_id=seed["company_id"], decision_id=seed["decision_id"])
    asyncio.run(exercise())


@pytest.mark.parametrize("failure", ["timeout", "token"])
def test_missing_token_and_budget_timeout_preserve_checkpoint_and_classify_job(comment_sessions, monkeypatch, failure):
    network_calls = []
    class SlowMetaClient:
        def __init__(self, *args):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def list_comments_page(self, *args, **kwargs):
            network_calls.append(1)
            await asyncio.sleep(0.05)
    monkeypatch.setattr(comments, "MetaGraphClient", SlowMetaClient)
    if failure == "timeout":
        monkeypatch.setattr(comments, "BATCH_SECONDS", 0.02)
    else:
        def missing_token(_ciphertext):
            raise meta_tokens.TokenEncryptionUnavailable("synthetic missing key")
        monkeypatch.setattr(comments, "decrypt_page_token", missing_token)
    async def exercise():
        seed = await seed_comment_frontier(comment_sessions)
        async with comment_sessions() as db:
            assert await comments.enqueue_comment_batches(db, utcnow()) == 1
            await db.commit()
            job = await db.scalar(select(Job).where(Job.kind == "research_comments"))
        await comments.research_comments_task_async(job.id)
        async with comment_sessions() as db:
            saved = await db.get(Job, job.id)
            assert saved.error["code"] == ("meta_comment_timeout" if failure == "timeout" else "page_token_unavailable")
            assert saved.status == ("queued" if failure == "timeout" else "failed")
            checkpoint = await db.get(ResearchCommentCheckpoint, seed["checkpoint_id"])
            assert checkpoint.cursor_after is None and checkpoint.pages_processed == 0
            assert not (await db.scalars(select(ResearchCommentVersion))).all()
        # Early duplicate delivery must respect retry_not_before or a terminal state.
        await comments.research_comments_task_async(job.id)
        assert len(network_calls) <= 1 if failure == "timeout" else not network_calls
    asyncio.run(exercise())
