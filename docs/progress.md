# Tiến độ triển khai

Cập nhật gần nhất: 2026-09-24 00:08 (Asia/Ho_Chi_Minh)

## Trạng thái phiên

- Branch: `codex/product-v1-completion`; latest code/test commit `bba034e` bổ sung real-mode acceptance cho manual campaign, approval và export; base `origin/main` là `07938bd`. Tài liệu đang được đồng bộ trước khi push.
- Phase hiện tại: hardening/bàn giao. Recommendation có feedback/audit, Apply → brief revision chờ duyệt → owner accept/discard có version guard, và ghi nhận outcome baseline/follow-up.
- Trạng thái: REC-002, real-mode manual workflow test và cập nhật test report đã hoàn tất trên worktree; còn fetch remote và push branch bàn giao.
- Snapshot source M1/M2/M3 đã được đưa vào worktree riêng; checkout và index gốc ở `/Users/lethanh/agent` được giữ nguyên.
- Phase 0 (audit và sáu tài liệu) đã hoàn tất. Phase 1 có Python/npm dependencies; clean SQLite migration 0001→0007 pass. Chưa nghiệm thu stack PostgreSQL/Redis/MinIO bằng Docker.
- Phase 3 có campaign CRUD, manual post/version, approval và CSV/XLSX export tenant-scoped. Content generation API đang fail-closed với `503 provider_approval_required`.
- Phase 5 có manual metric snapshot import API/UI, tenant/post validation, duplicate detection, timestamp/source/age metadata, dashboard nhóm theo pillar/format và freshness/coverage. Phase 6 có recommendation rule-based có evidence/abstain; feedback được lưu; Apply tạo brief revision; owner accept theo version guard; REC-002 lưu kết quả so sánh trước/sau cùng source, metric và tuổi bài.

## Tiến độ theo subsystem

| Subsystem | Implementation | Verification | Bằng chứng và việc còn lại |
|---|---|---|---|
| Auth/workspace/membership | API/session/tenant permission nền | Fixture suite pass; đăng nhập UI real mode và tải workspace từ API thật pass trên SQLite cô lập | `services/api/auth.py`, `services/api/workspaces.py`; account chỉ tồn tại trong DB tạm. |
| Upload/ingestion/jobs | Upload, parser, persistent jobs/recovery, storage adapters | Unit/fixture suite pass; PostgreSQL/MinIO/restart runtime chưa xác minh | `services/api/documents.py`, `services/worker/tasks.py`; cần test trên isolated PostgreSQL và object store. |
| Brand Profile | Handler/source/revision/confirm có trong code; production LLM extraction worker fail-closed | Fake-provider/fixture tests pass; live provider chưa chạy | `services/api/brand_profiles.py`, `services/worker/tasks.py`; cần chấp thuận data flow trước khi worker gọi LLM. |
| Retrieval | Tenant/source/version/locator contracts; lexical mode mặc định | Fixture tests pass; semantic vector mode chưa cấu hình | `services/ingestion/knowledge_store.py`; cần provider embedding riêng, threshold và reindex để bật semantic. |
| DeepSeek | Chat Completions JSON-mode adapter, validation và lỗi chuẩn hóa | Fake-client tests pass; live smoke skip | Thiếu key và cần xác nhận rõ việc gửi Brand Profile/tài liệu tenant tới dịch vụ ngoài. |
| Campaign | Tạo/list/detail, brief/pillar/channel có kiểm tra | API tests pass trên SQLite | `services/api/campaign_workflows.py`; chưa có browser real-mode flow. |
| Manual content/version | Tạo bài thủ công, sửa thành version bất biến, conflict `409` | Tenant, history và stale version tests pass | Chỉnh sửa bài đã duyệt đặt lại trạng thái cần duyệt. Sinh/sửa bằng AI chưa bật. |
| Approval | Quyết định gắn với version hiện tại/pending; lưu lịch sử | Exact-version, stale-version, reapproval tests pass | Chưa có publish guard/integration. |
| Export | Tải CSV/XLSX thật, idempotency, chống công thức spreadsheet | API download tests pass | Storage production/MinIO chưa chạy kiểm chứng. Export không đồng nghĩa đã đăng bài. |
| Meta | Chưa có connector/live publish; real-mode có trang hướng dẫn export và đăng thủ công | Trang publishing được xác minh trên production build; không gọi Meta | Cần Page/app/token/quyền và Meta App Review để bật kết nối tự động. |
| Metrics/dashboard | Manual snapshots API + migration 0005 + dashboard response/UI; counts giữ null, có coverage/freshness, grouping | Analytics API tests pass; clean SQLite migration 0001→0007; OpenAPI hiện hành | Snapshot nhập tay là dữ liệu người dùng cung cấp, chưa có Meta sync/metrics ingestion tự động. |
| Recommendation | Deterministic proposal/abstain; persisted lifecycle + feedback/audit; Apply tạo brief revision; accept/discard + version conflict; outcome baseline/follow-up theo source, metric và age range | API test cover cohort computation/evidence IDs/readback/idempotency, sai source/window và draft pending; Playwright outcome flow desktop/mobile pass | Cần nhập số liệu thực tế sau thời gian thử nghiệm; chênh lệch là mô tả, không chứng minh nhân quả. |
| Frontend | Auth/workspace/docs/brand/campaign/manual post/export, metrics/recommendation/outcome tracker và trang hướng dẫn xuất bản thủ công | Typecheck/lint/build trên `72ad60a`; 41 unit tests; 32 prior desktop/mobile mock E2E; REC-002 browser flow pass 2/2 projects; real-mode manual workflow pass trên `bba034e` | Browser xác minh login, campaign, manual post, duyệt và tải export qua API thật/SQLite; brand extraction và AI content vẫn chưa xác minh do AI-001. |
| Security/ops | Production JWT secret checks, Secure cookie, API docs tắt khi production | Security tests pass; `npm audit` reports 0 vulnerabilities | Cần full security review, PostgreSQL/Compose, backup/restore và real E2E. |

