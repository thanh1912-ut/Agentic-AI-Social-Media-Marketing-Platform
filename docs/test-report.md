# Báo cáo kiểm thử

Cập nhật: 2026-09-23, Asia/Ho_Chi_Minh. Source được kiểm thử là commit `628efcb` trên branch `codex/product-v1-completion`, base `origin/main` tại `07938bd`.

Môi trường: Python 3.11.16, Node.js 26.7.0, SQLite tạm, Chromium desktop/mobile qua Playwright. Frontend E2E dùng Next.js local và MSW; không kết nối API/DB thật.

## Đã chạy

| Check | Kết quả | Giới hạn |
|---|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider` | **82 passed, 1 skipped** | Skip là `tests/test_deepseek_api_smoke.py`; fake-provider tests không phát sinh request thật. Có worker guard, metrics import/report/tenant tests và recommendation save/feedback/apply/revision conflict. LangGraph phát một deprecation warning. |
| `.venv/bin/python scripts/export_openapi.py --check` | PASS | OpenAPI khớp generated contract. |
| `.venv/bin/python -m compileall -q database services packages` | PASS | Kiểm tra cú pháp Python. |
| SQLite `alembic upgrade head` trên DB tạm mới | PASS | Đã áp dụng liên tiếp migration 0001→0006; không đại diện cho PostgreSQL/pgvector. |
| `npm run gen:api -- --from ../../packages/contracts/openapi.json` | PASS | Generated TypeScript HTTP DTOs từ backend OpenAPI. |
| `npm run typecheck` (trong `apps/web`) | PASS | TypeScript không phát hiện lỗi. |
| `npm test` (trong `apps/web`) | **41 passed** | 2 test files. |
| `npm run lint` (trong `apps/web`) | PASS | ESLint hoàn tất; Vite in cảnh báo cấu hình loader không ảnh hưởng kết quả. |
| `npm run build` (trong `apps/web`) | PASS | Optimized production build; analytics route được tạo; Next cảnh báo `next start` không hỗ trợ standalone output, nhưng Playwright server vẫn chạy được. |
| `npm run test:e2e` (trong `apps/web`) | **32 passed** | Desktop + mobile Chromium; gồm nhập snapshot/dashboard và recommendation feedback/apply/owner review qua MSW fixtures, không phải real API. |
| `npm ls postcss --all` | PASS | PostCSS 8.5.24 và 8.5.28 có trong dependency tree. |
| `npm audit --audit-level=high` | PASS | Registry hiện trả 0 vulnerabilities. |
| `git diff --check` | PASS | Kiểm tra working diff; vendored skills giữ nguyên line endings/hard breaks từ upstream commit nền. |

## Chưa nghiệm thu

- PostgreSQL migration/integration: PostgreSQL local chấp nhận kết nối, nhưng chưa xác nhận DB riêng an toàn; không ghi vào DB chưa xác minh.
- Docker Compose, worker/scheduler restart, MinIO/S3: Docker/Podman và MinIO không sẵn có.
- DeepSeek live: không có `DEEPSEEK_API_KEY`; live smoke đã skip. Chưa đo latency/token/chi phí.
- Meta publish/metrics: chưa có app/page/token/quyền/App Review.
- Real API E2E: chưa có test account/API origin; demo E2E chỉ dùng mock data.

## Phạm vi bằng chứng

Campaign, manual post/version, approval và CSV/XLSX export được kiểm tra qua API tests dùng SQLite/fixtures; không đại diện cho PostgreSQL hoặc triển khai production. Manual metrics, recommendation feedback, Apply draft và accept/version conflict được kiểm tra bằng SQLite API tests; UI flow được kiểm tra riêng bằng MSW E2E. Browser tests không chứng minh nguồn metrics Meta hoặc real API. Test tenant isolation/version conflict không phải full security audit. Upload-driven profile extraction worker fail-closed trước khi khởi tạo provider; generation route trả `503 provider_approval_required`, nên không test nào gửi brand/document content tới DeepSeek.

## Lệnh tái kiểm tra

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/python -m compileall -q database services packages
(cd apps/web && npm run typecheck && npm test && npm run lint && npm run build)
npm audit --audit-level=high
```

Chỉ chạy live DeepSeek, real browser E2E, PostgreSQL migration hoặc Meta checks sau khi secret/service riêng được provision và data flow cần thiết đã được cho phép. Không ghi secrets vào repo hoặc test report.
