# Báo cáo kiểm thử

Cập nhật: 2026-09-24 08:30 (Asia/Ho_Chi_Minh). Trên worktree cô lập của branch `codex/product-v1-completion`, account lifecycle bổ sung password reset và invitation/email. Full Python suite mới nhất: **123 passed, 1 skipped**; skip là live DeepSeek smoke do chưa có key. Frontend: **45 Vitest pass**, typecheck, ESLint, production build pass; Playwright invite flow **2 passed** trên desktop/mobile Chromium. Runtime recovery đã pass trước đó trên PostgreSQL/Redis cô lập với Celery `solo`; Compose, Beat process, ingestion worker và prefork Linux vẫn chưa được nghiệm thu. Các kết quả này được ghi nhận trên worktree trước bước push.

## Account lifecycle và SMTP tùy chọn

| Check | Kết quả | Giới hạn |
|---|---|---|
| `tests/test_account_lifecycle.py` trong full Python suite | **5 test pass**: reset link chỉ dùng một lần; mọi token reset cũ, access token cũ và refresh sessions bị thu hồi sau reset; SMTP không cấu hình trả lời trung tính; SMTP lỗi không lộ chẩn đoán; invitation fallback/resend/accept/re-activation; SMTP STARTTLS/login và credential không nằm trong message body/header. | SMTP fake; không gửi thư ra ngoài hoặc xác minh mailbox/provider thật. |
| `services/api/config.py` | **PASS**: URL frontend phải là HTTP(S) origin; production bắt buộc HTTPS; SMTP username/password phải đi cùng nhau; STARTTLS và SSL không thể bật đồng thời; có host thì cần `EMAIL_FROM`. | Chưa chạy trong production deployment. |
| OpenAPI export/check và `npm run gen:api -- --from ../../packages/contracts/openapi.json` | **PASS** | TypeScript schema sinh từ OpenAPI backend; không có contract hand-maintained cho endpoints mới. |
| Frontend `npm run typecheck`, `npm test`, `npm run lint`, `npm run build` | **PASS; 45 Vitest tests passed** | Build không chứng minh gửi thư hoặc provider thật. |
| `npm run test:e2e -- slice1-brand.spec.ts --grep 'tạo, gửi lại và chấp nhận' --workers=1` | **2 passed** (desktop + mobile Chromium) | Tạo lời mời, resend xoay token và render/accept trang lời mời bằng MSW. Token fixture được dùng cho page navigation; đây không phải real API browser acceptance. |
| Live SMTP | **NOT VERIFIED** | Không có SMTP host/credentials hoặc mailbox test trong môi trường; không phát sinh email ra ngoài. |
| Live DeepSeek smoke | **SKIPPED** | Cần provision `DEEPSEEK_API_KEY` qua secret store; không paste key vào chat. |

## RAG-001 — local multilingual E5

