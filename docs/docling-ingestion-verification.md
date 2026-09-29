# Docling ingestion verification

Recorded: 2026-09-29 14:20 Asia/Ho_Chi_Minh.

Test target: uncommitted working tree on `codex/docling-document-ingestion`,
base `aec998479d3d53c4743a662f61f5666a9835d242`. These are development acceptance
results, not verification of a pushed release.

## Environment

- Python 3.14.5, isolated virtualenv; Docling 2.130.0 and IBM models 4.0.3.
- Dedicated PostgreSQL at 127.0.0.1:16435; database `docling_ingestion_test`.
- Separate Redis queue/cache instances at 16383/16384.
- API 18102 and frontend 13102, real mode; inline jobs disabled.
- Ingestion worker: queue `ingestion`, solo pool, concurrency 1.
- Knowledge retrieval: lexical; no external embedding service enabled.
- Local file storage and offline model artifacts. S3/MinIO and Docker were not exercised.

## Results

| Area | Status | Evidence |
|---|---|---|
| Dependency resolution | PASS | Project and Docling installed in isolated environment; `pip check` passed. |
| PDF/DOCX/XLSX/CSV/TXT conversion fixtures | PASS | Real Docling conversion tests, including PDF text and scan rejection. PDF test requires `DOCLING_ARTIFACTS_PATH`; missing this variable caused one initial environment failure. |
| Full user CSV regression | PASS | 41,188 data rows × 21 columns, 44 batches, 864,969 cells including header; reconstructed checksum matches. Source data is not committed. |
| CSV direct conversion performance | PASS | 9.83 s; child peak RSS 514,932,736 bytes (~491 MiB). This is local measured performance, not an SLA. |
| Durable CSV ingestion | PASS | API → PostgreSQL job → Redis/Celery → Docling → PostgreSQL, measured 22.27 s. Job `e7b1fd3e` is only a recorded prefix, not a complete identifier. |
| Fresh PostgreSQL migration | PASS | Migration through 0020 and Alembic drift check passed. Upgrade from every historical schema was not re-exercised in this round. |
| Backend suite | PASS_WITH_TARGETED_RECHECK | Latest full configured run: 238 passed, 1 skipped, 1 failed in 93.65 s. Failure expected the old whole-job failure when AI was absent. After correcting the expectation, `tests/test_postgres_application_modules.py::test_postgres_api_persists_existing_product_modules` passed separately in 5.83 s. No single all-green full-suite rerun is claimed. |
| Frontend checks | PASS | Earlier checks on this task's frontend changes: lint, typecheck, 47 tests across four files. No frontend edits since those checks. |
| Contract / syntax checks | PASS | OpenAPI check, Python compile and Compose YAML parsing passed. Syntax checks are not a substitute for a Python linter. |
| Production frontend build | NOT_RUN | Must use a separate build directory/copy to preserve the active preview. |
| Browser upload of all five formats | NOT_RUN | File chooser automation failed for the live DOCX. Authenticated API upload was used instead; no end-to-end browser upload claim. |
| Browser result and reload | PASS | DOCX ready, knowledge ready, profile ready; saved Brand Profile draft still visible after reload. |
| Live DeepSeek | PASS | One generation request, successful structured profile, no repair; details below. |
| DeepSeek failure isolation | PASS | Successful extraction/knowledge remain ready when no provider is configured; profile reports unavailable separately. |
| Full Docling acceptance | PARTIAL | Remaining cases below prevent a claim of complete acceptance. |

## Live DeepSeek document analysis

User-authorized source: `MGAI - AI Agent.docx` (33,921 bytes). The file was
uploaded using the normal authenticated API and CSRF flow. It was not committed.

- Workspace: `b0b61bdd-559c-423c-b0d8-718cfada1bac`.
- Document: `96df94e2-daf7-42b0-a821-cdbc4e720134`.
- Durable job: `c1170aa0-ed25-4e09-ae6a-a1b065fef8d4`, succeeded.
- Celery delivery: `0fdc27fc-9dda-41dc-b1f9-956ae9b45b18`.
- 90 document chunks and 90 knowledge chunks persisted.
- Model: `deepseek-flash`; one POST generation request, zero repairs.
- Provider usage: 1,490 input tokens, 4,693 output tokens; latency 20,553 ms.
- No monetary cost calculated because unit pricing was not verified.
- Input snapshot: two eligible documents, but all three selected chunks were
  from this DOCX; zero CSV chunks were sent. The full CSV was not sent to AI.
- Brand Profile revision 2 remains unconfirmed. It contains two suggested
  fields (products and target audience) and seven missing fields. This is a
  persisted draft, not a complete or approved brand identity.
- Both suggestion excerpts match stored document/knowledge chunks and refer to
  the DOCX. Comparing against a concatenated extracted-content preview produced
  a representation mismatch; exact preview-display citation rendering has not
  been accepted. The browser source-toggle interaction was also inconclusive.

GET `/models` succeeded before generation and confirmed the configured model.
The generic opt-in live-provider pytest stayed skipped to avoid a second live
call. API key content, credentials and raw document output are excluded here.

## Remaining acceptance work

- Reproduce browser file selection/upload without concurrent user interaction,
  for each supported format; source-toggle display needs verification.
- Verify immediate converter cancellation on lease loss, not merely prevention
  of a stale worker commit after conversion completes.
- Verify failed reprocess preserves the previously active retrieval version,
  and update chunker version identity if table grouping changed.
- Expand literal TXT punctuation, XLSX typed/formula/merged-cell batch-boundary
  coverage and mixed PDF coverage checks.
- Finish production build, release diff/secret review, commit and remote SHA
  verification. Current runtime uses temporary paths and is not durable deployment.
- Facebook publishing, market crawling, campaign generation and their scheduler
  are outside this live document acceptance. Only the ingestion worker was
  started in this round; other queues/Beat must be checked before testing them.
