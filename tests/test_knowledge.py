from dataclasses import dataclass

from services.agents.knowledge import InMemoryKnowledgeIndex, chunk_document, normalize_text


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
