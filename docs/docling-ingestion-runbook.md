# Docling ingestion runbook

## Supported files and limits

The Documents area accepts PDF with a text layer, DOCX, XLSX, CSV and TXT. Image files are rejected. OCR is disabled; image-only scanned PDFs return `pdf_no_text_layer`. Current processing limits are 25 MiB per file, 10 files per request, 20,000,000 normalized characters, 100,000 table rows, 256 columns per table, 1,000,000 cells, 200 PDF pages, and 600 seconds per file.

## Docling worker setup

Docling 2.130.0 is an optional `docling` extra used by the dedicated ingestion worker. Set `DOCLING_ARTIFACTS_PATH` to a persistent, read-only-at-runtime model directory. Download and verify only layout and table models once with:

```sh
python scripts/download_docling_models.py --output /absolute/path/docling-models
python scripts/download_docling_models.py --output /absolute/path/docling-models --verify-only
```

The setup step writes a SHA-256 manifest. It disables OCR, picture models, VLM and remote services. Jobs run offline and must not download models.

## Compose operations

Build the application and dedicated worker using the project Compose files. Run the `docling-model-setup` service with the `docling-models` profile before starting `worker-ingestion`. The dedicated worker consumes only the `ingestion` queue with concurrency 1; the normal worker continues consuming `default,agent`.

Stop only the `worker-ingestion` process started for this checkout when doing maintenance. Do not stop a shared PostgreSQL, Redis or preview process. For retries, use the document's “Đọc lại tài liệu” action. If extraction and knowledge are ready but Brand Profile failed, use “Thử lại Brand Profile” so Docling does not run again.

## Troubleshooting

- `parser_model_unavailable`: verify the model directory and checksums; do not enable runtime downloads.
- `parser_timeout`: reduce the file size or split the source document; the worker kills the converter process at the configured deadline.
- `parser_limit_exceeded`: check the named page, row, column, cell or character limit.
- `pdf_no_text_layer`: provide a PDF with selectable text; OCR is intentionally off.
- `ai_not_configured`: extraction and saved knowledge remain available; configure the selected server-side AI provider and retry the profile step only.
- CSV row/delimiter errors: export UTF-8 CSV and preserve quoting; delimiter sniffing supports comma, semicolon, tab and pipe.

Do not put source files, extracted content, API keys, tokens, passwords or database DSNs into Git or logs.


## Current local test preview (2026-09-29)

Worktree: `/Users/lethanh/.codex/worktrees/docling-ingestion/agent`.
Frontend: `http://127.0.0.1:13102`; API: `http://127.0.0.1:18102`.
Use the existing test login; no account password is stored in this document.
PostgreSQL uses port 16435, Redis queue 16383 and Redis cache 16384.
These differ from other previews and the machine's default services.

The current virtualenv is `/private/tmp/docling-ingestion-venv`, model directory
`/private/tmp/docling-models`, and shared API/worker storage
`/private/tmp/docling-ingestion-storage`. These are temporary test paths: migrate
artifacts and data to persistent storage before treating this as a deployment.
Do not delete them while the preview uses them.

All processes must receive the same database, queue and storage configuration.
Set `AUTO_CREATE_SCHEMA=0`, `INLINE_JOBS=0`, `STORAGE_BACKEND=local` and an absolute
`STORAGE_ROOT`. Run Alembic before starting the API. The current local test has
`RATE_LIMITS_ENABLED=0`; do not copy this into a public deployment.

The dedicated DeepSeek secret file is
`/Users/lethanh/.local/share/agentic-marketing/secrets/deepseek-docling.env`, mode
0600. Its allowed settings are `LLM_PROVIDER`, `DEEPSEEK_API_KEY`,
`DEEPSEEK_BASE_URL`, and `LLM_DEFAULT_MODEL`. Read it as data and load only those
keys into API/worker environments; do not shell-source it, print it, put it in
frontend variables or commit it. The application does not automatically load
this file. Restart the relevant processes after updating configuration.
Keep the configured model; the live test confirmed it using GET `/models`.

Worker settings for the verified local path:

```text
DOCLING_ARTIFACTS_PATH=/private/tmp/docling-models
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
EMBEDDING_PROVIDER=none
RETRIEVAL_MODE=lexical
```

After loading the local configuration without exposing secrets, use:

```sh
/private/tmp/docling-ingestion-venv/bin/python -m uvicorn services.api.main:app --host 127.0.0.1 --port 18102
/private/tmp/docling-ingestion-venv/bin/celery -A services.worker.celery_app:celery_app worker --loglevel=INFO --queues=ingestion --concurrency=1 --pool=solo
```

Run the frontend from `apps/web` with `NEXT_PUBLIC_USE_MOCKS=0`,
`NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:18102` (no `/api/v1`),
and `npm run dev -- --port 13102`. API CORS and `WEB_BASE_URL` must use the same
127.0.0.1 host and frontend port. Only the ingestion worker was started in this
round. Campaign/research jobs need the `agent` queue; Meta jobs and scheduler
recovery need `default` plus Beat. Do not start recovery blindly against the
integration-test database: synthetic fault-test jobs may remain there.

Stop each process through Ctrl-C in its owning terminal, or verify its PID,
command, port and working directory before sending TERM. Do not use broad
`pkill`, flush Redis, stop default database services, or rebuild the active
frontend's `.next` output underneath its development process.

## Interpreting the AI result

Reading a file, making knowledge available, and producing a Brand Profile are
separate stages. An AI error does not mean Docling failed. If extraction and
knowledge are ready, use profile-only retry; do not upload the document again.
Each profile retry can make a billable provider request. The completed smoke
test used one generation request and should not be retried merely to reproduce
its screenshot. Review missing fields and citations before confirming the
profile; the test left revision 2 unconfirmed.

Rollback changes requires the normal ingestion code/worker to match its queue
routing. Preserve the original files, normalized artifacts and prior profile
revisions; do not delete history to roll back a parser or UI change. A full
rollback/reprocess acceptance drill has not yet been run.
