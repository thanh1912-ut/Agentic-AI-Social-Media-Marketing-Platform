from dataclasses import dataclass

from services.agents.knowledge import CHUNKER_VERSION, InMemoryKnowledgeIndex, chunk_document, normalize_text
from services.agents.knowledge.chunking import MAX_CHUNK_TOKENS
from services.agents.knowledge.retrieval import RetrievedChunk, _lexical_score, filter_relevant_chunks


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
        minimum_semantic_margin=0.0,
        minimum_hybrid_lexical_score=0.12,
    )

    assert [item.chunk.chunk_id for item in selected] == [
        strong_semantic.chunk.chunk_id,
        exact_lexical.chunk.chunk_id,
    ]


def test_semantic_retrieval_abstains_when_top_matches_are_ambiguous(normalized_document) -> None:
    chunks = chunk_document(normalized_document, max_tokens=20, overlap_tokens=4)[:2]
    close_matches = [
        RetrievedChunk(chunks[0], score=0.84, semantic_score=0.84, lexical_score=0.0),
        RetrievedChunk(chunks[1], score=0.81, semantic_score=0.81, lexical_score=0.0),
    ]

    assert filter_relevant_chunks(close_matches, top_k=2) == []


def test_semantic_retrieval_keeps_a_clear_match(normalized_document) -> None:
    chunks = chunk_document(normalized_document, max_tokens=20, overlap_tokens=4)[:2]
    clear_match = RetrievedChunk(chunks[0], score=0.88, semantic_score=0.88, lexical_score=0.0)
    weak_runner_up = RetrievedChunk(chunks[1], score=0.78, semantic_score=0.78, lexical_score=0.0)

    assert filter_relevant_chunks([clear_match, weak_runner_up], top_k=2) == [clear_match]


def test_semantic_confidence_compares_sources_and_keeps_matching_source_chunks(normalized_document) -> None:
    chunks = chunk_document(normalized_document, max_tokens=20, overlap_tokens=4)[:3]
    same_source = [
        RetrievedChunk(chunks[0], score=0.90, semantic_score=0.90, lexical_score=0.0),
        RetrievedChunk(chunks[1], score=0.89, semantic_score=0.89, lexical_score=0.0),
    ]
    other_source_chunk = chunks[2].__class__(
        **{**chunks[2].__dict__, "source_id": "unrelated-source"}
    )
    other_source = RetrievedChunk(
        other_source_chunk, score=0.83, semantic_score=0.83, lexical_score=0.0
    )

    assert filter_relevant_chunks([*same_source, other_source], top_k=3) == same_source


def test_lexical_relevance_ignores_question_words_but_requires_content_overlap() -> None:
    address = "Địa chỉ cửa hàng tại số 12 đường Nguyễn Huệ, Thành phố Hồ Chí Minh."
    promotion = "Ưu đãi cuối tuần giảm giá cho khách đặt món trực tuyến."

    assert _lexical_score("Cửa hàng ở đâu?", address) == 1.0
    assert _lexical_score("Thời tiết Đà Lạt cuối tuần", promotion) < 0.45
