# Kế hoạch triển khai sản phẩm v1

Cập nhật: 2026-09-24 (Asia/Ho_Chi_Minh)

## Mục tiêu và phạm vi

Hoàn thiện sản phẩm pilot cho 3–5 SME Việt Nam, ưu tiên F&B và bán lẻ. Luồng v1 cần đi từ đăng nhập và workspace đến tài liệu thương hiệu, Brand Profile có nguồn, campaign, nội dung sinh bằng DeepSeek, chỉnh sửa/version, duyệt, export hoặc đăng thủ công, metrics có nguồn và recommendation có bằng chứng. Facebook tự động chỉ được bật khi quyền/Meta App Review đã được xác minh. Mục tiêu ngân sách vận hành là 2–5 triệu đồng/tháng; chưa có số liệu chi phí LLM nên không khẳng định hiện đạt ngân sách.

Giữ kiến trúc modular monolith và stack đã có: Next.js/React/TypeScript, FastAPI/Pydantic, SQLAlchemy/Alembic, PostgreSQL/pgvector, Redis/Celery, MinIO/S3 và LangGraph. Không tạo HTTP service riêng cho từng agent. PostgreSQL là nguồn sự thật cho trạng thái nghiệp vụ/job; agent không được giữ Meta token hay quyền publish.

## Hiện trạng đã kiểm tra

