# Tiến độ triển khai

Cập nhật gần nhất: 2026-09-24 06:26 (Asia/Ho_Chi_Minh)

## Trạng thái hiện tại

- Branch: `codex/product-v1-completion`; baseline `996d4c3` đã có trên PR #1. Snapshot này ghi nhận phần local E5/RAG và evidence mới nhất trên cùng branch.
- Phase hiện tại: Phase 7 — hardening và bàn giao core pilot. Mốc mới: real-mode browser manual flow pass riêng trên SQLite và PostgreSQL; database dump/restore counts khớp và archive/restore local object storage giữ nguyên SHA-256.
- Công việc trong phiên: mở rộng real API E2E để upload ảnh, kiểm version/approval hash, export; nghiệm thu với PostgreSQL 18, chạy dump/restore, kiểm tra readiness với PostgreSQL/Redis/local storage, và xác nhận Celery worker nhận task recovery qua Redis. Process/runtime và dữ liệu test tạm đã dừng/xóa; báo cáo đã được đẩy lên PR #1.
- Mốc RAG mới: chọn local FastEmbed multilingual E5 small pinned 384d; thêm query/passage prefix, chunker v3 300-token window, dimension-flexible pgvector và relevance gate raw-score. PostgreSQL migration từ schema `vector(1536)` giữ vector cũ, nhận vector 384 và retrieval tách theo model identity. Full Python suite hiện **112 passed, 1 skipped**.
- Giới hạn mới: model weights không cache trong sandbox này và DNS tải model bị chặn, nên adapter real load chưa kiểm chứng tại worktree. Synthetic holdout 12 truy vấn đạt Hit@1 75%, Hit@3 91.7%, MRR .850; chưa phải benchmark tài liệu SME.
- Checkout dùng cho task là `/private/tmp/agentic-v1-media`; working tree và index gốc tại `/Users/lethanh/agent` được giữ nguyên.
- Chủ dự án đã chấp thuận gửi đoạn trích tài liệu, Brand Profile và strategy/topic/date của slot được chọn tới DeepSeek. Chưa có `DEEPSEEK_API_KEY`; không có live model call hay số liệu token/cost/latency.

## Tiến độ theo subsystem

