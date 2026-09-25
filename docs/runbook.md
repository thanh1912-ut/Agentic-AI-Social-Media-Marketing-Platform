# Runbook phát triển và pilot

> Hướng dẫn này phản ánh cấu hình hiện có và sẽ được cập nhật sau khi các lệnh được chạy thật. Không dùng ví dụ local cho production. Không ghi secrets vào Git, log hay tài liệu.

## Runtime yêu cầu

- Python 3.11+ theo `pyproject.toml`.
- Node.js >=22 và npm, theo root package manifests/lockfile.
- Docker Compose v2 cho stack đầy đủ; PostgreSQL có extension pgvector, Redis, MinIO.
- DeepSeek API key server-side để chạy LLM thật. Chủ dự án đã chấp thuận gửi đoạn trích tài liệu, Brand Profile, cùng campaign strategy, slot topic và ngày đã chọn tới DeepSeek khi sinh theo slot.
- Semantic retrieval mặc định trong `.env.example` dùng FastEmbed multilingual E5 chạy tại worker; text và query không rời runtime. Tải model weights cần mạng ở lần đầu và cache nằm ở `EMBEDDING_CACHE_DIR`. `EMBEDDING_PROVIDER=none` bật lexical-only. Embedding provider ngoài như OpenAI vẫn bị chặn khi chưa có chấp thuận riêng (`EMBEDDING_DATA_FLOW_APPROVED=1`).
- Pilot Facebook Page cần một workspace ID, Page ID và Page access token được đặt ở server. OAuth/App Review cho Page của khách ngoài team cần một giai đoạn riêng.

