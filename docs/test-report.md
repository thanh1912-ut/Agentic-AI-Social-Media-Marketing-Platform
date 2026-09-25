# Báo cáo kiểm thử

Cập nhật: 2026-09-25 17:40 (Asia/Ho_Chi_Minh).

## Backend security regression acceptance — 2026-09-25

| Check | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| Focused production config, Redis limiter, market API/source tests | **29 passed** | Python 3.11.16, dependencies cài trong target cô lập; SQLite/fake Meta/Redis. Bao gồm production chặn SQLite, wildcard CORS và S3 defaults; Settings repr không lộ credential; route wiring cho 6 crawl/10 Page-verification requests mỗi giờ; UTF-16 DTD regression. |
| Full Python suite | **190 passed, 1 skipped** | Skip là opt-in live DeepSeek smoke; một LangGraph pending-deprecation warning. Chạy với Python 3.11.16 từ `/private/tmp`, không ghi `.data` hay pytest cache vào repo. |
| `git diff --check` | PASS | Source và docs diff sạch tại thời điểm kiểm tra. |
| `npm audit --json` | **BLOCKED — no registry DNS** | npm không phân giải `registry.npmjs.org`; lệnh không trả advisory result. Không được diễn giải là 0 vulnerabilities. Current manifest: Next.js 15.5.25. |
| Next.js upstream release check | **15.5.26 available** | Official Sep 22 security note says 15.x is not affected by the described RCE; 15.5.26 contains related hardening. Frontend manifest/lockfile chưa được thay đổi trong lượt backend này. |

Python runtime dependency target lấy từ lượt acceptance trước; không có DeepSeek/Meta request. Edge security headers, Compose/MinIO, production proxy và frontend dependency advisories chưa được xác minh.

## Nhiều Fanpage và nghiên cứu thị trường — API/PostgreSQL/Celery acceptance, 2026-09-25

| Check | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| Full Python suite | **185 passed, 1 skipped** | Python 3.11.16; chạy với dependency target cô lập và SQLite/fake providers. Skip là live DeepSeek smoke opt-in; một LangGraph pending-deprecation warning. PostgreSQL được kiểm tra riêng ở acceptance bên dưới. |
| Frontend | **47 Vitest passed; ESLint PASS; TypeScript PASS** | TypeScript cần `--incremental false` vì sandbox không cho tạo `tsconfig.tsbuildinfo` trong worktree. |
| Python source checks | **Ruff PASS; compileall PASS; `git diff --check` PASS** | Áp dụng lên worker, Meta client và các test liên quan. |
| OpenAPI | **PASS** | `scripts/export_openapi.py --output <absolute openapi.json> --check`; schema không đổi trong phần metrics hiện tại. |
| Production Next.js build | **PASS** | Next.js 15.5.25 compile, typecheck, generate static pages và hoàn tất build. |
| Playwright mock E2E | **42/42 PASS** | Chạy trên branch hiện tại bằng Chromium, desktop/mobile, sau build; không gọi backend thật. |
| Fanpage & market UI walkthrough | **PASS — demo mode** | Playwright CLI mở route, xác nhận form nhóm/nguồn/crawl và report mẫu; UI hiện rõ nhãn demo. Đây không phải bằng chứng UI real-mode cho market crawl. |
| Direct crawler trial (15:18), `https://taphoammo.vn/` | **PASS — 4 URL cùng host** | `crawl_public_site` xác minh `robots.txt`, giới hạn 4 trang; lượt này chỉ giữ kết quả trong tiến trình. Site có trang chủ, ưu đãi Moma Cloud, chatbot AI và Plugin WP Invoice Generator; website không cung cấp views/interactions/comments/follower, nên không đủ để kết luận hot trend. |
| API + worker market crawl trên PostgreSQL (16:27) | **PASS — persisted flow** | PostgreSQL 18.3/pgvector 0.8.2 đã migrate 0001→0012. API tạo tài khoản/workspace, nhóm và nguồn; `POST .../crawl` chạy inline worker, job `succeeded`; lưu **4 MarketEvidence, 4 MarketObservation, 4 raw snapshots có SHA-256**, report và `next_due_at` đúng 12 giờ. Raw file nằm trong local storage cô lập. |
| FastAPI ASGI → Redis/Celery queue `agent` (17:05) | **PASS — actual worker process** | PostgreSQL 18.3/pgvector 0.8.2, Redis 8.6.3, Celery 5.6.3 `solo`; API tạo disposable owner/workspace/group/source cho `https://example.com/`, dispatch `market_research_task` lên `agent`; worker hoàn thành job/cycle, report `deepseek_not_configured`, lưu 1 evidence/observation/raw snapshot và next due +12h. Không gọi LLM hoặc Meta. |
| Celery Beat → recovery/default → market/agent queue (17:07) | **PASS — scheduled cycle** | Beat chạy cấu hình thật của app (recovery mỗi phút), gửi `recover_due_jobs`; worker trả `1`, tạo scheduled cycle, dispatch market task và lưu report/evidence. DB readback: `scheduled:20260925T100610`, cycle/job `succeeded`, 1 evidence, observation và raw snapshot; source/group next due +12h. Beat chỉ được chạy qua một tick có due job; chưa chờ lịch 12h thật. |