| Subsystem | Implementation | Verification | Evidence | Next action |
|---|---|---|---|---|
| Auth/workspace/membership | Session, workspace và tenant permissions | API fixture tests pass; real-mode manual flow đã được kiểm tra trước đó trên SQLite | `services/api/auth.py`, `services/api/workspaces.py`, `docs/test-report.md` | Chạy lifecycle trên runtime PostgreSQL/Redis triển khai. |
| Upload/ingestion/jobs | Parser, durable ingestion/recovery và server-generated object keys | Python suite pass; full worker restart và MinIO chưa xác minh | `services/api/documents.py`, `services/ingestion`, `services/worker` | Nghiệm thu trên PostgreSQL/Redis/object storage. |
| Brand Profile | Extraction worker, source citations, revision/edit/confirm; DeepSeek server-side adapter | Fake-model API/worker tests pass; live provider NOT_VERIFIED | `services/api/brand_profiles.py`, `services/worker/tasks.py` | Provision key trong secret store rồi chạy live smoke/browser path. |
| Retrieval | Tenant/source/version/locator filters; local multilingual E5; query/passage prefixes; raw relevance gates | 26 focused tests pass; synthetic E5 holdout Hit@1 .75 / Hit@3 .917 / MRR .850; PostgreSQL legacy-to-flexible vector migration and dimension-isolated retrieval pass | `services/agents/providers/fastembed.py`, `services/ingestion/knowledge_store.py`, `docs/test-report.md` | Tải/khởi động model trên deployment có network/cache; reprocess tài liệu cũ; đánh giá trên corpus SME. |
| DeepSeek | Một Chat Completions JSON-mode adapter dùng worker factory; timeout/input/output limits | Fake-client pass; live smoke skip vì thiếu key | `services/agents/providers/deepseek.py`, `services/worker/model_provider.py` | Xác nhận model trong account, live request và chi phí/latency sau khi key được provision. |
| PostgreSQL migrations/API | Alembic 0001→0010, gồm media assets/approval hash và flexible embedding dimensions; API campaign/media/approval/export | PostgreSQL 18.3 + pgvector 0.8.2 migration pass trên schema cũ `vector(1536)`; manual real-mode browser/API flow pass; SQLite 0001→0010 cũng pass | migration 0010, `tests/e2e/manual-workflows.real.spec.ts`, `docs/test-report.md` | Kiểm tra worker/Redis/S3 và readiness trên runtime triển khai. |
| Runtime/infrastructure | Compose khai báo API, worker, scheduler, PostgreSQL, Redis, object storage | Disposable PostgreSQL + Redis + FastAPI/local storage: `/healthz` 200, `/readyz` báo đủ 3 dependency; Celery ping nhận phản hồi và worker thực thi `recover_due_jobs` qua Redis (0 job trong DB rỗng). Compose/MinIO, scheduler process, ingestion job và restart recovery chưa xác minh | `infra/`, `docker-compose.yml`, `docs/runbook.md`, `docs/test-report.md` | Chạy full Compose/MinIO và xác nhận restart/recovery trên job có thật. |
| Campaign/content slots | Brief, strategy, slots, durable generation/revise, version guard | API/worker fixtures và desktop/mobile mock E2E pass; live LLM NOT_VERIFIED | `services/api/campaign_workflows.py`, `services/worker/content_tasks.py` | DeepSeek live browser acceptance sau khi có secret. |
| Media assets | JPEG/PNG/WebP upload, tenant-scoped preview/download, attach/detach theo version, export reference | Python integration; 14/14 desktop/mobile MSW E2E; real API/browser E2E pass trên SQLite và PostgreSQL, xác nhận version 2, media SHA, approval hash và XLSX download | `services/api/media.py`, post editor, `tests/e2e/manual-workflows.real.spec.ts`, migration 0009 | DONE cho manual media workflow; Meta image publishing thuộc META-001. |
| Approval/export | Approval gắn exact version và SHA-256 của nội dung/media; CSV/XLSX có media filename/hash/path | API test và full frontend build pass; manual export/download browser evidence đã có | `services/api/content_integrity.py`, campaign workflow, `docs/test-report.md` | Publisher tương lai phải so hash trước khi gửi; Meta connector chưa có. |
| Meta | Trang real mode giải thích fallback export → đăng tay → nhập metrics; chưa có connector | Publishing UI/browser kiểm tra trước đó; không gọi Meta API | `apps/web/src/app/w/[workspaceId]/publishing/page.tsx` | BLOCKED_EXTERNAL: cần app/Page/token/quyền/App Review và reconciliation. |
| Metrics/dashboard | Manual snapshots, null-aware KPI, coverage/freshness, grouping | SQLite API/browser evidence và existing test suite pass | `services/api/analytics.py`, analytics UI | Nhập nguồn số liệu thật; Meta sync còn mở. |
| Recommendation | Evidence/abstain, feedback, apply draft, owner accept/version guard, outcome windows | SQLite API tests và desktop/mobile mock flow pass | recommendation routes/UI, migration 0006–0007 | Kiểm chứng với dữ liệu pilot; không diễn giải outcome như quan hệ nhân quả. |
| Frontend | Auth, brand, campaigns, media editor, analytics, publishing guidance | Typecheck, 43 Vitest, lint/build; 14/14 desktop/mobile mock E2E; real API/browser manual flow pass trên SQLite và PostgreSQL | `apps/web`, `tests/e2e/manual-workflows.real.spec.ts` | Real-mode AI generation/Brand Profile browser path cần DeepSeek key. |
| Security/operations | CSRF, tenant checks, rate limits, upload validation, approval hash | 112 pytest passed/1 live-DeepSeek skip; PostgreSQL pg_dump/restore counts khớp; local object archive checksum roundtrip 2 objects | `docs/security-review.md`, `docs/test-report.md` | Worker lease/restart, Redis/MinIO, proxy/edge, scheduled backup, load smoke và full operational review còn mở. |

## Blockers và ảnh hưởng

