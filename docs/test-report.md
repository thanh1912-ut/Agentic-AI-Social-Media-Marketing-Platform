# Báo cáo kiểm thử

Cập nhật: 2026-09-24 02:40 (Asia/Ho_Chi_Minh). Bộ kiểm tra mới nhất chạy trên implementation commit `6f2f67c` của branch `codex/product-v1-completion`. Branch đã có security fixes `d9cb6a8`, `1e1589f`, rate limits `004020e` và DeepSeek integration. Project owner đã chấp thuận data flow đoạn trích tài liệu + Brand Profile tới DeepSeek. Real-mode analytics smoke lịch sử chạy trên backend source `628efcb`; publishing route fix `c77720d` và contract-test adjustment `73ff4f7` là các commits trước đó.

Môi trường: Python 3.11.16, Node.js 26.7.0, SQLite tạm, Chromium desktop/mobile. Bộ Playwright tự động dùng Next.js local và MSW; ngoài ra có một browser smoke thủ công qua Codex browser với Next.js + FastAPI real mode và DB SQLite hoàn toàn mới.

## Đã chạy

| Check | Kết quả | Giới hạn |
|---|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider` | **82 passed, 1 skipped** | Skip là `tests/test_deepseek_api_smoke.py`; fake-provider tests không phát sinh request thật. REC-002 test cover accepted revision, metric cohorts, evidence/snapshot IDs, idempotency/readback, sai source/window và draft pending. |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_storage_security.py tests/test_backend_foundation.py tests/test_brand_profile_integration.py` | **18 passed** | Traversal/absolute/Windows/empty-segment keys bị chặn; upload với filename `../../outside.txt` vẫn dùng basename metadata và object key server sinh; CORS preflight chỉ cho method/header cần thiết. |
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_backend_foundation.py` | **4 passed** | Bao gồm refresh-only cookie, bogus bearer không bypass CSRF, logout và revoked refresh. |
| `.venv/bin/python -m pytest -q -p no:cacheprovider` sau security hardening | **92 passed, 1 skipped** | Full Python suite trên code commit `1e1589f`; một cảnh báo pending-deprecation từ LangGraph serializer. Không gọi DeepSeek thật. |
| `.venv/bin/python -m pytest -p no:cacheprovider tests/test_rate_limits.py tests/test_production_security_config.py::test_production_rejects_disabled_rate_limits -q` | **4 passed** | Hạn mức `429`, hashed IP key, Redis failure fail-closed ở production/fail-open ở development, và production không thể tắt limiter. |
| `.venv/bin/python -m pytest -p no:cacheprovider -q` trên commit `004020e` | **96 passed, 1 skipped** | Full Python suite; skip là live DeepSeek smoke. LangGraph có một pending-deprecation warning. Không gọi provider thật. |
| `.venv/bin/python scripts/export_openapi.py --check`; `compileall` cho database/services/packages/tests; `git diff --check` | PASS | OpenAPI không đổi; cú pháp Python và whitespace sạch. |
| `.venv/bin/python scripts/export_openapi.py --check` | PASS | OpenAPI khớp generated contract sau khi thêm outcome API. |
| `PYTHONPYCACHEPREFIX=/private/tmp/... .venv/bin/python -m compileall -q database services packages` | PASS | Kiểm tra cú pháp Python, bytecode được ghi ra cache tạm riêng. |
| SQLite `alembic upgrade head` trên DB tạm mới | PASS | Đã áp dụng liên tiếp migration 0001→0007; không đại diện cho PostgreSQL/pgvector. |
| `npm run gen:api -- --from ../../packages/contracts/openapi.json` | PASS | Generated TypeScript HTTP DTOs từ backend OpenAPI. |
| `npm run typecheck -- --incremental false` (trong `apps/web`, commit `72ad60a`) | PASS | TypeScript không phát hiện lỗi. |
| `npm test` (trong `apps/web`, commit `72ad60a`) | **41 passed** | 2 test files. |
| `npm run lint` (trong `apps/web`, commit `72ad60a`) | PASS | ESLint hoàn tất. |
| `npm run build` (trong `apps/web`, commit `72ad60a`) | PASS | Production build tạo route analytics với outcome tracker và publishing route. |
| Frontend security hardening trên code commits `d9cb6a8`/`1e1589f` | **43 tests passed**; typecheck, lint, `npm run build` PASS | Runtime-config serializer test chặn `</script>`; client refresh test xác nhận gửi CSRF header. Next build cần quyền ghi cục bộ vào `.next`, sau đó hoàn tất. |
| `npm run test:e2e` (trong `apps/web`) | **32 passed** | Desktop + mobile Chromium; gồm nhập snapshot/dashboard và recommendation feedback/apply/owner review qua MSW fixtures, không phải real API. |
| `npm run test:e2e -- --grep 'ghi feedback và áp dụng recommendation'` | **2 passed** | Desktop + mobile Chromium; accept brief revision, ghi outcome và kiểm tra limitations bằng MSW demo response; không phải số liệu thật. |
| `E2E_REAL_API_BASE_URL=http://127.0.0.1:8000 npm run test:e2e:real -- --grep 'campaign → manual post'` | **1 passed** | Chromium real mode: test tự đăng ký owner vào API loopback, tạo campaign, viết bài thủ công, duyệt v1, tạo export và tải XLSX. API chạy trên SQLite vừa migrate 0001→0007, storage ở `/private/tmp`; không dùng MSW, PostgreSQL, DeepSeek hay Meta. |
| Real-mode browser smoke trên API thật | **PASS — analytics/recommendation và manual-publish fallback** | Analytics/recommendation smoke chạy trên code `628efcb`: DB SQLite riêng trong `/private/tmp`, account test qua API, 1 campaign + 10 bài + 10 metric points giả lập; UI login, dashboard, save recommendation, feedback, Apply và owner accept; API xác nhận `version=2` và brief được cập nhật. Sau đó production build `c77720d` xác nhận route publishing nêu rõ Meta chưa kết nối và hướng dẫn thủ công. Không dùng MSW, PostgreSQL, DeepSeek hay Meta. Smoke thủ công, chưa phải test tự động tái chạy. |
| `npm ls postcss --all` | PASS | PostCSS 8.5.24 và 8.5.28 có trong dependency tree. |
| `npm audit --audit-level=high` | PASS | Registry hiện trả 0 vulnerabilities. |
| Runtime-config/CORS security regressions | PASS | Inline config test blocks `</script>` termination; API preflight test rejects unlisted request headers. |
| Cookie refresh/logout CSRF regressions | PASS | API yêu cầu token khi refresh cookie còn nhưng access cookie mất; frontend refresh client gửi token; logout revoke refresh session. |
| `git diff --check` | PASS | Kiểm tra working diff sạch sau rate-limit implementation. |
| Focused content API/worker, provider, Brand Profile and agent tests | **30 passed** | SQLite fixture verifies confirmed-profile gate, idempotency, exact citation provenance, durable draft/version/run persistence and configured DeepSeek worker path. No live provider call. |
| Full Python suite (`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q`) | **101 passed, 1 skipped** | Skip is live DeepSeek smoke: no `DEEPSEEK_API_KEY`; adapter/client tests use fakes. LangGraph emitted one pending-deprecation warning. |
| OpenAPI export + `--check`; generated TypeScript schema | PASS | Content generation now documents `202` and `Idempotency-Key`; backend OpenAPI and frontend generated schema updated. |
| Frontend unit tests | **43 passed** | Vitest 4 files. |
| Frontend typecheck | PASS | `npx tsc --noEmit --incremental false`; default project command could not write its protected `tsconfig.tsbuildinfo` cache. |
| Frontend lint and production build | PASS | ESLint and Next.js production build completed. |
| Latest full Python suite on AI-revise working tree | **103 passed, 1 skipped** | Python 3.11.16; fixture/API/worker tests include revise idempotency, exact expected-version recheck, scope preservation, `ai_revised` history, approval reset, failed-job retry and queued-job recovery. Skip is live DeepSeek smoke; one existing LangGraph pending-deprecation warning. |
| Focused `tests/test_campaign_workflows.py` | **7 passed** | SQLite fixture integration; no external model calls. |
| OpenAPI export/check and generated frontend schema | PASS | Added AI revise route, DTO and `202` job response; `scripts/export_openapi.py --check` is clean. |
| `npx tsc --noEmit --incremental false`; `npx vitest run`; focused ESLint | PASS; **43 tests passed** | Frontend checks use the updated generated API schema. |
| `npm run test:e2e -- slice2-campaign.spec.ts` | **8 passed** | Production Next.js + MSW demo; 4 desktop and 4 mobile tests, including AI revise UI/status/version. It does not call DeepSeek. |
| Python `compileall` for database/services/packages/tests | PASS | Bytecode cache is written under `/private/tmp`; no test DB or provider used. |

