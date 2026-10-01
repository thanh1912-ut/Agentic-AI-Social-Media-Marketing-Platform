"""Screened summaries → durable report → explicitly selected campaign.

Provider responses are synthetic. PostgreSQL variants use the real fenced
session, usage ledger and constraints; no live Gemini/Facebook calls.
"""
import asyncio
import copy
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from database.models import (
    AIUsageBudgetDay, AIUsageLedger, Campaign, Job, MarketReport,
    MarketReportCommentAnalysis, ResearchCommentAnalysisBatch, ResearchCycle, utcnow,
)
from services.research.comment_reports import result_hash
from services.worker import ai_budget, comment_analysis_tasks, comment_report_tasks, content_tasks, research_tasks
from tests.test_screened_comment_analysis import (
    FakeGemini, configured, enqueue, market_api, owned_api, postgres_only, screened,
)

# Imported fixtures are deliberately registered for the composed boundary.
__all__ = ["market_api", "owned_api", "screened"]


class ReportGemini(FakeGemini):
    def generate(self, *, system_prompt, input_payload, response_model):
        self.calls += 1
        self.inputs.append(copy.deepcopy(input_payload))
        if self.hook:
            self.hook()
        if self.fail:
            from services.agents.providers.errors import ProviderTimeoutError
            raise ProviderTimeoutError("Synthetic report timeout")
        batch_id = input_payload["screened_comment_analyses"][0]["batch_id"]
        parsed = response_model(headline="Hướng viết từ câu hỏi đã chọn", summary="Giải thích cách sử dụng; mẫu chưa đại diện toàn Page.",
            trends=[{"title": "Câu hỏi cách dùng", "explanation": "Một đoạn đã kiểm tra hỏi cách dùng.",
                     "confidence": 0.4, "comment_analysis_ids": [batch_id]}],
            suggestions=[{"title": "Hướng dẫn bắt đầu", "angle": "Giải thích cách dùng bằng nội dung có nguồn.",
                          "hook": "Bạn muốn bắt đầu từ đâu?", "format": "text", "comment_analysis_ids": [batch_id]}])
        return parsed, SimpleNamespace(model=self.model_name, input_tokens=20, output_tokens=10)


@pytest.fixture
def report_work(screened, monkeypatch):
    _client, sessions, _seed, _headers, _base, _body, _sent = screened
    postgres_only(sessions)
    configured(monkeypatch, FakeGemini())
    monkeypatch.setattr(comment_report_tasks, "SessionLocal", sessions)
    model = ReportGemini()
    monkeypatch.setattr(research_tasks, "configured_structured_model", lambda: model)
    parent_id = enqueue(screened)
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(parent_id))
    async def child():
        async with sessions() as db:
            parent = await db.get(Job, parent_id)
            assert parent.status == "succeeded"
            child_id = parent.result["report_job_id"]
            child = await db.get(Job, child_id)
            assert child.status == "queued" and child.last_dispatch_error == "queue_unavailable"
            assert await db.scalar(select(ResearchCycle.id).where(ResearchCycle.job_id == child_id))
            return child_id
    return screened, parent_id, asyncio.run(child()), model


def execute(work):
    _screened, _parent_id, child_id, _model = work
    asyncio.run(comment_report_tasks.comment_report_task_async(child_id))
    async def report_id():
        async with _screened[1]() as db:
            job = await db.get(Job, child_id)
            assert job.status == "succeeded", job.error
            return job.result["report_id"]
    return asyncio.run(report_id())


def draft(work, report_id):
    (client, _sessions, seed, headers, _base, *_), *_rest = work
    response = client.post(f"/api/v1/workspaces/{seed['company_id']}/market-research/reports/{report_id}/draft",
                           headers=headers, json={"suggestion_index": 0})
    assert response.status_code == 201, response.text
    return response.json()["campaign_id"]


