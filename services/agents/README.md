# M3 DeepSeek handoff for Brand and Content

## Provider adapter

`services.agents.providers.DeepSeekStructuredModel` implements the existing
`StructuredModel.generate(...)` protocol. Brand and Content handlers can share
one instance; the adapter uses DeepSeek Chat Completions with
`response_format={"type":"json_object"}`, adds the response Pydantic schema
and a JSON example to the system prompt, then parses JSON and validates it with
Pydantic. It makes at most one repair request for empty, incomplete, malformed,
or schema-invalid output. The OpenAI SDK is configured with `max_retries=0` so
M2's job retry policy remains the only transport retry layer.

Factory/callable for M2:

```python
from services.agents.brand_agent import BrandAgent, run_brand_profile_handler
from services.agents.providers import configured_deepseek_structured_model

model = configured_deepseek_structured_model()
agent = BrandAgent(model)
result = run_brand_profile_handler(
    agent=agent,
    company_id="tenant-123",
    brand_id="brand-456",
    document_ids=["doc-789"],
    job_id="job-abc",
    run_id="run-def",
    input_snapshot_id="snapshot-ghi",
    business_hint="Nhà hàng Việt Nam",
    context=[{
        "company_id": "tenant-123",
        "brand_id": "brand-456",
        "source_id": "menu-2026-04",
        "document_id": "doc-789",
        "source_version": "3",
        "source_hash": "sha256:...",
        "locator": "page=2;table=1[row=3]",
        "text": "Cơm gà | 65.000 đồng",
    }],
)
payload = result.to_payload()  # pass this shape to M2 persistence
```

Do not pass an additional repair callback for this adapter. It validates before
returning and owns the single repair opportunity. Content uses the same model
factory through `ContentAgent(model)` and `GeneratedPost` response validation.

Runtime settings are `DEEPSEEK_API_KEY`, `LLM_DEFAULT_MODEL`, optional
`DEEPSEEK_BASE_URL` (defaults to `https://api.deepseek.com`),
`DEEPSEEK_MAX_TOKENS` (defaults to 8192), `AI_REQUEST_TIMEOUT_SECONDS`
(defaults to 60), and `LLM_MAX_INPUT_CHARS` (defaults to 24,000). There is no
OpenAI key requirement for Brand/Content text generation. Current DeepSeek
Chat Completions docs list `deepseek-flash` and `deepseek-v4-pro`; check the
account's available IDs using `GET /models` before configuring a deployment.
The direct M3 factory accepts `DEEPSEEK_MODEL` as an alias for
`LLM_DEFAULT_MODEL`; if both are set, they must match. M2's provider selector
uses `LLM_DEFAULT_MODEL`.
The configured ID is sent on every request; response metadata records the
provider as `deepseek` and uses the returned model ID when the API supplies it.

## Input and output example

These are illustrative examples, not output from a live DeepSeek run.

```json
{
  "company_id": "tenant-123",
  "brand_id": "brand-456",
  "document_ids": ["doc-789"],
  "job_id": "job-abc",
  "run_id": "run-def",
  "input_snapshot_id": "snapshot-ghi",
  "business_hint": "Nhà hàng Việt Nam",
  "context": [{
    "source_id": "menu-2026-04",
    "document_id": "doc-789",
    "source_version": "3",
    "source_hash": "sha256:...",
    "locator": "page=2;table=1[row=3]",
    "text": "Quán Bếp Mộc | Cơm gà | 65.000 đồng"
  }]
}
```

One valid structured `BrandProfile` response shape for that source is:

```json
{
  "brand_id": "brand-456",
  "business": "Quán Bếp Mộc",
  "products": ["Cơm gà"],
  "audience": [],
  "voice": [],
  "constraints": [],
  "facts": [{
    "key": "business",
    "value": "Quán Bếp Mộc",
    "status": "confirmed",
    "evidence": [{
      "source_id": "menu-2026-04",
      "document_id": "doc-789",
      "source_version": "3",
      "locator": "page=2;table=1[row=3]",
      "excerpt": "Quán Bếp Mộc"
    }]
  }, {
    "key": "product_price",
    "value": "Cơm gà | 65.000 đồng",
    "status": "confirmed",
    "evidence": [{
      "source_id": "menu-2026-04",
      "document_id": "doc-789",
      "source_version": "3",
      "locator": "page=2;table=1[row=3]",
      "excerpt": "Cơm gà | 65.000 đồng"
    }]
  }],
  "unknowns": ["Chưa có nguồn xác nhận audience hoặc brand voice."],
  "contradictions": [],
  "requires_confirmation": true,
  "profile_version": "draft"
}
```

The returned payload contains a draft `profile`, exact `source_references`,
`missing_information`, `contradictions`, IDs, repair count, and generation
metadata. The draft always has `requires_confirmation=true`. M2 owns allocating
IDs, transactions, status updates, and persistence; do not publish or confirm
the generated profile automatically.

## Normalized provider errors

