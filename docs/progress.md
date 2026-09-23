# Tiến độ triển khai

Cập nhật gần nhất: 2026-09-24 04:14 (Asia/Ho_Chi_Minh)

## Trạng thái phiên

- Branch: `codex/product-v1-completion`, PR #1 đang mở. Bản cập nhật hiện tại hoàn tất campaign strategy/content slots, nối slot vào DeepSeek generation job, thêm migration 0008; API/worker tests và 12 desktop/mobile E2E đã pass. Đang hoàn tất docs và review diff trước khi push.
- Phase hiện tại: AI integration và bàn giao. Branch có REC-002, real-mode manual workflow, security fixes, rate limits, Brand Profile/DeepSeek worker flow, durable content-generation jobs và AI revise version workflow.
- Trạng thái: data flow gửi đoạn trích tài liệu và Brand Profile tới DeepSeek, cùng strategy/chủ đề/ngày slot khi người dùng chọn slot, đã được chủ dự án chấp thuận ngày 2026-09-24. Code path đã bật qua factory server-side; API key chưa có nên live request/model-account check chưa chạy.
- Snapshot source M1/M2/M3 đã được đưa vào worktree riêng; checkout và index gốc ở `/Users/lethanh/agent` được giữ nguyên.
- Phase 0 (audit và sáu tài liệu) đã hoàn tất. Phase 1: dependency checks pass; migration 0001→0008 đã chạy trên PostgreSQL 18 + pgvector cô lập, sau đó `upgrade head` chạy lại không đổi schema. Full Compose/Redis/MinIO runtime chưa nghiệm thu.
- Phase 3 có campaign CRUD và brief edit tenant-scoped; update dùng expected version và stale update trả 409. Manual post/version, approval và CSV/XLSX export cũng có. Content generation và AI revise dùng durable/idempotent jobs, xác minh Brand Profile đã xác nhận, tenant/relevance/source context và base version; revise lưu `ai_revised` PostVersion, giữ trường ngoài scope và buộc duyệt lại khi bài từng được duyệt. Không tự gửi duyệt hoặc đăng.
- PLAN-001 đã có strategy summary và content slots persisted trên campaign; slot lưu ngày/trụ/format/topic, edit có version guard và slot được khóa khi đang chạy/đã sinh. API reserve slot theo idempotency key; worker gửi strategy/topic/ngày đã chọn tới DeepSeek, lưu `content_slot_id`/ngày dự kiến vào draft và gắn lại slot. Retry/cancel giải phóng hoặc lấy lại reservation. Chủ dự án đã chấp thuận thêm data flow slot ngày 2026-09-24.
- Phase 5 có manual metric snapshot import API/UI, tenant/post validation, duplicate detection, timestamp/source/age metadata, dashboard nhóm theo pillar/format và freshness/coverage. Phase 6 có recommendation rule-based có evidence/abstain; feedback được lưu; Apply tạo brief revision; owner accept theo version guard; REC-002 lưu kết quả so sánh trước/sau cùng source, metric và tuổi bài.

## Tiến độ theo subsystem