def test_report_only_receives_summary_and_duplicate_delivery_is_idempotent(report_work):
    (client, sessions, seed, headers, base, body, _), parent, child, model = report_work
    report_id = execute(report_work)
    asyncio.run(comment_report_tasks.comment_report_task_async(child))
    asyncio.run(comment_analysis_tasks.comment_analysis_task_async(parent))
    assert model.calls == 1
    payload = model.inputs[0]
    assert payload["evidence"] == [] and payload["web_entity_snapshots"] == []
    assert body["comments"][0]["text"] not in str(payload)
    assert "author_alias" not in str(payload) and "Other question" not in str(payload)
    async def verify():
        async with sessions() as db:
            report = await db.get(MarketReport, report_id)
            pin = report.report_json["comment_analysis_refs"][0]
            batch = await db.get(ResearchCommentAnalysisBatch, pin["batch_id"])
            link = await db.scalar(select(MarketReportCommentAnalysis).where(MarketReportCommentAnalysis.report_id == report_id))
            assert link.result_hash == pin["result_hash"] == result_hash(batch.result_json)
            assert link.input_hash == batch.input_hash == pin["input_hash"]
            assert report.coverage_json["analysis_scope"] == "selected_screened_comments"
            assert report.report_json["privacy_coverage"]["comments_content_status"] == "screened_summaries"
            ledgers = (await db.scalars(select(AIUsageLedger).where(AIUsageLedger.company_id == seed["company_id"]))).all()
            assert len(ledgers) == 2 and all(row.status == "succeeded" for row in ledgers)
            assert all(row.result_json is None or set(row.result_json) == {"comment_analysis_batch_id"} for row in ledgers)
            day = await db.get(AIUsageBudgetDay, (seed["company_id"], ai_budget._budget_date()))
            assert day.spent_micro_usd == 106 and day.reserved_micro_usd == 0
            assert len((await db.scalars(select(Job).where(Job.idempotency_key == "comment-report:" + batch.id))).all()) == 1
    asyncio.run(verify())
    history = client.get(base + "/comment-analyses", headers=headers).json()["items"][0]
    assert history["report_job_id"] == child and history["report_id"] == report_id
    listing = client.get(f"/api/v1/workspaces/{seed['company_id']}/market-research/groups/{seed['group_id']}/reports", headers=headers)
    assert listing.status_code == 200 and listing.json()[0]["coverage"]["comment_provenance_status"] == "verified"


def test_selected_direction_pins_exact_analysis_without_latest_fallback(report_work):
    (client, sessions, seed, headers, base, body, _), _parent, _child, _model = report_work
    report_id = execute(report_work)
    campaign_id = draft(report_work, report_id)
    async def context():
        async with sessions() as db:
            campaign = await db.get(Campaign, campaign_id)
            before = copy.deepcopy(campaign.brief_json["market_research_context"])
            rows = await content_tasks._market_evidence_context(db, company_id=seed["company_id"],
                brand_id="synthetic-brand", campaign_group_id=seed["group_id"], brief_data=campaign.brief_json)
            assert len(rows) == 1 and rows[0]["source_kind"] == "comment_analysis"
            assert rows[0]["source_hash"] == before["comment_analysis_refs"][0]["result_hash"]
            assert "Người đọc hỏi cách dùng" in rows[0]["text"] and body["comments"][0]["text"] not in rows[0]["text"]
            # A changed result must not be consumed silently through the original pin.
            batch = await db.get(ResearchCommentAnalysisBatch, before["comment_analysis_refs"][0]["batch_id"])
            changed = copy.deepcopy(batch.result_json)
            changed["topics"][0]["summary"] = "Changed synthetic result"
            batch.result_json = changed
            await db.commit()
        async with sessions() as db:
            campaign = await db.get(Campaign, campaign_id)
            with pytest.raises(content_tasks.ContentGenerationFailure, match="Phân tích bình luận"):
                await content_tasks._market_evidence_context(db, company_id=seed["company_id"], brand_id="synthetic-brand",
                    campaign_group_id=seed["group_id"], brief_data=campaign.brief_json)
    asyncio.run(context())
    refused = client.post(f"/api/v1/workspaces/{seed['company_id']}/market-research/reports/{report_id}/draft",
                          headers=headers, json={"suggestion_index": 0})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "report_comment_analysis_unavailable"


def test_suppression_tombstones_only_dependent_reports_and_invalidates_campaign(report_work):
    (client, sessions, seed, headers, base, body, _), _parent, _child, _model = report_work
    report_id = execute(report_work)
    campaign_id = draft(report_work, report_id)
    independent_id = str(uuid4())
    async def independent():
        async with sessions() as db:
            db.add(MarketReport(id=independent_id, company_id=seed["company_id"], group_id=seed["group_id"],
                window_start=utcnow(), window_end=utcnow(), report_json={"headline": "Independent website report", "suggestions": []},
                evidence_ids_json=[], coverage_json={}))
            await db.commit()
    asyncio.run(independent())
    response = client.post(base + f"/comments/{body['comments'][0]['version_id']}/suppress",
                           headers=headers, json={"reason": "subject_request"})
    assert response.status_code == 200, response.text
    async def verify():
        async with sessions() as db:
            affected = await db.get(MarketReport, report_id)
            assert affected.report_json["status"] == "comment_data_erased"
            assert affected.report_json["suggestions"] == []
            assert (await db.get(MarketReport, independent_id)).report_json["headline"] == "Independent website report"
            campaign = await db.get(Campaign, campaign_id)
            assert campaign.version == 2 and "market_research_context" not in campaign.brief_json
            with pytest.raises(content_tasks.ContentGenerationFailure, match="Nguồn hướng viết"):
                await content_tasks._market_evidence_context(db, company_id=seed["company_id"], brand_id="synthetic-brand",
                    campaign_group_id=seed["group_id"], brief_data=campaign.brief_json)
    asyncio.run(verify())


