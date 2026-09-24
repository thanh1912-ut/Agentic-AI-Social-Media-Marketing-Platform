# Quyết định kỹ thuật

Ngày tạo: 2026-09-23. Trạng thái dưới đây được ghi từ audit đầu; cần cập nhật nếu test/implementation buộc đổi.

## DEC-001 — Modular monolith

- Vấn đề: cần nhiều worker/agent nhưng một sản phẩm v1 nhỏ, tenant/auth/approval phải nhất quán.
- Quyết định: giữ Next.js + FastAPI modular monolith; worker và scheduler chạy process riêng, không tạo HTTP service riêng cho agent.
- Lý do: giữ transaction/job/permission rõ, giảm chi phí vận hành.
- Không chọn: microservices/Kubernetes.
- Ảnh hưởng: API/schema/data lưu PostgreSQL; Redis chỉ queue/cache; file ở local/S3-compatible storage; vận hành mục tiêu 2–5 triệu đồng/tháng chưa được đo.
- Trạng thái: PROVISIONAL, phù hợp Compose/code hiện tại.

## DEC-002 — LangGraph cho workflow bền và có kiểm soát

- Vấn đề: ingest→retrieve→profile cần state, error handling và human confirmation; tương lai content có review/approval.
- Quyết định: giữ LangGraph cho control-flow; agent không được có node/API publish.
- Lý do: cần resume/branch/state có kiểm soát hơn một tool loop đơn giản. Đây là lựa chọn khớp skill `ecosystem-primer`/`langgraph-fundamentals`.
- Không chọn: Deep Agents managed runtime cho core API vì hệ thống cần auth/tenant và custom routes; single agent loop cũng không đủ cho workflow.
- Ảnh hưởng: cần persistence/checkpoint nơi phù hợp; nghiệp vụ và job ledger vẫn lưu trong DB.
- Trạng thái: PROVISIONAL tới khi integration/recovery tests pass.

## DEC-003 — DeepSeek làm provider LLM duy nhất

