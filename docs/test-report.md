# Báo cáo kiểm thử

Cập nhật: 2026-09-24 00:21 (Asia/Ho_Chi_Minh). REC-002 implementation `72ad60a` và real-mode E2E `bba034e` trên branch `codex/product-v1-completion`, base `origin/main` tại `07938bd`. Real-mode analytics smoke lịch sử chạy trên backend source `628efcb`; publishing route fix `c77720d` và contract-test adjustment `73ff4f7` là các commits trước đó.

Môi trường: Python 3.11.16, Node.js 26.7.0, SQLite tạm, Chromium desktop/mobile. Bộ Playwright tự động dùng Next.js local và MSW; ngoài ra có một browser smoke thủ công qua Codex browser với Next.js + FastAPI real mode và DB SQLite hoàn toàn mới.

## Đã chạy

| Check | Kết quả | Giới hạn |
|---|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider` | **82 passed, 1 skipped** | Skip là `tests/test_deepseek_api_smoke.py`; fake-provider tests không phát sinh request thật. REC-002 test cover accepted revision, metric cohorts, evidence/snapshot IDs, idempotency/readback, sai source/window và draft pending. |
| `.venv/bin/python scripts/export_openapi.py --check` | PASS | OpenAPI khớp generated contract sau khi thêm outcome API. |
| `PYTHONPYCACHEPREFIX=/private/tmp/... .venv/bin/python -m compileall -q database services packages` | PASS | Kiểm tra cú pháp Python, bytecode được ghi ra cache tạm riêng. |
| SQLite `alembic upgrade head` trên DB tạm mới | PASS | Đã áp dụng liên tiếp migration 0001→0007; không đại diện cho PostgreSQL/pgvector. |
| `npm run gen:api -- --from ../../packages/contracts/openapi.json` | PASS | Generated TypeScript HTTP DTOs từ backend OpenAPI. |
| `npm run typecheck -- --incremental false` (trong `apps/web`, commit `72ad60a`) | PASS | TypeScript không phát hiện lỗi. |
| `npm test` (trong `apps/web`, commit `72ad60a`) | **41 passed** | 2 test files. |
| `npm run lint` (trong `apps/web`, commit `72ad60a`) | PASS | ESLint hoàn tất. |
| `npm run build` (trong `apps/web`, commit `72ad60a`) | PASS | Production build tạo route analytics với outcome tracker và publishing route. |
| `npm run test:e2e` (trong `apps/web`) | **32 passed** | Desktop + mobile Chromium; gồm nhập snapshot/dashboard và recommendation feedback/apply/owner review qua MSW fixtures, không phải real API. |
| `npm run test:e2e -- --grep 'ghi feedback và áp dụng recommendation'` | **2 passed** | Desktop + mobile Chromium; accept brief revision, ghi outcome và kiểm tra limitations bằng MSW demo response; không phải số liệu thật. |
| `E2E_REAL_API_BASE_URL=http://127.0.0.1:8000 npm run test:e2e:real -- --grep 'campaign → manual post'` | **1 passed** | Chromium real mode: test tự đăng ký owner vào API loopback, tạo campaign, viết bài thủ công, duyệt v1, tạo export và tải XLSX. API chạy trên SQLite vừa migrate 0001→0007, storage ở `/private/tmp`; không dùng MSW, PostgreSQL, DeepSeek hay Meta. |
| Real-mode browser smoke trên API thật | **PASS — analytics/recommendation và manual-publish fallback** | Analytics/recommendation smoke chạy trên code `628efcb`: DB SQLite riêng trong `/private/tmp`, account test qua API, 1 campaign + 10 bài + 10 metric points giả lập; UI login, dashboard, save recommendation, feedback, Apply và owner accept; API xác nhận `version=2` và brief được cập nhật. Sau đó production build `c77720d` xác nhận route publishing nêu rõ Meta chưa kết nối và hướng dẫn thủ công. Không dùng MSW, PostgreSQL, DeepSeek hay Meta. Smoke thủ công, chưa phải test tự động tái chạy. |
| `npm ls postcss --all` | PASS | PostCSS 8.5.24 và 8.5.28 có trong dependency tree. |
| `npm audit --audit-level=high` | PASS | Registry hiện trả 0 vulnerabilities. |
| `git diff --check` | PASS | Kiểm tra working diff; vendored skills giữ nguyên line endings/hard breaks từ upstream commit nền. |

## Chưa nghiệm thu

- PostgreSQL migration/integration: PostgreSQL local chấp nhận kết nối, nhưng chưa xác nhận DB riêng an toàn; không ghi vào DB chưa xác minh.
- Docker Compose, worker/scheduler restart, MinIO/S3: Docker/Podman và MinIO không sẵn có.
- DeepSeek live: không có `DEEPSEEK_API_KEY`; live smoke đã skip. Chưa đo latency/token/chi phí.
- Meta publish/metrics: chưa có app/page/token/quyền/App Review.
- Real-mode browser E2E đầy đủ: analytics/recommendation và manual campaign → post → approval → export đã qua browser/API thật trên SQLite. Upload-driven Brand Profile extraction và AI content generation chưa đi qua browser vì đang fail-closed theo AI-001; PostgreSQL/MinIO cũng chưa nghiệm thu.

## Phạm vi bằng chứng

Campaign, manual post/version, approval và CSV/XLSX export có API tests SQLite và một real-mode browser flow riêng; không đại diện cho PostgreSQL hoặc triển khai production. Manual metrics, recommendation feedback, Apply draft, accept/version conflict và REC-002 outcome persistence được kiểm tra bằng SQLite API tests; UI outcome flow có MSW E2E và không tạo bằng chứng về hiệu suất thật. Real-mode smoke cũ xác minh analytics/recommendation; test mới xác minh manual campaign → post → approval → export/download. Test tenant isolation/version conflict không phải full security audit. Upload-driven profile extraction worker fail-closed trước khi khởi tạo provider; generation route trả `503 provider_approval_required`, nên không test nào gửi brand/document content tới DeepSeek.

## Lệnh tái kiểm tra

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/python -m compileall -q database services packages
(cd apps/web && npm run typecheck && npm test && npm run lint && npm run build)
npm audit --audit-level=high
```

Chỉ chạy live DeepSeek, real browser E2E, PostgreSQL migration hoặc Meta checks sau khi secret/service riêng được provision và data flow cần thiết đã được cho phép. Không ghi secrets vào repo hoặc test report.
