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
    new_id,
    utcnow,
)
from database.job_fencing import claim_job_fence, isolated_job_fence
from packages.contracts import BrandProfile as InternalBrandProfile
from packages.contracts import NormalizedDocument, TableBlock, TextBlock
from services.agents.knowledge.interfaces import source_context
from services.api.config import settings
from services.api.db import SessionLocal
from services.api.job_service import append_job_event
from services.api.storage import storage
from services.ingestion.knowledge_store import PostgresKnowledgeIndex
from services.ingestion.parsers import ParseError, parse_document
from services.agents.knowledge.chunking import chunk_document
from services.worker.async_runtime import run_worker_coroutine
from .celery_app import celery_app
from services.ingestion.knowledge_store import embedding_identity
from .model_provider import AIConfigurationError, configured_embedding_provider


PROFILE_STEP = "create_brand_profile"  # Legacy job-step key retained for existing jobs.


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
    claim_token = new_id()
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
                claim_token=claim_token,
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
        if (job.result or {}).get("mode") == "profile_only":
            job.status = "failed"
            job.progress = 100
            job.finished_at = now
            job.lease_until = None
            job.claim_token = None
            job.error = {"code": "brand_profile_generation_removed", "message": "Tài liệu chỉ được đọc và lưu làm kiến thức."}
            await append_job_event(db, job, "error", "Brand Profile do Owner tự viết; không chạy AI trên tài liệu.", 100)
            await db.commit()
            return None
        await _set_step(db, job.id, "receive_file", status="succeeded", progress=100, message="Đã nhận tệp và kiểm tra quyền truy cập.")
        await _set_step(db, job.id, "detect_type", status="succeeded", progress=100, message="Đã xác nhận định dạng tài liệu.")
        await _set_step(db, job.id, "extract_text", status="running", progress=5, message="Đang đọc nội dung tài liệu.")
        job.progress = 10
        await append_job_event(db, job, "status", "Worker đã nhận job.", 10)
        await db.commit()
        claim_job_fence(job.id, claim_token)
        return job.company_id, job.created_by, document_ids