DeepSeek docs được xem lại ngày 2026-09-24: dùng `deepseek-flash` (V4.1-Flash); `deepseek-v4-pro` được route sang Flash và tính giá Flash từ 14/9 cho đến khi V4.1-Pro ra mắt. Giá peak hiện tại là $0.30/M input cache miss, $0.006/M cache hit, $1.20/M output; off-peak bằng một nửa. Repo mặc định `LLM_DEFAULT_MODEL=deepseek-flash`; trước khi vận hành cần chạy smoke list-model với key của account cụ thể và đo usage thật. Xem [DEC-003](decisions.md#dec-003--deepseek-làm-provider-llm-duy-nhất) và scenario có giả định tại [test-report.md](test-report.md). Pilot Meta đang triển khai cho một Page; các URL Page Feed, Page Insights, permissions và access-token guide trả HTTP 429 trong lần truy cập 2026-09-24. Phiên bản, quyền, token lifetime, fields publish/metrics và rate limits vẫn `VERIFY CURRENT META API`; chỉ mở cho Page thật sau khi xác minh bằng app/token được cấp quyền. Xem [Meta feasibility spike](meta-feasibility-spike.md).

## Password reset, invitation và email delivery

Account lifecycle có endpoint/UI cho yêu cầu reset mật khẩu, đặt mật khẩu mới, preview/chấp nhận lời mời và gửi lại lời mời. Email là tùy chọn. Reset link dùng một lần và hết hạn theo `PASSWORD_RESET_EXPIRE_MINUTES`; reset thành công sẽ thu hồi mọi reset token đang mở, refresh session và access token của tài khoản. Access tokens có password-version claim; token cũ do phiên bản trước phát hành được kiểm tra bằng thời điểm `iat` đến khi tự hết hạn. Invitation link hết hạn sau 7 ngày.

Để bật email ở server, đặt `WEB_BASE_URL` thành origin HTTPS của frontend production cùng `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_STARTTLS`, `SMTP_SSL`, `SMTP_TIMEOUT_SECONDS` và `EMAIL_FROM`. Với port submission thông dụng dùng `SMTP_STARTTLS=1`, `SMTP_SSL=0`; với SSL implicit, cấu hình hai cờ theo yêu cầu nhà cung cấp. Username/password phải cùng có hoặc cùng trống; không bật đồng thời STARTTLS và SSL. SMTP password chỉ được cấu hình qua secret store/runtime, không commit `.env`.

Nếu SMTP chưa được cấu hình, forgot-password luôn trả câu trung tính và không tạo link/token có thể dùng; giao diện yêu cầu người dùng liên hệ quản trị viên nếu không nhận được thư. Invitation vẫn được tạo và UI hiển thị link để owner chuyển cho thành viên qua kênh riêng. Nếu SMTP từ chối email lời mời, server cũng trả link fallback. Reset email chạy sau khi response trung tính đã được gửi; nếu SMTP lỗi, người dùng có thể yêu cầu link mới và token chưa dùng sẽ hết hạn theo TTL hoặc bị thu hồi khi một link khác được dùng. Email delivery chưa có durable queue/retry hoặc delivery telemetry. SMTP errors được chuẩn hóa để không đưa diagnostic hoặc credential vào API response. Unit/integration tests dùng fake SMTP; trước pilot phải gửi tới mailbox kiểm soát, xác minh TLS, From/domain policy, deliverability và quy trình xử lý khi không nhận được thư.

## PostgreSQL migrations

`alembic upgrade head` đã được xác minh tới migration 0012 trên PostgreSQL 18.3 cô lập, có pgvector 0.8.2. Migration 0010 đổi cột vector cố định thành flexible vector, giữ row cũ 1536 chiều; vector 384 chiều mới được insert và retrieval filter đúng model identity. Migration 0012 thêm nhóm Page/thị trường và evidence; API + inline worker crawl website thật đã lưu bằng chứng trên PostgreSQL test DB. SQLite upgrade/downgrade tới 0012 pass theo test branch. PostgreSQL migration 0010 downgrade có chủ ý từ chối khi còn vector không phải 1536 chiều. FastAPI/browser manual flow cũng pass trên PostgreSQL + local storage. Migration environment tự tạo/nâng `alembic_version.version_num` lên `VARCHAR(128)` trên PostgreSQL vì revision IDs dài hơn giới hạn mặc định 32 ký tự. Một smoke test tạo user/workspace/campaign qua API, clean-stop rồi khởi động lại FastAPI và PostgreSQL, sau đó login/đọc lại campaign thành công. Runtime recovery và upload TXT/DOCX/PDF/XLSX/CSV đã được xác minh trên PostgreSQL/Redis cô lập với Celery `solo`: worker đọc job từ queue `default`, lưu normalized/document/knowledge chunks; idempotent replay trả cùng job. XLSX parser đọc binary stream nên hỗ trợ storage key server sinh không có suffix. Khi thiếu DeepSeek key, document/knowledge vẫn ready, job/profile step kết thúc `ai_not_configured`. Compose, Beat, worker process restart, prefork Linux và MinIO vẫn chưa được nghiệm thu; xem [báo cáo upload runtime](test-report.md).

## Document parser bounds and versioning

`.env.example` defaults to `MAX_UPLOAD_BYTES=26214400` (25 MiB per file), `MAX_FILES_PER_REQUEST=10`, and `PARSER_VERSION=m2-parser-v2`. Uploads are checked for supported MIME/extension and byte limits across the entire batch before object writes; files are scanned in 64 KiB chunks and rewound so the batch is not retained in memory. A rejected file makes the whole upload request fail without partially creating document rows or objects.

Parser code has fixed safety limits: 2,000,000 text characters; 20,000 table rows, 256 columns and 200,000 cells; 1,000 PDF pages; 100 MiB uncompressed and 10,000 entries for DOCX/XLSX archives; and 40,000,000 image pixels. Limit violations produce `parser_limit_exceeded`; scanned PDFs without a text layer produce `pdf_no_text_layer`. These parser bounds are implemented in `services/ingestion/parsers.py`; changing parser behavior or limits requires bumping `PARSER_VERSION`.

After deploying a new parser version, queue each active existing document through `POST /api/v1/workspaces/{workspace_id}/documents/{document_id}/reprocess`. Reprocess writes the current configured parser version before creating the durable job, so knowledge indexing uses that identity. Brand Profile extraction still requires a provisioned DeepSeek key; successful parsing/indexing remains visible even when the provider is not configured.

## Embedding local và đổi model

`.env.example` chọn `EMBEDDING_PROVIDER=fastembed`, `EMBEDDING_MODEL=intfloat/multilingual-e5-small`, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 chiều và `RETRIEVAL_MODE=semantic_vector`. E5 cần prefix `passage:` cho text index và `query:` cho truy vấn; adapter thêm prefix tự động. Chunker `vi-token-window-v3-300` giữ cửa sổ 300 token với overlap 40, chừa khoảng an toàn so với tokenizer max 512. Lần đầu xử lý tài liệu, worker tải weights vào cache. Trong Compose, named volume `embedding_models` giữ model giữa các lần restart. Sau khi provision cache, đặt `EMBEDDING_LOCAL_FILES_ONLY=1` để cấm tải trong runtime.

Khi đổi provider/model/chunker so với index hiện tại, nội dung cũ không được tự coi là đã index bằng cấu hình mới. Reprocess từng tài liệu đang hoạt động qua `POST /api/v1/workspaces/{workspace_id}/documents/{document_id}/reprocess`; worker sẽ chuẩn hóa/index lại bằng provider cấu hình và tạo Brand Profile run mới. Chỉ sinh bài semantic sau khi các nguồn liên quan đã reprocess thành công. Đánh giá hiện tại dùng corpus synthetic nhỏ; nghiệm thu retrieval cho pilot cần thêm truy vấn/tài liệu thật được workspace owner cho phép dùng.

## Cài local

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
npm ci
cp .env.example .env
```

Sửa `.env` cục bộ trong editor, không paste key vào chat. Provision `DEEPSEEK_API_KEY` trong môi trường server/secret store; không commit `.env`. Đặt `LLM_PROVIDER=deepseek`, `LLM_DEFAULT_MODEL` thành model ID được DeepSeek API list cho tài khoản, `DEEPSEEK_MAX_TOKENS=8192`, `LLM_MAX_INPUT_CHARS=24000` và `AI_REQUEST_TIMEOUT_SECONDS=120`. Không cần `OPENAI_API_KEY` cho LLM. Brand Profile extraction, content-generation và AI-revise workers gọi cùng adapter DeepSeek sau khi nhận job; thiếu key sẽ khiến job kết thúc với lỗi `ai_not_configured`. API generate/revise trả `202` + `job_id`; Brand Profile hiện tại phải được user xác nhận trước. Revise yêu cầu `version` hiện tại và `Idempotency-Key`, tạo PostVersion mới (`ai_revised`), không ghi đè lịch sử; scope `media` chỉ sửa mô tả ảnh, không tạo/thay ảnh. Bài vẫn cần người duyệt; worker không tự publish. Job content có thể retry qua `/api/v1/jobs/{job_id}/retry` trong giới hạn cấu hình; worker kiểm lại base version trước khi lưu. Để retrieval lexical, giữ `EMBEDDING_PROVIDER=none` và `RETRIEVAL_MODE=lexical`.

## Kết nối một Facebook Page cho pilot

1. Đăng nhập bằng tài khoản **owner** và lấy workspace ID từ `GET /api/v1/me`
   (`active_workspace_id`) hoặc `GET /api/v1/workspaces`. Chọn đúng Page ID trong
   tài khoản Meta của bạn; lấy Page access token bằng quy trình chính thức của
   app/Page. [Meta Facebook API collection trên Postman](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api)
   là điểm tham khảo, không thay cho kiểm tra quyền/Graph API trên app thật.
2. Trong `.env` local đã được `.gitignore` bỏ qua, điền
   `META_WORKSPACE_ID=<workspace-id>` và `META_PAGE_ID=<page-id>`; đặt
   `META_PAGE_ACCESS_TOKEN` **chỉ trên server**. Giữ `META_GRAPH_VERSION=v26.0`
   làm giá trị khởi đầu của pilot, rồi xác minh version này hoạt động với app
   và Page thật. Với deployment, đặt bốn biến trong secret store/runtime và
   chỉ cấp cho process backend cần dùng; không đưa token vào `NEXT_PUBLIC_*`,
   frontend, Git, chat, URL query, log hay ảnh chụp màn hình. `META_APP_ID` và
   `META_APP_SECRET` dành cho OAuth tương lai, không thay Page token trong pilot.
   Để tự thu thập Page đối thủ, cấu hình riêng `META_PUBLIC_CONTENT_ACCESS_TOKEN`
   ở backend/worker bằng app/user access token của Meta App đã được duyệt Page
   Public Content Access/Metadata. Đây là quyền app-level và không thể suy ra
   chỉ từ Page Access Token của Page thuộc workspace. Nếu Meta trả lỗi quyền,
   nguồn hiển thị `needs_access`; dùng nhập tay cho đến khi app được duyệt.
   Page views không được giả định có sẵn. Nhóm Facebook hiện vẫn nhập tay.
3. Khởi động lại API/worker sau khi đổi biến môi trường. Đọc
   `GET /api/v1/workspaces/{workspace_id}/meta/connection`, rồi owner gọi
   `POST /api/v1/workspaces/{workspace_id}/meta/connection/verify`. Page ID/name
   server đọc từ Meta phải trùng Page đã cấu hình; bước này đọc tối đa một bài
   để thử quyền đọc feed, không đăng bài. Quyền publish chỉ được Meta kiểm tra
   khi owner gửi một bài cụ thể. Chưa xác minh được identity/feed thì giữ connector ở trạng thái không khả dụng và tiếp tục
   export/đăng thủ công/nhập metrics. Thử với Page và bài mà owner cho phép dùng
   để nghiệm thu.
4. Tạo hoặc chọn bài, gửi duyệt và để owner duyệt **đúng phiên bản hiện tại**.
   Owner bấm đăng riêng cho từng bài bằng
   `POST /api/v1/workspaces/{workspace_id}/meta/publications` với `post_id` và
   `version`; response `202` trả job để theo dõi. Server kiểm lại approval,
   hash nội dung và Page ngay trước khi gọi Meta. Pilot dành cho text và tối đa
   một ảnh khi Page capability đã được xác minh; video/carousel chưa hỗ trợ.
   Đọc `GET /api/v1/workspaces/{workspace_id}/meta/publications` để xem trạng
   thái và external post ID/permalink. Nếu kết quả là `outcome_unknown`, mở Page
   kiểm tra; chỉ owner ghi kết quả qua
   `POST /api/v1/workspaces/{workspace_id}/meta/publications/{publication_id}/reconcile`.
   Không bấm thử lại hoặc để job tự gửi lại khi chưa biết bài đã lên hay chưa.
5. Khi muốn cập nhật số liệu, owner gọi
   `POST /api/v1/workspaces/{workspace_id}/meta/metrics/sync` để nhập bài trên
   Page, gồm bài cũ đăng ngoài nền tảng. Mỗi lượt lấy tối đa 5 trang × 100 bài,
   lưu cursor; bấm đồng bộ tiếp để đi sâu hơn vào lịch sử. Không có bộ lọc ngày.
   Đọc lại qua `GET /api/v1/workspaces/{workspace_id}/meta/page-posts` (phân
   trang `limit` tối đa 100 và `offset`); kiểm tra Page/external post ID,
   `published_at`, `last_synced_at` và các count có thể thiếu: `reactions`,
   `comments`, `shares`. `engagements` là tổng count hiện có, có thể chưa đủ nếu
   một loại count không khả dụng. Chưa có reach/views/clicks hoặc snapshot theo
   cửa sổ đo cho Page posts. Bài lịch sử chỉ dùng cho phân tích, không tự có
   approval hay trạng thái “đã đăng qua nền tảng”. Quyền đọc và khả năng có
   từng count cần kiểm chứng trên Page thật; không điền 0 thay số liệu thiếu.

Nếu token hết hạn hoặc bị thu hồi, thay secret trong server runtime, khởi động
lại process liên quan và xác minh Page identity/capability trước khi tiếp tục.
Không dán token vào chat hay gửi qua request từ browser. Pilot này không làm
OAuth nhiều khách hàng, App Review cho Page ngoài team, lịch đăng tự động,
video/carousel hoặc webhook. Chưa có bằng chứng live cho Page/token/quyền của
chủ dự án; xem [ma trận kiểm chứng](meta-feasibility-spike.md).

## Cấu hình production chung

`.env.example` để `RATE_LIMITS_ENABLED=0` cho local development. Production phải đặt `APP_ENV=production`, `RATE_LIMITS_ENABLED=1`, `COOKIE_SECURE=1`, PostgreSQL `DATABASE_URL`, danh sách `CORS_ALLOWED_ORIGINS` chỉ gồm HTTPS origins cụ thể và một `REDIS_URL` khả dụng; cấu hình production từ chối SQLite, CORS wildcard, limiter bị tắt và S3 dùng credentials `minioadmin`. Auth, upload, content-generation, Meta Page verification và manual market-crawl routes dùng fixed-window Redis limits; production trả `503` cho route bị giới hạn khi Redis không dùng được. Các mức hiện tại được ghi trong [security-review.md](security-review.md). Limit key dựa trên `request.client.host`: sau reverse proxy, cấu hình Uvicorn chỉ tin forwarded headers từ proxy thực tế và xác nhận API không truy cập trực tiếp từ nguồn không tin cậy. Không lấy `X-Forwarded-For` tùy ý làm client identity.

Khi triển khai production, đặt `ALLOWED_HOSTS` thành hostname API thật, ví dụ `api.example.com`; để trống hoặc `*` sẽ làm API từ chối khởi động. `FORWARDED_ALLOW_IPS` phải là danh sách IP/CIDR mà API thực sự nhìn thấy ở proxy; mặc định là `127.0.0.1`, không dùng `*`. Chỉ expose API qua proxy đã tin cậy và giữ `CORS_ALLOWED_ORIGINS` khớp origin frontend.

`MAX_REQUEST_BODY_BYTES` mặc định là `268435456` (256 MiB tổng cho một request); `MAX_UPLOAD_BYTES` mặc định là 25 MiB mỗi file, tối đa 10 file. Giữ body limit ít nhất lớn hơn per-file limit 1 MiB để multipart overhead không làm upload hợp lệ bị từ chối. ASGI trả `413 request_too_large` cho Content-Length vượt ngưỡng và đếm stream khi route đọc body. Cấu hình thêm body-size limit ở reverse proxy/ingress để từ chối traffic trước khi vào API. Production `DEEPSEEK_BASE_URL` phải dùng HTTPS; không đặt credentials hoặc query string trong URL.

## Khởi động full stack

```bash
docker compose up --build
```

Compose chạy PostgreSQL/pgvector, Redis, MinIO, migration, storage init, API, worker và scheduler. API phụ thuộc Redis health; rate limits ở production fail-closed nếu Redis mất kết nối sau startup. Chờ health checks xong rồi xác nhận:

```bash
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/readyz
```

Web chạy ở `http://127.0.0.1:3000`. Khi dùng browser real API, cấu hình `NEXT_PUBLIC_API_BASE_URL` là API origin, không thêm `/api/v1`; đặt `NEXT_PUBLIC_USE_MOCKS=0`. Không fallback sang MSW nếu API lỗi.

## Chạy process riêng khi không có Docker

Chỉ dùng database đã xác nhận là DB test/development, không trỏ vào production. Cấu hình `DATABASE_URL`, `REDIS_URL`, `STORAGE_BACKEND=local`, `STORAGE_ROOT`, `INLINE_JOBS=0` theo môi trường. Chạy migration, rồi các process:

```bash
alembic upgrade head
python -m services.api
celery -A services.worker.celery_app:celery_app worker --loglevel=INFO --queues=default,agent --concurrency=2
```

Scheduler task `services.worker.scheduled_jobs.recover_due_jobs` được route tới queue `default`, queue mà Compose worker consume. Chạy một Beat process duy nhất:

```bash
celery -A services.worker.celery_app:celery_app beat --loglevel=INFO --schedule=.data/celerybeat-schedule
```

Dùng worker và Beat sau khi PostgreSQL/Redis health checks pass; không chạy nhiều Beat instance dùng chung lịch.

Runtime smoke chạy trên PostgreSQL 18.3/pgvector 0.8.2, Redis 8.6.3 và Celery 5.6.3 `solo`. Recovery task đã được route tới `default`; worker xử lý upload/content/research trên các lần acceptance riêng. Lượt 17:02–17:08 xác nhận FastAPI ASGI enqueue market job vào queue `agent`, worker lưu evidence/report, và Beat phát `recover_due_jobs` theo schedule cấu hình; recovery trả 1 khi tạo scheduled cycle rồi market task hoàn tất. Lượt 20:13–20:15 warm-stop worker 1, enqueue job khi worker dừng (Redis `agent` depth 1), start worker 2 và xác nhận job/report/evidence persisted bằng `scripts/worker_restart_smoke.py`. Job dùng một manual-only Facebook Group source cùng dữ liệu tổng hợp; không scrape Facebook, không gọi DeepSeek và báo `deepseek_not_configured`. Beat test chỉ quan sát một due tick, không đợi lịch 12h. Chưa kiểm tra crash khi task đang chạy, `acks_late` redelivery, Compose, MinIO hoặc prefork Linux; lần thử prefork macOS trước đây dừng bên trong Celery/Billiard. Upload TXT, DOCX, PDF, XLSX, CSV có smoke runtime riêng; xem test report. Các dịch vụ disposable đã được dừng; PostgreSQL dùng chung trên máy không bị chạm.

### Nghiệm thu queued job qua worker restart

Chỉ chạy trên PostgreSQL và Redis **loopback, disposable**; database name phải chứa `test`, `smoke`, `acceptance` hoặc `restart`. Script ghi thêm user/workspace/nhóm/nguồn/evidence giả lập và không xóa dữ liệu sau khi chạy. Không cấu hình DeepSeek hay Meta credential; đặt `INLINE_JOBS=0`. Migration phải ở head và Redis `agent`/`default` queues phải trống.

1. Khởi động PostgreSQL/Redis và chạy `.venv/bin/python -m alembic upgrade head`.
2. Khởi động worker 1 bằng lệnh ở mục worker bên trên; chờ `ready`, sau đó dừng bằng Ctrl+C và chờ warm shutdown hoàn tất.
3. Khi không có worker, chạy `.venv/bin/python scripts/worker_restart_smoke.py enqueue`; lưu `job_id` được in ra.
4. Khởi động worker mới với cùng DATABASE_URL/REDIS_URL; chờ task kết thúc.
5. Chạy `.venv/bin/python scripts/worker_restart_smoke.py verify --job-id <job_id>`.

Smoke này chứng minh queued work được xử lý sau khi worker process được thay thế. Nó không chứng minh kill giữa task, unacked message redelivery, production broker failover, Compose, MinIO hoặc Linux prefork.

## Tạo tài khoản và seed

API hiện có register/login và workspace bootstrap. Tạo user test riêng; không dùng tài khoản/DB production. Nếu SMTP chưa được cấu hình, invitation trả link fallback để owner chuyển cho người nhận qua kênh riêng. Không có seed credentials mặc định được nghiệm thu.

Cookie-authenticated refresh/logout yêu cầu header `X-CSRF-Token` khớp cookie `agentic_csrf`; web client gửi token khi refresh session. Bearer-only clients không cần CSRF token nếu không gửi kèm session cookies.

## Mocks và real mode

- Demo UI: `NEXT_PUBLIC_USE_MOCKS=1`; dữ liệu do MSW cung cấp, không phải API evidence.
- Real mode: `NEXT_PUBLIC_USE_MOCKS=0`; UI gọi API, hiển thị lỗi khi backend lỗi, không dùng dữ liệu mock thay thế.
- Campaign supports tenant-scoped create/list/detail and brief/strategy/slot editing. Updates include the latest `version`; stale updates return `409 version_conflict`. Slots contain a date, pillar, format and topic; slot generation reserves one slot and links its generated draft. A repeated idempotency key returns the same job. Slots are locked while a job is active and after a draft is linked; failed/cancelled jobs release the reservation, and retry reclaims it only if campaign context has not changed. Generation by slot sends the approved campaign strategy, selected slot topic/date, Brand Profile and relevant source excerpts to DeepSeek; backend-only IDs stay out of the model prompt. In a post editor, upload JPEG/PNG/WebP images up to `MAX_IMAGE_BYTES` (default 12 MiB) and `MAX_IMAGE_PIXELS` (default 40 million pixels), add alt text, preview, and save attachments as a new immutable post version; removing an attachment also creates a new version. The authenticated content route is workspace-scoped. Approval stores the SHA-256 of the exact version, including attached asset hashes; export includes each image filename, hash, and API path. There is no asset delete endpoint so old versions retain valid references. CSV/XLSX export remains the manual fallback; Page publishing requires the separate owner action and connector capability check.
- Analytics supports manual snapshots: choose a source ID and measurement timestamp, add one or more workspace posts, and enter age-at-measurement plus available metrics. Counts must be integers; cost/revenue may be decimal. Leave unavailable values blank. Duplicate `(workspace, post, source, measured_at)` snapshots return conflict. Only mark attribution valid when its method/window is verified.
- Dashboard uses latest per-post snapshots for the selected source and reports freshness, coverage, pillar/format groups and missing-value notes. Recommendations are deterministic test suggestions with evidence IDs; they abstain on small samples and do not establish causality. Save a proposal to persist its evidence fingerprint, then record useful/not useful/already done feedback. An owner can choose a campaign and Apply to create a pending brief revision; inspect before/after values, then accept or discard. Campaign changes only on accept; a stale base version returns `409` and needs a new revision.
- After an accepted revision has run, choose that campaign and the recommendation's same source on Analytics. Record baseline and follow-up measurement windows, one metric, and a shared post-age range. Windows must not overlap and both cohorts need usable snapshots. The API persists computed values, coverage/sample size, outcome-specific evidence IDs, snapshot IDs and limitations; repeated identical submissions are idempotent. The comparison is observational and must not be presented as causal proof. Apply migration 0007 before using this feature on an existing database.
- LLM fixture tests do not call DeepSeek. API+worker fixture integration verifies the confirmed-profile gate, idempotency, exact-source citations, saved draft/version, slot strategy/topic/date payload, slot retry/cancel handling, AI revise scope, expected-version guard, and reapproval. The live adapter smoke checks that the configured model appears in the account's model list, then makes one structured JSON request; it may incur charges. In a secured environment with the server key provisioned, run `RUN_DEEPSEEK_API_SMOKE=1 .venv/bin/python -m pytest -m api_smoke tests/test_deepseek_api_smoke.py -q`. The user-approved data flow covers Brand Profile, retrieved document excerpts, and selected slot strategy/topic/date; backend-only tenant/brand/content-slot database IDs are not sent in the prompt.
- Real-mode smoke analytics/recommendation đã chạy trên API loopback với SQLite mới và dữ liệu giả lập. `tests/e2e/manual-workflows.real.spec.ts` tự tạo owner/campaign, viết bài, upload ảnh thật, lưu version 2, gửi/duyệt, đọc lại media SHA và approval hash qua API, tạo export và tải XLSX. Test đã pass riêng trên SQLite và PostgreSQL 18 + local storage; không dùng MSW, DeepSeek, Meta hoặc Redis. Trang `Xuất bản` hướng dẫn export/đăng thủ công/nhập số liệu khi Meta chưa kết nối. Các test account/database chỉ tồn tại trong môi trường disposable và được xóa sau test. AI API+worker fixture test không gọi DeepSeek; adapter live smoke đã pass riêng, còn full provider-backed worker/browser flow chưa nghiệm thu.

## Test, OpenAPI và build

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/export_openapi.py --check
PYTHONPYCACHEPREFIX=/tmp/agentic-pycache .venv/bin/python -m compileall -q database services packages
(cd apps/web && npm run gen:api -- --from ../../packages/contracts/openapi.json)
(cd apps/web && npm run typecheck && npm test && npm run lint && npm run build)
(cd apps/web && npm run test:e2e)
```

Với API test đã chạy ở `http://127.0.0.1:8000`, CORS cần cho phép `http://127.0.0.1:3101`; chạy real-mode browser flow từ `apps/web` bằng:

```bash
E2E_REAL_API_BASE_URL=http://127.0.0.1:8000 npm run test:e2e:real -- manual-workflows.real.spec.ts --workers=1
```

Hai Playwright configs build `output: standalone`, copy `public/` và `.next/static/` vào standalone tree giống Dockerfile, rồi chạy `node .next/standalone/apps/web/server.js`. `apps/web/scripts/prepare-standalone.mjs` thực hiện bước copy; vì vậy E2E kiểm tra cùng kiểu server production thay vì `next start`.

Flow đăng ký account ngẫu nhiên mới, tạo campaign/post, upload ảnh, duyệt đúng version và tải XLSX. Dùng database test mới hoặc database cô lập; không trỏ vào production. Nó không gọi DeepSeek/Meta và không kiểm tra worker queue.

Với API local đã sẵn sàng trên PostgreSQL + Redis + object storage, chạy readiness smoke giới hạn loopback:

```bash
.venv/bin/python scripts/load_smoke.py --url http://127.0.0.1:8000/readyz --requests 100 --concurrency 10
```

Script từ chối URL không phải loopback, không retry và không thay cho load test campaign/write path hay production capacity test. Chỉ chạy trên stack cô lập; xem kết quả, scope và giá model trong `docs/test-report.md`.

Không chạy live smoke hoặc real E2E nếu credential chưa được provision. The build requires write access to `apps/web/.next`. Xem `docs/test-report.md` để tách fixture, integration, browser, live LLM và Meta results.

## Migration, backup và restore

Development/test migration:

```bash
alembic upgrade head
alembic current
```

Trên disposable PostgreSQL, `pg_dump -Fc` rồi `pg_restore` sang database mới đã giữ nguyên counts của company/campaign/post/version/approval/media/export. Thư mục local object storage gồm media và XLSX cũng đã archive/restore, so sánh đường dẫn và SHA-256 của 2 object. Đây là smoke test thủ công; chưa có lịch backup tự động, MinIO/S3 recovery hoặc production cutover drill.

Với PostgreSQL tools đã cấu hình qua `PGHOST`/`PGPORT`/`PGUSER` và secret store/pgpass:

```bash
pg_dump --format=custom --no-owner --no-acl --file="$BACKUP_DIR/agentic.dump" "$PGDATABASE"
createdb "$RESTORE_DATABASE"
pg_restore --exit-on-error --no-owner --no-privileges --dbname="$RESTORE_DATABASE" "$BACKUP_DIR/agentic.dump"
```

Xác nhận Alembic revision, row counts và dữ liệu mẫu trên database mới trước khi dùng. Với local storage, archive root đã cấu hình rồi restore vào root tạm và so checksum; với MinIO/S3, dùng công cụ backup riêng phù hợp bucket/versioning và thực hiện test restore độc lập. Không chạy restore đè lên database hiện hành.

## Job lỗi, token lỗi, provider lỗi

- Job: xem `/api/v1/jobs/{job_id}` và events; retry chỉ khi job `retryable` và operation idempotent. Không blind retry publication có `outcome_unknown`.
- Upload: tên file chỉ dùng làm metadata hiển thị và được lấy basename; storage key do server sinh, adapter từ chối key có traversal. Kiểm MIME/size/parser status; PDF scan/mật khẩu/unsupported phải báo trạng thái/hint thay vì tạo profile rỗng.
- DeepSeek: kiểm provider/model, key ở secret store, timeout/rate limit/balance. Không in key hoặc response nhạy cảm. No implicit provider fallback.
- Retrieval: kiểm active source, tenant/brand, parser/chunker/embed version, locator và hai relevance threshold. Nếu đổi embedding model, reprocess tài liệu trước khi tạo nội dung. `EMBEDDING_PROVIDER=none` là lexical-only.
- MinIO/S3: xác nhận health, bucket và credentials; database chứa metadata, object storage chứa binary.

## Rollback và giới hạn

Trước release, chụp backup DB/object metadata, ghi commit/branch và migration head. Nếu release lỗi, quay lại image/commit trước và thực hiện migration rollback chỉ khi migration có downgrade an toàn; không tự drop dữ liệu. Tắt Page connector hoặc quay về export/nhập metrics thủ công nếu Page identity, permissions, token hoặc đối soát kết quả đăng chưa được live kiểm chứng.
