"""Restricted ledger export/re-application before a restored database is served.

No bodies, names, profile URLs, tokens, or provider data are exported. Source
comment IDs remain restricted operational data. Missing tenant/actor mappings
abort the transaction; an operator must resolve them before serving the restore.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from database.models import Company, MarketEvidence, ResearchCommentSuppression, ResearchCommentVersion, ResearchSource, User
from .comment_suppression import suppress_comment_tree


class DeletionLedgerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    id: UUID
    company_id: UUID
    source_id: UUID
    post_key_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    external_comment_id: str = Field(min_length=1, max_length=100)
    reason: Literal["subject_request", "out_of_scope", "privacy_risk"]
    created_by: UUID
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("timezone is required")
        return value


async def export_deletion_ledger(db):
    query = select(ResearchCommentSuppression).order_by(ResearchCommentSuppression.company_id,
        ResearchCommentSuppression.source_id, ResearchCommentSuppression.post_key_hash,
        ResearchCommentSuppression.external_comment_id).execution_options(yield_per=1000)
    rows = await db.stream_scalars(query)
    async for row in rows:
        values = {field: getattr(row, field) for field in DeletionLedgerRecord.model_fields
                  if field != "schema_version"}
        # SQLite fixture drivers discard timezone; persisted dates are UTC.
        if values["created_at"].tzinfo is None:
            values["created_at"] = values["created_at"].replace(tzinfo=timezone.utc)
        yield DeletionLedgerRecord(**values)


async def apply_deletion_ledger(db, records: list[DeletionLedgerRecord]) -> dict[str, int]:
    """Caller commits once; replay never restores content or duplicates entries."""
    rows = [DeletionLedgerRecord.model_validate(record.model_dump()) for record in records]
    inserted, erased = 0, 0
    touched = set()
    for record in sorted(rows, key=lambda row: (str(row.company_id), str(row.source_id), row.post_key_hash, row.external_comment_id)):
        company_id, source_id = str(record.company_id), str(record.source_id)
        await db.scalar(select(Company.id).where(Company.id == company_id).with_for_update())
        source = await db.scalar(select(ResearchSource).where(
            ResearchSource.company_id == company_id, ResearchSource.id == source_id).with_for_update())
        actor = await db.scalar(select(User.id).where(User.id == str(record.created_by)))
        if source is None or actor is None:
            raise ValueError("deletion_ledger_mapping_missing")
        existing = await db.scalar(select(ResearchCommentSuppression).where(
            ResearchCommentSuppression.company_id == company_id, ResearchCommentSuppression.source_id == source_id,
            ResearchCommentSuppression.post_key_hash == record.post_key_hash,
            ResearchCommentSuppression.external_comment_id == record.external_comment_id,
        ))
        if existing is None:
            db.add(ResearchCommentSuppression(**{key: value for key, value in record.model_dump(mode="json").items()
                if key not in {"schema_version", "created_at"}}, created_at=record.created_at))
            inserted += 1
        touched.add((company_id, source_id, record.post_key_hash))
    await db.flush()
    # Match the post key rather than an old evidence row ID: the restored
    # database may have a previous row for the same source/permalink.
    evidence_cache = {}
    for company_id, source_id, key in sorted(touched):
        scope = (company_id, source_id)
        if scope not in evidence_cache:
            evidence_rows = (await db.scalars(select(MarketEvidence).where(
                MarketEvidence.company_id == company_id, MarketEvidence.source_id == source_id))).all()
            evidence_cache[scope] = {hashlib.sha256(row.canonical_url.encode("utf-8")).hexdigest(): row
                                     for row in evidence_rows}
        evidence = evidence_cache[scope].get(key)
        if evidence is not None:
            blocked = (await db.scalars(select(ResearchCommentSuppression).where(
                ResearchCommentSuppression.company_id == company_id, ResearchCommentSuppression.source_id == source_id,
                ResearchCommentSuppression.post_key_hash == key))).all()
            for entry in blocked:
                version = await db.scalar(select(ResearchCommentVersion).where(
                    ResearchCommentVersion.company_id == company_id, ResearchCommentVersion.source_id == source_id,
                    ResearchCommentVersion.evidence_id == evidence.id,
                    ResearchCommentVersion.external_comment_id == entry.external_comment_id).limit(1))
                if version is not None:
                    result = await suppress_comment_tree(db, version=version, actor_id=entry.created_by, reason=entry.reason)
                    erased += result.versions_erased
    return {"ledger_records": len(rows), "inserted": inserted, "versions_erased": erased}
