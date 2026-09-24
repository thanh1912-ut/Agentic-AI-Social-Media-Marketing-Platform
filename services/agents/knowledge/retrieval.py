"""Tenant-filtered hybrid retrieval with bounded candidates/context."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from packages.contracts import NormalizedDocument

from .chunking import CHUNKER_VERSION, KnowledgeChunk, _tokens, chunk_document


# Vietnamese question particles and grammatical words add little evidence that
# a chunk answers the query. Keep domain words such as "nhà", "hàng", and
# "món" so exact product and location queries still match.
_LEXICAL_STOP_WORDS = frozenset(
    "a à ạ á ả ã ă ằ ắ ẳ ẵ ặ â ầ ấ ẩ ẫ ậ các cái của cho có đã đang để được đâu "
    "gì khi là mà mỗi một mấy nào nên nếu những như ở ra sẽ thì trong từ tại theo "
    "vào và với vì về bị bởi qua trên dưới sau trước nhưng hãy giúp mình tôi bạn "
    "chúng họ này đó kia ấy vậy bao nhiêu"
    .split()
)


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one passage vector per input text."""

    def embed_query(self, query: str) -> Sequence[float]:
        """Return a search-query vector; providers without query prefixes may reuse embed()."""


def _embed_query(embedder: EmbeddingProvider, query: str) -> Sequence[float]:
    query_embedder = getattr(embedder, "embed_query", None)
    if callable(query_embedder):
        return query_embedder(query)
    vectors = embedder.embed([query])
    if len(vectors) != 1:
        raise ValueError("embedding provider must return one query vector")
    return vectors[0]


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


def filter_relevant_chunks(
    candidates: Iterable[RetrievedChunk],
    *,
    top_k: int,
    minimum_score: float = 0.12,
    minimum_semantic_score: float = 0.82,
    minimum_semantic_margin: float = 0.04,
    minimum_hybrid_lexical_score: float = 0.45,
) -> list[RetrievedChunk]:
    """Rank and suppress low-evidence candidates before passing context to an LLM."""

    if top_k < 1:
        raise ValueError("top_k must be positive")
    if (
        not 0 <= minimum_score <= 1
        or not 0 <= minimum_semantic_score <= 1
        or not 0 <= minimum_semantic_margin <= 1
        or not 0 <= minimum_hybrid_lexical_score <= 1
    ):
        raise ValueError("relevance thresholds must be between 0 and 1")
    ranked = sorted(candidates, key=lambda item: (-item.score, item.chunk.chunk_id))
    best_by_source: dict[str, float] = {}
    for item in ranked:
        if item.semantic_score > best_by_source.get(item.source_id, 0.0):
            best_by_source[item.source_id] = item.semantic_score
    semantic_ranked = sorted(
        ((score, source_id) for source_id, score in best_by_source.items() if score > 0),
        reverse=True,
    )
    semantic_margin = (
        semantic_ranked[0][0] - semantic_ranked[1][0]
        if len(semantic_ranked) > 1
        else semantic_ranked[0][0] - minimum_semantic_score
        if semantic_ranked
        else 0.0
    )
    semantic_confident = bool(
        semantic_ranked
        and semantic_ranked[0][0] >= minimum_semantic_score
        and semantic_margin >= minimum_semantic_margin
    )
    best_semantic_source = semantic_ranked[0][1] if semantic_confident else None
    lexical_threshold = minimum_hybrid_lexical_score if semantic_ranked else minimum_score
    # A high E5 cosine alone is not enough for Vietnamese no-answer queries.
    # Require the best semantic match to separate from its runner-up. Lexical
    # evidence can still admit a precise match after question words are removed.
    selected = [
        item
        for item in ranked
        if item.lexical_score >= lexical_threshold
        or (
            semantic_confident
            and item.source_id == best_semantic_source
            and item.semantic_score >= minimum_semantic_score
        )
    ]
    return selected[:top_k]


def _lexical_score(query: str, text: str) -> float:
    query_terms = {
        term.casefold()
        for term in _tokens(query)
        if term.isalnum() and term.casefold() not in _LEXICAL_STOP_WORDS
    }
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
        self._source_hashes: set[tuple[str, str, str, str, str, str, str]] = set()

    def upsert(
        self,
        document: NormalizedDocument,
        *,
        embedder: EmbeddingProvider | None = None,
        batch_size: int = 32,
        parser_version: str = "unknown",
        chunker_version: str = CHUNKER_VERSION,
        embedding_model_version: str | None = None,
    ) -> int:
        """Index one document and return the number of newly embedded chunks."""

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        resolved_embedding_version = embedding_model_version or (
            getattr(embedder, "model_name", None) if embedder is not None else None
        )
        source_key = (document.company_id, document.brand_id, document.source_id)
        dedupe_key = (
            *source_key,
            document.source_hash,
            parser_version,
            chunker_version,
            resolved_embedding_version or "no-embedding",
        )
        if dedupe_key in self._source_hashes:
            self._chunks = {
                chunk_id: replace(chunk, active=document.active)
                if (chunk.company_id, chunk.brand_id, chunk.source_id) == source_key
                else chunk
                for chunk_id, chunk in self._chunks.items()
            }
            return 0

        chunks = chunk_document(
            document,
            parser_version=parser_version,
            chunker_version=chunker_version,
            embedding_model_version=resolved_embedding_version,
        )
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
        # Replace only after all embeddings have succeeded so a provider error
        # cannot destroy the previously indexed version.
        old_ids = [
            chunk_id
            for chunk_id, chunk in self._chunks.items()
            if (chunk.company_id, chunk.brand_id, chunk.source_id) == source_key
        ]
        for chunk_id in old_ids:
            del self._chunks[chunk_id]
        self._chunks.update({chunk.chunk_id: chunk for chunk in chunks})
        self._source_hashes = {
            key for key in self._source_hashes if key[:3] != source_key
        }
        self._source_hashes.add(dedupe_key)
        return len(chunks)

    def upsert_many(
        self,
        documents: Iterable[NormalizedDocument],
        *,
        embedder: EmbeddingProvider | None = None,
        batch_size: int = 32,
        parser_version: str = "unknown",
        chunker_version: str = CHUNKER_VERSION,
        embedding_model_version: str | None = None,
    ) -> int:
        embedded = 0
        for document in documents:
            embedded += self.upsert(
                document,
                embedder=embedder,
                batch_size=batch_size,
                parser_version=parser_version,
                chunker_version=chunker_version,
                embedding_model_version=embedding_model_version,
            )
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
        minimum_score: float = 0.12,
        minimum_semantic_score: float = 0.82,
        minimum_semantic_margin: float = 0.04,
        minimum_hybrid_lexical_score: float = 0.45,
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
            query_vector = _embed_query(embedder, query)

        ranked: list[RetrievedChunk] = []
        for chunk in candidates:
            lexical = _lexical_score(query, chunk.text)
            semantic = _cosine(query_vector, chunk.embedding)
            if query_vector is None:
                score = lexical
            else:
                score = 0.75 * semantic + 0.25 * lexical
            ranked.append(RetrievedChunk(chunk, score, semantic, lexical))
        candidate_pool = sorted(ranked, key=lambda item: (-item.score, item.chunk.chunk_id))[
            : self.max_candidates
        ]
        return filter_relevant_chunks(
            candidate_pool,
            top_k=top_k,
            minimum_score=minimum_score,
            minimum_semantic_score=minimum_semantic_score,
            minimum_semantic_margin=minimum_semantic_margin,
            minimum_hybrid_lexical_score=minimum_hybrid_lexical_score,
        )
