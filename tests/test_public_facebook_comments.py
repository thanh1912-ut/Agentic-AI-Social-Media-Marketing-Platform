"""Synthetic public Page adapter/persistence/API regression (not live Facebook)."""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import select

from database.models import (
    MarketObservation, ResearchCommentCheckpoint, ResearchCommentPageReceipt,
    ResearchCommentProcessingDecision, ResearchCommentVersion, ResearchSource, utcnow,
)
from services.research import facebook_cli_collector as collector
from services.research.comment_quarantine import decrypt_candidate
from services.worker import research_tasks
from tests.helpers.comment_frontier import seed_comment_frontier
from tests.test_market_research_api import market_api as _market_api_fixture
from tests.test_research_comment_quarantine import comment_sessions as _comment_sessions_fixture

# Re-export fixture objects, independent of test-module collection order.
market_api = _market_api_fixture
comment_sessions = _comment_sessions_fixture


def post_payload():
    return {"id": "456", "comment_records": collector._safe_comments([
        {"id": "opaque-comment-one", "author_alias": "user_name01", "author_id": "not-persisted",
         "author_name": "Private synthetic name", "text": "Giá? Gọi 0901 234 567 hoặc person@example.invalid",
         "published_at": "2026-09-30T01:00:00Z", "text_truncated": False,
         "likes": 2, "reactions": 9, "reaction_breakdown": {"LIKE": 2, "LOVE": 7}, "reply_count": 3},
        {"id": "opaque-comment-two", "author_alias": "user_name01", "text": "Câu hỏi khác",
         "text_truncated": False, "likes": 9, "reactions": 9, "reaction_breakdown": {}, "reply_count": None},
    ]), "comment_coverage": {"mode": "tier0_embedded", "returned_count": 2,
        "provider_reported_count": 200, "next_cursor_present": True, "stop_reason": "signed_out_embedded_comments"}}


async def seed_public(sessions):
    seed = await seed_comment_frontier(sessions)
    async with sessions() as db:
        source = await db.get(ResearchSource, seed["source_id"])
        source.source_type = "competitor_facebook_page"
        source.collection_mode = "public_web"
        source.connection_id = None
        await db.commit()
        return seed, source


async def persist(seed, source, *, time=None, decision_id=None, payload=None):
    return await research_tasks._persist_evidence(company_id=seed["company_id"], group_id=seed["group_id"],
        source=source, url=source.url + "/posts/456", title="Synthetic post", text="Synthetic post",
        published_at=None, metrics={"comments":200, "reaction_breakdown":{"LIKE":5},
        "comment_coverage":post_payload()["comment_coverage"]}, comments=[], raw_body=None,
        observed_at=time or utcnow(), public_external_id="456", public_comment_post=payload or post_payload(),
        comment_decision_id=decision_id or seed["decision_id"])


def test_public_comments_pin_versions_replay_and_keep_individual_counts(comment_sessions):
    async def exercise():
        seed, source = await seed_public(comment_sessions)
        observed = utcnow()
        await persist(seed, source, time=observed)
        await persist(seed, source, time=observed)
        async with comment_sessions() as db:
            rows=(await db.scalars(select(ResearchCommentVersion))).all()
            assert len(rows)==2
            assert rows[0].likes==2 and rows[1].likes is None
            assert rows[0].redaction_json["reactions"]==9
            assert rows[0].redaction_json["author_alias"]=="user_name01"
            assert not any(v in str(rows[0].redaction_json) for v in ("Private synthetic name","not-persisted"))
            binding={"company_id":seed["company_id"],"source_id":source.id,
                     "observation_id":rows[0].observation_id,"comment_id":rows[0].external_comment_id}
            text=decrypt_candidate(rows[0].candidate_ciphertext,binding=binding)
            assert "0901" not in text and "person@example.invalid" not in text
            assert rows[0].status=="privacy_hold" and rows[0].expires_at-rows[0].captured_at<=timedelta(hours=24)
            observation=await db.get(MarketObservation,rows[0].observation_id)
            assert observation.comments_json==[]
            assert observation.metrics_json["comment_coverage"]["history_complete"] is False
            checkpoint=await db.scalar(select(ResearchCommentCheckpoint).where(
                ResearchCommentCheckpoint.observation_id==observation.id))
            assert checkpoint.received_count==2 and not checkpoint.pagination_exhausted
            assert len((await db.scalars(select(ResearchCommentPageReceipt))).all())==1
        await persist(seed, source, time=observed+timedelta(seconds=1))
        async with comment_sessions() as db:
            assert len((await db.scalars(select(ResearchCommentVersion))).all())==4
    asyncio.run(exercise())