async def _parse_uploaded_document(document: Document):
    if hasattr(storage, "path"):
        parsed_path = storage.path(document.storage_key)
        return await asyncio.to_thread(parse_document, parsed_path, kind=document.kind, mime_type=document.mime_type, filename=document.filename)
    with TemporaryDirectory(prefix="agentic-ingest-") as temp_dir:
        parsed_path = Path(temp_dir) / Path(document.filename).name
        parsed_path.write_bytes(await storage.read(document.storage_key))
        return await asyncio.to_thread(parse_document, parsed_path, kind=document.kind, mime_type=document.mime_type, filename=document.filename)


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
        extracted_chunks = chunk_document(
            normalized,
            parser_version=document.parser_version,
            chunker_version=settings.chunker_version,
            embedding_model_version=embedding_identity(embedder)[1],
        )
        for chunk_index, chunk in enumerate(extracted_chunks):
            db.add(
                DocumentChunk(
                    company_id=company_id,
                    document_id=document_id,
                    chunk_index=chunk_index,
                    kind=chunk.kind,
                    text=chunk.text,
                    locator=chunk.locator,
                    metadata_json={"chunker_version": settings.chunker_version},
                )
            )
        _embedding_provider, embedding_model_version = embedding_identity(embedder)
        effective_retrieval_mode = "lexical" if embedder is None else settings.retrieval_mode
        knowledge_chunks = await index.upsert(
            db,
            normalized,
            embedder=embedder,
            parser_version=document.parser_version,
            chunker_version=settings.chunker_version,
            embedding_model_version=embedding_model_version,
        )
        document.status = "ready"
        document.normalized_json = normalized.model_dump(mode="json")
        document.knowledge_status = "ready"
        document.retrieval_mode = effective_retrieval_mode
        document.profile_status = "not_applicable"
        table_characters = sum(
            sum(len(value) for value in table.headers)
            + sum(sum(len(value) for value in row) for row in table.rows)
            for table in normalized.table_blocks
        )
        document.extracted = {
            **parsed.metadata,
            "characters": sum(len(block.text) for block in normalized.text_blocks) + table_characters,
            "warnings": parsed.warnings,
            "normalized_blocks": len(extracted_chunks),
            "knowledge_chunks": knowledge_chunks,
            "retrieval_mode": effective_retrieval_mode,
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
            document.profile_status = "not_applicable"
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
            document.retrieval_mode = "not_available"
            document.profile_status = "not_applicable"
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


@isolated_job_fence
async def ingest_document_task_batch_async(
    job_id: str,
    document_ids: list[str],
    *,
    index: PostgresKnowledgeIndex | None = None,
    embedder=None,
) -> None:
    """Extract supported files and persist searchable knowledge without AI profile generation."""

    claimed = await _claim_job(job_id, document_ids)
    if claimed is None:
        return
    company_id, created_by, scoped_document_ids = claimed
    knowledge_index = index or PostgresKnowledgeIndex()
    if embedder is None:
        try:
            embedder = configured_embedding_provider()
        except AIConfigurationError:
            embedder = None
    successful_text_ids: list[str] = []
    failed_documents: list[dict[str, Any]] = []
    image_ids: list[str] = []
    warnings: list[str] = []
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)

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
                document.profile_status = "not_applicable"
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
        async with SessionLocal() as db:
            job = await db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if job is None or job.status != "running":
                await db.rollback()
                return
            docs = (await db.scalars(select(Document).where(
                Document.company_id == company_id,
                Document.id.in_(successful_text_ids),
            ))).all()
            for document in docs:
                document.profile_status = "not_applicable"
            partial = bool(failed_documents)
            job.status = "failed" if partial else "succeeded"
            job.progress = 100
            job.finished_at = utcnow()
            job.lease_until = None
            job.error = ({"code": "partial_batch", "message": "Đã lưu kiến thức cho tệp đọc được; một số tệp bị lỗi riêng.", "retryable": False} if partial else None)
            job.result = {
                **(job.result or {}),
                "document_ids": scoped_document_ids,
                "normalized_document_ids": successful_text_ids,
                "failed_documents": failed_documents,
                "knowledge_status": "ready",
                "profile_status": "not_applicable",
                "profile_generation": "removed_owner_authored_profile",
                "warnings": list(dict.fromkeys(warnings)),
                "partial": partial,
            }
            await _set_step(db, job_id, "chunk_and_index", status="succeeded", progress=100, message="Đã lưu kiến thức cho content agent.")
            await _set_step(db, job_id, PROFILE_STEP, status="skipped", message="Không áp dụng: hồ sơ thương hiệu do Owner tự viết.")
            await append_job_event(db, job, "complete" if not partial else "error", "Đã đọc tài liệu và lưu kiến thức; không tạo Brand Profile.", 100)
            await db.commit()
        return

    error_code = "no_text_content" if image_ids and not failed_documents else "document_ingestion_failed"
    error_message = "Không có nội dung văn bản để lưu vào kiến thức." if image_ids and not failed_documents else "Không có tài liệu văn bản nào xử lý thành công."
    error_hint = "Tải lên PDF có lớp chữ, DOCX, XLSX, CSV hoặc TXT; OCR ảnh chưa được bật." if image_ids and not failed_documents else "Kiểm tra tệp lỗi trong danh sách tài liệu rồi tải lại."
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
            await _set_step(db, job_id, PROFILE_STEP, status="skipped", message="Không áp dụng: hồ sơ thương hiệu do Owner tự viết.")
            await append_job_event(db, job, "error", error_message, 100)
            await db.commit()


@celery_app.task(bind=True, autoretry_for=(), acks_late=True, time_limit=1500, soft_time_limit=1400)
def ingest_document_task(self, job_id: str, document_id: str, document_ids: list[str] | None = None) -> None:
    run_worker_coroutine(ingest_document_task_batch_async(job_id, document_ids or [document_id]))