@pytest.mark.parametrize("change", ["lease_lost", "suppress", "expired", "brand_applied"])
def test_context_or_lease_changed_during_provider_call_cannot_store_report(report_work, change):
    (client, sessions, seed, headers, base, body, _), parent_id, child_id, model = report_work
    def hook():
        async def mutate():
            async with sessions() as db:
                if change == "lease_lost":
                    job = await db.get(Job, child_id)
                    job.claim_token = str(uuid4())
                    job.lease_until = utcnow() + timedelta(minutes=5)
                elif change == "expired":
                    parent = await db.get(Job, parent_id)
                    batch = await db.get(ResearchCommentAnalysisBatch, parent.result["batch_id"])
                    batch.provider_valid_until = utcnow() - timedelta(seconds=1)
                elif change == "brand_applied":
                    from database.models import Brand
                    db.add(Brand(company_id=seed["company_id"], profile={"profile_mode": "manual_text_v1",
                        "profile_text": "Synthetic owner-authored brand", "confirmed_at": utcnow().isoformat(),
                        "confirmed_by": seed["user_id"]}))
                else:
                    from services.research.comment_analysis import lock_source
                    from services.research.comment_suppression import suppress_comment_tree
                    from database.models import ResearchCommentVersion
                    await lock_source(db, seed["company_id"], seed["source_id"])
                    version = await db.get(ResearchCommentVersion, body["comments"][0]["version_id"])
                    await suppress_comment_tree(db, version=version, actor_id=seed["user_id"], reason="subject_request")
                await db.commit()
        asyncio.run(mutate())
    model.hook = hook
    asyncio.run(comment_report_tasks.comment_report_task_async(child_id))
    assert model.calls == 1
    async def verify():
        async with sessions() as db:
            assert not await db.scalar(select(MarketReport.id).where(MarketReport.company_id == seed["company_id"]))
    asyncio.run(verify())


def test_report_budget_wait_and_timeout_do_not_repeat_provider_calls(report_work):
    (_client, sessions, seed, _headers, _base, _body, _), _parent_id, child_id, model = report_work
    async def exhausted():
        async with sessions() as db:
            day = await db.get(AIUsageBudgetDay, (seed["company_id"], ai_budget._budget_date()))
            day.spent_micro_usd = day.limit_micro_usd
            await db.commit()
    asyncio.run(exhausted())
    asyncio.run(comment_report_tasks.comment_report_task_async(child_id))
    assert model.calls == 0
    async def reset():
        async with sessions() as db:
            job = await db.get(Job, child_id)
            assert job.status == "queued" and job.result["retry_not_before"]
            job.result = {key: value for key, value in job.result.items() if key != "retry_not_before"}
            job.lease_until = None
            day = await db.get(AIUsageBudgetDay, (seed["company_id"], ai_budget._budget_date()))
            day.spent_micro_usd = 53
            await db.commit()
    asyncio.run(reset())
    model.fail = True
    asyncio.run(comment_report_tasks.comment_report_task_async(child_id))
    assert model.calls == 1
    async def recover():
        async with sessions() as db:
            job = await db.get(Job, child_id)
            assert job.status == "failed" and job.error["code"] == "provider_outcome_unknown"
            job.status = "queued"
            job.lease_until = None
            await db.commit()
    asyncio.run(recover())
    asyncio.run(comment_report_tasks.comment_report_task_async(child_id))
    assert model.calls == 1


def test_missing_cycle_fails_durably_without_provider(report_work):
    (_client, sessions, _seed, _headers, _base, _body, _), _parent_id, child_id, model = report_work
    from sqlalchemy import delete
    async def remove():
        async with sessions() as db:
            await db.execute(delete(ResearchCycle).where(ResearchCycle.job_id == child_id))
            await db.commit()
    asyncio.run(remove())
    asyncio.run(comment_report_tasks.comment_report_task_async(child_id))
    assert model.calls == 0
    async def verify():
        async with sessions() as db:
            job = await db.get(Job, child_id)
            assert job.status == "failed" and job.error["code"] == "comment_report_cycle_missing"
    asyncio.run(verify())


