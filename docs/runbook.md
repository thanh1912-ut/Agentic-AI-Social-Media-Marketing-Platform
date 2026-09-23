# Runbook phát triển và pilot

> Hướng dẫn này phản ánh cấu hình hiện có và sẽ được cập nhật sau khi các lệnh được chạy thật. Không dùng ví dụ local cho production. Không ghi secrets vào Git, log hay tài liệu.

## Runtime yêu cầu

- Python 3.11+ theo `pyproject.toml`.
- Node.js >=22 và npm, theo root package manifests/lockfile.
- Docker Compose v2 cho stack đầy đủ; PostgreSQL có extension pgvector, Redis, MinIO.
- DeepSeek API key server-side để chạy LLM thật. Chủ dự án đã chấp thuận gửi đoạn trích tài liệu và Brand Profile tới DeepSeek.
- Embedding bên ngoài là data flow riêng; `EMBEDDING_DATA_FLOW_APPROVED=0` mặc định chặn cấu hình provider embedding ngoài. Giữ `EMBEDDING_PROVIDER=none` và lexical mode cho tới khi có chấp thuận riêng.
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

Sửa `.env` cục bộ trong editor, không paste key vào chat. Provision `DEEPSEEK_API_KEY` trong môi trường server/secret store; không commit `.env`. Đặt `LLM_PROVIDER=deepseek`, `LLM_DEFAULT_MODEL` thành model ID được DeepSeek API list cho tài khoản, `DEEPSEEK_MAX_TOKENS=8192`, `LLM_MAX_INPUT_CHARS=24000` và `AI_REQUEST_TIMEOUT_SECONDS=120`. Không cần `OPENAI_API_KEY` cho LLM. Brand Profile extraction, content-generation và AI-revise workers gọi cùng adapter DeepSeek sau khi nhận job; thiếu key sẽ khiến job kết thúc với lỗi `ai_not_configured`. API generate/revise trả `202` + `job_id`; Brand Profile hiện tại phải được user xác nhận trước. Revise yêu cầu `version` hiện tại và `Idempotency-Key`, tạo PostVersion mới (`ai_revised`), không ghi đè lịch sử; scope `media` chỉ sửa mô tả ảnh, không tạo/thay ảnh. Bài vẫn cần người duyệt; worker không tự publish. Job content có thể retry qua `/api/v1/jobs/{job_id}/retry` trong giới hạn cấu hình; worker kiểm lại base version trước khi lưu. Để retrieval lexical, giữ `EMBEDDING_PROVIDER=none` và `RETRIEVAL_MODE=lexical`.

`.env.example` để `RATE_LIMITS_ENABLED=0` cho local development. Production phải đặt `APP_ENV=production`, `RATE_LIMITS_ENABLED=1`, `COOKIE_SECURE=1` và một `REDIS_URL` khả dụng; cấu hình production từ chối limiter bị tắt. Auth, upload và content-generation routes dùng fixed-window Redis limits; production trả `503` cho các route này khi Redis không dùng được. Các mức hiện tại được ghi trong [security-review.md](security-review.md). Limit key dựa trên `request.client.host`: sau reverse proxy, cấu hình Uvicorn chỉ tin forwarded headers từ proxy thực tế và xác nhận API không truy cập trực tiếp từ nguồn không tin cậy. Không lấy `X-Forwarded-For` tùy ý làm client identity.

## Khởi động full stack

```bash
docker compose up --build
```

Compose chạy PostgreSQL/pgvector, Redis, MinIO, migration, storage init, API, worker và scheduler. API phụ thuộc Redis health; rate limits ở production fail-closed nếu Redis mất kết nối sau startup. Chờ health checks xong rồi xác nhận:

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

Cookie-authenticated refresh/logout yêu cầu header `X-CSRF-Token` khớp cookie `agentic_csrf`; web client gửi token khi refresh session. Bearer-only clients không cần CSRF token nếu không gửi kèm session cookies.

## Mocks và real mode