| Provider condition | Exception / Brand result code | Job retry guidance |
| --- | --- | --- |
| Missing key/model or invalid adapter settings | `ProviderConfigurationError` / `provider_not_configured` | No |
| 401/403 authentication failure | `ProviderAuthenticationError` / `provider_authentication_failed` | No; fix secret |
| 404 unknown/unavailable model ID | `ProviderModelNotFoundError` / `provider_model_not_found` | No; fix model/account configuration |
| 429 rate limit | `ProviderRateLimitError` / `provider_rate_limited` | Retryable; M2 applies backoff |
| Timeout | `ProviderTimeoutError` / `provider_timeout` | Retryable by M2 |
| 402 insufficient account balance | `ProviderRequestError`, `retryable=False` | No; account action required |
| 408/5xx transport/provider response | `ProviderRequestError`, `retryable=True` | Retryable by M2 |
| Other 4xx/provider request failure | `ProviderRequestError`, `retryable=False` | Fix request/configuration |
| Empty, truncated, malformed JSON, or schema mismatch after one repair | `ProviderOutputError` / `invalid_structured_output` | No automatic job retry by default |
| Citation outside the retrieved source/version/locator/text | `InvalidSourceReferenceError` / `invalid_source_reference` | No; do not persist as grounded |
| Input exceeds configured bound | `ProviderContextLimitError` / `context_limit_exceeded` | No; reduce/re-chunk context |

Exceptions contain safe messages, not raw provider responses or secrets. The
Brand handler depends on the shared `ProviderError` hierarchy, not an OpenAI
exception. `repair_attempts` includes the adapter's one JSON/schema repair.

## Source metadata, relevance, and persistence requirements for M2

Before calling the handler, M2 must authorize the tenant and brand, restrict
retrieval to active, non-deleted sources allowed for that brand, and return
stable `source_id`, `document_id`, `source_version`, `source_hash`, `locator`,
and exact `text` for each context item. The handler cross-checks cited source,
document/version, locator, and excerpt. It removes top-level claims without
grounded evidence and retains contradictions only with evidence from at least
two source locations.

Retrieval relevance must be measured and filtered before generation. The
lexical-only default admits content-term overlap at `score >= 0.12`. With
embeddings, a chunk can pass through lexical rescue at `0.45`; semantic
retrieval requires a best source score of at least `0.82` and a `0.04` gap over
the next source; with only one source, its score must be at least `0.86`. These
are conservative pilot thresholds, not calibrated confidence probabilities.
`scripts/evaluate_retrieval.py` runs a small local E5 positive/no-answer check;
evaluate with approved SME queries before pilot acceptance. Include only
bounded top-k results. Do not report an LLM-generated score as retrieval
relevance.

The M3 `PersistentKnowledgeRepository` interface expects M2 persistence to
deduplicate using source content hash plus parser, chunker, and embedding model
versions, and to store the locator and source/version metadata with each chunk.
It allows `embedder=None` for explicit lexical mode, which must be keyed with
`embedding_model_version="lexical-v1"` and must not be represented as a vector
embedding.
M2 owns the repository implementation and must persist the draft profile,
source references, job/run/snapshot IDs, model/provider, prompt/schema versions,
token counts, latency, repair count, and retry/error semantics in its normal
transaction. Serialize via `result.to_payload()` when using the backend-facing
Brand handler envelope. Existing Python
`GenerationMetadata` requires a numeric `estimated_cost_usd`; DeepSeek sets an
internal compatibility sentinel of `0.0` with `estimated_cost_available=false`,
and `to_payload()` converts that value to JSON `null`. M2 must persist/display
the serialized null and availability flag, never interpret the internal zero
sentinel as free or as a measured cost. DeepSeek token pricing has not been
verified for this integration, so cost is unavailable.

The current M2 `AiTaskResult` shape returns `GenerationMetadata` but does not
carry an `estimated_cost_available` flag. If M2 keeps that path, include the
flag in its task/persistence envelope or serialize cost as null before storing;
otherwise use the Brand handler envelope above. Do not validate the null cost
back into the existing non-nullable `GenerationMetadata` model without a
coordinated M2 contract update.

## Embeddings and retrieval limits

The `EmbeddingProvider` interface remains independent of the chat model.
DeepSeek chat is not assumed to provide compatible embeddings. M2 can supply a
local embedding implementation or a separately selected embedding provider;
persist its name/version and vector dimensions independently from the
DeepSeek model. `InMemoryKnowledgeIndex` with no embedder uses lexical overlap
only. That is a lexical retrieval pilot, not complete vector RAG or durable
retrieval. Full vector RAG requires M2's persistent vector index and an
explicitly configured embedder.

## CI and live smoke status

`tests/test_deepseek_provider.py` uses fake transport responses; it verifies
JSON-mode request fields, schema instructions, Pydantic validation, a maximum
of one repair, and normalized timeout/auth/rate-limit/output errors. No live
result is claimed by those tests. This environment currently has no
`DEEPSEEK_API_KEY` or `DEEPSEEK_MODEL`, so an authenticated Brand Agent run,
real latency, and real token usage are unavailable until M2 configures the
server secret/model. Report cost as unavailable unless an authoritative price
table is verified for the exact model and date.
