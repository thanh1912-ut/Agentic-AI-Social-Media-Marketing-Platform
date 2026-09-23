# Tiến độ triển khai

Cập nhật gần nhất: 2026-09-24 05:06 (Asia/Ho_Chi_Minh)

## Trạng thái hiện tại

- Branch: `codex/product-v1-completion`; implementation commit `43ab2d3` trên PR #1. Bộ kiểm tra dưới đây chạy trên đúng source snapshot của commit này.
- Phase hiện tại: Phase 7 — hardening và bàn giao core pilot. Mốc vừa đạt: MEDIA-001 asset ảnh được tích hợp từ upload tới post version, approval fingerprint và export; 14 browser E2E desktop/mobile, 105 backend tests, 43 frontend tests và PostgreSQL migrations 0001→0009 đã pass.
- Công việc trong phiên: cập nhật sáu tài liệu vận hành, rà staged diff và push implementation cùng evidence lên PR #1. Working tree đã sạch; không có service API/web nào đang chạy sau E2E.
- Checkout dùng cho task là `/private/tmp/agentic-v1-media`; working tree và index gốc tại `/Users/lethanh/agent` được giữ nguyên.
- Chủ dự án đã chấp thuận gửi đoạn trích tài liệu, Brand Profile và strategy/topic/date của slot được chọn tới DeepSeek. Chưa có `DEEPSEEK_API_KEY`; không có live model call hay số liệu token/cost/latency.

## Tiến độ theo subsystem

| Subsystem | Implementation | Verification | Evidence | Next action |
|---|---|---|---|---|
| Auth/workspace/membership | Session, workspace và tenant permissions | API fixture tests pass; real-mode manual flow đã được kiểm tra trước đó trên SQLite | `services/api/auth.py`, `services/api/workspaces.py`, `docs/test-report.md` | Chạy lifecycle trên runtime PostgreSQL/Redis triển khai. |
| Upload/ingestion/jobs | Parser, durable ingestion/recovery và server-generated object keys | Python suite pass; full worker restart và MinIO chưa xác minh | `services/api/documents.py`, `services/ingestion`, `services/worker` | Nghiệm thu trên PostgreSQL/Redis/object storage. |
| Brand Profile | Extraction worker, source citations, revision/edit/confirm; DeepSeek server-side adapter | Fake-model API/worker tests pass; live provider NOT_VERIFIED | `services/api/brand_profiles.py`, `services/worker/tasks.py` | Provision key trong secret store rồi chạy live smoke/browser path. |
| Retrieval | Tenant/source/version/locator filters; lexical retrieval và relevance threshold | Fixture tests pass; semantic embeddings NOT_CONFIGURED | `services/ingestion/knowledge_store.py` | Chọn embedding provider/data flow; reindex trước khi bật semantic mode. |
| DeepSeek | Một Chat Completions JSON-mode adapter dùng worker factory; timeout/input/output limits | Fake-client pass; live smoke skip vì thiếu key | `services/agents/providers/deepseek.py`, `services/worker/model_provider.py` | Xác nhận model trong account, live request và chi phí/latency sau khi key được provision. |
| PostgreSQL migrations | Alembic schema 0001→0009, gồm media_assets và post approval hash | PostgreSQL 18.3 + pgvector 0.8.2: upgrade mới và rerun pass; SQLite upgrade/rerun cũng pass | migration 0009, `docs/test-report.md` | Chạy API/worker data-path trên runtime triển khai. |
| Runtime/infrastructure | Compose khai báo API, worker, scheduler, PostgreSQL, Redis, object storage | Compose/containers chưa boot; không có Docker/Podman hoặc MinIO trong môi trường | `infra/`, `docker-compose.yml`, `docs/runbook.md` | Provision test services; health/readiness, job recovery và storage smoke. |
| Campaign/content slots | Brief, strategy, slots, durable generation/revise, version guard | API/worker fixtures và desktop/mobile mock E2E pass; live LLM NOT_VERIFIED | `services/api/campaign_workflows.py`, `services/worker/content_tasks.py` | DeepSeek live browser acceptance sau khi có secret. |
| Media assets | JPEG/PNG/WebP upload, tenant-scoped preview/download, attach/detach theo version, export reference | Python integration coverage; 14/14 desktop/mobile Playwright campaign E2E pass | `services/api/media.py`, `apps/web/src/app/w/[workspaceId]/campaigns/[campaignId]/posts/[postId]/page.tsx`, migration 0009 | DONE cho manual media workflow; Meta image publishing thuộc META-001. |
| Approval/export | Approval gắn exact version và SHA-256 của nội dung/media; CSV/XLSX có media filename/hash/path | API test và full frontend build pass; manual export/download browser evidence đã có | `services/api/content_integrity.py`, campaign workflow, `docs/test-report.md` | Publisher tương lai phải so hash trước khi gửi; Meta connector chưa có. |
| Meta | Trang real mode giải thích fallback export → đăng tay → nhập metrics; chưa có connector | Publishing UI/browser kiểm tra trước đó; không gọi Meta API | `apps/web/src/app/w/[workspaceId]/publishing/page.tsx` | BLOCKED_EXTERNAL: cần app/Page/token/quyền/App Review và reconciliation. |
| Metrics/dashboard | Manual snapshots, null-aware KPI, coverage/freshness, grouping | SQLite API/browser evidence và existing test suite pass | `services/api/analytics.py`, analytics UI | Nhập nguồn số liệu thật; Meta sync còn mở. |
| Recommendation | Evidence/abstain, feedback, apply draft, owner accept/version guard, outcome windows | SQLite API tests và desktop/mobile mock flow pass | recommendation routes/UI, migration 0006–0007 | Kiểm chứng với dữ liệu pilot; không diễn giải outcome như quan hệ nhân quả. |
| Frontend | Auth, brand, campaigns, media editor, analytics, publishing guidance | Typecheck, 43 Vitest, lint, production build pass; 14/14 focused desktop/mobile E2E pass | `apps/web`, `tests/e2e/slice2-campaign.spec.ts` | Real-mode AI generation/browser path cần DeepSeek key. |
| Security/operations | CSRF, tenant checks, rate limits, upload validation, approval hash | 105 pytest pass/1 live-DeepSeek skip; OpenAPI/compile/diff checks pass | `docs/security-review.md`, `docs/test-report.md` | Backup/restore, proxy/edge controls, load smoke và full operational review còn mở. |