- Remote được fetch tại 2026-09-23. `origin/main` ở `07938bd`; local `main` ở `648ff66` có tree nội dung giống hệt remote, nhưng lịch sử có một commit restore backend trùng patch. Branch bàn giao hiện là `codex/product-v1-completion`, tạo trên `origin/main` mới nhất.
- Snapshot local trước khi tiếp quản gồm thay đổi staged, unstaged và file untracked M1/M2/M3. Snapshot đã được chép sang worktree riêng; checkout/index gốc được giữ nguyên.
- Backend có auth/session, workspace/membership, document upload/ingestion/jobs, Brand Profile/revision/confirmation API, campaign CRUD, manual post/version, approval history/decision, export creation/download. Campaign/content HTTP contract được sinh từ FastAPI OpenAPI.
- Upload-driven profile extraction worker và content generation hiện fail-closed trước lời gọi LLM. Generation route trả `503 provider_approval_required`; không gửi Brand Profile/văn bản nguồn tenant sang DeepSeek cho tới khi data flow được chấp thuận. Agent/provider hiện chỉ được kiểm tra bằng fake clients.
- Campaign/export và manual metrics endpoints có API tests trên SQLite. Frontend có form campaign/manual post, tải export, màn hình snapshot/dashboard và outcome tracker; typecheck, 41 unit tests, lint, production build và desktop/mobile flow cho recommendation outcome đều pass.
- DeepSeek adapter đang dùng Chat Completions JSON mode, prompt có schema/example, parse/validate Pydantic và tối đa một lần sửa output. `deepseek-flash` hiện có trong danh sách model chính thức và JSON mode được tài liệu hóa; vẫn cần live request để xác nhận key/model của tài khoản. [Model list](https://api-docs.deepseek.com/api/list-models/), [JSON output](https://api-docs.deepseek.com/guides/json_mode/).
- Embedding cấu hình độc lập; mặc định `EMBEDDING_PROVIDER=none`, `RETRIEVAL_MODE=lexical`. Đây là retrieval lexical pilot, chưa phải semantic/vector RAG hoàn chỉnh. Không mặc định DeepSeek có embeddings.
- Python 3.11.16 và Node 26.7.0 có sẵn. PostgreSQL local chấp nhận kết nối ở `127.0.0.1:5432`, Redis trả `PONG`; Docker/Podman và MinIO không khả dụng trong môi trường này. Python và npm dependencies đã được cài trong worktree.
- `DEEPSEEK_API_KEY`, LLM model override và isolated PostgreSQL `DATABASE_URL` chưa được cung cấp trong process môi trường. Không có `.env` trong worktree; không sao chép secrets từ checkout gốc. Một account và SQLite DB E2E tạm thời đã được tạo trong `/private/tmp` để kiểm tra real-mode browser; không giữ lại credential trong repo.
- Real-mode browser smoke đã xác minh login/workspace, metrics dashboard, recommendation feedback/Apply và owner accept. Test riêng sau đó xác minh real-mode login → tạo campaign → bài thủ công → duyệt → export/download trên SQLite tạm. Không gọi DeepSeek/Meta; đây không thay bằng chứng PostgreSQL/MinIO, brand extraction hay AI content generation.
- Điều hướng `Xuất bản` trước đây dẫn tới 404 và bị guard real-mode che nội dung. Commit `c77720d` thêm trang giải thích rõ giới hạn Meta và quy trình export/đăng thủ công/nhập metrics; route được xác minh trong production build và browser. Commit `73ff4f7` chỉnh contract test để không yêu cầu trạng thái dữ liệu cho trang thông tin tĩnh.
- Bằng chứng kiểm thử và giới hạn được ghi trong [test-report.md](test-report.md); kết quả SQLite không được xem là bằng chứng PostgreSQL hoặc live provider.

## Kiến trúc và quyết định chính

1. Tiếp tục modular monolith: `apps/web` → FastAPI → PostgreSQL; durable jobs trong DB, Redis/Celery làm queue, object storage tách khỏi DB.
2. Dùng LangGraph cho workflow có nhánh, resume và state bền; dùng LangChain provider-neutral model/RAG abstractions bên trong. Không chuyển sang Deep Agents managed runtime vì cần custom tenant/auth/API và tự host.
3. Dùng một DeepSeek adapter qua factory của worker. Không fallback âm thầm sang OpenAI. Chat structured output dùng documented JSON mode cho Chat Completions và Pydantic validation; metadata chi phí phải là unavailable khi chưa có giá được xác minh.
4. Giữ embedding tách khỏi LLM. Ban đầu có thể nghiệm thu lexical retrieval nếu UI/docs ghi rõ. Semantic mode chỉ bật khi model/provider, dimension, tenant filter, threshold, reindex và locator được cấu hình đầy đủ.
5. Pydantic HTTP DTO/OpenAPI là nguồn contract cho frontend; internal M2↔M3 contracts được map tường minh. Không để TS mock types giả làm API thật.
6. Khi Meta chưa được cấp quyền, nghiệm thu export + manual publish + manual metrics import. Không tuyên bố automatic publishing/monitoring.

## Các phase và tiêu chí hoàn thành

| Phase | Phụ thuộc | Tiêu chí hoàn thành |
|---|---|---|
| 0. Audit, snapshot, docs | Repo access | Chốt remote/base, bảo toàn local work; sáu tài liệu có trạng thái/evidence rõ. |
| 1. Môi trường chạy | Python/Node deps; PostgreSQL/Redis; object storage hoặc local test adapter | Cài từ lock/manifest; migration lên PostgreSQL test DB; API, worker, scheduler và web health/readiness; không dùng DB production. |
| 2. Brand Knowledge | Phase 1; DeepSeek key/model và approval data flow cho live | Upload → durable job → parse → chunk/index → retrieve → Brand Profile có source → sửa/confirm; tenant checks, conflict 409, restart persistence. Tách fixture và live API evidence. Hiện local ingestion/fixture path có; LLM extraction production bị khóa chờ approval. |
| 3. Campaign/content/approval/export | Phase 2; DB schema/API/OpenAPI; chấp thuận data flow cho provider ngoài | Campaign/brief thật; generate/revise content job; immutable version; approval gắn hash/version; edit yêu cầu duyệt lại; CSV/XLSX download thật. Campaign/manual post/version/approval/export đã triển khai và có API evidence trên SQLite. AI generate/revise đang chờ chấp thuận; publish hash guard còn thiếu. |
| 4. Meta/manual publishing | Approved version; credentials/Meta App Review | Khi chưa đủ quyền: manual export/publish state được ghi rõ. Connector chỉ DONE khi version, permission, token, scheduling và reconcile được live kiểm chứng. |
| 5. Metrics/dashboard | Metrics contract; Meta hoặc manual import | Manual import lưu snapshot tenant-scoped, chặn duplicate, ghi source/time/post age; report định lượng bằng code giữ missing khác zero; dashboard hiển thị coverage/freshness và nhóm pillar/format. Đã có API, migration 0005 và UI; Meta auto-sync còn mở. |
| 6. Recommendation loop | Phase 5 | API đề xuất deterministic có evidence ID, mô tả giới hạn và abstain khi mẫu nhỏ. Feedback được lưu/audit; Apply tạo brief revision chờ owner duyệt; chấp nhận tăng campaign version theo optimistic concurrency. REC-002 lưu và đọc lại kết quả baseline/follow-up từ cùng source, metric và khoảng tuổi bài, kèm evidence/snapshot IDs và giới hạn suy luận. SQLite API + desktop/mobile mock E2E pass; không publish tự động. |
| 7. Hardening/bàn giao | Các phase trước | Tenant isolation, recovery, secrets, backup/restore, real-mode E2E, load smoke, docs và clean checkout được kiểm chứng. |

## Backlog ưu tiên

Chi tiết theo ID và tiêu chí ở [task-board.md](task-board.md). Thứ tự còn lại: isolated PostgreSQL/Compose runtime → DeepSeek data-flow approval + live smoke → browser E2E cho các luồng chưa kiểm tra → Meta permissions → hardening. Manual metrics import, report, feedback, brief revision và outcome comparison đã có fixture/API path; không coi đó là Meta sync, live provider test hoặc production runtime.

## Để sau v1

Video/Reels ingestion/publishing; AI tạo ảnh/video; Google OAuth trực tiếp; crawl đối thủ chưa có quyền; Ads optimization; Pixel/CAPI/CRM attribution; billing tự phục vụ; đa nền tảng; fine-tuning; Kubernetes; microservices. Các mục này là DEFERRED, không được trình bày như đã hoàn thành.
