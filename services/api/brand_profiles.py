"""HTTP Brand Profile DTOs, revisions, provenance and confirmation."""

from __future__ import annotations

import re
import uuid
import copy
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    AuditEvent,
    Brand,
    BrandProfileRevision,
    Company,
    Document,
    Membership,
    User,
    utcnow,
)
from .db import get_db
from .dependencies import current_user, membership_for, require_csrf, require_permission
from .errors import ApiProblem
from .permissions import has_permission
from .schemas import (
    BrandProfileFieldOut,
    BrandProfileOut,
    BrandProfileRevisionOut,
    ApiErrorEnvelope,
    ConfirmBrandProfileRequest,
    UpdateBrandProfileRequest,
)


router = APIRouter(tags=["brand-profile"])

PROFILE_READ_ERRORS = {
    401: {"model": ApiErrorEnvelope, "description": "Unauthenticated"},
    403: {"model": ApiErrorEnvelope, "description": "Workspace access denied"},
    404: {"model": ApiErrorEnvelope, "description": "Profile not found"},
    500: {"model": ApiErrorEnvelope, "description": "Internal server error"},
}
PROFILE_WRITE_ERRORS = {
    **PROFILE_READ_ERRORS,
    409: {"model": ApiErrorEnvelope, "description": "Version conflict; reload the current revision"},
    422: {"model": ApiErrorEnvelope, "description": "Invalid request"},
}

