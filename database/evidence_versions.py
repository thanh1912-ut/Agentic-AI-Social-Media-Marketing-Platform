"""Helpers for immutable, fingerprinted market-evidence content versions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import MarketEvidence, MarketEvidenceVersion, new_id


async def ensure_evidence_version(
    db: AsyncSession,
    evidence: MarketEvidence,
    *,
    title: str,
    text: str,
    published_at: datetime | None,
    captured_at: datetime,
    parser_version: str,
) -> MarketEvidenceVersion:
    """Return the immutable version for this exact normalized payload."""
    title = " ".join(title.split())[:1000]
    text = " ".join(text.split())[:12000]
    published = published_at.isoformat() if published_at else None
    canonical = json.dumps(
        {"title": title, "text": text, "published_at": published},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    version = await db.scalar(
        select(MarketEvidenceVersion).where(
            MarketEvidenceVersion.company_id == evidence.company_id,
            MarketEvidenceVersion.evidence_id == evidence.id,
            MarketEvidenceVersion.content_hash == fingerprint,
            MarketEvidenceVersion.parser_version == parser_version,
        )
    )
    if version is None:
        version = MarketEvidenceVersion(
            id=new_id(),
            company_id=evidence.company_id,
            evidence_id=evidence.id,
            content_hash=fingerprint,
            parser_version=parser_version,
            title=title,
            text=text,
            published_at=published_at,
            captured_at=captured_at,
        )
        db.add(version)
        await db.flush()
    return version