| Check | Kết quả | Giới hạn |
|---|---|---|
| `tests/test_fastembed_provider.py`, `tests/test_knowledge.py`, `tests/test_deepseek_config.py` | **30 passed** | Fake ONNX output; xác nhận prefix `passage:`/`query:`, vector 384 chiều, cửa sổ chunk 300 token, abstention khi semantic mơ hồ và lexical fallback. |
| Runtime E5 và retrieval/no-answer calibration | **PASS** trên model local `intfloat/multilingual-e5-small@614241f...`; 6/6 truy vấn có đáp án hit đúng nguồn hạng 1, 0/8 truy vấn ngoài miền trả context. | Corpus synthetic nhỏ, chỉ kiểm tra hành vi trên câu hỏi này; không đại diện SME/customer corpus hoặc quality SLA. Chạy lại bằng `python scripts/evaluate_retrieval.py --cache-dir <model-cache> --local-files-only`. Model tải về cache tạm; không gửi tài liệu/query workspace tới dịch vụ embedding. |
| Synthetic retrieval ranking calibration/holdout trước khi siết gate | E5, weight semantic 0.75: calibration Hit@1 75%, Hit@3 100%, MRR .875; separate holdout Hit@1 75%, Hit@3 91.7%, MRR .850. Trên Apple M2/16 GB, cold load ~17 giây; embed 12 passages + 12 queries ~0.11 giây; peak RSS ~1.05 GB. | Chỉ 24 truy vấn synthetic, không có SME/customer corpus; metric ranking cũ không được xem là SLA cho relevance gate mới. [FastEmbed/Qdrant](https://github.com/qdrant/fastembed), [model card và prefix/dimension details](https://huggingface.co/intfloat/multilingual-e5-small). |
| Relevance defaults | Lexical-only `0.12`; hybrid lexical rescue `0.45`; semantic floor `0.82`; semantic inter-source margin `0.04` (single-source score phải đạt `0.86`). | Thresholds là cấu hình pilot bảo thủ, không phải xác suất confidence; cần hiệu chỉnh bằng truy vấn và tài liệu SME được cho phép trước khi nghiệm thu pilot. |
| PostgreSQL 18.3 + pgvector 0.8.2 migration 0009→0010 | **PASS** | Test disposable bắt đầu từ schema `vector(1536)` như deployment cũ, chứa row 1536 chiều trước upgrade; sau migration giữ row đó, nhận row 384 chiều và Postgres retrieval chỉ trả model version khớp. Downgrade chủ động từ chối khi vector 384 còn tồn tại. |
| SQLite migration 0001→0010 | **PASS** | JSON test representation cho vectors giữ được độ dài linh hoạt; SQLite không kiểm tra cosine/vector operator của pgvector. |
| Full Python suite; OpenAPI check; `compileall`; Compose YAML; `git diff --check` | **123 passed, 1 skipped; PASS** cho các kiểm tra còn lại | Live DeepSeek smoke là skip duy nhất. Docker Compose runtime chưa chạy vì máy thiếu Docker/Podman. |

Model choice là local `intfloat/multilingual-e5-small`, pinned revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions. Tokenizer revision đó khai báo context 512; chunker v3 dùng cửa sổ 300 token/overlap 40 để chừa khoảng đệm. Chỉ public model weights được tải; workspace documents/queries được encode tại worker. Existing documents cần reprocess sau khi chuyển provider/model/chunker. `.env.example` bật local model; OpenAI embeddings vẫn cần data-flow approval riêng. Chất lượng retrieval cần kiểm chứng tiếp bằng tài liệu/query do SME pilot cung cấp. [Pinned tokenizer config](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/tokenizer_config.json).

Cập nhật: 2026-09-24 05:32 (Asia/Ho_Chi_Minh). Kết quả real-mode mới nhất chạy trên commit `4f9a97a` của branch `codex/product-v1-completion`. Backend full suite **105 passed, 1 skipped** và frontend **43 passed/typecheck/lint/build** được chạy trên implementation commit `43ab2d3`; `4f9a97a` chỉ mở rộng real-mode browser acceptance test. Project owner đã chấp thuận gửi đoạn trích tài liệu, Brand Profile và strategy/topic/date của slot đã chọn tới DeepSeek.

Môi trường: Python 3.11.16, Node.js 26.7.0, SQLite và PostgreSQL 18.3 disposable, local object storage, Chromium desktop/mobile. Bộ Playwright mock dùng MSW; real-mode Playwright kết nối FastAPI thật và đã chạy riêng với cả SQLite lẫn PostgreSQL.

## Snapshot nghiệm thu MEDIA-001 mới nhất

| Check | Kết quả | Giới hạn |
|---|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider` | **105 passed, 1 skipped** | Chạy trên code snapshot nêu ở đầu tài liệu. Skip duy nhất là live DeepSeek smoke vì chưa có `DEEPSEEK_API_KEY`; một cảnh báo pending deprecation của LangGraph. Suite gồm API/worker fixtures và test media upload/tenant isolation/version/approval hash; fixture không gọi provider thật. |
| `npm run test:e2e -- slice2-campaign.spec.ts --workers=1` | **14 passed** (7 desktop + 7 mobile) | Chromium với MSW. Có upload ảnh, preview, attach vào version mới và detach bằng version kế tiếp. Không gọi API thật, DeepSeek hay Meta. Chạy server cần quyền localhost; lần được nghiệm thu chạy trên loopback. |
| Frontend `npm run typecheck`, `npm test`, `npm run lint`, `npm run build` | **PASS; 43 tests passed** | Production build có route post editor/media; không phải real-mode API acceptance. |
| Fresh SQLite Alembic `upgrade head`, rerun, `current` | **PASS — `0009_media_assets_and_approval_hash (head)`** | DB disposable `/private/tmp/agentic-v1-media-migration-final.sqlite`; không dùng app/customer data. |
| Fresh PostgreSQL 18.3 Alembic `upgrade head`, rerun | **PASS — migration 0001→0009; pgvector 0.8.2** | Cluster dùng một lần, bind loopback `127.0.0.1:55439`, dừng sau test; `media_assets` có 12 cột, `post_approvals.content_sha256` NOT NULL. Đây chỉ là migration test, không phải API/worker runtime acceptance trên PostgreSQL. |
| `.venv/bin/python scripts/export_openapi.py --check`; Python `compileall`; `git diff --check` | **PASS** | OpenAPI/generated TypeScript đồng bộ; không phát hiện lỗi cú pháp hoặc whitespace. |
| `E2E_REAL_API_BASE_URL=http://127.0.0.1:18000 E2E_REAL_PORT=13101 npm run test:e2e:real -- manual-workflows.real.spec.ts --workers=1` với SQLite 0001→0009 + local storage | **1 passed** | `NEXT_PUBLIC_USE_MOCKS=0`; tạo account mới, tạo campaign/post, upload ảnh qua FastAPI, lưu version 2, duyệt, đọc lại media SHA/approval hash qua API và download XLSX. Không MSW, DeepSeek, Meta hay Redis. |
| Cùng real-mode browser test với PostgreSQL 18.3 + pgvector 0.8.2 mới migrate 0001→0009 + local storage | **1 passed** | Cùng luồng thật với DB PostgreSQL; không đại diện cho worker/Redis/MinIO hoặc LLM live. |
| PostgreSQL `pg_dump -Fc` → `pg_restore` sang database mới | **PASS** | Counts trước/sau khớp theo thứ tự companies/campaigns/posts/versions/approvals/media_assets/exports: `1/1/1/2/1/1/1`; restored revision là `0009_media_assets_and_approval_hash`. Test DB hoàn toàn disposable. |
| Local object storage archive/restore checksum roundtrip | **PASS — 2 objects** | Tệp media và export được tar vào thư mục test mới; danh sách đường dẫn và SHA-256 trước/sau giống nhau. Đây không phải MinIO/S3 backup acceptance. |
| Disposable PostgreSQL + Redis + FastAPI runtime | **PASS — `/healthz` 200, `/readyz` ready** | PostgreSQL test DB, Redis và local object storage riêng; readiness báo `database`, `redis`, `object_storage` đều true. Không phải Compose/production deployment. |
| Celery recovery trên PostgreSQL/Redis | **PASS — một job được phục hồi** | PostgreSQL 18.3, Redis 8.6.3, Celery 5.6.3 `solo`. Gửi task không chỉ định queue; route đưa task vào `default`. Recovery tìm thấy job có lease hết hạn, đưa job về hàng chờ, xóa lease; worker xử lý lại content job và ghi lỗi cấu hình `ai_not_configured` ở attempt 2 vì không có key. Không gửi request tới DeepSeek. |
| Celery worker event loop và queue routing | **PASS — 4 focused worker tests** | Hai lần gọi coroutine dùng lại event loop của process; Beat entry và router đều chọn queue `default`. Beat process chưa được khởi chạy. |

Không có DeepSeek key nên chưa có model-list/live JSON request hoặc chi phí/latency thực. Không có Meta credentials và không đăng bài thật. Docker/Podman và MinIO không khả dụng, nên Compose, Beat process, document-ingestion task, worker process restart và object-store deployment chưa được kiểm tra. Recovery với job có lease hết hạn đã chạy qua Redis; worker dùng Celery `solo` trên macOS. Lần thử pool prefork dừng trong Celery/Billiard trước khi vào code dự án, nên prefork Linux vẫn cần chạy. 14 campaign-slice E2E dùng MSW; real-mode E2E riêng kết nối FastAPI và PostgreSQL/SQLite thật. Backend media integration tests dùng API fixture suite; các kiểu kiểm thử không gộp chung.

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
| PostgreSQL 18.3 migration trên disposable cluster `agentic_v1_test` | PASS | Alembic clean upgrade 0001→0007 và rerun `upgrade head`; pgvector 0.8.2; 27 public base tables; revision `0007_recommendation_experiment_outcomes` dài 39 ký tự. Cluster và role test riêng; PostgreSQL 15 dùng chung không bị sửa. |
| Campaign brief update API | **7 passed** trong `tests/test_campaign_workflows.py` | SQLite fixture; sửa brief tăng version, gửi lại version cũ trả `409 version_conflict`; không gọi LLM. |
| `npm run test:e2e -- slice2-campaign.spec.ts` | **10 passed** | 5 desktop + 5 mobile Chromium trên MSW; thêm sửa brief, hiển thị nội dung mới và tăng version. Không gọi DeepSeek. |
| `npm run typecheck -- --incremental false`, `npm test`, `npm run lint`, `npm run build` | PASS; **43 unit tests** | Next production build gồm campaign detail editor. |
| `.venv/bin/pytest -q` | **103 passed, 1 skipped** | Skip là live DeepSeek smoke vì chưa provision `DEEPSEEK_API_KEY`; suite dùng SQLite/fake provider. |
| `.venv/bin/python scripts/export_openapi.py --check`; `PYTHONPYCACHEPREFIX=/private/tmp/agentic-v1-pycache-20260924 .venv/bin/python -m compileall -q database services packages tests`; `git diff --check` | PASS | OpenAPI/generated TypeScript synchronized; bytecode output isolated under `/private/tmp`. |
| `.venv/bin/pytest -p no:cacheprovider -q` | **104 passed, 1 skipped** | Python 3.11.16; includes campaign slot reservation, duplicate/idempotency guard, strategy/topic/date model payload, slot→draft link, lock-after-generation, terminal failure release, retry reacquisition and cancellation release. Skip is the live DeepSeek smoke because no `DEEPSEEK_API_KEY` is provisioned. |
| PostgreSQL 18.3 disposable cluster migration | PASS | Clean Alembic upgrade 0001→0008 and idempotent rerun; pgvector 0.8.2; 27 public tables; `campaigns.content_plan_json` is JSON NOT NULL with default `{}`. The shared PostgreSQL 15 service was not used. |
| SQLite disposable migration | PASS | Clean Alembic upgrade 0001→0008 and idempotent rerun using a database under `/private/tmp`. |
| OpenAPI export/check and generated TypeScript schema | PASS | Campaign content-plan DTOs and `slot_id` generation request match backend schemas. |
| Frontend `npm run typecheck`, `npm test`, `npm run lint` | PASS; **43 unit tests** | Slot edit, management fields and MSW generation request types compile; Vitest has 4 passing files. |
| `npm run test:e2e -- slice2-campaign.spec.ts` | **12 passed** | 6 desktop + 6 mobile Chromium tests; added edit strategy/topic and route generation by selected slot topic. MSW only; no DeepSeek request. The test run also completed the production build. |
| Python `compileall` and `git diff --check` | PASS | Bytecode cache uses `/private/tmp`; whitespace check is clean. |

## Chưa nghiệm thu

- PostgreSQL migration: clean migration path is verified on a disposable PostgreSQL 18/pgvector cluster; full API/worker integration against PostgreSQL and the shared PostgreSQL 15 service remain unverified.
- Docker Compose, worker/scheduler restart, MinIO/S3: Docker/Podman và MinIO không sẵn có.
- DeepSeek live: user đã chấp thuận đoạn trích tài liệu, Brand Profile, campaign strategy và slot topic/date đã chọn, nhưng không có `DEEPSEEK_API_KEY`; live smoke đã skip. Chưa xác minh model list của tài khoản, latency/token/chi phí.
- Meta publish/metrics: chưa có app/page/token/quyền/App Review.
- Real-mode browser E2E đầy đủ: analytics/recommendation và manual campaign → post → approval → export đã qua browser/API thật trên SQLite. AI generation/revise path được kiểm tra qua API+worker fixtures và mock browser, chưa gọi DeepSeek hoặc chạy browser path với model thật; PostgreSQL/MinIO cũng chưa nghiệm thu.

## Phạm vi bằng chứng

Campaign, manual post/version, approval, export, content generation and AI revise have SQLite API/worker fixture tests; only manual workflows have real-mode browser coverage. Strategy/slot editing and click-through to a slot-specific job have desktop/mobile MSW coverage. AI revise and generation have mock browser coverage but no live-provider browser run. These tests do not represent full PostgreSQL or production deployment. Content integration validates versioned workspace context, threshold-filtered active sources, exact citation metadata, slot strategy/topic/date, and unapproved draft/version behavior; fake models never send data to DeepSeek. User approved sending Brand Profile, document excerpts and the selected slot strategy/topic/date; the API key is still absent. Backend-only company/brand/slot database IDs are excluded from model prompts, and external embeddings remain separately gated. Manual metrics, recommendation feedback, Apply draft, accept/version conflict and REC-002 outcome persistence are checked by SQLite API tests; UI outcome flow uses MSW and is not performance evidence. Tenant tests are not a full security audit. Security review reproduced traversal through `LocalObjectStorage.put('../outside.txt')`; rate limits have fake-Redis unit tests but real Redis, reverse proxy and edge controls remain unverified. See [security-review.md](security-review.md).

## Lệnh tái kiểm tra

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/python -m compileall -q database services packages
(cd apps/web && npx tsc --noEmit --incremental false && npm test && npm run lint && npm run build)
npm audit --audit-level=high
```

Run live DeepSeek smoke only in a secured server environment after the approved API key is provisioned. Full PostgreSQL/Redis/MinIO runtime and Meta checks still require isolated services/credentials. Never write secrets into the repository or test report.
