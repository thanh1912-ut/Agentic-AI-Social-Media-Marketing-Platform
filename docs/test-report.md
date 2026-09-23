# Báo cáo kiểm thử

Cập nhật: 2026-09-23 23:37 (Asia/Ho_Chi_Minh). Backend regression source là commit `628efcb`; frontend route fix là `c77720d`; contract-test adjustment là `73ff4f7` trên branch `codex/product-v1-completion`, base `origin/main` tại `07938bd`. Docs được bổ sung sau các commit code.

Môi trường: Python 3.11.16, Node.js 26.7.0, SQLite tạm, Chromium desktop/mobile. Bộ Playwright tự động dùng Next.js local và MSW; ngoài ra có một browser smoke thủ công qua Codex browser với Next.js + FastAPI real mode và DB SQLite hoàn toàn mới.

## Đã chạy

| Check | Kết quả | Giới hạn |
|---|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider` | **82 passed, 1 skipped** | Skip là `tests/test_deepseek_api_smoke.py`; fake-provider tests không phát sinh request thật. Có worker guard, metrics import/report/tenant tests và recommendation save/feedback/apply/revision conflict. LangGraph phát một deprecation warning. |
| `.venv/bin/python scripts/export_openapi.py --check` | PASS | OpenAPI khớp generated contract. |
| `.venv/bin/python -m compileall -q database services packages` | PASS | Kiểm tra cú pháp Python. |
| SQLite `alembic upgrade head` trên DB tạm mới | PASS | Đã áp dụng liên tiếp migration 0001→0006; không đại diện cho PostgreSQL/pgvector. |
| `npm run gen:api -- --from ../../packages/contracts/openapi.json` | PASS | Generated TypeScript HTTP DTOs từ backend OpenAPI. |
| `node_modules/.bin/tsc --noEmit --incremental false` (trong `apps/web`, trên code `c77720d` + test `73ff4f7`) | PASS | TypeScript không phát hiện lỗi; tắt incremental để tránh ghi cache ra ngoài sandbox. |
| `npm test` (trong `apps/web`, trên code `c77720d` + test `73ff4f7`) | **41 passed** | 2 test files; static publishing page được phân loại là trang thông tin, vẫn có contract assertion để nói rõ trạng thái Meta. |
| `npm run lint` (trong `apps/web`, trên code `c77720d` + test `73ff4f7`) | PASS | ESLint hoàn tất. |
| `npm run build` (trong `apps/web`, trên code `c77720d`) | PASS | Production build tạo route `/w/[workspaceId]/publishing`; `next start` in cảnh báo cấu hình standalone nhưng page được phục vụ và kiểm tra trong browser. |
| `npm run test:e2e` (trong `apps/web`) | **32 passed** | Desktop + mobile Chromium; gồm nhập snapshot/dashboard và recommendation feedback/apply/owner review qua MSW fixtures, không phải real API. |
| Real-mode browser smoke trên API thật | **PASS — analytics/recommendation và manual-publish fallback** | Analytics/recommendation smoke chạy trên code `628efcb`: DB SQLite riêng trong `/private/tmp`, account test qua API, 1 campaign + 10 bài + 10 metric points giả lập; UI login, dashboard, save recommendation, feedback, Apply và owner accept; API xác nhận `version=2` và brief được cập nhật. Sau đó production build `c77720d` xác nhận route publishing nêu rõ Meta chưa kết nối và hướng dẫn thủ công. Không dùng MSW, PostgreSQL, DeepSeek hay Meta. Smoke thủ công, chưa phải test tự động tái chạy. |
| `npm ls postcss --all` | PASS | PostCSS 8.5.24 và 8.5.28 có trong dependency tree. |
| `npm audit --audit-level=high` | PASS | Registry hiện trả 0 vulnerabilities. |
| `git diff --check` | PASS | Kiểm tra working diff; vendored skills giữ nguyên line endings/hard breaks từ upstream commit nền. |

## Chưa nghiệm thu

- PostgreSQL migration/integration: PostgreSQL local chấp nhận kết nối, nhưng chưa xác nhận DB riêng an toàn; không ghi vào DB chưa xác minh.
- Docker Compose, worker/scheduler restart, MinIO/S3: Docker/Podman và MinIO không sẵn có.
- DeepSeek live: không có `DEEPSEEK_API_KEY`; live smoke đã skip. Chưa đo latency/token/chi phí.
- Meta publish/metrics: chưa có app/page/token/quyền/App Review.
- Real-mode browser E2E đầy đủ: đã xác minh login và analytics/recommendation trên SQLite thật; brand extraction, AI content, exact-version approval và export chưa đi qua browser real mode. Content bị khóa bởi AI-001.

## Phạm vi bằng chứng

Campaign, manual post/version, approval và CSV/XLSX export được kiểm tra qua API tests dùng SQLite/fixtures; không đại diện cho PostgreSQL hoặc triển khai production. Manual metrics, recommendation feedback, Apply draft và accept/version conflict được kiểm tra bằng SQLite API tests; UI flow có cả MSW E2E và một real-mode smoke đi qua FastAPI thật. Smoke không chứng minh nguồn metrics Meta hoặc PostgreSQL/production. Test tenant isolation/version conflict không phải full security audit. Upload-driven profile extraction worker fail-closed trước khi khởi tạo provider; generation route trả `503 provider_approval_required`, nên không test nào gửi brand/document content tới DeepSeek.

## Lệnh tái kiểm tra

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/python -m compileall -q database services packages
(cd apps/web && npm run typecheck && npm test && npm run lint && npm run build)
npm audit --audit-level=high
```

Chỉ chạy live DeepSeek, real browser E2E, PostgreSQL migration hoặc Meta checks sau khi secret/service riêng được provision và data flow cần thiết đã được cho phép. Không ghi secrets vào repo hoặc test report.