- Vấn đề: người vận hành dùng DeepSeek API; OpenAI `parse()` không được giả định tương thích chỉ do SDK chung.
- Quyết định: một adapter trong `services/agents/providers/deepseek.py`, worker lấy qua factory; dùng Chat Completions JSON mode + schema/example trong prompt + Pydantic validation, tối đa một repair.
- Lý do: tài liệu chính thức được kiểm tra lại 2026-09-24; `deepseek-flash` hiện gọi DeepSeek-V4.1-Flash; từ 2026-09-14, `deepseek-v4-pro` cũng được route sang Flash và tính giá Flash cho tới khi V4.1-Pro ra mắt. Chat Completions JSON mode dùng `response_format={"type":"json_object"}`. Giá Flash tại thời điểm kiểm tra: peak $0.30/M input cache miss, $0.006/M cache hit, $1.20/M output; off-peak bằng một nửa. Vì vậy model mặc định `deepseek-flash` là lựa chọn đúng. [JSON Output](https://api-docs.deepseek.com/guides/json_mode/), [Model list](https://api-docs.deepseek.com/api/list-models/), [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/), [V4.1-Flash release](https://api-docs.deepseek.com/news/news260910/).
- Không chọn: fallback âm thầm sang OpenAI hoặc gọi structured-output helper chưa xác minh.
- Ảnh hưởng: `LLM_PROVIDER`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `LLM_DEFAULT_MODEL` cấu hình server-side; lỗi token/model/timeout phải chuẩn hóa. Có thể lập scenario từ bảng giá công khai, nhưng chưa có token usage/chi phí thực của workspace.
- Trạng thái: adapter IMPLEMENTED; model ID và bảng giá công khai được xác nhận từ docs; account-specific availability và live request NOT_VERIFIED do chưa có `DEEPSEEK_API_KEY`. Scenario ngân sách có giả định ở `docs/test-report.md`, chưa phải dự báo tổng OPEX.

## DEC-004 — Embedding độc lập với DeepSeek chat

- Vấn đề: DeepSeek chat docs không chứng minh embedding endpoint tương thích.
- Quyết định: dùng FastEmbed chạy local với `intfloat/multilingual-e5-small` ONNX, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`, 384 chiều. Model dùng prefix `passage:` cho tài liệu và `query:` cho truy vấn. Nội dung workspace không gửi tới dịch vụ embedding; chỉ tải weights công khai một lần vào cache. Provider ngoài như OpenAI vẫn cần chấp thuận data flow riêng. `EMBEDDING_PROVIDER=none` là chế độ lexical fallback.
- Lý do: không gửi DeepSeek key sang provider khác và không gắn nhãn lexical là semantic RAG.
- Không chọn: giả định DeepSeek `/embeddings` hoặc service provider không được cấp quyền.
- Ảnh hưởng: pgvector lưu được nhiều dimension; provider/model version lọc các index riêng và migration `0010` giữ vectors cũ. Chunker v3 giới hạn cửa sổ ở 300 token, overlap 40 để chừa biên dưới context 512 token của model. Hybrid score dùng weight semantic 0.75/lexical 0.25 để xếp hạng; gate dùng ngưỡng lexical-only 0.12, lexical rescue 0.45, semantic 0.82 và semantic inter-source margin 0.04 (single-source floor hiệu dụng 0.86).
- Bằng chứng: PostgreSQL migration thử trên schema legacy `vector(1536)` giữ vector cũ, nhận vector 384 mới và truy vấn chỉ lấy đúng model version. Adapter chạy thật với pinned weights. `scripts/evaluate_retrieval.py` đạt 6/6 positive Hit@1 và 0/8 no-answer false contexts trên synthetic set; ranking holdout cũ 12 truy vấn Hit@1 75%, Hit@3 91.7%, MRR 0.850. Chưa có SME corpus để nghiệm thu chất lượng pilot; các synthetic set không phải quality SLA.
- Nguồn triển khai: [FastEmbed chính thức của Qdrant](https://github.com/qdrant/fastembed), [multilingual E5 small model card](https://huggingface.co/intfloat/multilingual-e5-small) và [tokenizer config tại revision đã pin](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/tokenizer_config.json).
- Trạng thái: IMPLEMENTED, local semantic path available; production retrieval quality and model-cache provisioning remain IN_PROGRESS.

## DEC-005 — OpenAPI là contract HTTP cho frontend

- Vấn đề: Python M2↔M3 internal models và TypeScript UI types khác tầng, trùng tên nhưng không nhất thiết cùng nghĩa.
- Quyết định: Pydantic HTTP DTO → FastAPI OpenAPI → generated TS types; internal model map tường minh.
- Lý do: có một nguồn contract HTTP, phát hiện lệch sớm.
- Không chọn: tự suy API type từ internal model hoặc `any`.
- Ảnh hưởng: phải regenerate/check OpenAPI artifacts khi đổi DTO.
- Trạng thái: một phần đã thiết lập cho auth/document/brand; campaign/content contract chưa có backend thật.

## DEC-006 — Manual Meta fallback cho pilot

- Vấn đề: Page permission/App Review/version/token/metrics semantics chưa được kiểm chứng trên app và Page được cấp quyền.
- Quyết định: chưa bật auto publish/sync; export + manual publication/metrics là fallback v1 khi kiểm chứng được.
- Lý do: tránh blind retry POST gây đăng trùng và tránh claim quyền chưa có.
- Không chọn: scraping/browser automation để lách permission.
- Ảnh hưởng: Meta connector trạng thái BLOCKED_EXTERNAL cho tới khi có credentials, quyền và live evidence; user vẫn phân biệt export với publish.
- Bằng chứng: ngày 2026-09-24 đã thử đọc [Page Feed](https://developers.facebook.com/docs/graph-api/reference/page/feed/), [Page Insights](https://developers.facebook.com/docs/graph-api/reference/page/insights/), [permissions](https://developers.facebook.com/docs/permissions/) và [access-token guide](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/); cả bốn trang trả HTTP 429. Đây không phải xác minh nội dung tài liệu hiện hành.
- Trạng thái: `BLOCKED_EXTERNAL`; `VERIFY CURRENT META API` cho version, permission, token, publish/schedule, metrics, rate limits và webhooks khi docs truy cập được. Không thiết kế/claim connector tự động trước bước này và app/Page/token/App Review.

## DEC-007 — DeepSeek xử lý trích đoạn tài liệu và Brand Profile sau chấp thuận

- Vấn đề: Brand Profile extraction và content generation cần gửi đoạn trích tài liệu/Brand Profile tới nhà cung cấp LLM bên ngoài.
- Quyết định: chủ dự án chấp thuận ngày 2026-09-24 gửi đoạn trích tài liệu và Brand Profile tới DeepSeek. Worker Brand Profile dùng adapter DeepSeek server-side; API tạo durable/idempotent content job, chỉ dùng hồ sơ đã xác nhận và nguồn tenant đang hoạt động, rồi lưu bài ở trạng thái draft để người dùng duyệt.
- Lý do: đây là data flow cốt lõi cho sản phẩm. Provider chỉ nhận nội dung cần cho tác vụ; mã tenant và mã thương hiệu không được đưa vào prompt, liên hệ/đối thủ không được gửi trong profile content-generation. Tenant/source authorization, revision checks và citations được xác minh trong backend.
- Ảnh hưởng: AI endpoint giờ trả `202` cùng job ID; thiếu key tạo lỗi cấu hình bền vững trên job thay vì trả `503` tại API. Retrieval mặc định lexical. Embedding provider bên ngoài vẫn yêu cầu cờ chấp thuận riêng và mặc định tắt. DeepSeek cost metadata được lưu `null` khi chưa có giá được xác minh.
- Trạng thái: IMPLEMENTED + fixture-tested; live DeepSeek/model-account verification chưa chạy vì môi trường chưa có `DEEPSEEK_API_KEY`.

## DEC-008 — Cấu hình bảo mật production và PostCSS

- Quyết định: production đòi hỏi JWT secret riêng tối thiểu 32 bytes và `COOKIE_SECURE=1`; API docs/OpenAPI UI tắt trong production. PostCSS được override tối thiểu lên nhánh vá hiện dùng trong lockfile.
- Bằng chứng: production config tests pass; `npm ls postcss --all` cho 8.5.24/8.5.28; npm audit trước đó trả 0 vulnerabilities.
- Trạng thái: IMPLEMENTED; full security review vẫn cần làm.

## DEC-009 — Recommendation là mô tả bằng chứng, không phải nhân quả

- Vấn đề: snapshot quan sát được có thể lệch về pillar, format, tuổi bài hoặc cách thu thập; không đủ để kết luận một thay đổi gây ra hiệu quả.
- Quyết định: tính KPI và nhóm dữ liệu bằng code; chỉ đề xuất thử nghiệm deterministic khi đủ ít nhất 5 bài qua ít nhất 2 pillar, gắn evidence IDs, giới hạn, confidence thấp và bước đo lại. Nếu dữ liệu thiếu thì abstain.
- Không chọn: để LLM tự khẳng định nguyên nhân hoặc tự áp dụng chiến lược/publish.
- Ảnh hưởng: feedback, apply thành revision và theo dõi kết quả thử nghiệm là phần tiếp theo; UI phải giữ rõ đây là đề xuất mô tả.
- Trạng thái: API/UI recommendation, feedback và draft-apply IMPLEMENTED; post-experiment outcome tracking INCOMPLETE.

## DEC-010 — Apply recommendation tạo brief revision cần duyệt

- Vấn đề: áp dụng lời khuyên trực tiếp vào campaign đang chạy sẽ bỏ qua xác nhận của owner và có thể ghi đè brief đã đổi sau khi recommendation được tạo.
- Quyết định: persist recommendation theo fingerprint evidence; ghi feedback/audit; Apply chỉ tạo `CampaignBriefRevisionDraft` ở trạng thái pending review. Owner accept mới cập nhật `Campaign.version`, và chỉ khi `base_version` vẫn khớp; nếu lệch trả `409`.
- Không chọn: sửa campaign ngay khi nhấn Apply hoặc ghi đè draft cũ.
- Ảnh hưởng: migration 0006; API/OpenAPI cho save/feedback/apply/decision; UI diff before/after. Không tự sinh content hay publish; bước AI generation vẫn phụ thuộc data-flow approval.
- Trạng thái: IMPLEMENTED; SQLite API tests, desktop/mobile MSW E2E và real-mode browser smoke (metrics → feedback → pending revision → owner accept) đều pass; PostgreSQL runtime chưa được xác minh.

## DEC-011 — Trang xuất bản minh bạch khi Meta chưa kết nối

- Vấn đề: mục Xuất bản trên menu real mode từng bị guard ẩn và dẫn người dùng tới trang 404; chưa có Meta app/Page permission để tự đăng.
- Quyết định: hiển thị trang trạng thái trong real mode, nói rõ chưa kết nối Meta và hướng dẫn review → export → đăng thủ công → nhập metrics. Không giả lập trạng thái đăng hoặc gọi Meta API.
- Ảnh hưởng: `apps/web/src/app/w/[workspaceId]/publishing/page.tsx`; bỏ guard chung che route real mode.
- Trạng thái: IMPLEMENTED; typecheck, lint, production build và browser kiểm tra route pass; Meta connector vẫn BLOCKED_EXTERNAL.

## DEC-012 — Theo dõi kết quả recommendation bằng cohort snapshots

- Vấn đề: sau khi owner chấp nhận brief revision, sản phẩm cần lưu kết quả đo trước/sau để operator đối chiếu mà không gán quan hệ nhân quả.
- Quyết định: chỉ ghi outcome cho revision đã accepted; người dùng chọn metric, hai cửa sổ không chồng lấn, source ID và cùng khoảng tuổi bài. API chọn snapshot mới nhất của từng bài trong mỗi cửa sổ, tính metric bằng module analytics, lưu coverage/sample size, snapshot IDs, evidence IDs, người ghi và audit event. Request lặp có fingerprint sẽ trả lại kết quả đã ghi.
- Không chọn: sinh kết quả bằng LLM, tính từ mock/demo data ở real mode, hoặc diễn giải khác biệt như tác động nhân quả.
- Ảnh hưởng: migration 0007; API GET/POST và UI lịch sử outcome; thiếu cohort/metric trả lỗi rõ, baseline bằng 0 thì không tính relative change; mẫu nhỏ hoặc coverage thấp được ghi vào limitations.
- Trạng thái: IMPLEMENTED; SQLite API test, migration sạch 0001→0007, OpenAPI/TypeScript generation, desktop/mobile MSW E2E pass. PostgreSQL runtime và số liệu Meta thật chưa kiểm chứng.

## DEC-013 — Tên file upload không tham gia object key

- Vấn đề: tên file do client gửi không phải đường dẫn an toàn. Ghép nguyên tên vào key local đã cho phép ghi ra ngoài storage root.
- Quyết định: chỉ lưu basename đã chuẩn hóa làm metadata; tạo object key từ tenant, content hash và UUID do server sinh. Local và S3 adapter đều từ chối key tuyệt đối, rỗng, có dấu phân cách Windows, NUL hoặc segment `.`/`..`; local adapter còn xác nhận đường dẫn resolve vẫn nằm trong root.
- Lý do: giới hạn đường biên filesystem/object namespace tại adapter, kể cả khi một caller truyền key lỗi.
- Ảnh hưởng: key mới không còn phụ thuộc tên file. Key legacy bất thường bị từ chối và cần upload lại từ nguồn gốc nếu được phát hiện.
- Trạng thái: IMPLEMENTED; kiểm thử tái hiện trước sửa và regression tests pass. Full PostgreSQL/MinIO runtime chưa được kiểm chứng.

## DEC-014 — Refresh và logout của cookie session cần CSRF token

- Vấn đề: refresh/logout thay đổi session bằng refresh cookie nhưng chưa dùng dependency CSRF; refresh client cũng bỏ qua header token. Access cookie hết hạn còn refresh cookie hợp lệ là trạng thái phổ biến nên chỉ kiểm access cookie không đủ.
- Quyết định: bảo vệ cả hai route bằng double-submit CSRF; mọi state-changing request có access hoặc refresh cookie phải gửi `X-CSRF-Token`, kể cả khi có Authorization header; bearer-only client được miễn khi không gửi session cookie. Refresh client đọc cookie `agentic_csrf` và gửi lại.
- Ảnh hưởng: refresh và logout từ web vẫn hoạt động; stale/forged bearer không thể bỏ qua CSRF khi refresh cookie hiện diện.
- Trạng thái: IMPLEMENTED; API test cover access-cookie-expired/refresh-only, bogus bearer, successful refresh, logout và revoked refresh; frontend client test xác nhận header được gửi.

## DEC-015 — Redis fixed-window limits cho route nhạy cảm

- Vấn đề: auth, upload và content-generation endpoints cần giới hạn chống brute force và lạm dụng; chưa có edge limiter được nghiệm thu.
- Quyết định: dùng atomic Redis `INCR`/`EXPIRE` Lua fixed window theo operation scope và hash của ASGI client host. Production yêu cầu bật limiter, fail-closed với `503` khi Redis thiếu/lỗi; development mặc định tắt và fail-open nếu Redis lỗi. Mức theo route được ghi tại `docs/security-review.md`.
- Không chọn: tin forwarded IP header do client gửi hoặc đưa Redis key vào log; proxy IP chỉ hợp lệ khi được cấu hình trusted tại ASGI server.
- Ảnh hưởng: Redis trở thành dependency của các route bị giới hạn trong production. Fixed window có burst ở boundary; edge/WAF và account-aware login controls chưa được kiểm chứng. Proxy IP behavior cần acceptance trên deployment.
- Trạng thái: IMPLEMENTED trong `004020e`; 4 focused tests và full Python suite **96 passed, 1 skipped**; Redis/Compose/proxy production runtime chưa được nghiệm thu.

## DEC-016 — AI revise là job dùng chung adapter và tạo version mới

- Vấn đề: editor đã có contract nháp cho AI revise nhưng backend chưa có route/worker; gọi model trong HTTP request sẽ chặn API và có thể ghi đè phiên bản người dùng đang duyệt.
- Quyết định: `POST /workspaces/{company_id}/posts/{post_id}/revise` tạo job `content_revise` có `Idempotency-Key`; dùng cùng DeepSeek adapter và tenant-filtered retrieval như content generation. Worker kiểm tra lại expected post, campaign và Brand Profile version trước khi lưu `PostVersion(source="ai_revised")`; chỉ field thuộc scope được đổi. Nếu bài đã từng được duyệt, version mới trở lại draft và cần duyệt lại. Không cho revise bài đã lên lịch/đã đăng.
- Không chọn: gọi DeepSeek đồng bộ từ API, thay thế lịch sử version, tự gửi duyệt/đăng, hoặc xem AI tạo mô tả ảnh là tạo media.
- Ảnh hưởng: thêm DTO/OpenAPI/TS type, worker job recovery/retry và editor UI; scope `media` chỉ cập nhật `image_brief`. Không thêm migration mới vì dùng job ledger và PostVersion schema hiện có.
- Trạng thái: IMPLEMENTED; SQLite API/worker fixture, retry/recovery, OpenAPI generation/check và Playwright mock desktop/mobile pass. Live DeepSeek request và real-provider browser flow NOT_VERIFIED do chưa provision key.

## DEC-017 — PostgreSQL Alembic version table cần chứa revision IDs dài

- Vấn đề: migration revision IDs mô tả đầy đủ tính năng dài hơn giới hạn `VARCHAR(32)` mà Alembic tạo mặc định; migration chạy được ở SQLite nhưng thất bại khi PostgreSQL lưu revision dài.
- Quyết định: trên PostgreSQL, migration environment tạo `alembic_version.version_num VARCHAR(128)` trước khi chạy migration và nâng column cũ nếu đang ngắn hơn. SQLite giữ hành vi Alembic mặc định.
- Ảnh hưởng: migration `0001→0007` chạy thành công trên PostgreSQL 18.3 với pgvector 0.8.2; chạy lại `upgrade head` không đổi schema. Kiểm thử dùng database/role trong disposable cluster ở `/private/tmp`, không chạm PostgreSQL 15 dùng chung.
- Trạng thái: IMPLEMENTED; 27 public tables, current revision dài 39 ký tự.

## DEC-018 — Campaign brief edit dùng optimistic concurrency

- Vấn đề: campaign đã tạo chưa có luồng sửa brief; chỉnh sửa đồng thời có thể ghi đè nội dung mới của người khác.
- Quyết định: thêm `PATCH /workspaces/{company_id}/campaigns/{campaign_id}` với quyền `campaign:edit` và expected `version`. Update thành công tăng version; request stale trả `409 version_conflict`. Giao diện cho phép sửa trường brief và yêu cầu người dùng tải lại bản mới nhất sau conflict.
- Ảnh hưởng: OpenAPI và TypeScript client được sinh lại; MSW hỗ trợ version conflict; campaign edit E2E chạy trên desktop/mobile.
- Trạng thái: IMPLEMENTED; API test xác nhận version bump và conflict, campaign slice có 10 E2E pass. Không tạo migration mới.

## DEC-019 — Lịch nội dung lưu trên Campaign và khóa slot trong lúc sinh

- Vấn đề: chỉ lưu brief và sinh theo số lượng/ngày tổng quát không giúp người dùng vận hành lịch bài theo chủ đề đã chọn; hai request đồng thời còn có thể cùng lấy một slot.
- Quyết định: lưu `strategy_summary` và tối đa 60 slot trong `Campaign.content_plan_json` bằng migration 0008. Mỗi slot có ID do client tạo, ngày, pillar, format và topic; backend quản lý liên kết draft và job đang giữ slot. Campaign version tăng khi reserve và khi gắn draft; optimistic updates bảo vệ sửa đồng thời. Retry/cancel/failure giải phóng slot đúng job, retry chỉ được nếu campaign context còn nguyên.
- DeepSeek data flow: chủ dự án chấp thuận gửi campaign strategy, slot topic và ngày đã chọn cùng Brand Profile và đoạn trích nguồn phù hợp khi người dùng bấm sinh theo slot. ID database và slot nội bộ không nằm trong prompt.
- Ảnh hưởng: draft lưu `content_slot_id` và `planned_date`; slot đã chạy/đã sinh không thể bị xóa hoặc sửa nội dung. Bài tạo ra vẫn là draft và cần người duyệt.
- Trạng thái: IMPLEMENTED; SQLite API/worker fixtures và PostgreSQL migration 0001→0008 pass. Live DeepSeek và full runtime chưa được xác minh.

## DEC-020 — Ảnh là asset tenant-scoped, gắn vào immutable post version

- Ngày: 2026-09-24.
- Vấn đề: upload ảnh trước đây chỉ tạo metadata tài liệu; editor không thể lưu ảnh thật vào bài và approval không có fingerprint bao phủ nội dung/media.
- Quyết định: thêm `media_assets` với hash SHA-256, MIME/dimension/size, server-generated storage key và uniqueness theo workspace+hash. Chỉ nhận JPEG/PNG/WebP khớp MIME; giới hạn mặc định 12 MiB và 40 triệu pixel. Download yêu cầu membership workspace. Gắn/gỡ ảnh qua post update sẽ tạo `PostVersion` mới; alt text và media metadata/hash nằm trong version. Mỗi approval lưu SHA-256 canonical hash của đúng version. Export ghi filename, asset hash và protected API path.
- Không chọn: URL public cho asset, sửa version tại chỗ, tự xóa asset đang có reference, hoặc tự publish ảnh lên Meta khi chưa có connector/quyền.
- Ảnh hưởng: migration 0009; endpoint upload/content mới; OpenAPI và TypeScript client cập nhật; file binary dùng object storage local/S3 adapter hiện tại. Asset được giữ lại để version cũ còn tham chiếu. Approval fingerprint đã lưu; connector tương lai phải đối chiếu hash trước khi publish.
- Trạng thái: IMPLEMENTED; backend suite 105 passed/1 live-provider skip; 14 desktop/mobile MSW Playwright tests, real-mode API/browser test pass riêng trên SQLite và PostgreSQL, frontend 43 tests/typecheck/lint/build và SQLite/PostgreSQL migration 0001→0009 đều pass. pg_dump/restore và local object archive checksum roundtrip cũng pass. Chưa có Meta image publishing hoặc live DeepSeek. Chi tiết ở `docs/test-report.md`.

## DEC-021 — Recovery chạy trên queue worker và dùng một event loop theo process

- Ngày: 2026-09-24.
- Vấn đề: Compose worker chỉ nghe queue `default,agent`, trong khi Celery Beat có thể gửi recovery task vào queue mặc định `celery`. Ngoài ra, `asyncio.run` tạo rồi đóng loop mỗi lần gọi; asyncpg pool có thể giữ connection gắn với loop đã đóng.
- Quyết định: route `services.worker.scheduled_jobs.recover_due_jobs` tới queue `default` ở cả task router và Beat entry. Các entrypoint đồng bộ của Celery dùng một event loop sống theo process; sau fork, PID mới tạo loop riêng.
- Lý do: worker Compose phải nhận recovery task và các task trong process cần dùng cùng event loop để tái sử dụng connection pool an toàn.
- Ảnh hưởng: không đổi schema/database. Entry point đóng coroutine rồi báo lỗi nếu được gọi khi loop đang chạy, vì worker sync xử lý task tuần tự.
- Bằng chứng: router/Beat unit test xác nhận queue `default`; unit test xác nhận loop reuse. PostgreSQL 18.3 + Redis 8.6.3 với Celery 5.6.3 `solo` đã nhận task recovery không chỉ định queue, khôi phục một stale lease và xử lý lại content job. Không có DeepSeek request; lỗi `ai_not_configured` là kết quả dự kiến khi thiếu key.
- Trạng thái: IMPLEMENTED tại `380ac6c`; Beat process, upload ingestion, worker process restart, Compose và prefork Linux còn cần nghiệm thu.

## DEC-022 — Account lifecycle email dùng SMTP tùy chọn và link mời thủ công

- Ngày: 2026-09-24.
- Vấn đề: forgot-password trước đó trả thông điệp như thể email đã được gửi dù không có mail adapter; workspace owner chưa thể tạo/gửi lại lời mời qua UI, và không có trang nhận lời mời/reset mật khẩu.
- Quyết định: thêm server-side SMTP adapter hỗ trợ STARTTLS hoặc SSL implicit, cấu hình qua `SMTP_*`, `EMAIL_FROM` và HTTPS `WEB_BASE_URL`; không đưa secret ra frontend/API. Password reset response luôn trung tính, token hash lưu phía server, raw token chỉ có trong email, token dùng một lần/hết hạn, reset thành công thu hồi mọi token reset khác, refresh sessions và access tokens được cấp theo password version. Reset email được gửi bằng FastAPI background task sau HTTP response để giảm timing side-channel theo account existence. Invitation gửi/resend xoay token; nếu SMTP chưa cấu hình hoặc không nhận email, owner nhận link thủ công để chuyển riêng. Invitee preview rồi chấp nhận; tài khoản mới đặt tên/mật khẩu ngay trong flow.
- Không chọn: trả reset token cho trình duyệt, tiết lộ SMTP failure hoặc account existence, hay coi email là đã gửi khi thiếu adapter.
- Ảnh hưởng: OpenAPI/generated TS types và UI auth/settings được cập nhật; production `WEB_BASE_URL` bắt buộc HTTPS. SMTP password cần đặt trong secret store. Reset delivery background hiện chưa có durable queue, retry, bounce handling hoặc telemetry; invitation delivery vẫn đợi trong request và lỗi có manual fallback. Access token cũ phát hành trước password-version claim dùng `iat` fallback để giữ tương thích; token mới bị thu hồi ngay khi password đổi.
- Bằng chứng: 5 account lifecycle integration tests trong full suite; fake SMTP STARTTLS/login/header sanitization; reset replay/stale-token/session revocation; invite fallback/resend/accept. Full Python suite **123 passed, 1 skipped**, frontend **45 passed**, typecheck/lint/build/OpenAPI pass, invitation Playwright **2/2** desktop/mobile.
- Trạng thái: IMPLEMENTED + fixture-tested; SMTP mailbox delivery chưa xác minh do môi trường chưa có credentials/mailbox. Chi tiết vận hành ở `docs/runbook.md` và giới hạn ở `docs/test-report.md`.