## Blockers và ảnh hưởng

- **AI-001 — DeepSeek live validation:** user đã chấp thuận data flow cho tài liệu, Brand Profile và slot strategy/topic/date; implementation và fake-client tests pass. Chưa có `DEEPSEEK_API_KEY`, nên model-list check, live request, browser flow, tokens, latency và chi phí chưa được xác minh. Cần provision key ở server secret store; không gửi key qua chat.
- **RUN-001 / OPS-001 — full runtime:** PostgreSQL migration test đã pass trong cluster cô lập. Docker/Podman và MinIO không có; Compose, API/worker/scheduler health, Redis queue behavior, MinIO, restart recovery và backup/restore chưa nghiệm thu. Có thể tiếp tục fixture và local adapter checks độc lập.
- **META-001 — external access:** chưa có Meta App/Page/token, permissions hoặc App Review. Automatic publishing/metrics sync bị chặn; fallback manual export/publish/import được giữ rõ trong UI.
- **RAG-001 — semantic embedding:** đang dùng lexical retrieval. Embedding provider và data flow bên ngoài chưa được chọn/chấp thuận; không bật vector generation mặc định.

## Bằng chứng mới nhất

- Python 3.11: `.venv/bin/python -m pytest -q -p no:cacheprovider` — **105 passed, 1 skipped**. Skip là live DeepSeek smoke; có một cảnh báo pending deprecation từ LangGraph.
- Frontend: `npm test` — **43 passed**; typecheck, ESLint và `next build` pass.
- Browser: `npm run test:e2e -- slice2-campaign.spec.ts --workers=1` — **14 passed** (7 desktop + 7 mobile), bao gồm upload ảnh, preview, attach version và detach version. Chạy MSW, không gọi DeepSeek.
- Database: PostgreSQL 18.3/pgvector 0.8.2 migration 0001→0009 và rerun pass; SQLite 0001→0009 pass. Đây là migration checks, chưa phải API/worker acceptance trên PostgreSQL.
- OpenAPI `--check`, Python compileall và `git diff --check` pass. Chi tiết môi trường/lệnh/giới hạn ở [test-report.md](test-report.md).

## Ba việc tiếp theo

1. Provision DeepSeek key ở server secret store; chạy model-list/JSON smoke và browser flow Brand Profile/content thật, ghi tokens/latency/cost.
2. Provision runtime test cô lập (PostgreSQL, Redis, object storage, Docker/Compose nếu có); kiểm tra API/worker restart, health/readiness và backup/restore.
3. Khi được cấp Meta app/Page/token và App Review, triển khai/test publisher duplicate-safe; đến lúc đó dùng manual fallback. Sau pilot, chọn riêng embedding provider/data flow nếu cần semantic RAG.

Không có URL service nào đang chạy. Hướng dẫn chạy và các giới hạn vận hành nằm ở [runbook.md](runbook.md); kế hoạch/phạm vi ở [implementation-plan.md](implementation-plan.md); kiểm thử ở [test-report.md](test-report.md).