- Demo UI: `NEXT_PUBLIC_USE_MOCKS=1`; dữ liệu do MSW cung cấp, không phải API evidence.
- Real mode: `NEXT_PUBLIC_USE_MOCKS=0`; UI gọi API, hiển thị lỗi khi backend lỗi, không dùng dữ liệu mock thay thế.
- Campaign supports tenant-scoped create/list/detail, manual post creation/edit with immutable versions, approval decisions tied to the exact version, and CSV/XLSX export. Exported content still needs a human to publish it on Meta.
- Analytics supports manual snapshots: choose a source ID and measurement timestamp, add one or more workspace posts, and enter age-at-measurement plus available metrics. Counts must be integers; cost/revenue may be decimal. Leave unavailable values blank. Duplicate `(workspace, post, source, measured_at)` snapshots return conflict. Only mark attribution valid when its method/window is verified.
- Dashboard uses latest per-post snapshots for the selected source and reports freshness, coverage, pillar/format groups and missing-value notes. Recommendations are deterministic test suggestions with evidence IDs; they abstain on small samples and do not establish causality. Save a proposal to persist its evidence fingerprint, then record useful/not useful/already done feedback. An owner can choose a campaign and Apply to create a pending brief revision; inspect before/after values, then accept or discard. Campaign changes only on accept; a stale base version returns `409` and needs a new revision.
- After an accepted revision has run, choose that campaign and the recommendation's same source on Analytics. Record baseline and follow-up measurement windows, one metric, and a shared post-age range. Windows must not overlap and both cohorts need usable snapshots. The API persists computed values, coverage/sample size, outcome-specific evidence IDs, snapshot IDs and limitations; repeated identical submissions are idempotent. The comparison is observational and must not be presented as causal proof. Apply migration 0007 before using this feature on an existing database.
- LLM fixture tests do not call DeepSeek. API+worker fixture integration verifies the confirmed-profile gate, idempotency, exact-source citations, saved draft/version, AI revise scope, expected-version guard, and reapproval. The live adapter smoke checks that the configured model appears in the account's model list, then makes one structured JSON request; it may incur charges. In a secured environment with the server key provisioned, run `RUN_DEEPSEEK_API_SMOKE=1 .venv/bin/python -m pytest -m api_smoke tests/test_deepseek_api_smoke.py -q`. The user-approved data flow is limited to Brand Profile and retrieved document excerpts; backend-only tenant/brand database IDs are not sent in the prompt.
- Real-mode smoke analytics/recommendation đã chạy trên API loopback với SQLite mới và dữ liệu giả lập. Thêm `tests/e2e/manual-workflows.real.spec.ts`: test tự tạo owner/campaign, viết bài thủ công, gửi và duyệt v1, tạo export rồi tải XLSX qua API thật; chạy với isolated SQLite migration 0001→0007 và local storage tạm, không gọi DeepSeek/Meta. Trang `Xuất bản` cũng được kiểm tra trên production build; khi Meta chưa kết nối, trang hướng dẫn export, đăng thủ công và nhập số liệu. Test account/database chỉ dùng trong môi trường tạm, không ghi vào repo. AI API+worker test dùng fake model; live DeepSeek/browser acceptance còn chờ secret và test runtime.

## Test, OpenAPI và build

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
PYTHONPYCACHEPREFIX=/tmp/agentic-pycache .venv/bin/python -m compileall -q database services packages
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
- Upload: tên file chỉ dùng làm metadata hiển thị và được lấy basename; storage key do server sinh, adapter từ chối key có traversal. Kiểm MIME/size/parser status; PDF scan/mật khẩu/unsupported phải báo trạng thái/hint thay vì tạo profile rỗng.
- DeepSeek: kiểm provider/model, key ở secret store, timeout/rate limit/balance. Không in key hoặc response nhạy cảm. No implicit provider fallback.
- Retrieval: kiểm active source, tenant/brand, parser/chunker/embed version, locator, relevance threshold. Lexical mode phải được gắn nhãn lexical.
- MinIO/S3: xác nhận health, bucket và credentials; database chứa metadata, object storage chứa binary.

## Rollback và giới hạn

Trước release, chụp backup DB/object metadata, ghi commit/branch và migration head. Nếu release lỗi, quay lại image/commit trước và thực hiện migration rollback chỉ khi migration có downgrade an toàn; không tự drop dữ liệu. Auto Facebook publish/sync vẫn bị khóa cho đến khi permission và duplicate-safe reconciliation được live kiểm chứng.