def test_report_link_catalog_matches_fresh_and_upgrade():
    fresh, upgrade = os.getenv("POSTGRES_COMMENT_REPORT_FRESH_URL"), os.getenv("POSTGRES_COMMENT_REPORT_UPGRADE_URL")
    if not fresh or not upgrade:
        pytest.skip("Disposable migration URLs required")
    def catalog(connection):
        inspector = inspect(connection)
        table = "market_report_comment_analyses"
        return {
            "columns": sorted((c["name"], str(c["type"]), c["nullable"], str(c["default"])) for c in inspector.get_columns(table)),
            "unique": sorted((c["name"], c["column_names"]) for c in inspector.get_unique_constraints(table)),
            "indexes": sorted((c["name"], c["column_names"], c["unique"]) for c in inspector.get_indexes(table)),
            "fks": sorted((c["name"], c["constrained_columns"], c["referred_table"], c["referred_columns"], c["options"]) for c in inspector.get_foreign_keys(table)),
        }
    async def read(url):
        engine = create_async_engine(url, poolclass=NullPool)
        async with engine.connect() as connection:
            result = await connection.run_sync(catalog)
        await engine.dispose()
        return result
    assert asyncio.run(read(fresh)) == asyncio.run(read(upgrade))


def test_postgres_link_rejects_source_from_different_group(report_work):
    (_client, sessions, seed, _headers, _base, _body, _), _parent, _child, _model = report_work
    report_id = execute(report_work)
    from database.models import MetaPageGroup
    from sqlalchemy.exc import IntegrityError
    async def invalid_link():
        async with sessions() as db:
            original = await db.scalar(select(MarketReportCommentAnalysis).where(MarketReportCommentAnalysis.report_id == report_id))
            group_id, other_report_id = str(uuid4()), str(uuid4())
            db.add(MetaPageGroup(id=group_id, company_id=seed["company_id"], name="Another synthetic group", industry="", region=""))
            await db.flush()
            db.add(MarketReport(id=other_report_id, company_id=seed["company_id"], group_id=group_id,
                window_start=utcnow(), window_end=utcnow(), report_json={}, evidence_ids_json=[], coverage_json={}))
            await db.flush()
            db.add(MarketReportCommentAnalysis(company_id=seed["company_id"], group_id=group_id,
                report_id=other_report_id, source_id=seed["source_id"], batch_id=original.batch_id,
                input_hash=original.input_hash, result_hash=original.result_hash))
            with pytest.raises(IntegrityError, match="fk_report_comment_source_group"):
                await db.commit()
            await db.rollback()
    asyncio.run(invalid_link())


def test_brief_edit_preserves_pins_and_cannot_clear_erasure_marker(report_work):
    (client, sessions, seed, headers, base, body, _), _parent, _child, _model = report_work
    campaign_id = draft(report_work, execute(report_work))
    url = f"/api/v1/workspaces/{seed['company_id']}/campaigns/{campaign_id}"
    async def payload():
        async with sessions() as db:
            row = await db.get(Campaign, campaign_id)
            brief = {key: value for key, value in row.brief_json.items() if key not in {
                "market_research_context", "market_research_context_invalidated"}}
            return {"version": row.version, "name": row.name + " revised", "brief": brief,
                    "content_plan": row.content_plan_json, "pillars": row.pillars_json, "channels": row.channels_json}, copy.deepcopy(row.brief_json.get("market_research_context"))
    request, original = asyncio.run(payload())
    response = client.patch(url, headers=headers, json=request)
    assert response.status_code == 200, response.text
    assert response.json()["brief"]["market_research_context"] == original
    request, _ = asyncio.run(payload())
    forbidden = {**request, "brief": {**request["brief"], "market_research_context": None}}
    response = client.patch(url, headers=headers, json=forbidden)
    assert response.status_code == 409 and response.json()["error"]["code"] == "research_context_pinned"
    removed = client.post(base + f"/comments/{body['comments'][0]['version_id']}/suppress", headers=headers,
                          json={"reason": "subject_request"})
    assert removed.status_code == 200
    request, _ = asyncio.run(payload())
    response = client.patch(url, headers=headers, json=request)
    assert response.status_code == 200 and response.json()["brief"]["market_research_context_invalidated"]["reason"] == "comment_data_erased"
