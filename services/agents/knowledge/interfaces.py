"""M2-owned persistence boundary required by M3 retrieval.

The repository must apply tenant, brand, active-source and lifecycle filters
inside the query before ranking. The version arguments are part of the key so
parser/chunker/embedding upgrades cannot silently reuse stale vectors. An
``embedder=None`` call selects lexical-only retrieval; use the stable version
marker ``lexical-v1`` for that mode rather than claiming a vector model.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from packages.contracts import NormalizedDocument

from .chunking import KnowledgeChunk
from .retrieval import EmbeddingProvider, RetrievedChunk


class PersistentKnowledgeRepository(Protocol):
    """Durable repository interface implemented by M2 (PostgreSQL/pgvector)."""

    async def upsert(
        self,
        session: Any,
        document: NormalizedDocument,
        *,
        embedder: EmbeddingProvider | None,
        parser_version: str,
        chunker_version: str,
        embedding_model_version: str,
        batch_size: int = 32,
    ) -> int: ...

    async def retrieve(
        self,
        session: Any,
        query: str,
        *,
        company_id: str,
        brand_id: str,
        active_source_ids: set[str],
        embedder: EmbeddingProvider | None,
        parser_version: str | None,
        chunker_version: str | None,
        embedding_model_version: str | None,
        minimum_score: float = 0.12,
        minimum_semantic_score: float = 0.82,
        minimum_semantic_margin: float = 0.04,
        minimum_hybrid_lexical_score: float = 0.45,
        top_k: int = 20,
    ) -> list[RetrievedChunk]: ...


def source_context(chunks: Sequence[KnowledgeChunk]) -> list[dict[str, str]]:
    """Produce only source identity and normalized content for the model."""

    return [
        {
            "company_id": item.company_id,
            "brand_id": item.brand_id,
            "source_id": item.source_id,
            "document_id": item.document_id,
            "source_version": item.source_version,
            "source_hash": item.source_hash,
            "locator": item.locator,
            "text": item.text,
        }
        for item in chunks
    ]
