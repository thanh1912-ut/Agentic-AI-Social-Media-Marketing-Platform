from dataclasses import dataclass

from services.agents.knowledge import CHUNKER_VERSION, InMemoryKnowledgeIndex, chunk_document, normalize_text
from services.agents.knowledge.chunking import MAX_CHUNK_TOKENS
from services.agents.knowledge.retrieval import RetrievedChunk, filter_relevant_chunks


@dataclass
class FakeEmbedder:
    calls: list[list[str]]

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[1.0, 0.0] for _ in texts]


def test_normalize_text_preserves_vietnamese_diacritics() -> None:
    assert normalize_text("  Cà  phê   sữa  ") == "Cà phê sữa"


def test_chunking_keeps_table_header_and_locator(normalized_document) -> None:
    chunks = chunk_document(normalized_document, max_tokens=20, overlap_tokens=4)
    table_chunks = [chunk for chunk in chunks if chunk.kind == "table"]
    assert len(table_chunks) == 2
    assert all("Sản phẩm" in chunk.text for chunk in table_chunks)
    assert table_chunks[0].locator.endswith("[row=1]")
    assert all(chunk.token_count <= 20 for chunk in chunks)


def test_default_chunk_size_stays_inside_local_embedding_context(normalized_document) -> None:
    original = normalized_document.text_blocks[0]
    long_block = original.model_copy(update={"text": "Cà phê rang xay Việt Nam. " * 100})
    long_document = normalized_document.model_copy(
        update={"text_blocks": [long_block], "table_blocks": []}
    )

    chunks = chunk_document(long_document)

    assert CHUNKER_VERSION == "vi-token-window-v3-300"
    assert len(chunks) > 1
    assert all(chunk.token_count <= MAX_CHUNK_TOKENS for chunk in chunks)


def test_index_is_idempotent_and_batches_embeddings(normalized_document) -> None:
    embedder = FakeEmbedder([])
    index = InMemoryKnowledgeIndex()
    first_count = index.upsert(normalized_document, embedder=embedder, batch_size=2)
    second_count = index.upsert(normalized_document, embedder=embedder, batch_size=2)
    assert first_count > 0
    assert second_count == 0
    assert len(embedder.calls) >= 2


def test_retrieval_filters_tenant_brand_and_active_sources(normalized_document) -> None:
    index = InMemoryKnowledgeIndex()
    index.upsert(normalized_document)
    wrong_tenant = normalized_document.model_copy(update={"company_id": "company-2"})
    index.upsert(wrong_tenant)
    results = index.retrieve(
        "giá Cơm gà",
        company_id="company-1",
        brand_id="brand-1",
        active_source_ids={"source-menu"},
    )
    assert results
    assert all(result.chunk.company_id == "company-1" for result in results)
    assert all(result.source_id == "source-menu" for result in results)
    assert all(result.locator for result in results)


def test_retrieval_context_is_bounded(normalized_document) -> None:
    index = InMemoryKnowledgeIndex(max_candidates=20, max_context=6)
    index.upsert(normalized_document)
    results = index.retrieve("món Việt", company_id="company-1", brand_id="brand-1", top_k=6)
    assert len(results) <= 6


def test_hybrid_retrieval_does_not_use_blended_score_as_relevance_gate(normalized_document) -> None:
    chunks = chunk_document(normalized_document, max_tokens=20, overlap_tokens=4)[:3]
    weak_semantic = RetrievedChunk(chunks[0], score=0.5, semantic_score=0.5, lexical_score=0.0)
    exact_lexical = RetrievedChunk(chunks[1], score=0.05, semantic_score=0.05, lexical_score=0.2)
    strong_semantic = RetrievedChunk(chunks[2], score=0.6, semantic_score=0.73, lexical_score=0.2)

    selected = filter_relevant_chunks(
        [weak_semantic, exact_lexical, strong_semantic],
        top_k=3,
        minimum_score=0.12,
        minimum_semantic_score=0.72,
    )

    assert [item.chunk.chunk_id for item in selected] == [
        strong_semantic.chunk.chunk_id,
        exact_lexical.chunk.chunk_id,
    ]
