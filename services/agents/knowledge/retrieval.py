"""Tenant-filtered hybrid retrieval with bounded candidates/context."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from packages.contracts import NormalizedDocument

from .chunking import KnowledgeChunk, _tokens, chunk_document


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one vector per input text."""


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: KnowledgeChunk
    score: float
    semantic_score: float
    lexical_score: float

    @property
    def source_id(self) -> str:
        return self.chunk.source_id

    @property
    def locator(self) -> str:
        return self.chunk.locator


def _lexical_score(query: str, text: str) -> float:
    query_terms = {term.casefold() for term in _tokens(query) if term.isalnum()}
    text_terms = {term.casefold() for term in _tokens(text) if term.isalnum()}
    if not query_terms:
        return 0.0
    return len(query_terms & text_terms) / len(query_terms)


def _cosine(left: Sequence[float] | None, right: Sequence[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm))


class InMemoryKnowledgeIndex:
    """Small deterministic index useful for fixtures and a pilot.

    The storage interface deliberately exposes the same invariants a pgvector
    implementation must preserve: source hash idempotency, tenant/brand
    filtering before ranking, bounded candidate pool and source locators.
    """

    def __init__(self, *, max_candidates: int = 20, max_context: int = 6) -> None:
        if max_candidates < 1 or max_context < 1 or max_context > max_candidates:
            raise ValueError("invalid retrieval bounds")
        self.max_candidates = max_candidates
        self.max_context = max_context
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._source_hashes: dict[tuple[str, str, str], str] = {}

    def upsert(
        self,
        document: NormalizedDocument,
        *,
        embedder: EmbeddingProvider | None = None,
        batch_size: int = 32,
    ) -> int:
        """Index one document and return the number of newly embedded chunks."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        source_key = (document.company_id, document.brand_id, document.source_id)
        if self._source_hashes.get(source_key) == document.source_hash:
            return 0

        old_ids = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if (chunk.company_id, chunk.brand_id, chunk.source_id) == source_key
        ]
        for chunk_id in old_ids:
            del self._chunks[chunk_id]

        chunks = chunk_document(document)
        if embedder:
            for start in range(0, len(chunks), batch_size):
                batch = chunks[start : start + batch_size]
                vectors = embedder.embed([chunk.text for chunk in batch])
                if len(vectors) != len(batch):
                    raise ValueError("embedding provider returned a mismatched batch length")
                for index, vector in enumerate(vectors):
                    chunks[start + index] = replace(
                        batch[index], embedding=tuple(float(value) for value in vector)
                    )
        self._chunks.update({chunk.chunk_id: chunk for chunk in chunks})
        self._source_hashes[source_key] = document.source_hash
        return len(chunks)

    def upsert_many(
        self,
        documents: Iterable[NormalizedDocument],
        *,
        embedder: EmbeddingProvider | None = None,
        batch_size: int = 32,
    ) -> int:
        embedded = 0
        for document in documents:
            embedded += self.upsert(document, embedder=embedder, batch_size=batch_size)
        return embedded

    def retrieve(
        self,
        query: str,
        *,
        company_id: str,
        brand_id: str,
        active_source_ids: set[str] | None = None,
        embedder: EmbeddingProvider | None = None,
        top_k: int = 6,
    ) -> list[RetrievedChunk]:
        if not query.strip():
            return []
        if not 1 <= top_k <= self.max_context:
            raise ValueError(f"top_k must be between 1 and {self.max_context}")

        candidates = [
            chunk
            for chunk in self._chunks.values()
            if chunk.active
            and chunk.company_id == company_id
            and chunk.brand_id == brand_id
            and (active_source_ids is None or chunk.source_id in active_source_ids)
        ]
        query_vector = None
        if embedder and candidates:
            vectors = embedder.embed([query])
            if len(vectors) != 1:
                raise ValueError("embedding provider must return one query vector")
            query_vector = vectors[0]

        ranked: list[RetrievedChunk] = []
        for chunk in candidates:
            lexical = _lexical_score(query, chunk.text)
            semantic = _cosine(query_vector, chunk.embedding)
            if query_vector is None:
                score = lexical
            else:
                score = 0.65 * semantic + 0.35 * lexical
            ranked.append(RetrievedChunk(chunk, score, semantic, lexical))
        ranked.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        return ranked[: self.max_candidates][:top_k]
