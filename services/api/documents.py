"""Tenant-scoped document upload and ingestion job endpoints."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, File, Header, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Document, Job, JobStep, Membership, RequestDeduplication, User
from services.ingestion.parsers import SUPPORTED_MIME_TYPES, infer_kind
from .config import settings
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .job_service import STEP_LABELS, accepted_response, dispatch_document_job
from .schemas import AcceptedResponse, DocumentOut, UploadLimits
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
        accepted_kinds=["pdf", "docx", "xlsx", "csv", "txt", "image"],
        accepted_mime_types=sorted(SUPPORTED_MIME_TYPES),
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
    if document is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy tài liệu.")
    return _document_out(document)


@router.post("/workspaces/{company_id}/documents", response_model=AcceptedResponse, status_code=202, dependencies=[Depends(require_csrf)])
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

    first_document: Document | None = None
    document_ids: list[str] = []
    total_files = len(files)
    for upload in files:
        filename = upload.filename or "untitled"
        mime_type = (upload.content_type or "application/octet-stream").lower()
        kind = infer_kind(filename, mime_type)
        if kind is None:
            raise ApiProblem(415, "unsupported_type", f"Định dạng tệp “{filename}” chưa được hỗ trợ.", field_errors=[{"field": "files", "message": "Chỉ nhận PDF, DOCX, XLSX, CSV, TXT và ảnh."}])
        content = await upload.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            raise ApiProblem(413, "file_too_large", f"Tệp “{filename}” vượt quá dung lượng cho phép.", field_errors=[{"field": "files", "message": f"Tối đa {settings.max_upload_bytes} byte mỗi tệp."}])
        source_hash = hashlib.sha256(content).hexdigest()
        existing = await db.scalar(select(Document).where(Document.company_id == company_id, Document.source_hash == source_hash, Document.parser_version == settings.parser_version))
        if existing:
            if first_document is None:
                first_document = existing
            document_ids.append(existing.id)
            continue
        document = Document(company_id=company_id, filename=filename, kind=kind, mime_type=mime_type, size_bytes=len(content), source_hash=source_hash, parser_version=settings.parser_version, storage_key=f"{company_id}/{source_hash}/{filename}", status="pending", uploaded_by=user.id)
        db.add(document)
        await db.flush()
        await storage.put(document.storage_key, content)
        if first_document is None:
            first_document = document
        document_ids.append(document.id)

    if first_document is None:
        raise ApiProblem(409, "already_exists", "Các tệp này đã được tải lên trước đó.")
    job = Job(company_id=company_id, created_by=user.id, kind="document_ingest", title=f"Đang đọc {total_files} tài liệu", status="queued", progress=0, result={"document_id": first_document.id, "document_ids": document_ids}, idempotency_key=idempotency_key)
    db.add(job)
    await db.flush()
    first_document.job_id = job.id
    for key in ("receive_file", "detect_type", "extract_text", "normalize", "chunk_and_index"):
        db.add(JobStep(job_id=job.id, step_key=key, label=STEP_LABELS[key], status="pending"))
    db.add(RequestDeduplication(company_id=company_id, operation="document_upload", idempotency_key=idempotency_key, response_json={"job_id": job.id}))
    await db.commit()
    await dispatch_document_job(job.id, first_document.id, document_ids)
    return await accepted_response(db, job)


@router.post("/workspaces/{company_id}/documents/{document_id}/reprocess", response_model=AcceptedResponse, status_code=202, dependencies=[Depends(require_csrf)])
async def reprocess_document(company_id: str, document_id: str, user: User = Depends(current_user), membership: Membership = Depends(require_permission("document:upload")), db: AsyncSession = Depends(get_db)):
    document = await db.scalar(select(Document).where(Document.id == document_id, Document.company_id == company_id))
    if document is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy tài liệu.")
    job = Job(company_id=company_id, created_by=user.id, kind="document_ingest", title=f"Đọc lại tài liệu “{document.filename}”", status="queued", progress=0, result={"document_id": document.id}, idempotency_key=f"reprocess:{document.id}:{document.updated_at.timestamp()}")
    document.status = "pending"
    document.error = None
    db.add(job)
    await db.flush()
    document.job_id = job.id
    for key in ("receive_file", "detect_type", "extract_text", "normalize", "chunk_and_index"):
        db.add(JobStep(job_id=job.id, step_key=key, label=STEP_LABELS[key], status="pending"))
    await db.commit()
    await dispatch_document_job(job.id, document.id)
    return await accepted_response(db, job)