@pytest.mark.parametrize("change",["revoked","collector_changed","source_disabled"])
def test_public_comment_decision_rechecked_after_fetch(comment_sessions,change):
    async def exercise():
        seed,source=await seed_public(comment_sessions)
        async with comment_sessions() as db:
            if change=="revoked":
                decision=await db.get(ResearchCommentProcessingDecision,seed["decision_id"])
                decision.status="revoked"
            else:
                current=await db.get(ResearchSource,source.id)
                if change=="collector_changed":
                    current.collection_mode="manual"
                else:
                    current.active=False
            await db.commit()
        if change=="source_disabled":
            with pytest.raises(Exception,match="Nguồn nghiên cứu đã bị tắt"):
                await persist(seed,source)
        else:
            await persist(seed,source)
        async with comment_sessions() as db:
            assert not (await db.scalars(select(ResearchCommentVersion))).all()
    asyncio.run(exercise())


def test_adapter_does_not_treat_reactions_as_likes_and_bounds_output():
    records=post_payload()["comment_records"]
    assert records[1]["likes"] is None and records[1]["reactions"]==9
    assert "author_name" not in records[0] and "author_id" not in records[0]
    assert collector.safe_reaction_breakdown({"LIKE":2,"LOVE":False,"person_name":12})=={"LIKE":2}
    with pytest.raises(Exception,match="Danh sách bình luận"):
        collector._safe_comments([{}]*101)


@pytest.mark.parametrize("raw,precision", [("1,2K", "approximate"), ("100+", "lower_bound"),
                                          ("12", "exact"), ("Private name", "unknown")])
def test_comment_reaction_counts_keep_display_precision_without_personal_text(raw, precision):
    value = {"id": "synthetic-comment", "author_alias": "user_name01", "text": "Question",
             "text_truncated": False, "reactions": 1200, "reactions_raw": raw}
    record = collector._safe_comments([value])[0]
    assert record["reactions_precision"] == precision
    assert record["reactions_raw"] == (raw if precision != "unknown" else None)
    assert record["author_identity_known"] is False


@pytest.mark.parametrize("reported,mode", [(2, "tier0_embedded"), (1, "unavailable")])
def test_adapter_rejects_mismatched_comment_coverage(tmp_path, monkeypatch, reported, mode):
    from tests.test_facebook_cli_collector import _row, _runner
    monkeypatch.setattr(collector, "canonicalize_url", lambda value: value)
    page = {"id": "123", "name": "Synthetic Page", "url": "https://www.facebook.com/synthetic", "kind": "page"}
    post = {"id": "456", "author_id": "123", "url": page["url"] + "/posts/456", "text": "Post",
            "counts": {}, "comment_records": [{"id": "synthetic-one", "author_alias": "user_name01",
            "text": "Comment", "text_truncated": False}], "comment_coverage": {"mode": mode,
            "returned_count": reported, "stop_reason": "signed_out_embedded_comments"}}
    rows = "\n".join([_row("page", page=page), _row("post", post=post),
                     _row("summary", engine_version=collector.ENGINE_VERSION, http_requests=2)])
    executable = _runner(tmp_path, f"import sys\nsys.stdout.write({rows!r} + '\\n')\n")
    with pytest.raises(Exception, match="Độ đầy đủ bình luận"):
        asyncio.run(collector.collect_public_facebook_page(page["url"], run_id="synthetic-run",
                    post_limit=10, include_comments=True, runner_path=executable))


def test_unavailable_comment_coverage_preserves_actual_access_reason():
    value = collector.safe_comment_coverage({"mode": "unavailable", "returned_count": 0,
                "provider_reported_count": 99, "stop_reason": "login_required", "history_complete": True})
    assert value["mode"] == "unavailable" and value["stop_reason"] == "login_required"
    assert value["history_complete"] is False


