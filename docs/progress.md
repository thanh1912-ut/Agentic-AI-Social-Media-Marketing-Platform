# Tiến độ triển khai

Cập nhật gần nhất: 2026-09-24 00:55 (Asia/Ho_Chi_Minh)

## Trạng thái phiên

- Branch: `codex/product-v1-completion`; security code commits `d9cb6a8` (upload/CORS/runtime config) và `1e1589f` (refresh/logout CSRF) đã được push; base `origin/main` là `07938bd`.
- Phase hiện tại: hardening/bàn giao. Recommendation có feedback/audit, Apply → brief revision chờ duyệt → owner accept/discard có version guard, và ghi nhận outcome baseline/follow-up.
- Trạng thái: REC-002, real-mode manual workflow và hai security hardening commits đã push. Python/frontend checks pass; docs security/test/progress đang phản ánh evidence ở `1e1589f`.
- Snapshot source M1/M2/M3 đã được đưa vào worktree riêng; checkout và index gốc ở `/Users/lethanh/agent` được giữ nguyên.
- Phase 0 (audit và sáu tài liệu) đã hoàn tất. Phase 1 có Python/npm dependencies; clean SQLite migration 0001→0007 pass. Chưa nghiệm thu stack PostgreSQL/Redis/MinIO bằng Docker.
- Phase 3 có campaign CRUD, manual post/version, approval và CSV/XLSX export tenant-scoped. Content generation API đang fail-closed với `503 provider_approval_required`.
- Phase 5 có manual metric snapshot import API/UI, tenant/post validation, duplicate detection, timestamp/source/age metadata, dashboard nhóm theo pillar/format và freshness/coverage. Phase 6 có recommendation rule-based có evidence/abstain; feedback được lưu; Apply tạo brief revision; owner accept theo version guard; REC-002 lưu kết quả so sánh trước/sau cùng source, metric và tuổi bài.

## Tiến độ theo subsystem

| Subsystem | Implementation | Verification | Evidence | Next action |
|---|---|---|---|---|
| Auth/workspace/membership | API/session/tenant permissions | Fixture API tests; UI real-mode login qua SQLite cô lập | `services/api/auth.py`, `services/api/workspaces.py` | Kiểm chứng PostgreSQL và full session lifecycle trên runtime riêng. |
| Upload/ingestion/jobs | Parser, durable jobs/recovery; server-generated object keys và traversal guard | Python suite pass; PostgreSQL/MinIO/restart runtime chưa xác minh | `services/api/documents.py`, `services/api/storage.py`, `tests/test_storage_security.py` | Kiểm legacy keys và chạy trên isolated PostgreSQL/object store. |
| Brand Profile | Handler, citations, revisions, confirmation; production LLM worker fail-closed | Fake-provider/fixture tests pass; live provider chưa chạy | `services/api/brand_profiles.py`, `services/worker/tasks.py` | Cần data-flow approval và key trước live Brand Profile E2E. |
| Retrieval | Tenant/source/version/locator; lexical mode mặc định | Fixture tests pass; semantic vector chưa cấu hình | `services/ingestion/knowledge_store.py` | Chọn embedding provider, cấu hình threshold và reindex trước semantic mode. |
| DeepSeek | Chat Completions JSON-mode adapter, validation, normalized errors | Fake-client pass; live smoke skipped | `services/agents/providers/deepseek.py`, `tests/test_deepseek_provider.py` | Cần chấp thuận gửi dữ liệu tenant ra ngoài và key trong secret store. |
| Campaign | Tenant-scoped create/list/detail và campaign brief | SQLite API tests; real-mode browser flow pass | `services/api/campaign_workflows.py`, `tests/e2e/manual-workflows.real.spec.ts` | Xác nhận lại trên PostgreSQL sau khi test DB được provision. |
| Manual content/version | Manual post, immutable versions, stale conflict `409` | API tests và real-mode browser test pass | `services/api/campaign_workflows.py` | AI create/revise chờ AI-001; edit sau approval cần duyệt lại. |
| Approval | Quyết định gắn exact current/pending version | Exact-version, stale-version, reapproval tests pass | `services/api/campaign_workflows.py` | Tích hợp publishing guard khi connector Meta đủ quyền. |
| Export | CSV/XLSX thật, idempotency, formula-safe output | API download + real-mode XLSX download pass | `services/api/campaign_workflows.py` | Kiểm thử object storage trên MinIO. |
| Meta | Chưa có connector; có hướng dẫn export và đăng tay | Publishing page production build/browser checked; không gọi Meta | `apps/web/src/app/w/[workspaceId]/publishing/page.tsx` | Cần Page/app/token/quyền và App Review. |
| Metrics/dashboard | Manual snapshots, API/UI dashboard, null-aware counts, coverage/freshness | SQLite API, clean migrations 0001→0007, OpenAPI pass | `services/api/analytics.py`, analytics UI | Meta sync và nguồn số liệu thật chưa có. |
| Recommendation | Rule-based evidence/abstain; feedback/audit; Apply draft, owner accept; outcome windows | API cohort/evidence/idempotency tests; desktop/mobile MSW flow pass | REC-001/REC-002 migrations and analytics API/UI | Nhập follow-up metrics thật; không diễn giải như bằng chứng nhân quả. |
| Frontend | Auth/workspace/docs/brand/campaign/manual post/export/analytics/recommendations | Typecheck/lint/build pass; 43 unit tests; 32 mock E2E; real-mode manual workflow pass | `apps/web/src/**`, `tests/e2e/**` | Brand extraction và AI content real E2E còn chờ AI-001. |
| Security/ops | JWT/docs protections, explicit CORS allowlist, safe inline config, upload traversal fix, refresh/logout CSRF | 92 Python pass/1 skip; 43 frontend tests; typecheck/lint/build pass | `docs/security-review.md`, storage/CORS/runtime-config/auth-CSRF regression tests | Rate-limit/host/edge review, PostgreSQL/Compose, backup/restore và deployment E2E còn mở. |

