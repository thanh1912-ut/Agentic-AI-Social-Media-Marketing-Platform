"""Pin approved comment summaries, and invalidate only their downstream reports."""
from __future__ import annotations

import json
from sqlalchemy import select

from database.models import (
    AIUsageLedger, Campaign, Job, MarketReport, MarketReportCommentAnalysis,
    ResearchCycle, ResearchSource, new_id, utcnow,
)
from services.agents.providers.comment_contracts import CommentAnalysis
from .comment_analysis import CommentAnalysisHeld, approved_input, text_hash, validate_screened_text


def result_hash(value):
    return text_hash(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


async def load_analysis(db, *, company_id, group_id, source_id, batch_id):
    source = await db.scalar(select(ResearchSource).where(ResearchSource.company_id == company_id,
        ResearchSource.group_id == group_id, ResearchSource.id == source_id))
    if source is None:
        raise CommentAnalysisHeld("comment_report_source_unavailable")
    batch, approved = await approved_input(db, company_id=company_id, source_id=source_id, batch_id=batch_id)
    if batch.status != "completed" or batch.result_json is None:
        raise CommentAnalysisHeld("comment_report_analysis_unavailable")
    parsed = CommentAnalysis.model_validate(batch.result_json)
    allowed = {item.evidence_ref for item in approved.comments}
    if any(ref not in allowed for topic in parsed.topics for ref in topic.evidence_refs):
        raise CommentAnalysisHeld("comment_report_citation_invalid")
    for topic in parsed.topics:
        validate_screened_text(topic.topic)
        validate_screened_text(topic.summary)
    for text in parsed.limitations:
        validate_screened_text(text)
    return {
        "batch_id": batch.id, "source_id": source.id,
        "input_hash": batch.input_hash, "result_hash": result_hash(parsed.model_dump(mode="json")),
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "coverage": {"selected_comments": len(approved.comments), "history_complete": False,
                     "selection_scope": "owner_screened_excerpts", "raw_comment_text_sent": False},
        "analysis": parsed.model_dump(mode="json"),
    }


async def enqueue_report(db, batch):
    """Called inside the parent job's fenced finish transaction; dispatch follows commit."""
    if not batch.result_json or not batch.result_json.get("topics"):
        return None
    key = "comment-report:" + batch.id
    existing = await db.scalar(select(Job).where(Job.company_id == batch.company_id, Job.idempotency_key == key))
    if existing is not None:
        return existing.id
    source = await db.scalar(select(ResearchSource).where(ResearchSource.company_id == batch.company_id,
        ResearchSource.id == batch.source_id))
    if source is None or not source.active:
        return None
    job = Job(id=new_id(), company_id=batch.company_id, created_by=batch.assessed_by,
        kind="research_comment_report", title="Đề xuất hướng viết từ bình luận đã kiểm tra", status="queued",
        progress=None, idempotency_key=key,
        result={"source_id": source.id, "batch_id": batch.id, "group_id": source.group_id})
    db.add(job)
    await db.flush()
    db.add(ResearchCycle(id=new_id(), company_id=batch.company_id, group_id=source.group_id, job_id=job.id,
        cycle_key=key, status="queued", source_results_json=[], collection_observed_at=utcnow()))
    return job.id


async def pinned_analysis(db, *, company_id, group_id, report_id, references):
    if not isinstance(references, list) or len(references) > 10:
        raise CommentAnalysisHeld("comment_report_pin_invalid")
    output = []
    seen = set()
    for pin in references:
        if not isinstance(pin, dict) or not all(isinstance(pin.get(key), str) for key in
                ("batch_id", "source_id", "input_hash", "result_hash")) or pin["batch_id"] in seen:
            raise CommentAnalysisHeld("comment_report_pin_invalid")
        seen.add(pin["batch_id"])
        link = await db.scalar(select(MarketReportCommentAnalysis).where(
            MarketReportCommentAnalysis.company_id == company_id, MarketReportCommentAnalysis.group_id == group_id,
            MarketReportCommentAnalysis.report_id == report_id, MarketReportCommentAnalysis.batch_id == pin["batch_id"],
            MarketReportCommentAnalysis.source_id == pin["source_id"]))
        if link is None or link.input_hash != pin["input_hash"] or link.result_hash != pin["result_hash"]:
            raise CommentAnalysisHeld("comment_report_pin_invalid")
        row = await load_analysis(db, company_id=company_id, group_id=group_id,
            source_id=pin["source_id"], batch_id=pin["batch_id"])
        if row["input_hash"] != pin["input_hash"] or row["result_hash"] != pin["result_hash"]:
            raise CommentAnalysisHeld("comment_report_analysis_changed")
        output.append(row)
    return output


async def invalidate_reports(db, *, company_id, source_id, batch_ids):
    """Exact dependency scope, never all reports of a source/workspace."""
    ids = set((await db.scalars(select(MarketReportCommentAnalysis.report_id).where(
        MarketReportCommentAnalysis.company_id == company_id, MarketReportCommentAnalysis.source_id == source_id,
        MarketReportCommentAnalysis.batch_id.in_(batch_ids)))).all())
    if not ids:
        return
    reports = (await db.scalars(select(MarketReport).where(MarketReport.company_id == company_id,
        MarketReport.id.in_(ids)).with_for_update())).all()
    cycles = {r.cycle_id for r in reports if r.cycle_id}
    for report in reports:
        report.report_json = {"status": "comment_data_erased", "headline": "Nguồn bình luận đã được xóa",
            "summary": "Báo cáo này không còn dùng để tạo nội dung.", "trends": [], "suggestions": []}
        report.coverage_json = {"status": "comment_data_erased", "source_data_removed": True}
        report.updated_at = utcnow()
    ledgers = (await db.scalars(select(AIUsageLedger).where(AIUsageLedger.company_id == company_id,
        AIUsageLedger.request_key.in_(["research-report:" + c for c in cycles])).with_for_update())).all()
    for row in ledgers:
        row.result_json = None
    campaigns = (await db.scalars(select(Campaign).where(Campaign.company_id == company_id).with_for_update())).all()
    for campaign in campaigns:
        brief = campaign.brief_json if isinstance(campaign.brief_json, dict) else {}
        context = brief.get("market_research_context")
        if isinstance(context, dict) and context.get("report_id") in ids:
            updated = dict(brief)
            updated.pop("market_research_context", None)
            updated["market_research_context_invalidated"] = {"reason": "comment_data_erased"}
            campaign.brief_json = updated
            campaign.version += 1
            campaign.updated_at = utcnow()