def test_public_comment_review_api_is_owner_scoped_expiring_and_revocable(market_api,monkeypatch):
    from types import SimpleNamespace
    from database.models import User, Membership
    from services.api.security import create_access_token
    from services.research import comment_quarantine
    client,sessions,key=market_api
    monkeypatch.setattr(comment_quarantine,'settings',SimpleNamespace(meta_token_encryption_key=key,meta_token_encryption_key_previous=''))
    monkeypatch.setattr(research_tasks,'SessionLocal',sessions)
    seed,source=asyncio.run(seed_public(sessions))
    async def token_for_seed():
        async with sessions() as db:
            user=await db.get(User,seed['user_id'])
            return create_access_token(user)[0]
    token=asyncio.run(token_for_seed())
    base=f"/api/v1/workspaces/{seed['company_id']}/market-research/sources/{source.id}"
    headers={'Authorization':'Bearer '+token}
    state=client.get(base+'/comment-processing',headers=headers)
    assert state.status_code==200 and state.json()['collection_allowed'] is True
    evidence_id=asyncio.run(persist(seed,source))
    first=client.get(base+f'/posts/{evidence_id}/comments',headers=headers,params={'limit':1})
    assert first.status_code==200,first.text
    data=first.json()
    assert first.headers['cache-control']=='no-store, private'
    assert data['status']=='privacy_hold' and len(data['comments'])==1 and data['next_cursor']
    assert data['provider_transmission_allowed'] is False
    assert data['comments'][0]['author_alias']=='user_name01'
    assert data['comments'][0]['author_identity_known'] is False
    assert data['comments'][0]['likes'] in (None,2) and data['comments'][0]['reactions']==9
    assert not any(v in first.text for v in ('0901 234 567','person@example.invalid','opaque-comment-one'))
    second=client.get(base+f'/posts/{evidence_id}/comments',headers=headers,params={'cursor':data['next_cursor'],'limit':1})
    assert second.status_code==200
    assert {data['comments'][0]['likes'],second.json()['comments'][0]['likes']} == {2,None}
    assert not second.json()['next_cursor']
    # A real membership in a different workspace cannot expose this Page/post.
    other, _other_source = asyncio.run(seed_public(sessions))
    async def other_token():
        async with sessions() as db:
            return create_access_token(await db.get(User, other['user_id']))[0]
    cross = client.get(base.replace(seed['company_id'], other['company_id']) + f'/posts/{evidence_id}/comments',
                       headers={'Authorization': 'Bearer ' + asyncio.run(other_token())})
    assert cross.status_code == 404
    # Pagination is bound to the observation: a new run invalidates this cursor.
    asyncio.run(persist(seed,source,time=utcnow()+timedelta(seconds=1)))
    stale=client.get(base+f'/posts/{evidence_id}/comments',headers=headers,params={'cursor':data['next_cursor']})
    assert stale.status_code==409
    async def role(value):
        async with sessions() as db:
            member=await db.scalar(select(Membership).where(Membership.company_id==seed['company_id']))
            member.role=value
            await db.commit()
    for value in ('editor','viewer'):
        asyncio.run(role(value))
        denied=client.get(base+f'/posts/{evidence_id}/comments',headers=headers)
        assert denied.status_code==403
    asyncio.run(role('owner'))
    client.cookies.set('agentic_csrf','synthetic-csrf')
    revoke=client.post(base+'/comment-processing/revoke',headers={**headers,'X-CSRF-Token':'synthetic-csrf'},
                       json={'expected_decision_id':seed['decision_id']})
    assert revoke.status_code==200 and revoke.json()['status']=='revoked'
    async def bodies_removed():
        async with sessions() as db:
            return all(c.candidate_ciphertext is None for c in (await db.scalars(select(ResearchCommentVersion))).all())
    assert asyncio.run(bodies_removed())
    after=client.get(base+f'/posts/{evidence_id}/comments',headers=headers)
    assert after.status_code==200 and after.json()['comments']==[]
