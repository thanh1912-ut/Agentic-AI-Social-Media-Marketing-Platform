"""Tenant-scoped document upload and ingestion job endpoints."""

from __future__ import annotations

import hashlib
import base64
import json
from itertools import islice
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Document, Job, JobStep, KnowledgeChunk, Membership, RequestDeduplication, User, new_id, utcnow
from services.ingestion.parsers import (
    MAX_DOCUMENT_CONVERSION_SECONDS,
    MAX_PARSED_TEXT_CHARACTERS,
    MAX_PDF_PAGES,
    MAX_TABLE_CELLS,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    SUPPORTED_MIME_TYPES,
    infer_kind,
    is_image_signature,
)
from .config import settings
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .job_service import STEP_LABELS, accepted_response, dispatch_document_job
from .rate_limits import rate_limit
from .schemas import AcceptedResponse, ApiErrorEnvelope, DocumentOut, ExtractedContentPage, ExtractedContentUnit, ReprocessDocumentRequest, UploadLimits
from .storage import storage


router = APIRouter(tags=["documents"])


def _document_error(raw: dict | None) -> dict | None:
    return raw or None


def _document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        workspace_id=document.company_id,
        filename=document.filename,
        kind=document.kind,
        mime_type=document.mime_type,
        size=document.size_bytes,
        status=document.status,
        progress=100 if document.status in {"ready", "failed", "unsupported"} else 0,
        job_id=document.job_id,
        error=_document_error(document.error),
        extracted=document.extracted,
        extraction_status=(
            "extracted"
            if document.normalized_json
            and not (document.extracted or {}).get("warnings")
            else "partial"
            if document.normalized_json
            else "metadata_only"
            if document.kind == "image" and document.status == "ready"
            else "failed"
            if document.status in {"failed", "unsupported"}
            else "pending"
        ),
        knowledge_status=document.knowledge_status,
        retrieval_mode=document.retrieval_mode,
        profile_status=document.profile_status,
        selectable_for_content=(
            document.deleted_at is None
            and document.is_active
            and document.status == "ready"
            and document.knowledge_status == "ready"
            and bool(document.normalized_json)
        ),
        uploaded_by=document.uploaded_by,
        uploaded_at=document.created_at,
        processed_at=document.processed_at,
    )


