"""Tenant-scoped image asset upload and download APIs."""

from __future__ import annotations

import hashlib
import io
import warnings
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import MediaAsset, Membership, User, new_id, utcnow
from .config import settings
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .media_schemas import MediaAssetOut
from .rate_limits import rate_limit
from .storage import storage


router = APIRouter(prefix="/workspaces/{company_id}/media", tags=["media-assets"])
FORMAT_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MAX_FILENAME_CHARS = 255


def _safe_filename(value: str | None) -> str:
    filename = PurePosixPath((value or "image").replace("\\", "/")).name
    filename = "".join(character for character in filename if character.isprintable() and character not in {"/", "\\"})
    return (filename.strip() or "image")[:MAX_FILENAME_CHARS]


def _inspect_image(content: bytes, declared_mime: str) -> tuple[str, int, int]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                mime_type = FORMAT_MIME.get(image.format or "")
                width, height = image.size
                if mime_type is None or mime_type != declared_mime:
                    raise ApiProblem(415, "unsupported_image_type", "Chỉ nhận ảnh JPEG, PNG hoặc WebP có MIME khớp nội dung.")
                if width < 1 or height < 1 or width * height > settings.max_image_pixels:
                    raise ApiProblem(413, "image_dimensions_exceeded", "Kích thước ảnh vượt giới hạn cho phép.")
                image.verify()
            with Image.open(io.BytesIO(content)) as decoded:
                decoded.load()
            return mime_type, width, height
    except ApiProblem:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ApiProblem(422, "invalid_image", "Tệp tải lên không phải ảnh hợp lệ hoặc ảnh bị lỗi.")


def _content_path(company_id: str, asset_id: str) -> str:
    return f"/workspaces/{company_id}/media/{asset_id}/content"


def _asset_out(asset: MediaAsset, company_id: str) -> MediaAssetOut:
    return MediaAssetOut(
        id=asset.id,
        filename=asset.filename,
        mime_type=asset.mime_type,
        size_bytes=asset.size_bytes,
        content_sha256=asset.content_sha256,
        width=asset.width,
        height=asset.height,
        alt_text=asset.alt_text,
        content_path=_content_path(company_id, asset.id),
    )


@router.post(
    "",
    response_model=MediaAssetOut,
    status_code=201,
    dependencies=[
        Depends(require_csrf),
        Depends(rate_limit("media_upload", max_requests=30, window_seconds=3600)),
    ],
)
async def upload_media_asset(
    company_id: str,
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str, Form(max_length=500)] = "",
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("post:edit")),
    db: AsyncSession = Depends(get_db),
) -> MediaAssetOut:
    filename = _safe_filename(file.filename)
    declared_mime = (file.content_type or "").lower().strip()
    if declared_mime not in set(FORMAT_MIME.values()):
        raise ApiProblem(415, "unsupported_image_type", "Chỉ nhận ảnh JPEG, PNG hoặc WebP.")
    content = await file.read(settings.max_image_bytes + 1)
    if len(content) > settings.max_image_bytes:
        raise ApiProblem(413, "file_too_large", f"Ảnh vượt quá giới hạn {settings.max_image_bytes} byte.")
    if not content:
        raise ApiProblem(422, "invalid_image", "Tệp ảnh không được để trống.")
    mime_type, width, height = _inspect_image(content, declared_mime)
    digest = hashlib.sha256(content).hexdigest()
    existing = await db.scalar(select(MediaAsset).where(MediaAsset.company_id == company_id, MediaAsset.content_sha256 == digest))
    if existing is not None:
        return _asset_out(existing, company_id)

    asset_id = new_id()
    storage_key = f"{company_id}/media/{digest}"
    asset = MediaAsset(
        id=asset_id, company_id=company_id, filename=filename, mime_type=mime_type,
        size_bytes=len(content), content_sha256=digest, width=width, height=height,
        alt_text=alt_text.strip(), storage_key=storage_key, uploaded_by=user.id, created_at=utcnow(),
    )
    try:
        await storage.put(storage_key, content)
        db.add(asset)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(select(MediaAsset).where(MediaAsset.company_id == company_id, MediaAsset.content_sha256 == digest))
        if existing is None:
            raise ApiProblem(409, "media_upload_conflict", "Không thể hoàn tất upload ảnh đồng thời. Hãy thử lại.", retryable=True)
        return _asset_out(existing, company_id)
    except Exception:
        await db.rollback()
        raise ApiProblem(503, "media_storage_unavailable", "Không lưu được ảnh vào object storage. Vui lòng thử lại.", retryable=True)
    return _asset_out(asset, company_id)


@router.get("/{asset_id}/content", response_class=Response)
async def download_media_asset(
    company_id: str,
    asset_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await membership_for(company_id, user, db)
    asset = await db.scalar(select(MediaAsset).where(MediaAsset.company_id == company_id, MediaAsset.id == asset_id))
    if asset is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy ảnh.")
    try:
        content = await storage.read(asset.storage_key)
    except Exception:
        raise ApiProblem(503, "media_storage_unavailable", "Không đọc được ảnh từ object storage.", retryable=True)
    return Response(
        content=content,
        media_type=asset.mime_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(asset.filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": asset.content_sha256,
            "X-Content-Type-Options": "nosniff",
        },
    )
