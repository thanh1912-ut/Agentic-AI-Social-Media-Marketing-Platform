# M3 slice 1 — contract, RAG và analytics foundations

Trạng thái: hoàn thành phần nền tảng chạy độc lập với backend thật.

## Bàn giao

- `packages/contracts/models.py`: strict Pydantic contracts cho
  `NormalizedDocument`, `BrandProfile`, `CampaignBrief`, `CampaignStrategy`,
  `GeneratedPost`, `ContentReview`, `AnalyticsReport`, `AnalyticsInsight`,
  `Recommendation` và `Experiment`.
- `packages/contracts/validation.py`: structured-output validation với tối đa
  một lần repair.
- `services/agents/knowledge/`: NFC/whitespace normalization, chunk text
  khoảng 600 token với overlap tối đa 80, table header + row, idempotent source
  hash, batch embedding và hybrid retrieval.
- `services/agents/brand_agent/` và `content_agent/`: provider-neutral handlers;
  Brand Profile luôn chờ human confirmation, Content luôn trả version mới.
- `services/agents/orchestrator/`: finite LangGraph wiring, checkpoint-friendly
  state, node tracking và tối đa hai automatic revisions; không có publish node.
- `services/agents/analytics/metrics.py`: metric/rate/report functions có
  coverage, sample size, measurement period và evidence IDs.
- `tests/fixtures/briefs_vi.py`: 50 brief tiếng Việt F&B/bán lẻ, gồm missing
  data, giá mâu thuẫn, ưu đãi hết hạn, revision và prompt injection.

## Sample input/output

```python
document = NormalizedDocument(
    company_id="company-1", brand_id="brand-1", document_id="doc-1",
    source_id="menu", source_version="v1", source_hash="sha256:...",
    text_blocks=[TextBlock(
        block_id="b1", heading="Giá", text="Cơm gà 65.000đ", locator="page=3"
    )],
)
chunks = chunk_document(document)
# chunks[0].source_id == "menu"
# chunks[0].locator == "page=3#chunk-1"
```

`build_analytics_report(...)` trả `AnalyticsReport.evidence[]`; insight và
recommendation phải tham chiếu các `evidence_id` này. Thiếu mẫu số trả
`value=None` với `unavailable_reason`, không trả `0`.

## Verification

```text
21 passed in 0.05s
```

## Cần M2 cung cấp

- Adapter persistence cho `NormalizedDocument`/chunk metadata trong PostgreSQL
  + pgvector, gồm active source filter và permission enforcement.
- NormalizedDocument thật từ ingestion, giữ source version/hash và locator.
- Job/run ID, input snapshot ID, backend version/status/authorization.
- Metrics normalized theo cùng Page, metric definition và post-age window.
- Provider adapter đã benchmark; handler không chứa credential/token.

## Chưa claim trong slice này

Chưa benchmark model/provider, chưa gọi LLM thật, chưa publish, chưa thay thế
OpenAPI/TypeScript contracts draft của M1 và chưa kết luận chất lượng trên 50
brief bằng LLM-as-judge. Các mục đó cần adapter và dữ liệu/tiêu chí từ M2/M1.
