"""Background document ingestion tasks."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import delete, select

from database.models import Document, DocumentChunk, Job, JobStep, utcnow
from packages.contracts import NormalizedDocument, TableBlock, TextBlock
from services.ingestion.parsers import ParseError, parse_document
from services.api.db import SessionLocal
from services.api.job_service import append_job_event
from services.api.storage import storage
from .celery_app import celery_app


async def _set_step(db, job_id: str, key: str, *, status: str, progress: int | None = None, message: str | None = None, error: dict | None = None) -> None:
    step = await db.scalar(select(JobStep).where(JobStep.job_id == job_id, JobStep.step_key == key))
    if step is None:
        return
    step.status = status
    step.progress = progress
    step.message = message
    step.error = error
    if status == "running":
        step.started_at = utcnow()
    if status in {"succeeded", "failed", "skipped"}:
        step.finished_at = utcnow()


async def ingest_document_task_async(job_id: str, document_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        document = await db.get(Document, document_id)
        if job is None or document is None:
            return
        if job.status == "cancelled":
            return
        job.status = "running"
        job.started_at = job.started_at or utcnow()
        job.attempts += 1
        job.lease_until = utcnow() + timedelta(minutes=15)
        document.status = "processing"
        await _set_step(db, job.id, "receive_file", status="succeeded", progress=100, message="Đã nhận tệp và kiểm tra quyền truy cập.")
        await _set_step(db, job.id, "detect_type", status="succeeded", progress=100, message=f"Đã nhận dạng {document.kind}.")
        await _set_step(db, job.id, "extract_text", status="running", progress=10)
        job.progress = 20
        await append_job_event(db, job, "step", "Bắt đầu đọc nội dung tệp.", 20)
        await db.commit()

        try:
            if hasattr(storage, "path"):
                parsed_path = storage.path(document.storage_key)
                parsed = parse_document(parsed_path, kind=document.kind, mime_type=document.mime_type, filename=document.filename)
            else:
                with TemporaryDirectory(prefix="agentic-ingest-") as temp_dir:
                    parsed_path = Path(temp_dir) / document.filename
                    parsed_path.write_bytes(await storage.read(document.storage_key))
                    parsed = parse_document(parsed_path, kind=document.kind, mime_type=document.mime_type, filename=document.filename)
            await _set_step(db, job.id, "extract_text", status="succeeded", progress=100, message="Đã đọc nội dung tệp.")
            await _set_step(db, job.id, "normalize", status="running", progress=10)
            job.progress = 45
            await db.commit()

            # Images are valid uploads but do not silently become empty text.
            # OCR is an explicit future capability, so the status is ready with
            # a warning and no M3 text handoff.
            if document.kind == "image":
                document.status = "ready"
                document.extracted = {**parsed.metadata, "warnings": parsed.warnings}
                document.processed_at = utcnow()
                job.result = {"document_id": document.id, "normalized": False, "warnings": parsed.warnings}
                job.status = "succeeded"
                job.progress = 100
                job.finished_at = utcnow()
                job.lease_until = None
                await _set_step(db, job.id, "normalize", status="succeeded", progress=100, message="Đã lưu metadata ảnh; chưa chạy OCR.")
                await _set_step(db, job.id, "chunk_and_index", status="skipped", message="Ảnh chưa có lớp văn bản; cần OCR trước khi tra cứu.")
                await _set_step(db, job.id, "extract_text", status="succeeded", progress=100)
                await db.commit()
                return

            text_blocks = [TextBlock(block_id=f"{document.id}:text:{index}", text=block.text, locator=block.locator, heading=block.heading, extraction_warnings=block.warnings) for index, block in enumerate(parsed.text_blocks, start=1)]
            table_blocks = [TableBlock(block_id=f"{document.id}:table:{index}", headers=table.headers, rows=table.rows, locator=table.locator, extraction_warnings=table.warnings) for index, table in enumerate(parsed.table_blocks, start=1)]
            normalized = NormalizedDocument(company_id=document.company_id, brand_id=f"brand:{document.company_id}", document_id=document.id, source_id=document.id, source_version=document.parser_version, source_hash=document.source_hash, text_blocks=text_blocks, table_blocks=table_blocks, extraction_warnings=parsed.warnings)
            await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
            chunk_index = 0
            for block in normalized.text_blocks:
                db.add(DocumentChunk(company_id=document.company_id, document_id=document.id, chunk_index=chunk_index, kind="text", text=block.text, locator=block.locator, metadata_json={"block_id": block.block_id, "warnings": block.extraction_warnings}))
                chunk_index += 1
            for block in normalized.table_blocks:
                table_text = " | ".join(block.headers) + "\n" + "\n".join(" | ".join(row) for row in block.rows)
                db.add(DocumentChunk(company_id=document.company_id, document_id=document.id, chunk_index=chunk_index, kind="table", text=table_text, locator=block.locator, metadata_json={"block_id": block.block_id, "headers": block.headers, "warnings": block.extraction_warnings}))
                chunk_index += 1
            document.status = "ready"
            document.extracted = {**parsed.metadata, "characters": sum(len(block.text) for block in parsed.text_blocks), "warnings": parsed.warnings, "chunks": chunk_index}
            document.processed_at = utcnow()
            await _set_step(db, job.id, "normalize", status="succeeded", progress=100, message="Đã chuẩn hoá text/table blocks và locator.")
            await _set_step(db, job.id, "chunk_and_index", status="succeeded", progress=100, message=f"Đã tạo {chunk_index} đoạn cho M3.")
            job.status = "succeeded"
            job.progress = 100
            job.result = {"document_id": document.id, "normalized": True, "chunks": chunk_index}
            job.finished_at = utcnow()
            job.lease_until = None
            await append_job_event(db, job, "status", "Đã xử lý xong tài liệu.", 100)
            await db.commit()
        except ParseError as exc:
            document.status = "failed" if exc.code != "unsupported_type" else "unsupported"
            document.error = {"code": exc.code, "message": exc.message, "hint": exc.hint}
            document.processed_at = utcnow()
            job.status = "failed"
            job.progress = 100
            job.error = {"code": exc.code, "message": exc.message, "hint": exc.hint, "retryable": exc.retryable}
            job.finished_at = utcnow()
            job.lease_until = None
            await _set_step(db, job.id, "extract_text", status="failed", progress=100, message=exc.message, error={"code": exc.code, "message": exc.message, "hint": exc.hint, "retryable": exc.retryable})
            for key in ("normalize", "chunk_and_index"):
                await _set_step(db, job.id, key, status="skipped", message="Bỏ qua vì bước đọc nội dung đã lỗi.")
            await append_job_event(db, job, "error", exc.message, 100)
            await db.commit()
        except Exception:
            document.status = "failed"
            document.error = {"code": "internal_error", "message": "Không xử lý được tài liệu.", "hint": "Hãy thử lại hoặc liên hệ hỗ trợ."}
            job.status = "failed"
            job.progress = 100
            job.error = {"code": "internal_error", "message": "Không xử lý được tài liệu.", "hint": "Hãy thử lại hoặc liên hệ hỗ trợ.", "retryable": True}
            job.finished_at = utcnow()
            job.lease_until = None
            await _set_step(db, job.id, "extract_text", status="failed", progress=100, message="Worker gặp lỗi không xác định.", error=job.error)
            await append_job_event(db, job, "error", "Worker gặp lỗi không xác định.", 100)
            await db.commit()
            raise


async def ingest_document_task_batch_async(job_id: str, document_ids: list[str]) -> None:
    """Process a multipart upload sequentially under one durable job ledger."""

    for document_id in document_ids:
        await ingest_document_task_async(job_id, document_id)
    async with SessionLocal() as db:
        job = await db.get(Job, job_id)
        if job is not None:
            job.result = {**(job.result or {}), "document_ids": document_ids}
            await db.commit()


@celery_app.task(bind=True, autoretry_for=(), acks_late=True, time_limit=900, soft_time_limit=840)
def ingest_document_task(self, job_id: str, document_id: str, document_ids: list[str] | None = None) -> None:
    asyncio.run(ingest_document_task_batch_async(job_id, document_ids or [document_id]))
