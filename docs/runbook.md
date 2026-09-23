# Runbook phát triển và pilot

> Hướng dẫn này phản ánh cấu hình hiện có và sẽ được cập nhật sau khi các lệnh được chạy thật. Không dùng ví dụ local cho production. Không ghi secrets vào Git, log hay tài liệu.

## Runtime yêu cầu

- Python 3.11+ theo `pyproject.toml`.
- Node.js >=22 và npm, theo root package manifests/lockfile.
- Docker Compose v2 cho stack đầy đủ; PostgreSQL có extension pgvector, Redis, MinIO.
- DeepSeek API key server-side để chạy LLM thật. Embedding provider riêng chỉ cần khi bật semantic-vector mode.
- Facebook Page/app/token/App Review chỉ cần khi bật connector tương ứng.

## Cài local

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
npm ci
cp .env.example .env
```

Sửa `.env` cục bộ trong editor, không paste key vào chat. Đặt `DEEPSEEK_API_KEY` và `LLM_DEFAULT_MODEL=deepseek-flash` hoặc model ID được tài khoản API liệt kê. `LLM_PROVIDER=deepseek`; không cần `OPENAI_API_KEY` cho LLM. Upload-driven Brand Profile extraction và content generation đều đang fail-closed cho provider ngoài. Generation API trả `503 provider_approval_required`; worker không tự khởi tạo DeepSeek khi không được truyền fake agent trong test. Chỉ sau khi chủ dự án chấp thuận rõ việc gửi Brand Profile và đoạn tài liệu tới DeepSeek mới triển khai lại các lời gọi live; thêm API key một mình không mở luồng. Để lexical mode, giữ `EMBEDDING_PROVIDER=none` và `RETRIEVAL_MODE=lexical`.

## Khởi động full stack

```bash
docker compose up --build
```

Compose chạy PostgreSQL/pgvector, Redis, MinIO, migration, storage init, API, worker và scheduler. Chờ health checks xong rồi xác nhận:

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/readyz
```

Web chạy ở `http://127.0.0.1:3000`. Khi dùng browser real API, cấu hình `NEXT_PUBLIC_API_BASE_URL` là API origin, không thêm `/api/v1`; đặt `NEXT_PUBLIC_USE_MOCKS=0`. Không fallback sang MSW nếu API lỗi.

## Chạy process riêng khi không có Docker

Chỉ dùng database đã xác nhận là DB test/development, không trỏ vào production. Cấu hình `DATABASE_URL`, `REDIS_URL`, `STORAGE_BACKEND=local`, `STORAGE_ROOT`, `INLINE_JOBS=0` theo môi trường. Chạy migration, rồi các process:

```bash
alembic upgrade head
python -m services.api
celery -A services.worker.celery_app:celery_app worker --loglevel=INFO --queues=default,agent --concurrency=2
```

Scheduler entry point cần xác minh trong `services/worker/scheduled_jobs.py` trước khi dùng; chưa ghi lệnh scheduler như đã nghiệm thu.

## Tạo tài khoản và seed

API hiện có register/login và workspace bootstrap. Tạo user test riêng; không dùng tài khoản/DB production. Invitation hiện chưa có email provider; link trả về phải được chuyển cho người nhận qua kênh riêng. Không có seed credentials mặc định được nghiệm thu.

## Mocks và real mode

- Demo UI: `NEXT_PUBLIC_USE_MOCKS=1`; dữ liệu do MSW cung cấp, không phải API evidence.
- Real mode: `NEXT_PUBLIC_USE_MOCKS=0`; UI gọi API, hiển thị lỗi khi backend lỗi, không dùng dữ liệu mock thay thế.
- Campaign supports tenant-scoped create/list/detail, manual post creation/edit with immutable versions, approval decisions tied to the exact version, and CSV/XLSX export. Exported content still needs a human to publish it on Meta.
- Analytics supports manual snapshots: choose a source ID and measurement timestamp, add one or more workspace posts, and enter age-at-measurement plus available metrics. Counts must be integers; cost/revenue may be decimal. Leave unavailable values blank. Duplicate `(workspace, post, source, measured_at)` snapshots return conflict. Only mark attribution valid when its method/window is verified.
- Dashboard uses latest per-post snapshots for the selected source and reports freshness, coverage, pillar/format groups and missing-value notes. Recommendations are deterministic test suggestions with evidence IDs; they abstain on small samples and do not establish causality. Save a proposal to persist its evidence fingerprint, then record useful/not useful/already done feedback. An owner can choose a campaign and Apply to create a pending brief revision; inspect before/after values, then accept or discard. Campaign changes only on accept; a stale base version returns `409` and needs a new revision. Experiment outcome tracking after the two-week test is not implemented.
- LLM fixture tests do not call DeepSeek. Upload-driven extraction and content generation remain paused. The live adapter smoke uses `tests/test_deepseek_api_smoke.py` and may incur charges; only run it in a secured environment after data-flow approval.
- Real-mode smoke đã chạy trên API loopback với một SQLite DB mới và dữ liệu giả lập: login, analytics dashboard, save/feedback/apply recommendation và owner accept. Trang `Xuất bản` cũng được kiểm tra trên production build; khi Meta chưa kết nối, trang hướng dẫn export, đăng thủ công và nhập số liệu. Test account/database này chỉ dùng cho lần kiểm tra đó, không lưu trong repo. E2E đầy đủ cho Brand Profile, content, exact-version approval và export vẫn cần chạy trong môi trường test riêng; không đưa password/API key vào docs hoặc output.

## Test, OpenAPI và build

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/python -m compileall -q database services packages
(cd apps/web && npm run gen:api -- --from ../../packages/contracts/openapi.json)
(cd apps/web && npm run typecheck && npm test && npm run lint && npm run build)
(cd apps/web && npm run test:e2e)
```

Không chạy live smoke hoặc real E2E nếu credential chưa được provision. The build requires write access to `apps/web/.next`. Xem `docs/test-report.md` để tách fixture, integration, browser, live LLM và Meta results.

## Migration, backup và restore

Development/test migration:

```bash
alembic upgrade head
alembic current
```

Backup/restore cần thêm kiểm chứng với DB test trước khi dùng ở môi trường pilot. Quy trình dự kiến: `pg_dump -Fc` vào vị trí backup được bảo vệ; restore vào database mới; xác nhận schema revision, row counts/sample records và truy cập file storage trước khi cutover. Không chạy restore lên DB hiện hành.

## Job lỗi, token lỗi, provider lỗi

- Job: xem `/api/v1/jobs/{job_id}` và events; retry chỉ khi job `retryable` và operation idempotent. Không blind retry publication có `outcome_unknown`.
- Upload: kiểm filename/MIME/size/parser status; PDF scan/mật khẩu/unsupported phải báo trạng thái/hint thay vì tạo profile rỗng.
- DeepSeek: kiểm provider/model, key ở secret store, timeout/rate limit/balance. Không in key hoặc response nhạy cảm. No implicit provider fallback.
- Retrieval: kiểm active source, tenant/brand, parser/chunker/embed version, locator, relevance threshold. Lexical mode phải được gắn nhãn lexical.
- MinIO/S3: xác nhận health, bucket và credentials; database chứa metadata, object storage chứa binary.

## Rollback và giới hạn

Trước release, chụp backup DB/object metadata, ghi commit/branch và migration head. Nếu release lỗi, quay lại image/commit trước và thực hiện migration rollback chỉ khi migration có downgrade an toàn; không tự drop dữ liệu. Auto Facebook publish/sync vẫn bị khóa cho đến khi permission và duplicate-safe reconciliation được live kiểm chứng.