- **AI-001 — DeepSeek live validation:** user đã chấp thuận data flow cho tài liệu, Brand Profile và slot strategy/topic/date; implementation và fake-client tests pass. Chưa có `DEEPSEEK_API_KEY`, nên model-list check, live request, browser flow, tokens, latency và chi phí chưa được xác minh. Cần provision key ở server secret store; không gửi key qua chat.
- **RUN-001 / OPS-001 — full runtime:** FastAPI readiness đã pass khi PostgreSQL 18, Redis 8 và local storage cùng chạy; Celery worker nhận ping và thực thi task recovery rỗng qua Redis. FastAPI manual flow chạy qua PostgreSQL thật; `pg_dump`/`pg_restore` sang DB mới khôi phục đúng counts và local asset archive roundtrip giữ nguyên 2 object. Docker/Podman và MinIO không có; scheduler, ingestion job, job restart/recovery có trạng thái thật, MinIO/S3 backup và deployment restore chưa nghiệm thu.
- **META-001 — external access:** chưa có Meta App/Page/token, permissions hoặc App Review. Automatic publishing/metrics sync bị chặn; fallback manual export/publish/import được giữ rõ trong UI.
- **RAG-001 — semantic embedding:** local provider và migration đã triển khai; model runtime download/encode chưa xác minh vì sandbox không phân giải DNS. E5 synthetic holdout nhỏ chưa đại diện dữ liệu SME. Cần cache weights trong deployment, reprocess tài liệu cũ và kiểm tra relevance với corpus được pilot cho phép.

## Bằng chứng mới nhất

- Python 3.11: `.venv/bin/python -m pytest -q -p no:cacheprovider` — **105 passed, 1 skipped** trên implementation commit `43ab2d3`. Skip là live DeepSeek smoke; có một cảnh báo pending deprecation từ LangGraph.
- Frontend: `npm test` — **43 passed**; typecheck, ESLint và `next build` pass.
- Browser: `npm run test:e2e -- slice2-campaign.spec.ts --workers=1` — **14 passed** (7 desktop + 7 mobile) với MSW. `manual-workflows.real.spec.ts` — **1 pass trên SQLite và 1 pass trên PostgreSQL**, không MSW: login, campaign/post, ảnh, versioned approval, API readback và XLSX download. Không gọi DeepSeek/Meta.
- Database/runtime: PostgreSQL 18.3/pgvector 0.8.2 migration 0001→0010, gồm legacy `vector(1536)` data-preservation + vector 384 insertion/retrieval; API/browser manual flow, pg_dump/restore counts và local storage checksum roundtrip pass. Một disposable PostgreSQL + Redis runtime cũng đạt `/healthz`, `/readyz`; Celery worker tiêu thụ task `recover_due_jobs` rỗng qua queue. SQLite migration và real API flow cũng pass. Scheduler, restart recovery, ingestion, Compose và MinIO acceptance còn mở.
- OpenAPI `--check`, Python compileall và `git diff --check` pass. Chi tiết môi trường/lệnh/giới hạn ở [test-report.md](test-report.md).
- RAG integration: `tests/test_fastembed_provider.py`, `tests/test_knowledge.py`, `tests/test_deepseek_config.py` — **26 passed**; full Python suite — **112 passed, 1 skipped** (live DeepSeek). SQLite migration 0001→0010 pass. PostgreSQL 18.3/pgvector 0.8.2 migration từ `vector(1536)` giữ vector cũ, insert/retrieve 384 chiều pass, downgrade guard chặn mất dữ liệu. OpenAPI check, compileall, Compose YAML parse và `git diff --check` pass.

## Ba việc tiếp theo

1. Provision DeepSeek key ở server secret store; chạy model-list/JSON smoke và browser flow Brand Profile/content thật, ghi tokens/latency/cost.
2. Provision runtime có model cache và corpus pilot được phép dùng; kiểm tra local FastEmbed encode/retrieval, reprocess, DeepSeek generation citations, API/worker restart và backup/restore.
3. Khi được cấp Meta app/Page/token và App Review, triển khai/test publisher duplicate-safe; đến lúc đó dùng manual fallback. Docker/Compose, scheduler, MinIO, worker restart với job tồn tại và production load vẫn cần nghiệm thu riêng.

Không có URL service nào đang chạy. Hướng dẫn chạy và các giới hạn vận hành nằm ở [runbook.md](runbook.md); kế hoạch/phạm vi ở [implementation-plan.md](implementation-plan.md); kiểm thử ở [test-report.md](test-report.md).