## Kiểm thử gần nhất

- Python: `82 passed, 1 skipped`; analytics import/report/recommendation/tenant isolation tests pass, production worker fail-closed trước provider. Skip là live DeepSeek smoke.
- Frontend: `41 passed`; typecheck, lint và production build pass.
- Playwright mock E2E cũ: `32 passed` desktop/mobile; REC-002 test riêng chạy lại `2 passed` (desktop + mobile), gồm accept revision và lưu/hiển thị outcome qua MSW demo data, không phải live API.
- Real-mode Playwright: `1 passed`; đăng ký account mới, login, tạo campaign, viết/duyệt bài thủ công, tạo export và tải XLSX qua FastAPI thật + SQLite tạm. Không gọi DeepSeek hoặc Meta.
- OpenAPI `--check`, Python `compileall` và SQLite migration 0001→0007 pass.
- `npm ls postcss --all` pass: PostCSS 8.5.24/8.5.28 trong cây dependency.
- `npm audit --audit-level=high` pass: 0 vulnerabilities.
- Real-mode browser smoke chạy với Next.js production build và FastAPI trên loopback, SQLite DB mới trong `/private/tmp`, account E2E và 10 metric points giả lập. Login, dashboard, lưu recommendation, feedback `useful`, Apply tạo pending draft, owner accept đều pass; API xác nhận campaign version `2` và brief có nội dung recommendation. Sau đó trang publishing ở commit `c77720d` hiển thị fallback thủ công, không 404. Không gọi DeepSeek hoặc Meta.
- PostgreSQL migration chưa chạy vì chưa xác định được DB test an toàn.

Chi tiết: [test-report.md](test-report.md).

## Blockers

- **AI-001 — chờ bạn chấp thuận data flow:** auto-review từ chối worker gửi Brand Profile và đoạn trích tài liệu workspace tới DeepSeek. Cả upload-driven profile extraction worker lẫn content generation endpoint đều fail-closed; endpoint trả `503 provider_approval_required`, không gọi provider. Cũng chưa có `DEEPSEEK_API_KEY` để live smoke.
- **DB/RUN-001 — runtime:** Docker/Podman và MinIO không có; PostgreSQL local đã lắng nghe nhưng chưa được xác minh là DB test riêng, nên không dùng để ghi migration.
- **E2E-001 — phạm vi:** real-mode đã kiểm tra analytics/recommendation và manual campaign → post → approval → export. Upload-driven Brand Profile extraction và AI content generation chưa nghiệm thu; phụ thuộc AI-001. Chưa chạy đầy đủ acceptance trên PostgreSQL/MinIO.
- **META-001 — quyền bên ngoài:** chưa có Meta app/Page credentials, permission hoặc App Review evidence.
- **RAG-001 — embedding:** DeepSeek chat không được mặc định coi là embedding API; hiện retrieval lexical.

## Việc tiếp theo

1. Chờ chấp thuận rõ cho data flow DeepSeek; sau đó cấu hình key ở secret store và chạy live smoke có kiểm soát.
2. Chạy PostgreSQL migration, Compose/runtime, backup/recovery và nghiệm thu Meta khi môi trường/quyền sẵn sàng.
3. Chạy brand extraction/content E2E khi AI-001 được giải quyết; kiểm tra REC-002 bằng số liệu vận hành thật khi có snapshot baseline/follow-up.