| Subsystem | Implementation | Verification | Evidence | Next action |
|---|---|---|---|---|
| Auth/workspace/membership | API/session/tenant permissions | Fixture API tests; UI real-mode login qua SQLite cô lập | `services/api/auth.py`, `services/api/workspaces.py` | Kiểm chứng PostgreSQL và full session lifecycle trên runtime riêng. |
| Upload/ingestion/jobs | Parser, durable jobs/recovery; server-generated object keys và traversal guard | Python suite pass; PostgreSQL/MinIO/restart runtime chưa xác minh | `services/api/documents.py`, `services/api/storage.py`, `tests/test_storage_security.py` | Kiểm legacy keys và chạy trên isolated PostgreSQL/object store. |
| Brand Profile | Handler/citations/revisions; worker dùng DeepSeek theo cấu hình, API key server-side | Fixture worker/API tests pass; live provider chưa chạy | `services/api/brand_profiles.py`, `services/worker/tasks.py` | Cần provision key và test model account/runtime thật. |
| Retrieval | Tenant/source/version/locator; lexical mode mặc định | Fixture tests pass; semantic vector chưa cấu hình | `services/ingestion/knowledge_store.py` | Chọn embedding provider, cấu hình threshold và reindex trước semantic mode. |
| DeepSeek | Chat Completions JSON-mode adapter; worker factory giới hạn input/token/timeout; API key chỉ ở server | Fake-client pass; live smoke skipped | `services/agents/providers/deepseek.py`, `services/worker/model_provider.py` | Cần provision key, xác minh model list của tài khoản và chạy live smoke. |
| PostgreSQL migrations | Migrations 0001→0008 và pgvector extension | Isolated PostgreSQL 18.3, pgvector 0.8.2; clean upgrade + rerun; JSON `content_plan_json` NOT NULL/default `{}`; 27 public tables | `database/migrations/env.py`, migration 0008, disposable DB | Chạy full API/worker stack và data-path trên PostgreSQL/Redis/MinIO. |
| Campaign | Tenant-scoped brief/strategy/slots; optimistic version; slot generation reservation and post linkage | SQLite API/worker tests; Playwright desktop/mobile slot edit → job route | `services/api/campaign_workflows.py`, `services/worker/content_tasks.py`, campaign detail UI | Acceptance trên PostgreSQL/Redis/MinIO; MEDIA-001 vẫn mở. |
| Media assets | Document uploader nhận ảnh làm metadata-only input; post version giữ media field và image brief | Parser/upload fixture pass; chưa có asset attach/preview API hoặc UI | `services/api/documents.py`, post editor | MEDIA-001: asset upload/list/preview/attach có tenant checks; approvals phải gắn media hash. |
| Content/version | Generation/revise là durable/idempotent jobs; slot sends approved strategy/topic/date; citations and immutable versions; human approval required | Python API/worker tests cover slot reservation/idempotency/retry/cancel and citations; live DeepSeek chưa chạy | `services/api/campaign_workflows.py`, `services/worker/content_tasks.py`, post editor | Provision DeepSeek key and run real provider E2E; verify full runtime. |
| Approval | Quyết định gắn exact current/pending version | Exact-version, stale-version, reapproval tests pass | `services/api/campaign_workflows.py` | Tích hợp publishing guard khi connector Meta đủ quyền. |
| Export | CSV/XLSX thật, idempotency, formula-safe output | API download + real-mode XLSX download pass | `services/api/campaign_workflows.py` | Kiểm thử object storage trên MinIO. |
| Meta | Chưa có connector; có hướng dẫn export và đăng tay | Publishing page production build/browser checked; không gọi Meta | `apps/web/src/app/w/[workspaceId]/publishing/page.tsx` | Cần Page/app/token/quyền và App Review. |
| Metrics/dashboard | Manual snapshots, API/UI dashboard, null-aware counts, coverage/freshness | SQLite API, clean migrations 0001→0007, OpenAPI pass | `services/api/analytics.py`, analytics UI | Meta sync và nguồn số liệu thật chưa có. |
| Recommendation | Rule-based evidence/abstain; feedback/audit; Apply draft, owner accept; outcome windows | API cohort/evidence/idempotency tests; desktop/mobile MSW flow pass | REC-001/REC-002 migrations and analytics API/UI | Nhập follow-up metrics thật; không diễn giải như bằng chứng nhân quả. |
| Frontend | Auth/workspace/docs/brand/campaign brief edit/manual post/AI revise/export/analytics/recommendations | Typecheck/lint/build pass; 43 unit tests; campaign slice E2E 10 pass desktop/mobile; earlier full mock E2E 32 pass; real-mode manual workflow pass | `apps/web/src/**`, `tests/e2e/**` | Brand extraction và AI generation/revise real-provider E2E còn chờ AI-001. |
| Security/ops | JWT/docs protections, explicit CORS allowlist, safe inline config, upload traversal fix, refresh/logout CSRF, Redis rate limits | Full Python suite 104 pass/1 skip; OpenAPI check, compile pass; 43 frontend tests, typecheck/lint/build pass | `docs/security-review.md`, storage/CORS/runtime-config/auth-CSRF/rate-limit regressions | Trusted proxy/edge behavior, Redis/Compose, MinIO, backup/restore và deployment E2E còn mở. |

## Kiểm thử gần nhất