## Kiểm thử gần nhất

- Python: `92 passed, 1 skipped`; gồm storage traversal, uploaded filename, explicit CORS preflight, refresh-only CSRF and logout tests. Skip là live DeepSeek smoke.
- Frontend: `43 passed`; typecheck, lint và production build pass.
- Playwright mock E2E cũ: `32 passed` desktop/mobile; REC-002 test riêng chạy lại `2 passed` (desktop + mobile), gồm accept revision và lưu/hiển thị outcome qua MSW demo data, không phải live API.
- Real-mode Playwright: `1 passed`; đăng ký account mới, login, tạo campaign, viết/duyệt bài thủ công, tạo export và tải XLSX qua FastAPI thật + SQLite tạm. Không gọi DeepSeek hoặc Meta.
- OpenAPI `--check`, Python `compileall` và SQLite migration 0001→0007 pass.
- `npm ls postcss --all` pass: PostCSS 8.5.24/8.5.28 trong cây dependency.
- `npm audit --audit-level=high` pass: 0 vulnerabilities.
- Real-mode browser smoke chạy với Next.js production build và FastAPI trên loopback, SQLite DB mới trong `/private/tmp`, account E2E và 10 metric points giả lập. Login, dashboard, lưu recommendation, feedback `useful`, Apply tạo pending draft, owner accept đều pass; API xác nhận campaign version `2` và brief có nội dung recommendation. Sau đó trang publishing ở commit `c77720d` hiển thị fallback thủ công, không 404. Không gọi DeepSeek hoặc Meta.
- PostgreSQL migration chưa chạy vì chưa xác định được DB test an toàn.
- Storage traversal được tái hiện rồi sửa; regression/full-suite evidence và giới hạn security review nằm trong [security-review.md](security-review.md).

Chi tiết: [test-report.md](test-report.md).

## Blockers

- **AI-001 — chờ bạn chấp thuận data flow:** auto-review từ chối worker gửi Brand Profile và đoạn trích tài liệu workspace tới DeepSeek. Cả upload-driven profile extraction worker lẫn content generation endpoint đều fail-closed; endpoint trả `503 provider_approval_required`, không gọi provider. Cũng chưa có `DEEPSEEK_API_KEY` để live smoke.
- **DB/RUN-001 — runtime:** Docker/Podman và MinIO không có; PostgreSQL local đã lắng nghe nhưng chưa được xác minh là DB test riêng, nên không dùng để ghi migration.
- **E2E-001 — phạm vi:** real-mode đã kiểm tra analytics/recommendation và manual campaign → post → approval → export. Upload-driven Brand Profile extraction và AI content generation chưa nghiệm thu; phụ thuộc AI-001. Chưa chạy đầy đủ acceptance trên PostgreSQL/MinIO.
- **META-001 — quyền bên ngoài:** chưa có Meta app/Page credentials, permission hoặc App Review evidence.
- **RAG-001 — embedding:** DeepSeek chat không được mặc định coi là embedding API; hiện retrieval lexical.

## Việc tiếp theo

1. Duy trì fail-closed cho AI tới khi data flow DeepSeek được chấp thuận và key được provision; sau đó chạy Brand Profile/content E2E.
2. Khi môi trường test được provision: nghiệm thu PostgreSQL, Compose, worker/MinIO và backup/restore trên dịch vụ cô lập.
3. Hoàn tất rate-limit/host/edge review và Meta feasibility khi credentials, Page permission và App Review sẵn sàng.