FIELD_LABELS = {
    "business_name": "Tên doanh nghiệp",
    "industry": "Ngành hàng",
    "description": "Giới thiệu doanh nghiệp",
    "products": "Sản phẩm chính",
    "target_audience": "Khách hàng mục tiêu",
    "brand_voice": "Giọng điệu thương hiệu",
    "tone_keywords": "Từ khoá giọng điệu",
    "do_not_use": "Từ ngữ cần tránh",
    "competitors": "Đối thủ chính",
    "contact": "Thông tin liên hệ",
}
FIELD_KEYS = tuple(FIELD_LABELS)
FIELD_FACT_KEYS = {
    "business_name": {"business_name", "brand_name", "company_name", "name"},
    "industry": {"industry", "sector", "category"},
    "description": {"business", "description", "overview", "business_description"},
    "products": {"product", "products", "service", "services"},
    "target_audience": {"audience", "target_audience", "customer", "customers"},
    "brand_voice": {"voice", "brand_voice", "tone", "tone_of_voice"},
    "tone_keywords": {"voice", "brand_voice", "tone", "tone_keywords"},
    "do_not_use": {"constraint", "constraints", "prohibited", "do_not_use"},
    "competitors": {"competitor", "competitors"},
    "contact": {"contact", "contact_info"},
}


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _location(locator: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    page = re.search(r"(?:^|[;#])page[=:](\d+)", locator)
    sheet = re.search(r"(?:^|[;#])sheet=([^;#]+)", locator)
    row = re.search(r"(?:^|[;#])row[=:](\d+)", locator)
    if page:
        result["page"] = int(page.group(1))
    if sheet:
        result["sheet"] = sheet.group(1)
    if row:
        result["row"] = int(row.group(1))
    return result


async def _provenance_for(
    db: AsyncSession,
    company_id: str,
    refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    document_ids = {str(ref.get("document_id", "")) for ref in refs}
    documents = (
        await db.scalars(
            select(Document).where(
                Document.company_id == company_id,
                Document.id.in_(document_ids or {"__no_document__"}),
            )
        )
    ).all()
    by_id = {document.id: document for document in documents}
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in refs:
        document_id = str(raw.get("document_id", ""))
        document = by_id.get(document_id)
        if document is None:
            # Never expose a source reference that does not resolve inside this tenant.
            continue
        locator = str(raw.get("locator", ""))
        quote = str(raw.get("excerpt") or "")
        identity = (document_id, locator, quote)
        if identity in seen:
            continue
        seen.add(identity)
        output.append(
            {
                "document_id": document.id,
                "document_name": document.filename,
                **_location(locator),
                "quote": quote,
            }
        )
    return output


async def internal_profile_to_http(
    db: AsyncSession,
    *,
    internal: dict[str, Any],
    brand: Brand,
    company: Company,
    confirmed_at: datetime | None = None,
    confirmed_by: str | None = None,
    profile_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map the M2↔M3 profile contract into the frontend HTTP DTO."""

    facts = internal.get("facts", [])
    value_map: dict[str, Any] = {
        "business_name": next(
            (fact.get("value") for fact in facts if str(fact.get("key", "")).casefold() in FIELD_FACT_KEYS["business_name"]),
            company.name,
        ),
        "industry": next(
            (fact.get("value") for fact in facts if str(fact.get("key", "")).casefold() in FIELD_FACT_KEYS["industry"]),
            company.industry,
        ),
        "description": internal.get("business"),
        "products": [
            {"id": f"prd_{uuid.uuid5(uuid.NAMESPACE_URL, str(item)).hex[:16]}", "name": item}
            for item in internal.get("products", [])
        ],
        "target_audience": internal.get("audience", []),
        "brand_voice": "、".join(internal.get("voice", [])) or None,
        "tone_keywords": internal.get("voice", []),
        "do_not_use": internal.get("constraints", []),
        "competitors": [],
        "contact": None,
    }

    refs_by_field: dict[str, list[dict[str, Any]]] = {}
    for key in FIELD_KEYS:
        accepted = FIELD_FACT_KEYS[key]
        refs_by_field[key] = [
            reference
            for fact in facts
            if str(fact.get("key", "")).casefold() in accepted
            for reference in fact.get("evidence", [])
        ]

    profile = profile_override or {}
    profile_confirmed_at = confirmed_at or profile.get("confirmed_at")
    profile_confirmed_by = confirmed_by or profile.get("confirmed_by")
    result: dict[str, Any] = {
        "id": brand.id,
        "workspace_id": company.id,
        "version": brand.version,
        "confirmed_at": profile_confirmed_at,
        "confirmed_by": profile_confirmed_by,
        "updated_at": brand.updated_at.isoformat() if brand.updated_at else utcnow().isoformat(),
    }
    for key in FIELD_KEYS:
        value = value_map[key]
        provenance = await _provenance_for(db, company.id, refs_by_field[key])
        if key == "business_name" and value == company.name and not refs_by_field[key]:
            state = "edited"  # entered by the user during workspace registration
        elif key == "industry" and value == company.industry and not refs_by_field[key] and value:
            state = "edited"  # entered by the user during workspace registration
        elif not _is_empty(value) and not provenance:
            # AI-derived content is not shown as a suggestion unless its source
            # resolves to a document in this tenant.
            state = "missing"
            value = None
        elif _is_empty(value):
            state = "missing"
            value = None
        else:
            state = "confirmed" if profile_confirmed_at else "suggested"
        stored_field = profile.get(key)
        if isinstance(stored_field, dict):
            value = stored_field.get("value", value)
            state = stored_field.get("state", state)
            provenance = stored_field.get("provenance", provenance)
            if stored_field.get("updated_at"):
                result.setdefault("_updated_at", {})[key] = stored_field["updated_at"]
        result[key] = {
            "key": key,
            "label": FIELD_LABELS[key],
            "value": value,
            "state": state,
            "provenance": provenance,
            "alternatives": [],
            **({"updated_at": stored_field["updated_at"]} if isinstance(stored_field, dict) and stored_field.get("updated_at") else {}),
            **({"updated_by": stored_field["updated_by"]} if isinstance(stored_field, dict) and stored_field.get("updated_by") else {}),
        }
    nonmissing = [result[key] for key in FIELD_KEYS if result[key]["state"] != "missing"]
    confirmed_count = sum(item["state"] == "confirmed" for item in nonmissing)
    result["completeness"] = confirmed_count / len(FIELD_KEYS) if FIELD_KEYS else 0
    result.pop("_updated_at", None)
    return result


async def _brand_and_company(db: AsyncSession, company_id: str) -> tuple[Brand, Company]:
    company = await db.get(Company, company_id)
    brand = await db.scalar(select(Brand).where(Brand.company_id == company_id))
    if company is None or brand is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy hồ sơ thương hiệu.")
    return brand, company


def _profile_http(profile: dict[str, Any]) -> BrandProfileOut:
    return BrandProfileOut.model_validate(profile)


async def _manual_profile_http(db: AsyncSession, brand: Brand, company: Company) -> BrandProfileOut:
    """Expose manual prose while leaving legacy AI fields empty and read-only."""
    raw = brand.profile if isinstance(brand.profile, dict) else {}
    payload = await internal_profile_to_http(db, internal={}, brand=brand, company=company, profile_override={})
    for key in FIELD_KEYS:
        payload[key] = {
            "key": key,
            "label": FIELD_LABELS[key],
            "value": None,
            "state": "missing",
            "provenance": [],
            "alternatives": [],
        }
    payload.update({
        "profile_mode": "manual_text_v1",
        "profile_text": raw.get("profile_text"),
        "confirmed_at": raw.get("confirmed_at"),
        "confirmed_by": raw.get("confirmed_by"),
        "applied_at": raw.get("confirmed_at"),
        "applied_by": raw.get("confirmed_by"),
        "completeness": 0,
        "version": brand.version,
        "updated_at": brand.updated_at.isoformat() if brand.updated_at else utcnow().isoformat(),
    })
    return _profile_http(payload)


@router.get(
    "/workspaces/{company_id}/brand-profile",
    response_model=BrandProfileOut,
    responses=PROFILE_READ_ERRORS,
)
async def get_brand_profile(
    company_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    brand, company = await _brand_and_company(db, company_id)
    if isinstance(brand.profile, dict) and brand.profile.get("profile_mode") == "manual_text_v1":
        return await _manual_profile_http(db, brand, company)
    saved = copy.deepcopy(brand.profile) if isinstance(brand.profile, dict) else {}
    if all(key in saved for key in FIELD_KEYS):
        payload = saved
    else:
        payload = await internal_profile_to_http(db, internal={}, brand=brand, company=company)
    return _profile_http(payload)


async def _profile_revision(
    db: AsyncSession,
    brand: Brand,
    company: Company,
    actor: User,
    *,
    profile: dict[str, Any],
    internal_profile: dict[str, Any] | None,
    source_refs: list[dict[str, Any]],
    job_id: str | None = None,
    input_snapshot_id: str | None = None,
    input_snapshot: dict[str, Any] | None = None,
    run_metadata: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    confirm: bool = False,
    create_revision: bool = True,
) -> BrandProfileRevision:
    next_version = brand.version + (1 if create_revision else 0)
    now = utcnow()
    if confirm:
        for key in FIELD_KEYS:
            field = profile.get(key, {})
            if isinstance(field, dict) and not _is_empty(field.get("value")):
                field["state"] = "confirmed"
        profile["confirmed_at"] = now.isoformat()
        profile["confirmed_by"] = actor.id
        if profile.get("profile_mode") == "manual_text_v1":
            profile["applied_at"] = now.isoformat()
            profile["applied_by"] = actor.id
        profile["completeness"] = sum(
            profile.get(key, {}).get("state") == "confirmed" for key in FIELD_KEYS
        ) / len(FIELD_KEYS)
    else:
        profile["confirmed_at"] = None
        profile["confirmed_by"] = None
        if profile.get("profile_mode") == "manual_text_v1":
            profile["applied_at"] = None
            profile["applied_by"] = None
    profile["version"] = next_version
    profile["updated_at"] = now.isoformat()
    brand.version = next_version
    brand.profile = profile
    db.add(
        AuditEvent(
            company_id=company.id,
            actor_user_id=actor.id,
            action=("brand_profile.apply" if profile.get("profile_mode") == "manual_text_v1" else "brand_profile.confirm") if confirm else "brand_profile.update",
            entity_type="brand_profile",
            entity_id=brand.id,
            metadata_json={"version": next_version, "job_id": job_id},
        )
    )
    if create_revision:
        revision = BrandProfileRevision(
            brand_id=brand.id,
            company_id=company.id,
            revision=next_version,
            profile_json=profile,
            internal_profile_json=internal_profile,
            source_refs_json=source_refs,
            warnings_json=warnings or [],
            input_snapshot_id=input_snapshot_id,
            input_snapshot_json=input_snapshot,
            run_metadata_json=run_metadata,
            job_id=job_id,
            confirmed_at=now if confirm else None,
            confirmed_by=actor.id if confirm else None,
        )
        db.add(revision)
    else:
        revision = await db.scalar(
            select(BrandProfileRevision)
            .where(BrandProfileRevision.brand_id == brand.id, BrandProfileRevision.revision == next_version)
            .with_for_update()
        )
        if revision is None:
            revision = BrandProfileRevision(
                brand_id=brand.id,
                company_id=company.id,
                revision=next_version,
                profile_json=profile,
                internal_profile_json=internal_profile,
                source_refs_json=source_refs,
                warnings_json=warnings or [],
                input_snapshot_id=input_snapshot_id,
                input_snapshot_json=input_snapshot,
                run_metadata_json=run_metadata,
                confirmed_at=now if confirm else None,
                confirmed_by=actor.id if confirm else None,
            )
            db.add(revision)
        else:
            revision.profile_json = profile
            revision.confirmed_at = now if confirm else None
            revision.confirmed_by = actor.id if confirm else None
    return revision


def _check_version(current: int, supplied: int) -> None:
    if current != supplied:
        raise ApiProblem(
            409,
            "version_conflict",
            "Hồ sơ thương hiệu vừa được người khác cập nhật. Bạn đang sửa một bản cũ.",
            details={"current_version": current, "your_version": supplied},
        )


@router.patch(
    "/workspaces/{company_id}/brand-profile",
    response_model=BrandProfileOut,
    dependencies=[Depends(require_csrf)],
    responses=PROFILE_WRITE_ERRORS,
)
async def update_brand_profile(
    company_id: str,
    request: UpdateBrandProfileRequest,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("brand:edit")),
    db: AsyncSession = Depends(get_db),
):
    if request.profile_text is not None:
        if not has_permission(membership.role, "brand:confirm"):
            raise ApiProblem(403, "forbidden", "Chỉ Owner mới được áp dụng hồ sơ thương hiệu.", details={"required_permission": "brand:confirm"})
        if request.fields or request.confirm:
            raise ApiProblem(422, "validation_error", "Hãy gửi duy nhất nội dung hồ sơ tự viết.")
        normalized_text = request.profile_text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized_text.strip():
            raise ApiProblem(422, "brand_profile_empty", "Hãy nhập nội dung hồ sơ thương hiệu trước khi lưu.")
        brand, company = await _brand_and_company(db, company_id)
        brand = await db.scalar(select(Brand).where(Brand.id == brand.id).with_for_update())
        _check_version(brand.version, request.version)
        current = brand.profile if isinstance(brand.profile, dict) else {}
        if current.get("profile_mode") == "manual_text_v1" and current.get("profile_text") == normalized_text:
            return await _manual_profile_http(db, brand, company)
        saved = {
            key: {"key": key, "label": FIELD_LABELS[key], "value": None, "state": "missing", "provenance": [], "alternatives": []}
            for key in FIELD_KEYS
        }
        saved.update({
            "id": brand.id,
            "workspace_id": company.id,
            "profile_mode": "manual_text_v1",
            "profile_text": normalized_text,
        })
        await _profile_revision(
            db,
            brand,
            company,
            user,
            profile=saved,
            internal_profile=None,
            source_refs=[],
            confirm=True,
            create_revision=True,
        )
        await db.commit()
        return await _manual_profile_http(db, brand, company)
    if request.fields or request.confirm:
        raise ApiProblem(410, "legacy_brand_profile_write_removed", "Hồ sơ thương hiệu hiện được Owner tự viết trong một ô văn bản. Hãy tải lại trang và dùng nút ‘Lưu và áp dụng’.")
    raise ApiProblem(422, "validation_error", "Thiếu profile_text.")


@router.post(
    "/workspaces/{company_id}/brand-profile/confirm",
    response_model=BrandProfileOut,
    dependencies=[Depends(require_csrf)],
    responses=PROFILE_WRITE_ERRORS,
)
async def confirm_brand_profile(
    company_id: str,
    request: ConfirmBrandProfileRequest,
    user: User = Depends(current_user),
    membership: Membership = Depends(require_permission("brand:confirm")),
    db: AsyncSession = Depends(get_db),
):
    brand, _company = await _brand_and_company(db, company_id)
    if not isinstance(brand.profile, dict) or brand.profile.get("profile_mode") != "manual_text_v1":
        raise ApiProblem(410, "brand_profile_manual_required", "Hồ sơ AI cũ chỉ để tham khảo. Owner cần tự viết nội dung rồi bấm ‘Lưu và áp dụng’.")
    raise ApiProblem(410, "brand_profile_apply_on_save", "Hồ sơ văn bản đã được áp dụng khi lưu. Hãy chỉnh nội dung rồi dùng ‘Lưu và áp dụng’ để tạo phiên bản mới.")


@router.get(
    "/workspaces/{company_id}/brand-profile/revisions",
    response_model=list[BrandProfileRevisionOut],
    responses=PROFILE_READ_ERRORS,
)
async def list_brand_profile_revisions(
    company_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    brand, _company = await _brand_and_company(db, company_id)
    rows = (
        await db.scalars(
            select(BrandProfileRevision)
            .where(BrandProfileRevision.brand_id == brand.id, BrandProfileRevision.company_id == company_id)
            .order_by(BrandProfileRevision.revision.desc())
        )
    ).all()
    return [
        BrandProfileRevisionOut(
            id=row.id,
            workspace_id=company_id,
            version=row.revision,
            profile=BrandProfileOut.model_validate(row.profile_json),
            confirmed_at=row.confirmed_at,
            confirmed_by=row.confirmed_by,
            created_at=row.created_at,
            input_snapshot_id=row.input_snapshot_id,
            warnings=row.warnings_json,
        )
        for row in rows
    ]


@router.get(
    "/workspaces/{company_id}/brand-profile/revisions/{revision_number}",
    response_model=BrandProfileRevisionOut,
    responses=PROFILE_READ_ERRORS,
)
async def get_brand_profile_revision(
    company_id: str,
    revision_number: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await membership_for(company_id, user, db)
    brand, _company = await _brand_and_company(db, company_id)
    row = await db.scalar(
        select(BrandProfileRevision).where(
            BrandProfileRevision.brand_id == brand.id,
            BrandProfileRevision.company_id == company_id,
            BrandProfileRevision.revision == revision_number,
        )
    )
    if row is None:
        raise ApiProblem(404, "not_found", "Không tìm thấy phiên bản hồ sơ thương hiệu.")
    return BrandProfileRevisionOut(
        id=row.id,
        workspace_id=company_id,
        version=row.revision,
        profile=BrandProfileOut.model_validate(row.profile_json),
        confirmed_at=row.confirmed_at,
        confirmed_by=row.confirmed_by,
        created_at=row.created_at,
        input_snapshot_id=row.input_snapshot_id,
        warnings=row.warnings_json,
    )