- Python: `104 passed, 1 skipped`; includes AI revise and content slot API/worker, idempotency, version recheck, reservation retry/cancel, source citations, scope preservation and reapproval. Skip là live DeepSeek smoke.
- Frontend: `43 passed`; typecheck and lint rerun pass, and production build pass.
- OpenAPI `--check` và generated TypeScript update phản ánh `202` + `Idempotency-Key` của content-generation endpoint.
- OpenAPI/TypeScript artifacts now include `POST /workspaces/{company_id}/posts/{post_id}/revise` with `202` job response and idempotency header.
- Playwright mock E2E cũ: `32 passed` desktop/mobile; REC-002 test riêng chạy lại `2 passed` (desktop + mobile), gồm accept revision và lưu/hiển thị outcome qua MSW demo data, không phải live API.
- Playwright campaign slice: `12 passed` (6 desktop + 6 mobile), có sửa strategy/topic qua MSW rồi tạo job theo chủ đề slot; các luồng bài/duyệt/revise vẫn pass; không gọi DeepSeek.
- Real-mode Playwright: `1 passed`; đăng ký account mới, login, tạo campaign, viết/duyệt bài thủ công, tạo export và tải XLSX qua FastAPI thật + SQLite tạm. Không gọi DeepSeek hoặc Meta.
- OpenAPI `--check`, Python `compileall` và SQLite migration 0001→0007 pass.
- `npm ls postcss --all` pass: PostCSS 8.5.24/8.5.28 trong cây dependency.
- `npm audit --audit-level=high` pass: 0 vulnerabilities.
- Real-mode browser smoke chạy với Next.js production build và FastAPI trên loopback, SQLite DB mới trong `/private/tmp`, account E2E và 10 metric points giả lập. Login, dashboard, lưu recommendation, feedback `useful`, Apply tạo pending draft, owner accept đều pass; API xác nhận campaign version `2` và brief có nội dung recommendation. Sau đó trang publishing ở commit `c77720d` hiển thị fallback thủ công, không 404. Không gọi DeepSeek hoặc Meta.
- PostgreSQL 18.3 isolated DB: Alembic clean upgrade 0001→0008 và rerun pass; `vector 0.8.2`, 27 public tables; `campaigns.content_plan_json` xác nhận JSON NOT NULL default `{}`. Trước fix, PostgreSQL từ chối revision ID 45 ký tự do bảng `alembic_version` mặc định `VARCHAR(32)`; migration env hiện tạo/nâng version column lên `VARCHAR(128)`.
- OpenAPI `--check`, Python `compileall`, SQLite migration 0001→0008 + rerun và clean PostgreSQL migration 0001→0008 + rerun pass.
- Storage traversal được tái hiện rồi sửa; regression/full-suite evidence và giới hạn security review nằm trong [security-review.md](security-review.md).

Chi tiết: [test-report.md](test-report.md).

## Blockers

- **AI-001 — live validation:** bạn đã chấp thuận gửi đoạn trích tài liệu, Brand Profile, và strategy/topic/date của slot được chọn tới DeepSeek. API/worker path đã được triển khai và fixture-tested; chưa có `DEEPSEEK_API_KEY`, nên chưa xác minh model list, live request, latency/token/cost hoặc browser E2E với LLM thật. Metadata chi phí được lưu `null`, không giả định bằng 0.
- **DB/RUN-001 — runtime:** migration đã được xác minh trên PostgreSQL 18/pgvector trong cluster tạm cô lập; PostgreSQL 15 dùng chung trên máy không bị thay đổi. Docker/Podman và MinIO không có, nên Compose, Redis thực, worker restart, object storage và health/readiness chưa được nghiệm thu.
- **E2E-001 — phạm vi:** real-mode đã kiểm tra analytics/recommendation và manual campaign → post → approval → export; AI generation/revise API+worker fixture integration và mock browser flow pass. Chưa chạy browser flow với LLM thật hoặc acceptance trên PostgreSQL/MinIO.
- **MEDIA-001 — product gap:** ảnh upload chưa có asset/list/preview/attach lifecycle; post versions và export chưa có media reference workflow. Phần này còn code độc lập, không phụ thuộc secret.
- **META-001 — quyền bên ngoài:** chưa có Meta app/Page credentials, permission hoặc App Review evidence.
- **RAG-001 — embedding:** retrieval vẫn lexical. Embedding bên ngoài có cờ riêng `EMBEDDING_DATA_FLOW_APPROVED=0`; chưa được chấp thuận hoặc bật.

## Việc tiếp theo

1. Provision `DEEPSEEK_API_KEY` trong secret store server-side; chạy model-list + structured-output smoke và E2E Brand Profile/content trên môi trường cô lập.
2. Hoàn tất MEDIA-001 (asset upload/list/preview/attach và media-aware approval/export) trước khi gọi core v1 hoàn chỉnh.
3. Khi môi trường test được provision: nghiệm thu full PostgreSQL/Compose/worker/MinIO, backup/restore, trusted proxy/Redis limits; hoàn tất Meta feasibility khi credentials, Page permission và App Review sẵn sàng.
