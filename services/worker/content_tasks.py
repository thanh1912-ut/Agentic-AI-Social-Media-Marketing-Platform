"""Durable, tenant-scoped campaign content generation worker."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update

from database.models import (
    AuditEvent,
    Brand,
    BrandProfileRevision,
    Campaign,
    CampaignPost,
    Company,
    ContentGenerationRun,
    Document,
    Job,
    JobEvent,
    JobStep,
    PostApproval,
    PostVersion,
    new_id,
    utcnow,
)
from packages.contracts import BrandProfile as InternalBrandProfile
from packages.contracts import CampaignBrief
from packages.prompts import CONTENT_POST_PROMPT_VERSION, CONTENT_REVISE_PROMPT_VERSION
from services.agents.content_agent import ContentAgent
from services.agents.knowledge.interfaces import source_context
from services.agents.providers.errors import ProviderError
from services.api.config import settings
from services.api.db import SessionLocal
from services.ingestion.knowledge_store import PostgresKnowledgeIndex
from services.worker.ai_tasks import run_content_task
from services.worker.async_runtime import run_worker_coroutine
from services.worker.celery_app import celery_app
from services.worker.model_provider import AIConfigurationError, configured_embedding_provider, configured_structured_model


class ContentGenerationFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


async def _set_step(db, job_id: str, key: str, status: str, progress: int, message: str) -> None:
    step = await db.scalar(select(JobStep).where(JobStep.job_id == job_id, JobStep.step_key == key))
    if step is None:
        return
    step.status = status
    step.progress = progress
    step.message = message
    if status == "running":
        step.started_at = utcnow()
        step.finished_at = None
    elif status in {"succeeded", "failed", "skipped"}:
        step.finished_at = utcnow()


async def _append_event(db, job: Job, event_type: str, message: str, progress: int) -> None:
    last = await db.scalar(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.sequence.desc()))
    db.add(JobEvent(
        job_id=job.id,
        sequence=(last.sequence + 1) if last else 1,
        event_type=event_type,
        message=message,
        progress=progress,
        at=utcnow(),
    ))


def _field_value(profile: dict[str, Any], key: str, fallback: Any = None) -> Any:
    field = profile.get(key)
    return field.get("value", fallback) if isinstance(field, dict) else fallback


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = item.get("name") if isinstance(item, dict) else item
        if isinstance(text, str) and text.strip():
            result.append(text.strip())
    return result


def _confirmed_profile(brand: Brand, company: Company, revision: BrandProfileRevision) -> InternalBrandProfile:
    raw = brand.profile if isinstance(brand.profile, dict) else {}
    if (
        revision.revision != brand.version
        or revision.confirmed_at is None
        or not raw.get("confirmed_at")
    ):
        raise ContentGenerationFailure(
            "brand_profile_not_confirmed",
            "Hồ sơ thương hiệu chưa được xác nhận ở phiên bản hiện tại.",
        )
    business = _field_value(raw, "description") or _field_value(raw, "business_name") or company.name
    if not isinstance(business, str) or not business.strip():
        business = company.name
    # Contact details and competitor notes are not needed for post drafting.
    voice = _strings(_field_value(raw, "tone_keywords", []))
    brand_voice = _field_value(raw, "brand_voice")
    if isinstance(brand_voice, str) and brand_voice.strip() and brand_voice not in voice:
        voice.append(brand_voice.strip())
    constraints = _strings(_field_value(raw, "do_not_use", []))
    return InternalBrandProfile(
        brand_id=brand.id,
        business=business.strip(),
        products=_strings(_field_value(raw, "products", [])),
        audience=_strings(_field_value(raw, "target_audience", [])),
        voice=voice,
        constraints=constraints,
        requires_confirmation=False,
        profile_version=str(brand.version),
    )


def _safe_metadata(metadata, snapshot_id: str, prompt_version: str = CONTENT_POST_PROMPT_VERSION) -> dict[str, Any] | None:
    if metadata is None:
        return None
    result = metadata.model_dump(mode="json")
    result.update({
        "prompt_version": prompt_version,
        "input_snapshot_id": snapshot_id,
        "estimated_cost_usd": None,
        "estimated_cost_available": False,
    })
    return result


async def _fail(job_id: str, failure: ContentGenerationFailure, *, attempts: int) -> None:
    retry = failure.retryable and attempts < settings.max_job_attempts
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None or job.status not in {"running", "queued"}:
            return
        if not retry and job.kind == "content_generation":
            result = dict(job.result or {})
            request = result.get("request") or {}
            slot_id = request.get("slot_id")
            if slot_id:
                campaign = await db.scalar(select(Campaign).where(
                    Campaign.id == result.get("campaign_id"),
                    Campaign.company_id == job.company_id,
                ).with_for_update())
                if campaign is not None:
                    plan = campaign.content_plan_json or {"strategy_summary": "", "slots": []}
                    updated_plan = {**plan, "slots": [dict(slot) for slot in plan.get("slots", [])]}
                    slot = next((item for item in updated_plan["slots"] if item.get("id") == slot_id), None)
                    if slot is not None and slot.get("generation_job_id") == job.id:
                        slot.pop("generation_job_id", None)
                        campaign.content_plan_json = updated_plan
                        expected_campaign_version = result.get("campaign_version")
                        context_is_current = campaign.version == expected_campaign_version
                        campaign.version += 1
                        campaign.updated_at = utcnow()
                        if context_is_current:
                            result["campaign_version"] = campaign.version
                            job.result = result
        job.status = "queued" if retry else "failed"
        job.progress = 15 if retry else 100
        job.finished_at = None if retry else utcnow()
        job.lease_until = None
        job.error = {
            "code": failure.code,
            "message": str(failure),
            "hint": "Hệ thống sẽ tự thử lại." if retry else "Kiểm tra cấu hình, hồ sơ thương hiệu và các nguồn tài liệu rồi gửi yêu cầu mới.",
            "retryable": retry,
        }
        steps = (await db.scalars(select(JobStep).where(JobStep.job_id == job_id))).all()
        for step in steps:
            if step.status == "running":
                step.status = "pending" if retry else "failed"
                step.progress = None if retry else 100
                step.message = str(failure)
                step.error = job.error
                step.finished_at = None if retry else utcnow()
        await _append_event(db, job, "error", str(failure), job.progress or 0)
        await db.commit()


async def content_generation_task_async(
    job_id: str,
    *,
    agent: ContentAgent | None = None,
    index: PostgresKnowledgeIndex | None = None,
    embedder=None,
) -> None:
    """Claim one queued job, retrieve approved workspace context, and save drafts atomically."""

    now = utcnow()
    async with SessionLocal() as db:
        claimed = await db.execute(
            update(Job)
            .where(Job.id == job_id, Job.kind.in_(("content_generation", "content_revise")), Job.status == "queued", Job.attempts < settings.max_job_attempts)
            .values(
                status="running",
                started_at=func.coalesce(Job.started_at, now),
                attempts=Job.attempts + 1,
                lease_until=now + timedelta(minutes=settings.job_lease_minutes),
                progress=5,
            )
        )
        if claimed.rowcount != 1:
            await db.rollback()
            return
        job = await db.get(Job, job_id)
        payload = dict(job.result or {}) if job else {}
        company_id = job.company_id if job else ""
        created_by = job.created_by if job else ""
        job_kind = job.kind if job else "content_generation"
        attempts = (job.attempts if job else 0)
        await _set_step(db, job_id, "prepare_context", "running", 5, "Đang kiểm tra campaign, Brand Profile và tài liệu nguồn.")
        await _append_event(db, job, "progress", "Đã nhận job sinh nội dung.", 5)
        await db.commit()

    try:
        agent = agent or ContentAgent(configured_structured_model())
        embedder = embedder if embedder is not None else configured_embedding_provider()
        knowledge_index = index or PostgresKnowledgeIndex()
        target_post = None
        plan_slot = None
        base_content: dict[str, Any] = {}
        async with SessionLocal() as db:
            campaign = await db.scalar(select(Campaign).where(Campaign.id == payload.get("campaign_id"), Campaign.company_id == company_id))
            brand = await db.scalar(select(Brand).where(Brand.company_id == company_id))
            company = await db.get(Company, company_id)
            if campaign is None or brand is None or company is None:
                raise ContentGenerationFailure("content_context_missing", "Không tìm thấy campaign hoặc hồ sơ của workspace.")
            revision = await db.scalar(select(BrandProfileRevision).where(
                BrandProfileRevision.brand_id == brand.id,
                BrandProfileRevision.company_id == company_id,
                BrandProfileRevision.revision == brand.version,
            ))
            if revision is None:
                raise ContentGenerationFailure("brand_profile_not_confirmed", "Không tìm thấy phiên bản Brand Profile hiện tại.")
            if campaign.version != payload.get("campaign_version") or brand.version != payload.get("brand_version"):
                raise ContentGenerationFailure("content_context_changed", "Campaign hoặc Brand Profile đã đổi sau khi gửi yêu cầu; hãy tạo job mới.")
            if job_kind == "content_revise":
                target_post = await db.scalar(select(CampaignPost).where(
                    CampaignPost.id == payload.get("post_id"),
                    CampaignPost.company_id == company_id,
                    CampaignPost.campaign_id == campaign.id,
                ))
                if target_post is None:
                    raise ContentGenerationFailure("post_not_found", "Không tìm thấy bài viết trong workspace.")
                if target_post.current_version != payload.get("post_version"):
                    raise ContentGenerationFailure("version_conflict", "Bài viết đã đổi phiên bản; hãy tải lại trước khi yêu cầu AI sửa.")
                if target_post.status in {"scheduled", "published"}:
                    raise ContentGenerationFailure("post_not_revisable", "Không thể sửa AI bài đã lên lịch hoặc đã đăng.")
                base_version_row = await db.scalar(select(PostVersion).where(
                    PostVersion.company_id == company_id,
                    PostVersion.post_id == target_post.id,
                    PostVersion.version == target_post.current_version,
                ))
                if base_version_row is None:
                    raise ContentGenerationFailure("content_version_missing", "Không tìm thấy phiên bản nội dung cần sửa.")
                base_content = dict(base_version_row.content_json)
            profile = _confirmed_profile(brand, company, revision)
            request_data = payload["request"]
            brief_data = campaign.brief_json
            if request_data.get("slot_id") and not target_post:
                plan = campaign.content_plan_json or {}
                plan_slot = next((slot for slot in plan.get("slots", []) if slot.get("id") == request_data["slot_id"]), None)
                if plan_slot is None:
                    raise ContentGenerationFailure("content_slot_not_found", "Không tìm thấy slot nội dung trong campaign hiện tại.")
                if plan_slot.get("generated_post_id"):
                    raise ContentGenerationFailure("content_slot_already_generated", "Slot này đã được dùng để sinh bài.")
                if plan_slot.get("generation_job_id") != job_id:
                    raise ContentGenerationFailure("content_slot_reservation_lost", "Slot không còn được giữ cho job hiện tại.")
            strategy_summary = (campaign.content_plan_json or {}).get("strategy_summary", "") if not target_post else ""
            audience = brief_data.get("audience", [])
            slot_date = plan_slot.get("scheduled_date") if plan_slot else None
            requirements = (
                [f"Bắt buộc: {item}" for item in brief_data.get("must_include", [])]
                + [f"Tránh: {item}" for item in brief_data.get("must_avoid", [])]
                + ([f"Chiến lược nội dung campaign: {strategy_summary}"] if strategy_summary else [])
                + ([f"Chủ đề slot: {plan_slot['topic']}"] if plan_slot else [])
                + ([request_data["instruction"]] if request_data.get("instruction") else [])
            )
            brief = CampaignBrief(
                objective=brief_data.get("objective_note") or brief_data.get("objective") or campaign.name,
                audience="; ".join(_strings(audience)) or "Khách hàng mục tiêu của thương hiệu",
                channel=(campaign.channels_json or ["facebook_page"])[0],
                campaign_name=campaign.name,
                offer=brief_data.get("key_message"),
                start_date=slot_date or request_data.get("start_date") or brief_data.get("start_date"),
                end_date=slot_date or request_data.get("end_date") or brief_data.get("end_date"),
                user_requirements=requirements,
            )
            documents = (await db.scalars(select(Document).where(
                Document.company_id == company_id,
                Document.is_active.is_(True),
                Document.deleted_at.is_(None),
                Document.status == "ready",
                Document.knowledge_status == "ready",
                Document.normalized_json.is_not(None),
            ))).all()
            source_ids = {item.source_id for item in documents}
            brand_version = brand.version
            campaign_version = campaign.version
            query_parts = [campaign.name, brief.objective, brief.audience, brief.offer or "", strategy_summary, *brief.user_requirements]
            if target_post:
                query_parts.extend([str(base_content.get("caption", "")), *request_data.get("instruction", "").split()])
            query = " ".join(part for part in query_parts if part).strip()[:2000]
            retrieved = await knowledge_index.retrieve(
                db,
                query,
                company_id=company_id,
                brand_id=brand.id,
                active_source_ids=source_ids,
                embedder=embedder,
                chunker_version=settings.chunker_version,
                embedding_model_version="lexical-v1" if embedder is None else None,
                minimum_score=settings.minimum_relevance_score,
                minimum_semantic_score=settings.minimum_semantic_score,
                minimum_semantic_margin=settings.minimum_semantic_margin,
                minimum_hybrid_lexical_score=settings.minimum_hybrid_lexical_score,
                top_k=min(20, knowledge_index.max_context),
            )
            context = source_context([item.chunk for item in retrieved])
            if not context:
                raise ContentGenerationFailure("no_relevant_context", "Không có đoạn tài liệu đủ liên quan để làm căn cứ sinh nội dung.")
            snapshot_payload = {
                "company_id": company_id,
                "brand_id": brand.id,
                "brand_version": brand_version,
                "campaign_id": campaign.id,
                "campaign_version": campaign_version,
                "brief": brief.model_dump(mode="json"),
                "request": request_data,
                "post_version": payload.get("post_version") if target_post else None,
                "sources": [
                    {key: item.get(key) for key in ("source_id", "document_id", "source_version", "source_hash", "locator")}
                    for item in context
                ],
            }
            snapshot_id = hashlib.sha256(json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            await _set_step(db, job_id, "prepare_context", "succeeded", 100, f"Đã xác minh {len(context)} đoạn nguồn của workspace.")
            await _set_step(db, job_id, "generate_posts", "running", 10, "Đang gửi nội dung đã xác nhận và các đoạn nguồn tới DeepSeek.")
            job = await db.get(Job, job_id)
            if job:
                job.progress = 20
                job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
                await _append_event(db, job, "progress", "Đã lấy ngữ cảnh nguồn theo tenant và ngưỡng liên quan.", 20)
            await db.commit()

        generated: list[dict[str, Any]] = []
        count = 1 if target_post or plan_slot else int(request_data["count"])
        pillars = [target_post.pillar] if target_post else [plan_slot["pillar"]] if plan_slot else request_data["pillars"]
        formats = [target_post.format] if target_post else [plan_slot["format"]] if plan_slot else request_data["formats"]
        for offset in range(count):
            pillar = pillars[offset % len(pillars)]
            content_format = formats[offset % len(formats)]
            content_requirements = {
                "pillar": pillar,
                "format": content_format,
                "instruction": request_data.get("instruction"),
                "strategy_summary": strategy_summary if not target_post else "",
                "slot_topic": plan_slot.get("topic") if plan_slot else None,
                "start_date": brief.start_date.isoformat() if brief.start_date else None,
                "end_date": brief.end_date.isoformat() if brief.end_date else None,
            }
            if target_post:
                content_requirements.update({
                    "revision_scope": request_data.get("scope", "all"),
                    "existing_post": {
                        "caption": base_content.get("caption", ""),
                        "hook": base_content.get("hook"),
                        "cta": base_content.get("cta"),
                        "hashtags": base_content.get("hashtags", []),
                        "image_brief": base_content.get("image_brief"),
                    },
                })
            task_result = run_content_task(
                job_id=job_id,
                input_snapshot_id=snapshot_id,
                agent=agent,
                profile=profile,
                brief=brief,
                base_version=f"campaign-{campaign_version}-brand-{brand_version}",
                next_version=(int(payload["post_version"]) + 1) if target_post else 1,
                context=context,
                content_requirements=content_requirements,
                channel=brief.channel,
                operation="revise" if target_post else "generate",
            )
            if target_post and request_data.get("scope", "all") in {"caption", "all"} and not task_result.payload.get("citations"):
                raise ContentGenerationFailure(
                    "content_citations_missing",
                    "AI không trả nguồn xác minh cho caption đã sửa; phiên bản mới chưa được lưu.",
                )
            generated.append({
                "payload": task_result.payload,
                "metadata": task_result.metadata,
                "pillar": pillar,
                "format": content_format,
                "repairs": task_result.repair_attempts,
                "slot_id": plan_slot["id"] if plan_slot else None,
                "planned_date": plan_slot["scheduled_date"] if plan_slot else None,
            })
            async with SessionLocal() as db:
                job = await db.get(Job, job_id)
                if job is None or job.status != "running":
                    return
                progress = 20 + int(60 * (offset + 1) / count)
                job.progress = progress
                job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
                await _set_step(db, job_id, "generate_posts", "running", int(100 * (offset + 1) / count), f"Đã sinh {offset + 1}/{count} bản nháp.")
                await _append_event(db, job, "progress", f"Đã sinh {offset + 1}/{count} bản nháp.", progress)
                await db.commit()

        async with SessionLocal() as db:
            job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            campaign = await db.scalar(select(Campaign).where(Campaign.id == payload.get("campaign_id"), Campaign.company_id == company_id).with_for_update())
            brand = await db.scalar(select(Brand).where(Brand.company_id == company_id).with_for_update())
            if job is None or campaign is None or brand is None or job.status != "running":
                return
            revision = await db.scalar(select(BrandProfileRevision).where(
                BrandProfileRevision.brand_id == brand.id,
                BrandProfileRevision.revision == brand.version,
            ))
            if campaign.version != campaign_version or brand.version != brand_version or revision is None or revision.confirmed_at is None:
                raise ContentGenerationFailure("content_context_changed", "Campaign hoặc hồ sơ đã đổi khi nội dung được sinh; bản nháp chưa được lưu.")
            created_posts: list[str] = []
            metadata_items: list[dict[str, Any]] = []
            total_repairs = 0
            input_tokens = output_tokens = latency_ms = 0
            prompt_version = CONTENT_REVISE_PROMPT_VERSION if target_post else CONTENT_POST_PROMPT_VERSION
            for item in generated:
                generated_post = item["payload"]
                post_id = target_post.id if target_post else new_id()
                now = utcnow()
                metadata = _safe_metadata(item["metadata"], snapshot_id, prompt_version)
                if metadata:
                    metadata_items.append(metadata)
                    input_tokens += int(metadata["input_tokens"])
                    output_tokens += int(metadata["output_tokens"])
                    latency_ms += int(metadata["latency_ms"])
                total_repairs += int(item["repairs"])
                citation_data = generated_post.get("citations", [])
                content = {
                    "caption": generated_post["caption"],
                    "hook": generated_post.get("hook"),
                    "cta": generated_post.get("cta"),
                    "hashtags": generated_post.get("hashtags", []),
                    "image_brief": generated_post.get("image_brief"),
                    "media": [],
                    "citations": citation_data,
                    "evidence_ids": generated_post.get("evidence_ids", []),
                    "generation_metadata": metadata,
                }
                if item.get("slot_id"):
                    content["content_slot_id"] = item["slot_id"]
                    content["planned_date"] = item["planned_date"]
                next_version = 1
                version_source = "ai_generated"
                if target_post:
                    locked_post = await db.scalar(select(CampaignPost).where(
                        CampaignPost.id == target_post.id,
                        CampaignPost.company_id == company_id,
                    ).with_for_update())
                    if locked_post is None or locked_post.current_version != payload.get("post_version"):
                        raise ContentGenerationFailure("version_conflict", "Bài viết đã đổi phiên bản trong lúc AI sửa; kết quả chưa được lưu.")
                    if locked_post.status in {"scheduled", "published"}:
                        raise ContentGenerationFailure("post_not_revisable", "Bài viết đã lên lịch hoặc đã đăng; kết quả chưa được lưu.")
                    next_version = locked_post.current_version + 1
                    scope = request_data.get("scope", "all")
                    content = dict(locked_post.current_json)
                    if scope in {"caption", "all"}:
                        content.update({
                            "caption": generated_post["caption"],
                            "hook": generated_post.get("hook"),
                            "cta": generated_post.get("cta"),
                            "citations": citation_data,
                            "evidence_ids": generated_post.get("evidence_ids", []),
                        })
                    if scope in {"hashtags", "all"}:
                        content["hashtags"] = generated_post.get("hashtags", [])
                    if scope in {"media", "all"}:
                        # AI produces an image brief only; it cannot upload or replace media.
                        content["image_brief"] = generated_post.get("image_brief")
                    content["generation_metadata"] = metadata
                    had_approval = bool(await db.scalar(select(PostApproval.id).where(
                        PostApproval.company_id == company_id,
                        PostApproval.post_id == locked_post.id,
                        PostApproval.decision == "approved",
                    ).limit(1)))
                    locked_post.current_version = next_version
                    locked_post.current_json = content
                    locked_post.status = "draft"
                    locked_post.pending_approval_version = None
                    locked_post.requires_reapproval = had_approval
                    locked_post.rejection_reason = None
                    locked_post.updated_at = now
                    version_source = "ai_revised"
                else:
                    db.add(CampaignPost(
                        id=post_id,
                        company_id=company_id,
                        campaign_id=campaign.id,
                        channel=brief.channel,
                        pillar=item["pillar"],
                        format=item["format"],
                        status="draft",
                        current_version=1,
                        current_json=content,
                        created_at=now,
                        updated_at=now,
                    ))
                db.add(PostVersion(
                    id=new_id(),
                    company_id=company_id,
                    campaign_id=campaign.id,
                    post_id=post_id,
                    version=next_version,
                    content_json=content,
                    source=version_source,
                    created_by=created_by,
                    created_by_name="AI assistant",
                    generation_job_id=job_id,
                    created_at=now,
                ))
                created_posts.append(post_id)
            if plan_slot and created_posts:
                current_plan = campaign.content_plan_json or {"strategy_summary": "", "slots": []}
                updated_plan = {**current_plan, "slots": [dict(slot) for slot in current_plan.get("slots", [])]}
                target_slot = next((slot for slot in updated_plan["slots"] if slot.get("id") == plan_slot["id"]), None)
                if target_slot is None or target_slot.get("generated_post_id") or target_slot.get("generation_job_id") != job_id:
                    raise ContentGenerationFailure("content_slot_conflict", "Slot đã thay đổi hoặc được dùng bởi job khác; không lưu trùng bài.")
                target_slot["generated_post_id"] = created_posts[0]
                target_slot.pop("generation_job_id", None)
                campaign.content_plan_json = updated_plan
                campaign.version += 1
                campaign.updated_at = utcnow()
                db.add(AuditEvent(
                    company_id=company_id,
                    actor_user_id=created_by,
                    action="campaign.content_slot.generate",
                    entity_type="campaign",
                    entity_id=campaign.id,
                    metadata_json={"slot_id": plan_slot["id"], "post_id": created_posts[0], "version": campaign.version},
                ))
            db.add(ContentGenerationRun(
                id=new_id(),
                company_id=company_id,
                campaign_id=campaign.id,
                job_id=job_id,
                post_ids_json=created_posts,
                input_snapshot_id=snapshot_id,
                run_metadata_json={
                    "provider": "deepseek",
                    "model": metadata_items[0]["model"] if metadata_items else settings.llm_default_model,
                    "prompt_version": prompt_version,
                    "schema_version": "GeneratedPost",
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_ms": latency_ms,
                    "repair_attempts": total_repairs,
                    "estimated_cost_usd": None,
                    "estimated_cost_available": False,
                    "retrieval_mode": settings.retrieval_mode,
                    "source_count": len(context),
                    "brand_version": brand_version,
                    "campaign_version": campaign_version,
                },
            ))
            db.add(AuditEvent(
                company_id=company_id,
                actor_user_id=created_by,
                action="content.revise" if target_post else "content.generate",
                entity_type="post" if target_post else "campaign",
                entity_id=target_post.id if target_post else campaign.id,
                metadata_json={"job_id": job_id, "post_ids": created_posts, "count": len(created_posts), "provider": "deepseek"},
            ))
            job.status = "succeeded"
            job.progress = 100
            job.finished_at = utcnow()
            job.lease_until = None
            job.error = None
            job.result = {
                **payload,
                "post_ids": created_posts,
                "input_snapshot_id": snapshot_id,
                "provider": "deepseek",
                "model": metadata_items[0]["model"] if metadata_items else settings.llm_default_model,
                "retrieval_mode": settings.retrieval_mode,
                "source_count": len(context),
                "repair_attempts": total_repairs,
                "estimated_cost_usd": None,
                "estimated_cost_available": False,
            }
            await _set_step(db, job_id, "generate_posts", "succeeded", 100, "Đã sửa bản nháp bằng AI." if target_post else f"Đã sinh {len(created_posts)} bản nháp.")
            await _set_step(db, job_id, "save_posts", "succeeded", 100, "Đã lưu phiên bản mới, chờ người dùng duyệt; chưa đăng bài." if target_post else "Đã lưu draft và phiên bản; chưa gửi duyệt hay đăng bài.")
            await _append_event(db, job, "complete", "Đã lưu phiên bản AI sửa; cần người dùng duyệt lại nếu cần." if target_post else "Đã lưu các bản nháp sinh bằng AI.", 100)
            await db.commit()
    except ContentGenerationFailure as failure:
        await _fail(job_id, failure, attempts=attempts)
    except AIConfigurationError as error:
        await _fail(job_id, ContentGenerationFailure("ai_not_configured", str(error)), attempts=attempts)
    except ProviderError as error:
        await _fail(job_id, ContentGenerationFailure("deepseek_request_failed", str(error), retryable=error.retryable), attempts=attempts)
    except Exception:
        await _fail(
            job_id,
            ContentGenerationFailure("content_generation_failed", "Không thể hoàn tất việc sinh nội dung.", retryable=True),
            attempts=attempts,
        )


@celery_app.task(bind=True, autoretry_for=(), acks_late=True, time_limit=1500, soft_time_limit=1400)
def content_generation_task(self, job_id: str) -> None:
    run_worker_coroutine(content_generation_task_async(job_id))