## Chưa nghiệm thu

- PostgreSQL migration/integration: PostgreSQL local chấp nhận kết nối, nhưng chưa xác nhận DB riêng an toàn; không ghi vào DB chưa xác minh.
- Docker Compose, worker/scheduler restart, MinIO/S3: Docker/Podman và MinIO không sẵn có.
- DeepSeek live: user đã chấp thuận đoạn trích tài liệu và Brand Profile data flow, nhưng không có `DEEPSEEK_API_KEY`; live smoke đã skip. Chưa xác minh model list của tài khoản, latency/token/chi phí.
- Meta publish/metrics: chưa có app/page/token/quyền/App Review.
- Real-mode browser E2E đầy đủ: analytics/recommendation và manual campaign → post → approval → export đã qua browser/API thật trên SQLite. AI generation/revise path được kiểm tra qua API+worker fixtures và mock browser, chưa gọi DeepSeek hoặc chạy browser path với model thật; PostgreSQL/MinIO cũng chưa nghiệm thu.

## Phạm vi bằng chứng

Campaign, manual post/version, approval, export, content generation and AI revise have SQLite API/worker fixture tests; only manual workflows have real-mode browser coverage. AI revise has mock browser coverage but no live-provider browser run. These tests do not represent PostgreSQL or production deployment. Content integration validates versioned workspace context, threshold-filtered active sources, exact citation metadata and unapproved draft/version behavior; fake models never send data to DeepSeek. User approved sending Brand Profile and document excerpts, and production workers use the configured DeepSeek adapter; the API key is still absent. Backend-only company/brand database IDs are excluded from model prompts, and external embeddings remain separately gated. Manual metrics, recommendation feedback, Apply draft, accept/version conflict and REC-002 outcome persistence are checked by SQLite API tests; UI outcome flow uses MSW and is not performance evidence. Tenant tests are not a full security audit. Security review reproduced traversal through `LocalObjectStorage.put('../outside.txt')`; rate limits have fake-Redis unit tests but real Redis, reverse proxy and edge controls remain unverified. See [security-review.md](security-review.md).

## Lệnh tái kiểm tra

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/python -m compileall -q database services packages
(cd apps/web && npx tsc --noEmit --incremental false && npm test && npm run lint && npm run build)
npm audit --audit-level=high
```

Run live DeepSeek smoke only in a secured server environment after the approved API key is provisioned. PostgreSQL migration and Meta checks still require isolated services/credentials. Never write secrets into the repository or test report.
