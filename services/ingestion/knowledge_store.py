"""PostgreSQL persistence adapter for the M3 knowledge-chunk interface."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Document, KnowledgeChunk as KnowledgeChunkRow
from packages.contracts import NormalizedDocument
from services.agents.knowledge.chunking import KnowledgeChunk, chunk_document
from services.agents.knowledge.retrieval import RetrievedChunk, _cosine, _lexical_score


class EmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one fixed-dimension embedding for each input string."""
        raise NotImplementedError


class PostgresKnowledgeIndex:
    """Durable source-hash-idempotent storage with tenant and active-source filters."""

    def __init__(self, *, max_candidates: int = 200, max_context: int = 40) -> None:
        self.max_candidates = max_candidates
        self.max_context = max_context

    async def upsert(
        self,
        db: AsyncSession,
        document: NormalizedDocument,
        *,
        embedder: EmbeddingProvider | None = None,
        batch_size: int = 32,
    ) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        source_filter = (
            KnowledgeChunkRow.company_id == document.company_id,
            KnowledgeChunkRow.brand_id == document.brand_id,
            KnowledgeChunkRow.source_id == document.source_id,
        )
        existing = (
            await db.scalars(
                select(KnowledgeChunkRow).where(
                    *source_filter,
                    KnowledgeChunkRow.source_hash == document.source_hash,
                )
            )
        ).all()
        if existing:
            await db.execute(
                update(KnowledgeChunkRow)
                .where(*source_filter, KnowledgeChunkRow.source_hash == document.source_hash)
                .values(is_active=document.active)
            )
            return 0

        await db.execute(
            update(KnowledgeChunkRow)
            .where(*source_filter)
            .values(is_active=False)
        )
        chunks = chunk_document(document)
        if embedder:
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start : start + batch_size]
                vectors = embedder.embed([item.text for item in batch])
                if len(vectors) != len(batch):
                    raise ValueError("embedding provider returned a mismatched batch length")
                for offset, vector in enumerate(vectors):
                    chunks[start + offset] = replace(
                        batch[offset], embedding=tuple(float(value) for value in vector)
                    )
        db.add_all(
            [
                KnowledgeChunkRow(
                    chunk_id=chunk.chunk_id,
                    company_id=chunk.company_id,
                    brand_id=chunk.brand_id,
                    source_id=chunk.source_id,
                    document_id=chunk.document_id,
                    source_version=chunk.source_version,
                    source_hash=chunk.source_hash,
                    locator=chunk.locator,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    kind=chunk.kind,
                    is_active=chunk.active,
                    embedding=list(chunk.embedding) if chunk.embedding is not None else None,
                )
                for chunk in chunks
            ]
        )
        return len(chunks)

    async def retrieve(
        self,
        db: AsyncSession,
        query: str,
        *,
        company_id: str,
        brand_id: str,
        active_source_ids: set[str] | None = None,
        embedder: EmbeddingProvider | None = None,
        top_k: int = 20,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        if not 1 <= top_k <= self.max_context:
            raise ValueError(f"top_k must be between 1 and {self.max_context}")
        statement = (
            select(KnowledgeChunkRow)
            .join(Document, Document.id == KnowledgeChunkRow.document_id)
            .where(
                KnowledgeChunkRow.company_id == company_id,
                KnowledgeChunkRow.brand_id == brand_id,
                KnowledgeChunkRow.is_active.is_(True),
                Document.company_id == company_id,
                Document.is_active.is_(True),
                Document.deleted_at.is_(None),
                Document.status == "ready",
                Document.knowledge_status == "ready",
            )
        )
        if active_source_ids is not None:
            if not active_source_ids:
                return []
            statement = statement.where(KnowledgeChunkRow.source_id.in_(active_source_ids))

        query_vector: Sequence[float] | None = None
        if embedder:
            vectors = embedder.embed([query])
            if len(vectors) != 1:
                raise ValueError("embedding provider must return one query vector")
            query_vector = vectors[0]
            # pgvector performs candidate ranking in Postgres; lexical score is
            # blended after tenant/active-source filtering.
            statement = (
                statement.where(KnowledgeChunkRow.embedding.is_not(None))
                .order_by(KnowledgeChunkRow.embedding.cosine_distance(list(query_vector)))
                .limit(self.max_candidates)
            )
        else:
            statement = statement.order_by(KnowledgeChunkRow.source_id, KnowledgeChunkRow.chunk_id).limit(self.max_candidates)

        rows = (await db.scalars(statement)).all()
        ranked: list[RetrievedChunk] = []
        for row in rows:
            chunk = KnowledgeChunk(
                chunk_id=row.chunk_id,
                company_id=row.company_id,
                brand_id=row.brand_id,
                source_id=row.source_id,
                document_id=row.document_id,
                source_version=row.source_version,
                source_hash=row.source_hash,
                locator=row.locator,
                text=row.text,
                token_count=row.token_count,
                kind=row.kind,
                active=row.is_active,
                embedding=tuple(row.embedding) if row.embedding is not None else None,
            )
            lexical = _lexical_score(query, chunk.text)
            semantic = _cosine(query_vector, chunk.embedding)
            score = lexical if query_vector is None else 0.65 * semantic + 0.35 * lexical
            ranked.append(RetrievedChunk(chunk, score, semantic, lexical))
        ranked.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        return ranked[:top_k]
