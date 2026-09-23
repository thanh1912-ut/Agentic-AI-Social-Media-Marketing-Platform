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
        profile["completeness"] = sum(
            profile.get(key, {}).get("state") == "confirmed" for key in FIELD_KEYS
        ) / len(FIELD_KEYS)
    else:
        profile["confirmed_at"] = None
        profile["confirmed_by"] = None
    profile["version"] = next_version
    profile["updated_at"] = now.isoformat()
    brand.version = next_version
    brand.profile = profile
    db.add(
        AuditEvent(
            company_id=company.id,
            actor_user_id=actor.id,
            action="brand_profile.confirm" if confirm else "brand_profile.update",
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
    if request.confirm and not has_permission(membership.role, "brand:confirm"):
        raise ApiProblem(403, "forbidden", "Bạn không có quyền xác nhận hồ sơ thương hiệu.", details={"required_permission": "brand:confirm"})
    brand, company = await _brand_and_company(db, company_id)
    brand = await db.scalar(select(Brand).where(Brand.id == brand.id).with_for_update())
    _check_version(brand.version, request.version)
    if not request.fields and not request.confirm:
        raise ApiProblem(422, "validation_error", "Chưa có thay đổi nào để lưu.")
    saved = brand.profile if isinstance(brand.profile, dict) else {}
    if not all(key in saved for key in FIELD_KEYS):
        saved = await internal_profile_to_http(db, internal={}, brand=brand, company=company)
    else:
        saved = copy.deepcopy(saved)
    seen: set[str] = set()
    now = utcnow().isoformat()
    for field in request.fields:
        if field.key not in FIELD_LABELS:
            raise ApiProblem(422, "validation_error", "Trường hồ sơ không được hỗ trợ.", field_errors=[{"field": f"fields.{field.key}", "message": "Trường hồ sơ không hợp lệ."}])
        if field.key in seen:
            raise ApiProblem(422, "validation_error", "Một trường không thể xuất hiện nhiều lần.")
        seen.add(field.key)
        value = field.value
        if field.key in {"target_audience", "tone_keywords", "do_not_use", "competitors"} and value is not None and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
            raise ApiProblem(422, "validation_error", "Giá trị trường phải là danh sách văn bản.")
        if field.key in {"business_name", "industry", "description", "brand_voice"} and value is not None and not isinstance(value, str):
            raise ApiProblem(422, "validation_error", "Giá trị trường phải là văn bản.")
        if field.key == "products" and value is not None and (not isinstance(value, list) or not all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in value)):
            raise ApiProblem(422, "validation_error", "Danh sách sản phẩm chưa hợp lệ.")
        if field.key == "contact" and value is not None and (not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())):
            raise ApiProblem(422, "validation_error", "Thông tin liên hệ chưa hợp lệ.")
        saved[field.key] = {
            "key": field.key,
            "label": FIELD_LABELS[field.key],
            "value": value,
            "state": "edited" if not _is_empty(value) else "missing",
            "provenance": [],
            "alternatives": [],
            "updated_at": now,
            "updated_by": user.id,
        }
    prior_revision = await db.scalar(
        select(BrandProfileRevision).where(
            BrandProfileRevision.brand_id == brand.id,
            BrandProfileRevision.revision == brand.version,
        )
    )
    await _profile_revision(
        db,
        brand,
        company,
        user,
        profile=saved,
        internal_profile=prior_revision.internal_profile_json if prior_revision else None,
        source_refs=prior_revision.source_refs_json if prior_revision else [],
        input_snapshot_id=prior_revision.input_snapshot_id if prior_revision else None,
        input_snapshot=prior_revision.input_snapshot_json if prior_revision else None,
        run_metadata=prior_revision.run_metadata_json if prior_revision else None,
        warnings=prior_revision.warnings_json if prior_revision else [],
        confirm=request.confirm,
        create_revision=bool(request.fields),
    )
    await db.commit()
    return _profile_http(saved)


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
    brand, company = await _brand_and_company(db, company_id)
    brand = await db.scalar(select(Brand).where(Brand.id == brand.id).with_for_update())
    _check_version(brand.version, request.version)
    saved = copy.deepcopy(brand.profile) if isinstance(brand.profile, dict) else {}
    if not all(key in saved for key in FIELD_KEYS):
        saved = await internal_profile_to_http(db, internal={}, brand=brand, company=company)
    prior_revision = await db.scalar(
        select(BrandProfileRevision).where(
            BrandProfileRevision.brand_id == brand.id,
            BrandProfileRevision.revision == brand.version,
        )
    )
    await _profile_revision(
        db,
        brand,
        company,
        user,
        profile=saved,
        internal_profile=prior_revision.internal_profile_json if prior_revision else None,
        source_refs=prior_revision.source_refs_json if prior_revision else [],
        input_snapshot_id=prior_revision.input_snapshot_id if prior_revision else None,
        input_snapshot=prior_revision.input_snapshot_json if prior_revision else None,
        run_metadata=prior_revision.run_metadata_json if prior_revision else None,
        warnings=prior_revision.warnings_json if prior_revision else [],
        confirm=True,
        create_revision=False,
    )
    await db.commit()
    return _profile_http(saved)


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
