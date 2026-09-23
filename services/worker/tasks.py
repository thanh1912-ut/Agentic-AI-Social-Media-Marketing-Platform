"""Durable document ingestion and Brand Profile extraction tasks."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from sqlalchemy import delete, select, update, func

from database.models import (
    Brand,
    Company,
    Document,
    DocumentChunk,
    Job,
    JobStep,
    User,
    BrandProfileRevision,
    utcnow,
)
from packages.contracts import BrandProfile as InternalBrandProfile
from packages.contracts import NormalizedDocument, SourceReference, TableBlock, TextBlock
from services.agents.brand_agent import BrandAgent
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.job_service import append_job_event
from services.api.storage import storage
from services.api.brand_profiles import _profile_revision, internal_profile_to_http
from services.ingestion.knowledge_store import PostgresKnowledgeIndex
from services.ingestion.parsers import ParseError, parse_document
from .celery_app import celery_app
from .model_provider import AIConfigurationError, OpenAIStructuredModel, configured_embedding_provider
from .ai_tasks import run_brand_profile_task


PROFILE_STEP = "create_brand_profile"
MAX_CONTEXT_CHUNKS = 40


async def _set_step(
    db,
    job_id: str,
    key: str,
    *,
    status: str,
    progress: int | None = None,
    message: str | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    step = await db.scalar(select(JobStep).where(JobStep.job_id == job_id, JobStep.step_key == key))
    if step is None:
        return
    step.status = status
    step.progress = progress
    step.message = message
    step.error = error
    if status == "running":
        step.started_at = utcnow()
        step.finished_at = None
    if status in {"succeeded", "failed", "skipped"}:
        step.finished_at = utcnow()


async def _claim_job(job_id: str, fallback_document_ids: list[str]) -> tuple[str, str, list[str]] | None:
    """CAS claim ensures only one worker delivery can own a queued job."""

    now = utcnow()
    async with SessionLocal() as db:
        claimed = await db.execute(
            update(Job)
            .where(
                Job.id == job_id,
                Job.status == "queued",
                Job.attempts < settings.max_job_attempts,
            )
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
            return None
        job = await db.get(Job, job_id)
        if job is None or job.kind != "document_ingest":
            await db.rollback()
            return None
        stored_ids = (job.result or {}).get("document_ids") or fallback_document_ids
        document_ids = list(dict.fromkeys(str(item) for item in stored_ids))
        documents = (
            await db.scalars(
                select(Document).where(
                    Document.company_id == job.company_id,
                    Document.id.in_(document_ids or {"__no_document__"}),
                    Document.deleted_at.is_(None),
                )
            )
        ).all()
        found_ids = {document.id for document in documents}
        if found_ids != set(document_ids):
            job.status = "failed"
            job.progress = 100
            job.finished_at = utcnow()
            job.lease_until = None
            job.error = {
                "code": "invalid_job_documents",
                "message": "Không thể xác minh đầy đủ tài liệu thuộc workspace.",
                "hint": "Tải lại tài liệu hoặc liên hệ quản trị viên.",
                "retryable": False,
            }
            await db.commit()
            return None
        await _set_step(db, job.id, "receive_file", status="succeeded", progress=100, message="Đã nhận tệp và kiểm tra quyền truy cập.")
        await _set_step(db, job.id, "detect_type", status="succeeded", progress=100, message="Đã xác nhận định dạng tài liệu.")
        await _set_step(db, job.id, "extract_text", status="running", progress=5, message="Đang đọc nội dung tài liệu.")
        job.progress = 10
        await append_job_event(db, job, "status", "Worker đã nhận job.", 10)
        await db.commit()
        return job.company_id, job.created_by, document_ids


async def _parse_uploaded_document(document: Document):
    if hasattr(storage, "path"):
        parsed_path = storage.path(document.storage_key)
        return parse_document(parsed_path, kind=document.kind, mime_type=document.mime_type, filename=document.filename)
    with TemporaryDirectory(prefix="agentic-ingest-") as temp_dir:
        parsed_path = Path(temp_dir) / Path(document.filename).name
        parsed_path.write_bytes(await storage.read(document.storage_key))
        return parse_document(parsed_path, kind=document.kind, mime_type=document.mime_type, filename=document.filename)


def _normalized_document(document: Document, brand: Brand, parsed) -> NormalizedDocument:
    text_blocks = [
        TextBlock(
            block_id=f"{document.id}:text:{index}",
            text=block.text,
            locator=block.locator,
            heading=block.heading,
            extraction_warnings=block.warnings,
        )
        for index, block in enumerate(parsed.text_blocks, start=1)
    ]
    table_blocks = [
        TableBlock(
            block_id=f"{document.id}:table:{index}",
            headers=table.headers,
            rows=table.rows,
            locator=table.locator,
            extraction_warnings=table.warnings,
        )
        for index, table in enumerate(parsed.table_blocks, start=1)
    ]
    return NormalizedDocument(
        company_id=document.company_id,
        brand_id=brand.id,
        document_id=document.id,
        source_id=document.source_id,
        source_version=document.source_version,
        source_hash=document.source_hash,
        text_blocks=text_blocks,
        table_blocks=table_blocks,
        extraction_warnings=parsed.warnings,
        active=document.is_active,
    )


async def _persist_normalized(
    *,
    company_id: str,
    document_id: str,
    normalized: NormalizedDocument,
    parsed,
    index: PostgresKnowledgeIndex,
    embedder=None,
) -> int:
    async with SessionLocal() as db:
        document = await db.scalar(
            select(Document).where(
                Document.id == document_id,
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            ).with_for_update()
        )
        if document is None:
            raise RuntimeError("document disappeared during ingestion")
        prior_versions = (
            await db.scalars(
                select(Document).where(
                    Document.company_id == company_id,
                    Document.source_id == document.source_id,
                    Document.id != document.id,
                    Document.is_active.is_(True),
                    Document.deleted_at.is_(None),
                ).with_for_update()
            )
        ).all()
        try:
            current_source_version = int(document.source_version)
        except (TypeError, ValueError):
            current_source_version = 1
        for prior in prior_versions:
            try:
                prior_source_version = int(prior.source_version)
            except (TypeError, ValueError):
                prior_source_version = 0
            if prior_source_version < current_source_version:
                prior.is_active = False
        await db.execute(delete(DocumentChunk).where(DocumentChunk.company_id == company_id, DocumentChunk.document_id == document_id))
        chunk_index = 0
        for block in normalized.text_blocks:
            db.add(
                DocumentChunk(
                    company_id=company_id,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    kind="text",
                    text=block.text,
                    locator=block.locator,
                    metadata_json={"block_id": block.block_id, "warnings": block.extraction_warnings},
                )
            )
            chunk_index += 1
        for block in normalized.table_blocks:
            table_text = " | ".join(block.headers) + "\n" + "\n".join(" | ".join(row) for row in block.rows)
            db.add(
                DocumentChunk(
                    company_id=company_id,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    kind="table",
                    text=table_text,
                    locator=block.locator,
                    metadata_json={"block_id": block.block_id, "headers": block.headers, "warnings": block.extraction_warnings},
                )
            )
            chunk_index += 1
        knowledge_chunks = await index.upsert(db, normalized, embedder=embedder)
        document.status = "ready"
        document.normalized_json = normalized.model_dump(mode="json")
        document.knowledge_status = "ready"
        document.profile_status = "pending"
        document.extracted = {
            **parsed.metadata,
            "characters": sum(len(block.text) for block in normalized.text_blocks),
            "warnings": parsed.warnings,
            "normalized_blocks": chunk_index,
            "knowledge_chunks": knowledge_chunks,
        }
        document.error = None
        document.processed_at = utcnow()
        await db.commit()
        return knowledge_chunks


async def _mark_document_error(company_id: str, document_id: str, error: dict[str, Any], *, unsupported: bool = False) -> None:
    async with SessionLocal() as db:
        document = await db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company_id))
        if document:
            document.status = "unsupported" if unsupported else "failed"
            document.error = error
            document.knowledge_status = "failed"
            document.profile_status = "failed"
            document.processed_at = utcnow()
            await db.commit()


async def _record_image_metadata(company_id: str, document_id: str, parsed) -> None:
    async with SessionLocal() as db:
        document = await db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company_id))
        if document:
            document.status = "ready"
            document.extracted = {**parsed.metadata, "warnings": parsed.warnings}
            document.normalized_json = None
            document.knowledge_status = "not_available"
            document.profile_status = "not_available"
            document.processed_at = utcnow()
            await db.commit()


async def _set_progress(job_id: str, progress: int, message: str, step_progress: int) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None or job.status != "running":
            return
        job.progress = progress
        job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
        await _set_step(db, job_id, "extract_text", status="succeeded", progress=100, message="Đã đọc và chuẩn hoá nội dung tệp.")
        await _set_step(db, job_id, "normalize", status="succeeded", progress=100, message="Đã lưu NormalizedDocument cùng hash, version và source locators.")
        await _set_step(db, job_id, "chunk_and_index", status="running", progress=step_progress, message=message)
        await append_job_event(db, job, "step", message, progress)
        await db.commit()


def _sanitize_profile_evidence(profile: InternalBrandProfile, retrieved) -> InternalBrandProfile:
    contexts: dict[str, list[Any]] = {}
    for item in retrieved:
        contexts.setdefault(item.chunk.source_id, []).append(item.chunk)
    facts = []
    for fact in profile.facts:
        references = []
        for reference in fact.evidence:
            candidates = contexts.get(reference.source_id, [])
            if not candidates:
                continue
            chunk = next((item for item in candidates if item.locator == reference.locator), candidates[0])
            excerpt = reference.excerpt
            if not excerpt or excerpt not in chunk.text:
                excerpt = chunk.text[: min(280, len(chunk.text))]
            references.append(
                SourceReference(
                    source_id=chunk.source_id,
                    document_id=chunk.document_id,
                    source_version=chunk.source_version,
                    locator=chunk.locator,
                    excerpt=excerpt,
                )
            )
        facts.append(fact.model_copy(update={"evidence": references}))
    return profile.model_copy(update={"facts": facts, "requires_confirmation": True})


async def _run_brand_profile(
    *,
    job_id: str,
    company_id: str,
    created_by: str,
    document_ids: list[str],
    all_document_ids: list[str],
    failed_documents: list[dict[str, Any]],
    image_ids: list[str],
    ingestion_warnings: list[str],
    index: PostgresKnowledgeIndex,
    agent: BrandAgent | None,
    embedder=None,
) -> tuple[int, dict[str, Any], list[str]]:
    async with SessionLocal() as db:
        company = await db.get(Company, company_id)
        brand = await db.scalar(select(Brand).where(Brand.company_id == company_id).with_for_update())
        if company is None or brand is None:
            raise RuntimeError("workspace brand record is missing")
        eligible = (
            await db.scalars(
                select(Document).where(
                    Document.company_id == company_id,
                    Document.id.in_(document_ids),
                    Document.is_active.is_(True),
                    Document.deleted_at.is_(None),
                    Document.status == "ready",
                    Document.knowledge_status == "ready",
                )
            )
        ).all()
        retrieved = await index.retrieve(
            db,
            "thương hiệu doanh nghiệp sản phẩm dịch vụ khách hàng mục tiêu giọng điệu",
            company_id=company_id,
            brand_id=brand.id,
            active_source_ids=None,
            embedder=embedder,
            top_k=MAX_CONTEXT_CHUNKS,
        )
        # The adapter joins active documents under this tenant before ranking.
        # No credentials, upload metadata, or user/session tokens enter context.
        if not retrieved:
            raise RuntimeError("no active normalized content is available for profile extraction")
        context = [
            {"source_id": item.chunk.source_id, "locator": item.chunk.locator, "text": item.chunk.text}
            for item in retrieved
        ]
        snapshot_payload = {
            "company_id": company_id,
            "brand_id": brand.id,
            "documents": [
                {
                    "document_id": document.id,
                    "source_id": document.source_id,
                    "source_version": document.source_version,
                    "source_hash": document.source_hash,
                }
                for document in sorted(eligible, key=lambda item: item.id)
            ],
            "retrieved_sources": [
                {
                    "document_id": item.chunk.document_id,
                    "source_id": item.chunk.source_id,
                    "source_version": item.chunk.source_version,
                    "source_hash": item.chunk.source_hash,
                    "locator": item.chunk.locator,
                }
                for item in retrieved
            ],
            "context": context,
        }
        snapshot_json = json.dumps(snapshot_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        input_snapshot_id = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
        if agent is None:
            agent = BrandAgent(OpenAIStructuredModel())
        await _set_step(db, job_id, PROFILE_STEP, status="running", progress=10, message="AI đang đề xuất hồ sơ thương hiệu từ các nguồn đang hoạt động.")
        job = await db.get(Job, job_id)
        if job:
            job.progress = 75
            job.lease_until = utcnow() + timedelta(minutes=settings.job_lease_minutes)
            await append_job_event(db, job, "step", "Đang tạo hồ sơ thương hiệu và gắn trích dẫn nguồn.", 75)
        await db.commit()

    async with SessionLocal() as db:
        existing_revision = await db.scalar(
            select(BrandProfileRevision).where(BrandProfileRevision.job_id == job_id)
        )
        if existing_revision is not None:
            return existing_revision.revision, existing_revision.run_metadata_json or {}, existing_revision.warnings_json or []

    result = await asyncio.to_thread(
        run_brand_profile_task,
        job_id=job_id,
        input_snapshot_id=input_snapshot_id,
        agent=agent,
        brand_id=brand.id,
        business_hint=f"{company.name}; {company.industry or ''}".strip("; "),
        context=context,
    )
    profile = _sanitize_profile_evidence(InternalBrandProfile.model_validate(result.payload), retrieved)
    warnings = list(ingestion_warnings) + list(profile.unknowns) + list(profile.contradictions)
    warnings.extend(
        warning
        for document in eligible
        for warning in (document.normalized_json or {}).get("extraction_warnings", [])
    )
    meta = result.metadata
    if meta:
        meta = meta.model_copy(update={"input_snapshot_id": input_snapshot_id})
    run_metadata = {
        "task_name": result.task_name,
        "job_id": job_id,
        "repair_attempts": result.repair_attempts,
        "generation": meta.model_dump(mode="json") if meta else None,
        "estimated_cost_available": False,
        "retrieved_chunks": len(retrieved),
    }
    source_refs = [
        reference.model_dump(mode="json")
        for fact in profile.facts
        for reference in fact.evidence
    ]
    async with SessionLocal() as db:
        company = await db.get(Company, company_id)
        brand = await db.scalar(select(Brand).where(Brand.company_id == company_id).with_for_update())
        actor = await db.get(User, created_by)
        if company is None or brand is None or actor is None:
            raise RuntimeError("workspace, brand, or actor disappeared during AI extraction")
        internal_payload = profile.model_dump(mode="json")
        internal_payload["profile_version"] = str(brand.version + 1)
        http_payload = await internal_profile_to_http(
            db,
            internal=internal_payload,
            brand=brand,
            company=company,
        )
        await _profile_revision(
            db,
            brand,
            company,
            actor,
            profile=http_payload,
            internal_profile=internal_payload,
            source_refs=source_refs,
            job_id=job_id,
            input_snapshot_id=input_snapshot_id,
            input_snapshot=snapshot_payload,
            run_metadata=run_metadata,
            warnings=warnings,
        )
        ready_documents = (
            await db.scalars(
                select(Document).where(
                    Document.company_id == company_id,
                    Document.id.in_([document.id for document in eligible]),
                )
            )
        ).all()
        for document in ready_documents:
            document.profile_status = "ready"
        partial = bool(failed_documents or image_ids)
        job = await db.get(Job, job_id)
        if job is None:
            raise RuntimeError("job disappeared during AI extraction")
        job.status = "failed" if partial else "succeeded"
        job.progress = 100
        job.finished_at = utcnow()
        job.lease_until = None
        job.result = {
            "document_ids": all_document_ids,
            "normalized_document_ids": document_ids,
            "failed_document_ids": [item["document_id"] for item in failed_documents],
            "metadata_only_document_ids": image_ids,
            "brand_id": brand.id,
            "profile_version": brand.version,
            "profile_run": run_metadata,
            "warnings": list(dict.fromkeys(warnings)),
            "partial": partial,
        }
        if partial:
            job.error = {
                "code": "partial_batch",
                "message": "Một số tệp chưa thể đưa vào hồ sơ thương hiệu.",
                "hint": "Kiểm tra các tệp bị lỗi rồi tải lại riêng.",
                "retryable": False,
            }
        else:
            job.error = None
        await _set_step(db, job_id, "chunk_and_index", status="succeeded", progress=100, message="Knowledge chunks đã được lưu; nguồn cũ hoặc đã xoá không còn trong retrieval.")
        await _set_step(db, job_id, PROFILE_STEP, status="succeeded", progress=100, message=f"Đã lưu Brand Profile bản {brand.version} cùng nguồn và input snapshot.")
        await append_job_event(db, job, "status", "Hoàn tất trích xuất hồ sơ thương hiệu." if not partial else "Đã tạo hồ sơ; một phần tệp trong batch bị lỗi.", 100)
        await db.commit()
    return brand.version, run_metadata, warnings


async def _fail_job(job_id: str, *, code: str, message: str, hint: str, retryable: bool) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is None or job.status in {"succeeded", "failed", "cancelled"}:
            return
        should_retry = retryable and job.attempts < settings.max_job_attempts
        job.status = "queued" if should_retry else "failed"
        job.progress = min(job.progress or 0, 90) if should_retry else 100
        job.finished_at = None if should_retry else utcnow()
        job.lease_until = None
        job.error = {"code": code, "message": message, "hint": hint, "retryable": should_retry}
        active_steps = (
            await db.scalars(select(JobStep).where(JobStep.job_id == job_id, JobStep.status == "running"))
        ).all()
        for step in active_steps:
            step.status = "pending" if should_retry else "failed"
            step.progress = None if should_retry else 100
            step.message = "Đang chờ worker thử lại." if should_retry else message
            step.error = job.error
            step.finished_at = None if should_retry else utcnow()
        await append_job_event(db, job, "error", message, job.progress)
        await db.commit()


async def ingest_document_task_batch_async(
    job_id: str,
    document_ids: list[str],
    *,
    agent: BrandAgent | None = None,
    index: PostgresKnowledgeIndex | None = None,
    embedder=None,
) -> None:
    """Process a multipart upload and generate at most one profile revision."""

    claimed = await _claim_job(job_id, document_ids)
    if claimed is None:
        return
    company_id, created_by, scoped_document_ids = claimed
    knowledge_index = index or PostgresKnowledgeIndex()
    embedder = embedder or configured_embedding_provider()
    successful_text_ids: list[str] = []
    failed_documents: list[dict[str, Any]] = []
    image_ids: list[str] = []
    warnings: list[str] = []

    try:
        for offset, document_id in enumerate(scoped_document_ids, start=1):
            async with SessionLocal() as db:
                document = await db.scalar(
                    select(Document).where(
                        Document.id == document_id,
                        Document.company_id == company_id,
                        Document.deleted_at.is_(None),
                    )
                )
                brand = await db.scalar(select(Brand).where(Brand.company_id == company_id))
                if document is None or brand is None:
                    failed_documents.append({"document_id": document_id, "code": "not_found"})
                    continue
                if document.status == "ready" and document.knowledge_status == "ready" and document.normalized_json:
                    successful_text_ids.append(document.id)
                    continue
                document.status = "processing"
                document.error = None
                document.profile_status = "pending"
                await db.commit()
                document_snapshot = {
                    "id": document.id,
                    "filename": document.filename,
                    "kind": document.kind,
                    "mime_type": document.mime_type,
                    "storage_key": document.storage_key,
                    "company_id": document.company_id,
                    "source_id": document.source_id,
                    "source_version": document.source_version,
                    "source_hash": document.source_hash,
                    "is_active": document.is_active,
                    "parser_version": document.parser_version,
                }
            document_obj = Document(**document_snapshot)
            try:
                parsed = await _parse_uploaded_document(document_obj)
                if document_obj.kind == "image":
                    await _record_image_metadata(company_id, document_id, parsed)
                    image_ids.append(document_id)
                    warnings.extend(parsed.warnings)
                    continue
                if not parsed.text_blocks and not parsed.table_blocks:
                    raise ParseError("empty_content", f"Tệp “{document_obj.filename}” không có nội dung văn bản.", "Hãy tải lên tài liệu có văn bản hoặc bảng dữ liệu.")
                async with SessionLocal() as db:
                    brand = await db.scalar(select(Brand).where(Brand.company_id == company_id))
                    if brand is None:
                        raise RuntimeError("workspace brand record is missing")
                    normalized = _normalized_document(document_obj, brand, parsed)
                await _persist_normalized(
                    company_id=company_id,
                    document_id=document_id,
                    normalized=normalized,
                    parsed=parsed,
                    index=knowledge_index,
                    embedder=embedder,
                )
                successful_text_ids.append(document_id)
                warnings.extend(parsed.warnings)
                progress = 20 + int(35 * offset / len(scoped_document_ids))
                await _set_progress(job_id, progress, f"Đã chuẩn hoá {offset}/{len(scoped_document_ids)} tài liệu.", int(100 * offset / len(scoped_document_ids)))
            except ParseError as exc:
                await _mark_document_error(
                    company_id,
                    document_id,
                    {"code": exc.code, "message": exc.message, "hint": exc.hint},
                    unsupported=exc.code == "unsupported_type",
                )
                failed_documents.append({"document_id": document_id, "code": exc.code, "message": exc.message})
                if exc.retryable:
                    await _fail_job(job_id, code=exc.code, message=exc.message, hint=exc.hint, retryable=True)
                    return

    except Exception:
        await _fail_job(
            job_id,
            code="ingestion_error",
            message="Không thể hoàn tất bước đọc và chuẩn hoá tài liệu.",
            hint="Hệ thống sẽ tự thử lại nếu còn lượt; nếu lỗi tiếp diễn, hãy kiểm tra tệp hoặc liên hệ hỗ trợ.",
            retryable=True,
        )
        return

    if successful_text_ids:
        try:
            await _set_progress(job_id, 65, "Các đoạn đã được lưu bền vững; đang chuẩn bị ngữ cảnh cho AI.", 100)
            profile_version, run_metadata, profile_warnings = await _run_brand_profile(
                job_id=job_id,
                company_id=company_id,
                created_by=created_by,
                document_ids=successful_text_ids,
                all_document_ids=scoped_document_ids,
                failed_documents=failed_documents,
                image_ids=image_ids,
                ingestion_warnings=warnings,
                index=knowledge_index,
                agent=agent,
                embedder=embedder,
            )
            warnings.extend(profile_warnings)
            return
        except AIConfigurationError:
            retryable = False
            code = "ai_not_configured"
            message = "Chưa cấu hình dịch vụ AI cho worker."
            hint = "Quản trị viên cần cấu hình OPENAI_API_KEY ở server rồi chạy lại tài liệu."
        except Exception:
            retryable = True
            code = "brand_profile_generation_failed"
            message = "Chưa thể tạo hồ sơ thương hiệu từ tài liệu."
            hint = "Hệ thống sẽ tự thử lại nếu còn lượt; không tải lại tệp để tránh tạo bản trùng."
        async with SessionLocal() as db:
            for document in (await db.scalars(select(Document).where(Document.company_id == company_id, Document.id.in_(successful_text_ids)))).all():
                document.profile_status = "failed"
        await _fail_job(job_id, code=code, message=message, hint=hint, retryable=retryable)
        return

    error_code = "no_text_content" if image_ids and not failed_documents else "document_ingestion_failed"
    error_message = "Đã lưu metadata ảnh nhưng chưa có văn bản để tạo hồ sơ." if image_ids and not failed_documents else "Không có tài liệu văn bản nào xử lý thành công."
    error_hint = "Tải lên thêm PDF có lớp chữ, DOCX, XLSX, CSV hoặc TXT; OCR ảnh chưa được bật." if image_ids and not failed_documents else "Kiểm tra tệp lỗi trong danh sách tài liệu rồi tải lại."
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job:
            job.result = {
                "document_ids": scoped_document_ids,
                "normalized_document_ids": [],
                "failed_document_ids": [item["document_id"] for item in failed_documents],
                "metadata_only_document_ids": image_ids,
                "warnings": list(dict.fromkeys(warnings)),
                "partial": bool(image_ids and failed_documents),
            }
            job.status = "failed"
            job.progress = 100
            job.finished_at = utcnow()
            job.lease_until = None
            job.error = {"code": error_code, "message": error_message, "hint": error_hint, "retryable": False}
            await _set_step(db, job_id, "chunk_and_index", status="skipped", message="Không có văn bản chuẩn hoá để lập chỉ mục.")
            await _set_step(db, job_id, PROFILE_STEP, status="skipped", message="Bỏ qua vì batch không có văn bản để tạo hồ sơ.")
            await append_job_event(db, job, "error", error_message, 100)
            await db.commit()


@celery_app.task(bind=True, autoretry_for=(), acks_late=True, time_limit=1500, soft_time_limit=1400)
def ingest_document_task(self, job_id: str, document_id: str, document_ids: list[str] | None = None) -> None:
    asyncio.run(ingest_document_task_batch_async(job_id, document_ids or [document_id]))