URL của crawl persisted: [trang chủ](https://taphoammo.vn/), [Chatbot AI 24/7](https://taphoammo.vn/chatbot-ai-tra-loi-khach-24-7), [ưu đãi Moma Cloud](https://taphoammo.vn/mung-quoc-khanh-02-09-moma-cloud-giam-den-50), [Plugin WP Multi SMTP](https://taphoammo.vn/plugin-wp-multi-smtp-gui-email-khong-gioi-han-qua-gmail).

| DeepSeek, Meta và browser real mode cho market crawl | **NOT RUN** | Không có `DEEPSEEK_API_KEY` trong process/env đã kiểm tra; report ghi `deepseek_not_configured`. Không gọi Meta. API acceptance dùng ASGI in-process, chưa chạy Uvicorn/Compose hoặc browser real mode; worker `solo` trên macOS, chưa kiểm chứng prefork Linux/process restart/MinIO. |

Runtime acceptance commands/config: Python 3.11.16 dependency target isolated; `alembic upgrade head` against fresh PostgreSQL 18.3/pgvector 0.8.2; Redis 8.6.3; `python -m celery -A services.worker.celery_app:celery_app worker --loglevel=INFO --queues=default,agent --pool=solo --concurrency=1`; `python -m celery -A services.worker.celery_app:celery_app beat --loglevel=INFO --schedule=/private/tmp/.../celerybeat-schedule`. API was exercised with `httpx.ASGITransport` and `INLINE_JOBS=0`; storage was local, `EMBEDDING_PROVIDER=none`, retrieval lexical, DeepSeek key empty. Services and database were isolated under `/private/tmp`; no shared/production database was used.

## Snapshot trước — Meta Page connector, 2026-09-24

Snapshot gốc là PR branch head `1f99bb7709f356975637b241895a34bc50e9764f`; hosted backend workflow [#68](https://github.com/thanh1912-ut/Agentic-AI-Social-Media-Marketing-Platform/actions/runs/35961071754) pass. Các kiểm tra lịch sử bên dưới thuộc snapshot Meta/PR base, không phải bằng chứng runtime cho feature nghiên cứu thị trường.

## Meta Page connector — local snapshot, 2026-09-24

| Check | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| `tests/test_meta_client.py` | **17 passed** | `httpx.MockTransport`: verify Page, text/photo request shape, history paging, counts/nulls, unsafe cursor/URL and sanitized errors. Không gọi Meta thật. |
| `npm run typecheck --workspace @agentic/web` | **PASS** | Các trang Settings, Publishing và Analytics dùng DTO của OpenAPI sinh tự động. |
| `scripts/export_openapi.py`, TypeScript `gen:api`, `scripts/export_openapi.py --check` | **PASS** | Thêm route/schema Meta và sinh lại `packages/contracts/openapi.json`, `apps/web/src/lib/api/schema.d.ts`. |
| `git diff --check`, Python `compileall` | **PASS** | Kiểm tra whitespace/syntax; không xác minh PostgreSQL migration hoặc job behavior trên dịch vụ thật. |
| API/worker acceptance và live Meta | **NOT RUN / NOT VERIFIED** | Chưa có API/worker fixture cho publish/reconcile/history sync trong lượt này; chưa cấu hình Page token trong backend của worktree và chưa gọi Graph thật. Xem [Meta feasibility spike](meta-feasibility-spike.md). |


## Live DeepSeek adapter smoke — 2026-09-24 13:00–13:02

| Check | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| `tests/test_deepseek_api_smoke.py` opt-in, Python 3.11.16 | **PASS — 1 passed** | Test đọc `DEEPSEEK_API_KEY` từ ignored local `.env` mà không in giá trị; bật `RUN_DEEPSEEK_API_SMOKE=1`. Account model-list có `deepseek-flash`; một Chat Completions request trả JSON hợp lệ theo `DeepSeekSmokeResult` Pydantic schema. Input chỉ là `{"ok":true,"provider":"deepseek"}`; không gửi tài liệu, Brand Profile hoặc campaign data. Adapter, factory và test file được đối chiếu byte-for-byte với code trên PR branch `codex/product-v1-completion`. |
| Token usage, model latency và chi phí của smoke | **NOT CAPTURED / UNAVAILABLE** | Pytest xác nhận kết quả nhưng không in/lưu `GenerationMetadata` usage hoặc latency; test không tạo cost record. Estimated cost tiếp tục được biểu diễn là unavailable, không phải 0. |
| Phạm vi chưa được chứng minh | **NOT VERIFIED** | Đây chỉ là adapter/model-account smoke, không gọi Brand Profile/content worker/API/browser flow; không chứng minh RAG SME quality, production secret provisioning, deployment hoặc ngân sách vận hành. |

Key chỉ được cấu hình trong ignored `.env` của isolated test checkout; không được đưa vào commit/PR. Người dùng đã chấp thuận data flow, nhưng smoke này chỉ gửi payload tổng hợp. Meta Graph API docs đã thử tìm kiếm và mở trực tiếp lần nữa; official search không trả kết quả, các trang `developers.facebook.com` trả HTTP 429. Kết quả mirror ngoài Meta không được xem là nguồn xác minh; connector vẫn `VERIFY CURRENT META API` / `BLOCKED_EXTERNAL`.

## Production Host/proxy, body-size và DeepSeek transport — 2026-09-24

| Check | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| Host allowlist và proxy trust | **PASS** | Production yêu cầu `ALLOWED_HOSTS` tường minh, từ chối Host lạ, wildcard toàn cục và wildcard sai dạng. `FORWARDED_ALLOW_IPS` chỉ nhận IP/CIDR hợp lệ; Uvicorn entrypoint nhận đúng danh sách cấu hình. Chưa kiểm tra địa chỉ proxy thật ở deployment. |
| Tổng request body | **PASS** | 13 focused tests cho giới hạn theo Content-Length và streamed body, request đúng ngưỡng, lỗi 413/error envelope/request ID; API từ chối trước parse khi Content-Length quá lớn. Mặc định 256 MiB; edge/ingress limit và Compose runtime chưa kiểm chứng. |
| DeepSeek transport | **PASS** | URL có cấu trúc HTTP(S) hợp lệ; production từ chối HTTP. Test không gửi request ra ngoài hoặc dùng API key. |
| Full Python suite | **147 passed, 1 skipped** | Python 3.11 cô lập; lượt full-suite mặc định không bật marker opt-in `RUN_DEEPSEEK_API_SMOKE`, nên live test được skip theo thiết kế. Smoke opt-in riêng ở trên đã pass; một LangGraph pending-deprecation warning. |
| OpenAPI, `compileall`, `git diff --check`, root/override Compose YAML | **PASS** | Cả hai YAML parse được và Dockerfile paths trong root stack/override tồn tại. Đây không thay cho `docker compose config` hoặc `up`; máy hiện không có Docker/Podman. |

GitHub backend workflow [#65](https://github.com/thanh1912-ut/Agentic-AI-Social-Media-Marketing-Platform/actions/runs/35957721239) pass trên code commit `c5bb13e`: pytest và OpenAPI đều thành công. Workflow chạy trước commit docs này.

## Parser formats, giới hạn và upload preflight — 2026-09-24

| Check | Kết quả | Giới hạn |
|---|---|---|
| `tests/test_ingestion_parsers.py` | **10 passed** | Synthetic TXT/CSV, PDF text layer, DOCX paragraphs + tables, XLSX nhiều sheet; kiểm tra locators `text:1`, `page=1`, `paragraph=1`, `table=1;row=1`, `sheet=...;row=1`, Unicode tiếng Việt, CSV blank/missing columns và lỗi empty/corrupt/unsupported. XLSX fixture dùng server-generated path không suffix để tái hiện storage key thật. |
| Parser safety bounds | **PASS** | Text tối đa 2,000,000 ký tự; bảng tối đa 20,000 dòng, 256 cột, 200,000 ô; PDF tối đa 1,000 trang; DOCX/XLSX tối đa 100 MiB sau giải nén và 10,000 archive entries; ảnh tối đa 40,000,000 pixel. Tests hạ ngưỡng bằng monkeypatch để xác nhận lỗi `parser_limit_exceeded`; scanned PDF vẫn báo `pdf_no_text_layer`. |
| Upload API preflight, SQLite API integration | **PASS; 2 cases** | Batch có file hợp lệ rồi file không hỗ trợ trả 415; file sau vượt giới hạn trả 413. Cả hai đều không tạo Document row hoặc object storage file. Upload quét kích thước theo block 64 KiB rồi rewind trước khi ghi, tránh giữ cả batch trong RAM. |
| Reprocess parser identity | **PASS** | Default `PARSER_VERSION` đổi `m2-parser-v1` → `m2-parser-v2`; endpoint reprocess cập nhật document về parser version cấu hình trước khi dispatch. Test xác nhận version mới được lưu. |
| Focused parser + Brand Profile integration suite | **22 passed** | SQLite fixture; bao gồm regression Brand Profile, partial batch, retry và missing-key state. |
| Full Python suite | **137 passed, 1 skipped** | Python 3.11.16; skip duy nhất live DeepSeek smoke vì không có key; một LangGraph pending-deprecation warning. OpenAPI `--check`, compileall và `git diff --check` cũng pass. |
| GitHub hosted backend workflow, commit `c9fc10d` | **PASS**, run #62 | Job `test` chạy pytest và `scripts/export_openapi.py --check`; [workflow run](https://github.com/thanh1912-ut/Agentic-AI-Social-Media-Marketing-Platform/actions/runs/35954996161). |

Parser coverage chứng minh từng parser và validation API ở mức unit/SQLite integration. Runtime smoke dưới đây kiểm chứng thêm DOCX paragraph/table và PDF/XLSX/CSV qua PostgreSQL/Redis/Celery; Docker/Podman/MinIO, Beat và worker process restart còn mở.

## DOCX upload/PostgreSQL worker smoke — 2026-09-24 10:46

| Check | Kết quả | Giới hạn |
|---|---|---|
| Fresh database `agentic_v1_parser_v2`, PostgreSQL 18.3 + pgvector 0.8.2, Alembic 0001→0010; Redis 8.6.3; FastAPI + Celery 5.6.3 `solo` trên queue `default` | **PASS** | Cluster/DB nằm dưới `/private/tmp`; storage local; embedding none/retrieval lexical; không dùng Compose/MinIO/shared database. |
| Upload synthetic DOCX có paragraph và table, sau đó replay cùng `Idempotency-Key` | **PASS** | Hai POST trả 202 và cùng job ID. Parser version `m2-parser-v2`; DB lưu 1 text block, 1 table block, header `Sản phẩm/Giá`, row `Cơm gà/65.000đ`; knowledge index có 2 chunks. |
| Trạng thái provider thiếu key | **PASS** | Không đặt `DEEPSEEK_API_KEY`. Document và knowledge `ready`; job/profile step `failed` với `ai_not_configured`. Không gửi request tới DeepSeek. |
| Dừng dịch vụ disposable | **PASS** | API, Celery, Redis và PostgreSQL đều được dừng sau smoke. |

Đây xác nhận DOCX parsing và lưu trữ qua PostgreSQL/Redis/Celery thật; PDF/XLSX/CSV worker smoke được ghi ở phần tiếp theo. Worker process restart, Beat, Compose, MinIO/S3 và prefork Linux vẫn cần nghiệm thu.

## PDF/XLSX/CSV upload và worker smoke — 2026-09-24 11:08

| Check | Kết quả | Giới hạn |
|---|---|---|
| Fresh database `agentic_v1_parser_formats`, PostgreSQL 18.3 + pgvector 0.8.2, Alembic 0001→0010; Redis 8.6.3; FastAPI và Celery 5.6.3 `solo` trên queue `default` | **PASS** | DB, object storage local và service disposable dưới `/private/tmp`; embedding tắt, retrieval lexical; không dùng Compose/MinIO/shared database. |
| Batch upload PDF text, XLSX và CSV qua API; worker lưu vào PostgreSQL | **PASS** | API trả 202; cả ba documents đạt `extraction_status=extracted`, `knowledge_status=ready`; mỗi loại có 1 document chunk và 1 knowledge chunk. |
| XLSX storage key không extension | **PASS sau fix** | Lượt đầu tái hiện `openpyxl` từ chối storage key không có `.xlsx` dù archive hợp lệ. Parser nay mở binary stream; unit regression dùng path không suffix; lượt chạy lại thành công. |
| Brand Profile khi không có key | **PASS theo giới hạn môi trường** | Document/knowledge của ba file vẫn ready; job/profile step kết thúc `ai_not_configured`. Không gửi request tới DeepSeek. |
| Cleanup services | **PASS** | FastAPI, Celery, Redis và PostgreSQL disposable đã dừng sau smoke. |

Kết quả này xác nhận đường upload → durable job → parser → PostgreSQL knowledge indexing cho PDF/XLSX/CSV trên service stack thật. Chưa xác nhận Compose, MinIO/S3, Beat, worker crash/restart, prefork Linux hoặc Brand Profile generation bằng DeepSeek.

## Upload và Celery worker trên PostgreSQL/Redis — 2026-09-24 10:10

| Check | Kết quả | Giới hạn |
|---|---|---|
| PostgreSQL 18.3 + pgvector 0.8.2, database `agentic_v1_ingestion`; Alembic 0001→0010; Redis 8.6.3; FastAPI thật + local object storage; Celery 5.6.3 `solo` consume queue `default` | **PASS** | Tất cả dịch vụ thử nghiệm cô lập dưới `/private/tmp`; không dùng database dùng chung, Compose hay MinIO. Embedding tắt (`EMBEDDING_PROVIDER=none`), retrieval lexical. |
| `POST` synthetic TXT upload và replay cùng idempotency key | **PASS** | Upload trả 202; replay trả lại cùng job ID. Worker nhận job bền vững từ queue `default`; parser lưu 1 normalized block và 1 knowledge chunk. |
| Trạng thái document/job khi không cấu hình `DEEPSEEK_API_KEY` | **PASS sau khi sửa lỗi được phát hiện trong lần chạy đầu** | `document.status=ready`, `knowledge_status=ready`, `profile_status=failed`; job và Brand Profile step đều `failed` với mã `ai_not_configured`. Lần chạy đầu làm lộ lỗi không commit trạng thái failed; commit `64d663e` sửa và regression tests xác nhận trạng thái retryable vẫn pending, terminal lỗi thành failed. Không gửi request tới DeepSeek. |
| Regression và full Python suite trên source `64d663e` | **124 passed, 1 skipped** (snapshot historical, before parser changes); focused profile/provider suite **6 passed** | Skip duy nhất là live DeepSeek smoke vì không có key; có một warning deprecation hiện hữu của LangGraph. |
| GitHub hosted backend workflow trên commit `64d663e` | **PASS**, job `test` hoàn tất | Đây là workflow check của GitHub trên commit đã push; không thay thế các kiểm tra còn mở bên dưới. |

Smoke này xác nhận upload TXT và provider-missing error path trên một process worker. Chưa xác nhận PDF/DOCX/XLSX/CSV trên service stack này, worker/process crash-restart, Beat, Compose, MinIO/S3, prefork Linux hoặc thành công khi gọi Brand Profile bằng DeepSeek thật.

## Recheck trên source 9d3dd6d — 2026-09-24 09:04

| Check | Kết quả | Giới hạn |
|---|---|---|
| `/Users/lethanh/.codex/worktrees/product-v1-completion/agent/.venv/bin/python -m pytest -q -p no:cacheprovider` | **123 passed, 1 skipped** | Lệnh chạy tại `/private/tmp/agentic-v1-media` với Python 3.11.16; interpreter mượn từ worktree Codex trước đó vì checkout hiện tại không có `.venv`. Skip duy nhất là live DeepSeek smoke do không có key. Một LangGraph pending-deprecation warning. |
| Python 3.11.16 interpreter: `scripts/export_openapi.py --check` và `-m compileall -q database services packages tests`; Python 3.13 YAML parse; `git diff --check` | **PASS** | Python bytecode cache ghi vào `/private/tmp`; YAML parse chỉ đọc cấu hình, không chạy Compose services. |
| Frontend `typecheck`, `npm test`, `lint`, `build` | **PASS; 45 Vitest passed** | Node 26.7.0/npm 11.19.0; Vite native-loader warning; build hoàn tất. |
| `E2E_PORT=3102 npm run test:e2e --workspace @agentic/web -- --workers=1` | **42 passed** (desktop/mobile Chromium) | MSW/mock API; webServer chạy generated standalone server như Docker image, sau khi copy `public/` và `.next/static/` vào standalone tree. Cần quyền sandbox mở rộng cho loopback. |
| SQLite migration + real `manual-workflows.real.spec.ts` | **1 passed** | Database mới trong `/private/tmp`, migration 0001→0010, FastAPI thật, local object storage, `INLINE_JOBS=1`; login/register → campaign → manual post → upload ảnh → version 2 → approve → XLSX download. Không MSW, Redis, DeepSeek, SMTP hoặc Meta; API process đã dừng sau lượt chạy. Next standalone dùng cùng helper với mock E2E. |
| DeepSeek API smoke | **SKIPPED** | Không có `DEEPSEEK_API_KEY`; không gửi request hoặc phát sinh chi phí. |
| Meta documentation/API smoke | **NOT VERIFIED** | Trong audit ngày 2026-09-24, thử lại bốn trang developer chính thức và tìm kiếm docs; trang đều trả HTTP 429, search không có kết quả. Không gọi Meta API. Giữ `VERIFY CURRENT META API` và `BLOCKED_EXTERNAL`. |
| Full Compose/MinIO/Beat/prefork runtime, SMTP delivery, SME retrieval acceptance | **NOT VERIFIED** | Docker/Podman/MinIO không có; thiếu SMTP/mailbox, DeepSeek key và corpus SME được phép dùng. Disposable PostgreSQL/browser checks được ghi riêng bên dưới; chúng không xác nhận Compose hay deployment runtime. |

GitHub check-run `test` là hosted check trên source commit `9d3dd6d` và có kết luận success; không gộp workflow runs cũ vào con số test local. Trong lượt sửa test harness, lần thử đầu dùng standalone server nhưng thiếu public/static assets nên login form không render; `apps/web/scripts/prepare-standalone.mjs` nay chuẩn bị các asset giống `infra/docker/web.Dockerfile`, và kết quả 42 + 1 pass ở trên là lượt chạy sau khi sửa. Test local không gọi DeepSeek/SMTP/Meta. Các kết quả PostgreSQL recovery, migration cũ 1536 chiều và PostgreSQL real browser smoke bên dưới là những lượt trước đó, không phải runtime PostgreSQL của lần recheck này.

## Runtime và load smoke bổ sung — 2026-09-24, branch snapshot `bb9665c`

| Check | Kết quả | Giới hạn |
|---|---|---|
| PostgreSQL 18.3 + pgvector 0.8.2, Alembic upgrade 0001→0010 | **PASS**, head `0010_flexible_embedding_dimensions` | Cluster/database mới dưới `/private/tmp/agentic-v1-runtime.opiIsx`, port 55432; không đụng PostgreSQL dùng chung. |
| `E2E_REAL_API_BASE_URL=http://127.0.0.1:18100 E2E_REAL_PORT=13102 npm run test:e2e:real --workspace @agentic/web -- manual-workflows.real.spec.ts --workers=1` | **1 passed** trên Chromium, API FastAPI thật và PostgreSQL 18.3; campaign → manual post → upload media → version 2 → approval → XLSX download | `NEXT_PUBLIC_USE_MOCKS=0`; local storage; không MSW, không DeepSeek, SMTP hay Meta. Worker queue không tham gia flow này. Dữ liệu ở DB thử nghiệm tạm. |
| `python scripts/load_smoke.py --url http://127.0.0.1:18100/readyz --requests 100 --concurrency 10` | **100/100 HTTP 200**, mọi response báo database/Redis/object storage ready; 0 lỗi, 0 retry; 852.77 req/s, p50 7.83 ms, p95 38.05 ms, max 40.54 ms | Chỉ endpoint readiness trên API một process, PG 18.3/pgvector, Redis 8.6.3 và local storage trên máy phát triển. Không đo campaign/write path, job queue, provider, multi-process hay production capacity. |
| Redis readiness outage/recovery | **PASS** | Dừng đúng Redis cô lập tại port 56379 làm `/readyz` trả 503 và `redis=false`; bật lại Redis thì `/readyz` trả 200/ready ở probe kế tiếp. Không retry request ngầm. Đây không phải retry/recovery của Celery job. |
| `scripts/load_smoke.py` syntax + loopback guard | **PASS** | Python compile và kiểm tra hostname/IP loopback; script từ chối target ngoài loopback, không nhận query/fragment và không retry. |

## Real-mode metrics E2E bổ sung — 2026-09-24

| Check | Kết quả | Giới hạn |
|---|---|---|
| `E2E_REAL_API_BASE_URL=http://127.0.0.1:18101 E2E_REAL_PORT=13102 npm run test:e2e:real --workspace @agentic/web -- manual-workflows.real.spec.ts --workers=1` | **1 passed** trên Chromium, FastAPI thật và PostgreSQL 18.3/pgvector 0.8.2 | Cụm/database mới dưới `/private/tmp/agentic-v1-metrics.KpVJtB`, port 55433; migration 0001→0010. Test không dùng MSW: campaign → manual post → media → approval → XLSX → lưu một dòng metrics snapshot → dashboard API readback xác nhận `reach=250`, `sample_size=1`, `coverage=1`; UI recommendation abstains với “Chưa đủ bằng chứng”. API và PostgreSQL đã dừng sau lượt chạy. Không gọi DeepSeek, SMTP hoặc Meta. |
| `npm run lint --workspace @agentic/web` | **PASS** | ESLint frontend sau khi sửa real-mode test. |

Một snapshot đơn chỉ xác nhận nhập liệu và phép tổng hợp hoạt động trên PostgreSQL; nó không đủ dữ liệu để đưa recommendation có căn cứ. Vì vậy test yêu cầu giao diện abstain, và không xem kết quả là xác nhận hiệu quả marketing.

## PostgreSQL/API restart persistence smoke — 2026-09-24

| Check | Kết quả | Giới hạn |
|---|---|---|
| Fresh PostgreSQL 18.3/pgvector 0.8.2 database; Alembic `upgrade head`; FastAPI thật trên `127.0.0.1:18102` | **PASS** | Database `agentic_v1_restart` trên cụm test port 55433, migration 0001→0010. Test tạo user/workspace qua `POST /api/v1/auth/register` và campaign qua `POST /api/v1/workspaces/{workspace_id}/campaigns`; cả hai trả 201. |
| Clean restart và readback | **PASS** | Dừng Uvicorn; PostgreSQL `pg_ctl -m fast -w stop`, rồi khởi động PostgreSQL và FastAPI lại. Login lại trả 200; `GET /api/v1/workspaces/{workspace_id}/campaigns?page_size=100` trả 200 và chứa cùng campaign ID/tên đã tạo trước restart. Test dùng local storage và không gọi DeepSeek/Meta/SMTP. |

Phép thử này chứng minh dữ liệu account/workspace/campaign còn trong PostgreSQL qua clean restart API và database process. Nó không chứng minh Celery worker process restart, Redis queue durability, Beat, MinIO, Compose hay restart khi có transaction/job đang chạy; các hạng mục đó vẫn mở.

### Scenario chi phí DeepSeek, không phải usage thực

Ngày 2026-09-24, bảng giá DeepSeek ghi `deepseek-flash` (DeepSeek-V4.1-Flash) ở peak là **$0.30/1M input token cache miss**, **$0.006/1M input token cache hit**, **$1.20/1M output token**; off-peak bằng nửa. Từ 2026-09-14, request dùng `deepseek-v4-pro` cũng được route sang Flash và tính giá Flash cho đến V4.1-Pro. Peak theo giờ Việt Nam là thứ Hai–thứ Sáu 08:00–11:00 và 13:00–17:00. [DeepSeek Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/), [V4.1-Flash release](https://api-docs.deepseek.com/news/news260910/).

Stress scenario: **5 SME × 200 job sinh/sửa bài = 1.000 job/tháng**; giả định mỗi lần gọi dùng 48.000 input token (coi trần 48.000 ký tự của adapter như 48.000 token), 8.192 output token, toàn bộ input cache miss và peak pricing. Một lần gọi tối đa tốn khoảng **$0.02423**; nếu mọi job đều cần thêm một lần repair cùng mức tối đa, ước tính là **$48.46 ≈ 1.269.188 đồng/tháng**, dùng tỷ giá bán USD 26.190 VND của Vietcombank cuối ngày 2026-09-23. [VOV, tỷ giá ngày 24/09/2026](https://vov.vn/thi-truong/ty-gia-usd-hom-nay-249-chi-so-usd-index-tang-len-10112-diem-post1335364.vov).

Con số này là scenario bảo thủ cho content generation/revision, không phải quote hay bảo đảm ngân sách: 48.000 ký tự không tương đương chính xác 48.000 token; chưa có usage thực; chưa cộng Brand extraction, số lần gọi ngoài scenario, hosting, database, Redis, object storage, email, thuế hoặc vận hành. Vì vậy chưa thể kết luận tổng OPEX đạt 2–5 triệu đồng/tháng; cần ghi nhận token usage thật từ job/workspace và lấy báo giá hạ tầng trước pilot.

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
| Earlier RAG evaluation snapshot, Python suite; OpenAPI check; `compileall`; Compose YAML; `git diff --check` | **123 passed, 1 skipped; PASS** cho các kiểm tra còn lại | Historical snapshot before later parser/account/security changes. Latest hardening verification is in the section at the top of this report. Live DeepSeek smoke remains the only skip; Compose runtime has not run because Docker/Podman are unavailable. |

Model choice là local `intfloat/multilingual-e5-small`, pinned revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 dimensions. Tokenizer revision đó khai báo context 512; chunker v3 dùng cửa sổ 300 token/overlap 40 để chừa khoảng đệm. Chỉ public model weights được tải; workspace documents/queries được encode tại worker. Existing documents cần reprocess sau khi chuyển provider/model/chunker. `.env.example` bật local model; OpenAI embeddings vẫn cần data-flow approval riêng. Chất lượng retrieval cần kiểm chứng tiếp bằng tài liệu/query do SME pilot cung cấp. [Pinned tokenizer config](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/tokenizer_config.json).

Cập nhật: 2026-09-24 05:32 (Asia/Ho_Chi_Minh). Kết quả real-mode mới nhất chạy trên commit `4f9a97a` của branch `codex/product-v1-completion`. Backend full suite **105 passed, 1 skipped** và frontend **43 passed/typecheck/lint/build** được chạy trên implementation commit `43ab2d3`; `4f9a97a` chỉ mở rộng real-mode browser acceptance test. Project owner đã chấp thuận gửi đoạn trích tài liệu, Brand Profile và strategy/topic/date của slot đã chọn tới DeepSeek.

Môi trường: Python 3.11.16, Node.js 26.7.0, SQLite và PostgreSQL 18.3 disposable, local object storage, Chromium desktop/mobile. Bộ Playwright mock dùng MSW; real-mode Playwright kết nối FastAPI thật và đã chạy riêng với cả SQLite lẫn PostgreSQL.

## Snapshot MEDIA-001 trước đó — historical runtime checks

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
| Celery worker event loop và queue routing trong snapshot này | **PASS — 4 focused worker tests** | Hai lần gọi coroutine dùng lại event loop của process; Beat entry và router đều chọn queue `default`. Lúc chạy snapshot này chưa khởi chạy Beat; Beat process được nghiệm thu riêng ở mục đầu tài liệu ngày 2026-09-25. |

Trong snapshot này không có DeepSeek key nên không có model-list/live JSON request hoặc usage cost/latency thực. Không có Meta credentials và không đăng bài thật. Docker/Podman và MinIO không khả dụng, nên Compose, document-ingestion task, worker process restart và object-store deployment chưa được kiểm tra ở thời điểm đó. Recovery với job có lease hết hạn đã chạy qua Redis; worker dùng Celery `solo` trên macOS. Lần thử pool prefork dừng trong Celery/Billiard trước khi vào code dự án, nên prefork Linux vẫn cần chạy. 14 campaign-slice E2E dùng MSW; real-mode E2E riêng kết nối FastAPI và PostgreSQL/SQLite thật. Backend media integration tests dùng API fixture suite; các kiểu kiểm thử không gộp chung.

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

- PostgreSQL/Redis: migration 0001→0010, manual API/browser flow và readiness failure/recovery đã chạy trên PostgreSQL/Redis cô lập; chưa kiểm tra full Compose, Celery job path/restart trong lượt này, MinIO/S3, production pool/proxy hoặc shared PostgreSQL service.
- DeepSeek live: user đã chấp thuận đoạn trích tài liệu, Brand Profile, campaign strategy và slot topic/date đã chọn. Adapter smoke đã xác minh model list và một JSON generation tổng hợp; chưa ghi token/latency/cost, chưa chạy full Brand→content worker/browser path. Key mới có trong ignored local checkout, chưa nằm ở production secret store.
- Meta publish/metrics: connector đã triển khai cho pilot một Page, nhưng token chưa được đặt trong backend của worktree. Chưa chạy Page verification, publish hoặc historical sync với Meta thật; quyền App/Page, Graph fields và token lifetime còn cần kiểm chứng.
- Real-mode browser E2E đầy đủ: campaign → post → media → approval → export đã chạy trên SQLite và PostgreSQL bằng API thật. Analytics/recommendation real browser smoke trước đó chạy trên SQLite; AI generation/revise vẫn chỉ có API/worker fixture và mock browser, chưa gọi DeepSeek hay kiểm tra real-provider browser path. MinIO chưa nghiệm thu.

## Phạm vi bằng chứng

Campaign, manual post/version, approval and export have SQLite/real-mode PostgreSQL browser coverage; generation and AI revise have SQLite API/worker fixture tests; live-provider browser run is outstanding. Strategy/slot editing and click-through to a slot-specific job have desktop/mobile MSW coverage. Content fixtures validate versioned workspace context, relevance-filtered active sources, exact citation metadata, slot strategy/topic/date and unapproved draft/version behavior; fake models never send data to DeepSeek. User approved sending Brand Profile, document excerpts and selected slot strategy/topic/date; a separate synthetic adapter smoke now passes, but no real workspace content has been sent. Backend-only company/brand/slot database IDs are excluded from model prompts, and external embeddings remain separately gated. Manual metrics, recommendation feedback, Apply draft, accept/version conflict and REC-002 outcome persistence are checked by SQLite API tests; UI outcome flow uses MSW. Tenant tests are not a full security audit. The previously reproduced path traversal was fixed and has regression coverage; this turn's Redis readiness outage check does not verify rate-limit behavior. Reverse proxy and edge controls remain unverified. See [security-review.md](security-review.md).

## Lệnh tái kiểm tra

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
.venv/bin/python -m compileall -q database services packages
(cd apps/web && npx tsc --noEmit --incremental false && npm test && npm run lint && npm run build)
npm audit --audit-level=high
```

Run live DeepSeek smoke only in a secured server environment after the approved API key is provisioned. Full PostgreSQL/Redis/MinIO runtime and Meta checks still require isolated services/credentials. Never write secrets into the repository or test report.