@router.get("/workspaces/{company_id}/documents/limits", response_model=UploadLimits)
async def upload_limits(company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await membership_for(company_id, user, db)
    return UploadLimits(
        max_file_size_bytes=settings.max_upload_bytes,
        max_files_per_request=settings.max_files_per_request,
        accepted_kinds=["pdf", "docx", "xlsx", "csv", "txt"],
        accepted_mime_types=sorted(SUPPORTED_MIME_TYPES),
        max_text_characters=MAX_PARSED_TEXT_CHARACTERS,
        max_table_rows=MAX_TABLE_ROWS,
        max_table_columns=MAX_TABLE_COLUMNS,
        max_table_cells=MAX_TABLE_CELLS,
        max_pdf_pages=MAX_PDF_PAGES,
        max_processing_seconds=MAX_DOCUMENT_CONVERSION_SECONDS,
        ocr_enabled=False,
    )


@router.get("/workspaces/{company_id}/documents", response_model=list[DocumentOut])
async def list_documents(company_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await membership_for(company_id, user, db)
    documents = (await db.scalars(select(Document).where(Document.company_id == company_id).order_by(Document.created_at.desc()))).all()
    return [_document_out(document) for document in documents]


@router.get("/workspaces/{company_id}/documents/{document_id}", response_model=DocumentOut)
async def get_document(company_id: str, document_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await membership_for(company_id, user, db)
    document = await db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company_id))
    if document is None or document.deleted_at is not None:
        raise ApiProblem(404, "not_found", "Không tìm thấy tài liệu.")
    return _document_out(document)


@router.get("/workspaces/{company_id}/documents/{document_id}/extracted-content", response_model=ExtractedContentPage)
async def get_extracted_content(
    company_id: str,
    document_id: str,
    cursor: str | None = Query(default=None, max_length=2000),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    document = await db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company_id))
    if document is None or document.deleted_at is not None:
        raise ApiProblem(404, "not_found", "Không tìm thấy tài liệu.")
    normalized = document.normalized_json
    if not normalized:
        raise ApiProblem(409, "extraction_not_ready", "Nội dung trích xuất chưa sẵn sàng.")

    offset = 0
    if cursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if payload.get("document_id") != document.id or payload.get("source_hash") != document.source_hash or payload.get("parser_version") != document.parser_version:
                raise ValueError("stale cursor")
            offset = int(payload["offset"])
            if offset < 0:
                raise ValueError("negative cursor")
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ApiProblem(409, "extracted_content_changed", "Dữ liệu tài liệu đã đổi; hãy tải lại từ trang đầu.") from exc

    text_blocks = normalized.get("text_blocks", [])
    table_blocks = normalized.get("table_blocks", [])
    total_rows = sum(len(table.get("rows", [])) for table in table_blocks)
    total_units = sum((len(str(block.get("text") or "")) + 7999) // 8000 for block in text_blocks)
    total_units += total_rows

    def iter_units():
        for block_index, block in enumerate(text_blocks, start=1):
            text = str(block.get("text") or "")
            base_locator = str(block.get("locator") or f"text:{block_index}")
            # Bound response size while preserving long text across cursor pages.
            for start in range(0, len(text), 8000):
                end = min(len(text), start + 8000)
                yield ExtractedContentUnit(kind="text", locator=f"{base_locator};chars={start + 1}-{end}", text=text[start:end])
        for table_index, table in enumerate(table_blocks, start=1):
            headers = [str(value) for value in (table.get("headers") or [])]
            table_locator = str(table.get("locator") or f"table={table_index}")
            for row_index, row in enumerate(table.get("rows", []), start=1):
                yield ExtractedContentUnit(kind="table_row", locator=f"{table_locator}[row={row_index}]", headers=headers, cells=[str(value) for value in row])

    selected = list(islice(iter_units(), offset, offset + limit))
    next_offset = offset + len(selected)
    has_more = next_offset < total_units
    next_cursor = None
    if has_more:
        payload = json.dumps({"document_id": document.id, "source_hash": document.source_hash, "parser_version": document.parser_version, "offset": next_offset}, separators=(",", ":")).encode()
        next_cursor = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return ExtractedContentPage(
        document_id=document.id,
        parser_version=document.parser_version,
        source_version=document.source_version,
        items=selected,
        next_cursor=next_cursor,
        has_more=has_more,
        total_text_blocks=len(normalized.get("text_blocks", [])),
        total_tables=len(normalized.get("table_blocks", [])),
        total_rows=total_rows,
        warnings=list((document.extracted or {}).get("warnings") or []),
    )


@router.post(
    "/workspaces/{company_id}/documents",
    response_model=AcceptedResponse,
    status_code=202,
    dependencies=[
        Depends(require_csrf),
        Depends(rate_limit("document_upload", max_requests=30, window_seconds=3600)),
    ],
    responses={
        status: {"model": ApiErrorEnvelope, "description": "API error envelope"}
        for status in (400, 401, 403, 409, 413, 415, 422, 500)
    },
)
async def upload_documents(
    company_id: str,
    files: Annotated[list[UploadFile], File(description="Một hoặc nhiều tài liệu thương hiệu")],
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("document:upload")),
    db: AsyncSession = Depends(get_db),
):
    if not idempotency_key or len(idempotency_key) > 200:
        raise ApiProblem(422, "validation_error", "Thiếu khoá chống gửi trùng.", field_errors=[{"field": "Idempotency-Key", "message": "Cần gửi Idempotency-Key hợp lệ."}])
    if not files:
        raise ApiProblem(400, "validation_error", "Chưa chọn tệp nào để tải lên.", field_errors=[{"field": "files", "message": "Cần ít nhất một tệp."}])
    if len(files) > settings.max_files_per_request:
        raise ApiProblem(413, "file_too_large", f"Mỗi lần chỉ nhận tối đa {settings.max_files_per_request} tệp.")
    duplicate = await db.scalar(select(RequestDeduplication).where(RequestDeduplication.company_id == company_id, RequestDeduplication.operation == "document_upload", RequestDeduplication.idempotency_key == idempotency_key))
    if duplicate:
        job = await db.get(Job, duplicate.response_json["job_id"])
        if job is None:
            raise ApiProblem(409, "state_conflict", "Yêu cầu cũ không còn hợp lệ.")
        return await accepted_response(db, job)

    prepared_uploads: list[tuple[str, str, str, UploadFile]] = []
    for upload in files:
        filename = (upload.filename or "untitled").replace("\\", "/").rsplit("/", 1)[-1] or "untitled"
        mime_type = (upload.content_type or "application/octet-stream").lower()
        if mime_type.startswith("image/") or Path(filename).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tif", ".tiff", ".bmp", ".ico"}:
            raise ApiProblem(415, "unsupported_type", "Không hỗ trợ tệp hình ảnh trong mục Tài liệu.", field_errors=[{"field": "files", "message": "Chỉ nhận PDF có lớp chữ, DOCX, XLSX, CSV và TXT. Ảnh dùng cho bài đăng vẫn được quản lý ở mục đăng bài."}])
        header = await upload.read(16)
        await upload.seek(0)
        if is_image_signature(header):
            raise ApiProblem(415, "unsupported_type", "Không hỗ trợ tệp hình ảnh trong mục Tài liệu.", field_errors=[{"field": "files", "message": "Tệp có nội dung hình ảnh dù phần mở rộng hoặc loại MIME khác. Chỉ nhận PDF có lớp chữ, DOCX, XLSX, CSV và TXT."}])
        kind = infer_kind(filename, mime_type)
        if kind is None:
            raise ApiProblem(415, "unsupported_type", f"Định dạng tệp “{filename}” chưa được hỗ trợ.", field_errors=[{"field": "files", "message": "Chỉ nhận PDF có lớp chữ, DOCX, XLSX, CSV và TXT."}])
        size = 0
        while size <= settings.max_upload_bytes:
            chunk = await upload.read(min(64 * 1024, settings.max_upload_bytes + 1 - size))
            if not chunk:
                break
            size += len(chunk)
        if size > settings.max_upload_bytes:
            raise ApiProblem(413, "file_too_large", f"Tệp “{filename}” vượt quá dung lượng cho phép.", field_errors=[{"field": "files", "message": f"Tối đa {settings.max_upload_bytes} byte mỗi tệp."}])
        await upload.seek(0)
        prepared_uploads.append((filename, mime_type, kind, upload))

    first_document: Document | None = None
    document_ids: list[str] = []
    for filename, mime_type, kind, upload in prepared_uploads:
        content = await upload.read(settings.max_upload_bytes + 1)
        source_hash = hashlib.sha256(content).hexdigest()
        existing = await db.scalar(select(Document).where(Document.company_id == company_id, Document.source_hash == source_hash, Document.parser_version == settings.parser_version))
        if existing:
            if existing.deleted_at is not None:
                try:
                    existing.source_version = str(int(existing.source_version) + 1)
                except (TypeError, ValueError):
                    existing.source_version = "2"
                existing.deleted_at = None
                existing.is_active = True
                existing.status = "pending"
                existing.error = None
                existing.knowledge_status = "pending"
                existing.profile_status = "not_applicable"
                await storage.put(existing.storage_key, content)
            if first_document is None:
                first_document = existing
            document_ids.append(existing.id)
            continue
        prior_version = await db.scalar(
            select(Document)
            .where(
                Document.company_id == company_id,
                func.lower(Document.filename) == filename.casefold(),
                Document.is_active.is_(True),
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
        )
        source_version = 1
        source_id = None
        if prior_version:
            source_id = prior_version.source_id
            try:
                source_version = int(prior_version.source_version) + 1
            except (TypeError, ValueError):
                source_version = 2
        document = Document(company_id=company_id, filename=filename, kind=kind, mime_type=mime_type, size_bytes=len(content), source_hash=source_hash, parser_version=settings.parser_version, storage_key=f"{company_id}/{source_hash}/{new_id()}", status="pending", profile_status="not_applicable", uploaded_by=user.id, source_version=str(source_version))
        if source_id:
            document.source_id = source_id
        db.add(document)
        await db.flush()
        await storage.put(document.storage_key, content)
        if first_document is None:
            first_document = document
        document_ids.append(document.id)

    if first_document is None:
        raise ApiProblem(409, "already_exists", "Các tệp này đã được tải lên trước đó.")
    document_ids = list(dict.fromkeys(document_ids))
    job = Job(company_id=company_id, created_by=user.id, kind="document_ingest", title="Đang đọc tài liệu và lưu kiến thức", status="queued", progress=0, result={"document_id": first_document.id, "document_ids": document_ids}, idempotency_key=idempotency_key)
    db.add(job)
    await db.flush()
    for document_id in document_ids:
        document = await db.get(Document, document_id)
        if document is not None and document.company_id == company_id:
            document.job_id = job.id
    for key in ("receive_file", "detect_type", "extract_text", "normalize", "chunk_and_index"):
        db.add(JobStep(job_id=job.id, step_key=key, label=STEP_LABELS[key], status="pending"))
    db.add(RequestDeduplication(company_id=company_id, operation="document_upload", idempotency_key=idempotency_key, response_json={"job_id": job.id}))
    await db.commit()
    await dispatch_document_job(job.id, first_document.id, document_ids)
    return await accepted_response(db, job)


@router.post("/workspaces/{company_id}/documents/{document_id}/reprocess", response_model=AcceptedResponse, status_code=202, dependencies=[Depends(require_csrf)])
async def reprocess_document(company_id: str, document_id: str, request: ReprocessDocumentRequest | None = None, user: User = Depends(current_user), membership: Membership = Depends(require_permission("document:upload")), db: AsyncSession = Depends(get_db)):
    document = await db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company_id))
    if document is None or document.deleted_at is not None:
        raise ApiProblem(404, "not_found", "Không tìm thấy tài liệu.")
    if not document.is_active:
        raise ApiProblem(409, "state_conflict", "Tài liệu này đã được thay thế và không thể đọc lại như nguồn đang hoạt động.")
    mode = request.mode if request else "document"
    if mode == "profile_only":
        raise ApiProblem(410, "brand_profile_generation_removed", "Tài liệu chỉ được đọc và lưu làm kiến thức. Owner tự nhập hồ sơ ở mục Thương hiệu.")
    active_job = await db.scalar(select(Job).where(Job.id == document.job_id, Job.status.in_(["queued", "running"]))) if document.job_id else None
    if active_job:
        return await accepted_response(db, active_job)
    job = Job(company_id=company_id, created_by=user.id, kind="document_ingest", title=f"Đọc lại tài liệu “{document.filename}”", status="queued", progress=0, result={"document_id": document.id, "mode": mode}, idempotency_key=f"reprocess:{document.id}:{mode}:{document.updated_at.timestamp()}")
    if mode == "document":
        document.status = "pending"
        document.error = None
        document.parser_version = settings.parser_version
        document.knowledge_status = "pending"
    document.profile_status = "not_applicable"
    db.add(job)
    await db.flush()
    document.job_id = job.id
    for key in ("receive_file", "detect_type", "extract_text", "normalize", "chunk_and_index"):
        db.add(JobStep(job_id=job.id, step_key=key, label=STEP_LABELS[key], status="pending"))
    await db.commit()
    await dispatch_document_job(job.id, document.id)
    return await accepted_response(db, job)


@router.delete("/workspaces/{company_id}/documents/{document_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_document(
    company_id: str,
    document_id: str,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("document:upload")),
    db: AsyncSession = Depends(get_db),
):
    document = await db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company_id))
    if document is None or document.deleted_at is not None:
        raise ApiProblem(404, "not_found", "Không tìm thấy tài liệu.")
    document.is_active = False
    document.deleted_at = utcnow()
    await db.execute(
        update(KnowledgeChunk)
        .where(
            KnowledgeChunk.company_id == company_id,
            KnowledgeChunk.document_id == document_id,
        )
        .values(is_active=False)
    )
    await db.commit()
