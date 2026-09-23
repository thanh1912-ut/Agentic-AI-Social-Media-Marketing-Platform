# Tiến độ triển khai

Cập nhật gần nhất: 2026-09-23 22:36 (Asia/Ho_Chi_Minh)

## Trạng thái phiên

- Branch: `codex/product-v1-completion`, tạo từ `origin/main` commit `07938bd` sau khi fetch.
- Snapshot source M1/M2/M3 đã được đưa vào worktree riêng; checkout và index gốc ở `/Users/lethanh/agent` được giữ nguyên.
- Phase 0 (audit và sáu tài liệu) đã hoàn tất. Phase 1 có Python/npm dependencies; clean SQLite migration 0001→0005 pass. Chưa nghiệm thu stack PostgreSQL/Redis/MinIO bằng Docker.
- Phase 3 có campaign CRUD, manual post/version, approval và CSV/XLSX export tenant-scoped. Content generation API đang fail-closed với `503 provider_approval_required`.
- Phase 5 có manual metric snapshot import API/UI, tenant/post validation, duplicate detection, timestamp/source/age metadata, dashboard nhóm theo pillar/format và freshness/coverage. Recommendation hiện là rule-based, có evidence và abstain; chưa có feedback/apply loop.

## Tiến độ theo subsystem

| Subsystem | Implementation | Verification | Bằng chứng và việc còn lại |
|---|---|---|---|
| Auth/workspace/membership | API/session/tenant permission nền | Fixture suite pass; chưa có browser real-mode E2E | `services/api/auth.py`, `services/api/workspaces.py`; cần test luồng người dùng qua API thật. |
| Upload/ingestion/jobs | Upload, parser, persistent jobs/recovery, storage adapters | Unit/fixture suite pass; PostgreSQL/MinIO/restart runtime chưa xác minh | `services/api/documents.py`, `services/worker/tasks.py`; cần test trên isolated PostgreSQL và object store. |
| Brand Profile | Handler/source/revision/confirm có trong code; production LLM extraction worker fail-closed | Fake-provider/fixture tests pass; live provider chưa chạy | `services/api/brand_profiles.py`, `services/worker/tasks.py`; cần chấp thuận data flow trước khi worker gọi LLM. |
| Retrieval | Tenant/source/version/locator contracts; lexical mode mặc định | Fixture tests pass; semantic vector mode chưa cấu hình | `services/ingestion/knowledge_store.py`; cần provider embedding riêng, threshold và reindex để bật semantic. |
| DeepSeek | Chat Completions JSON-mode adapter, validation và lỗi chuẩn hóa | Fake-client tests pass; live smoke skip | Thiếu key và cần xác nhận rõ việc gửi Brand Profile/tài liệu tenant tới dịch vụ ngoài. |
| Campaign | Tạo/list/detail, brief/pillar/channel có kiểm tra | API tests pass trên SQLite | `services/api/campaign_workflows.py`; chưa có browser real-mode flow. |
| Manual content/version | Tạo bài thủ công, sửa thành version bất biến, conflict `409` | Tenant, history và stale version tests pass | Chỉnh sửa bài đã duyệt đặt lại trạng thái cần duyệt. Sinh/sửa bằng AI chưa bật. |
| Approval | Quyết định gắn với version hiện tại/pending; lưu lịch sử | Exact-version, stale-version, reapproval tests pass | Chưa có publish guard/integration. |
| Export | Tải CSV/XLSX thật, idempotency, chống công thức spreadsheet | API download tests pass | Storage production/MinIO chưa chạy kiểm chứng. Export không đồng nghĩa đã đăng bài. |
| Meta | Không có connector/live publish | Chưa chạy; external access chưa có | Cần Page/app/token/quyền và Meta App Review. |
| Metrics/dashboard | Manual snapshots API + migration 0005 + dashboard response/UI; counts giữ null, có coverage/freshness, grouping | Analytics API tests pass; clean SQLite migration 0001→0005; OpenAPI hiện hành | Snapshot nhập tay là dữ liệu người dùng cung cấp, chưa có Meta sync/metrics ingestion tự động. |
| Recommendation | Deterministic proposal/abstain API, evidence IDs, confidence và limitation text/UI | API tests xác nhận proposal khi đủ mẫu và abstain khi thiếu mẫu | Chưa có feedback/apply persistence, chiến lược revision hoặc đo tác động thử nghiệm. |
| Frontend | Auth/workspace/docs/brand/campaign/manual post/export và metrics UI/API client | Typecheck, 41 unit tests, lint, production build và desktop/mobile mock E2E pass | Real API E2E chưa chạy do thiếu test account/API environment. |
| Security/ops | Production JWT secret checks, Secure cookie, API docs tắt khi production | Security tests pass; `npm audit` reports 0 vulnerabilities | Cần full security review, PostgreSQL/Compose, backup/restore và real E2E. |

## Kiểm thử gần nhất

- Python: `82 passed, 1 skipped`; analytics import/report/recommendation/tenant isolation tests pass, production worker fail-closed trước provider. Skip là live DeepSeek smoke.
- Frontend: `41 passed`; typecheck, lint và production build pass.
- Playwright mock E2E: toàn bộ desktop/mobile suite có luồng analytics pass; đây là MSW/demo data, không phải live API.
- OpenAPI `--check` và Python `compileall` pass.
- `npm ls postcss --all` pass: PostCSS 8.5.24/8.5.28 trong cây dependency.
- `npm audit --audit-level=high` pass: 0 vulnerabilities.
- PostgreSQL migration chưa chạy vì chưa xác định được DB test an toàn.

Chi tiết: [test-report.md](test-report.md).

## Blockers

- **AI-001 — chờ bạn chấp thuận data flow:** auto-review từ chối worker gửi Brand Profile và đoạn trích tài liệu workspace tới DeepSeek. Cả upload-driven profile extraction worker lẫn content generation endpoint đều fail-closed; endpoint trả `503 provider_approval_required`, không gọi provider. Cũng chưa có `DEEPSEEK_API_KEY` để live smoke.
- **DB/RUN-001 — runtime:** Docker/Podman và MinIO không có; PostgreSQL local đã lắng nghe nhưng chưa được xác minh là DB test riêng, nên không dùng để ghi migration.
- **E2E-001 — tài khoản:** chưa có credential/workspace riêng để chạy Playwright real API.
- **META-001 — quyền bên ngoài:** chưa có Meta app/Page credentials, permission hoặc App Review evidence.
- **RAG-001 — embedding:** DeepSeek chat không được mặc định coi là embedding API; hiện retrieval lexical.

## Việc tiếp theo

1. Chờ chấp thuận rõ cho data flow DeepSeek; sau đó cấu hình key ở secret store và chạy live smoke có kiểm soát.
2. Chạy PostgreSQL migration, Compose/runtime, real-mode Playwright, backup/recovery và nghiệm thu Meta khi môi trường/quyền sẵn sàng.
3. Hoàn thiện recommendation feedback/apply và publish guard; metrics import/dashboard cùng đề xuất rule-based hiện đã chạy được trên SQLite/mock UI.
