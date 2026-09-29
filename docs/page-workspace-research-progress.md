# Tiến độ Page workspace và Nghiên cứu

Ngày bắt đầu: 2026-09-30 (Asia/Ho_Chi_Minh)
Nhánh: `codex/page-workspaces-research`
Base đã kiểm tra: `codex/creative-studio-ui` @ `b769097bfdb3568889d974c6def95bb944559113`

## Checklist

- [DONE] Baseline repo, contract, auth, Page connection, Research, worker và collector.
- [DONE] Đăng ký chỉ tạo user; Page đã xác minh mới tạo workspace riêng.
- [DONE] Page identity/avatar fields, unique workspace binding, activation gate và reconnect cùng Page.
- [DONE] UI Nghiên cứu không hỏi tạo/chọn nhóm; backend giữ nhóm legacy nội bộ và facade workspace cho báo cáo.
- [PARTIAL] Page sở hữu lưu bài và chỉ số mà Meta trả. Nội dung bình luận đang `privacy_hold`; chỉ số đếm bình luận vẫn có thể được lưu.
- [PARTIAL] Public Facebook giữ collector Tier 0 hiện có. Nhóm chỉ báo `unsupported_tier0`; không có nội dung thảo luận.
- [PARTIAL] Ledger ngân sách tự động PostgreSQL và mức trần $2/workspace/ngày đã được thêm cho báo cáo Nghiên cứu chạy DeepSeek; API và UI hiển thị số đã dùng/giữ chỗ/còn lại. Bảng giá đã ghi nhận model Gemini/Qwen đã chọn, nhưng chưa route call của hai provider hoặc media vào ledger.
- [PARTIAL] Worker không gửi comment text cũ/mới cho agent. Chưa có pipeline nhận dạng/redact toàn diện, retention/deletion ledger hoặc quy trình pháp lý; không được coi là chứng nhận tuân thủ.
- [PARTIAL] OpenAPI và TypeScript declarations đã được regenerate. Frontend lint, typecheck, unit tests và desktop/mobile fixture E2E hiện đạt; các test này không thay cho nghiệm thu real API/browser.
- [PARTIAL] API/worker fixtures và PostgreSQL/Redis/Celery integration test đã chạy trên môi trường disposable; browser real mode, Meta/provider live và worker crawl chưa chạy.

## Bằng chứng ban đầu

- Checkout triển khai là managed worktree riêng; checkout shared `/Users/lethanh/agent` đang có nhiều staged/unstaged changes và không được chỉnh.
- Preview hiện tại dùng worktree `creative-studio-ui`; không dùng checkout đó để triển khai.
- Alembic head trong source là `0020_facebook_cli_public_collector.py`.
- `POST /auth/register` hiện tạo đồng thời user, company, owner membership và brand; biểu mẫu yêu cầu tên workspace.
- `MetaPageConnection` hiện có unique `(company_id, page_id)` nhưng chưa có binding toàn hệ thống và chưa lưu avatar.
- Nguồn nghiên cứu vẫn gắn `group_id`; giao diện có tab Fanpage/nguồn/báo cáo và form nhóm.
- `facebook-cli` `v0.3.0` Tier 0 không phân trang timeline lịch sử; Group discussions cần Tier 1; public collector hiện lưu `comments=[]` và runner chưa đưa media ra schema.
- Provider AI hiện có adapter DeepSeek; chưa có ledger ngân sách tự động.
- Không kiểm tra/đọc giá trị API key, Page token, cookie hoặc DSN trong quá trình baseline.

## Tiến độ triển khai — 2026-09-30

- DONE: `POST /auth/register` giữ user/session nhưng không tạo Company, Brand hay Membership; form không hỏi tên workspace.
- DONE: `POST /workspaces/from-page` xác minh `/me` có ID khớp Page ID, yêu cầu một read-only page-post call, rồi tạo Company, Owner, Brand trống, encrypted connection, nhóm Research nội bộ và owned-Page source trong transaction.
- DONE: Page ID được unique toàn workspace. Token Page không tự tạo membership; workspace hiện có chỉ trả cho member đã được cấp quyền.
- DONE: Owner reconnect qua `PATCH /workspaces/{id}/page-connection`; chỉ chấp nhận đúng Page cũ. UI đặt luồng này trong Cài đặt doanh nghiệp.
- DONE: API permissions và worker claims chặn tác vụ ghi/AI/research/publish nếu Page chưa active; scheduler bỏ qua workspace cần reconnect.
- DONE: Research source có thể tạo không truyền group ID; Nghiên cứu tự chọn nhóm nội bộ cho dữ liệu legacy. UI gộp public Page đối thủ/tin tức và giải thích giới hạn Group Tier 0.
- DONE: Không lấy text bình luận mới cho đến khi có điều kiện xử lý phù hợp; report bỏ qua comment text legacy, trả coverage `privacy_hold`.
- TODO: Playwright thật, nối Qwen/Gemini vào comment/media pipeline, privacy/retention/deletion và mở rộng ledger cho mọi AI tự động.
- BLOCKED: Không có căn cứ trong repo cho phép kết luận việc xử lý dữ liệu cá nhân đã đáp ứng đầy đủ luật; cần đánh giá tổ chức/pháp lý và triển khai retention/erasure trước khi mở comment/media processing.

### 2026-09-30 01:28 Asia/Ho_Chi_Minh — Kiểm thử và rà contract

- DONE: backend regression suite chạy cùng nhau: 71 passed, 6 skipped, 1 test Docling được loại riêng vì runtime/model không sẵn có.
- DONE: sau khi thêm test worker, lượt backend regression cuối đạt 75 passed, 6 skipped, 1 test Docling được loại riêng vì runtime/model không sẵn có.
- DONE: nhóm regression backend foundation/campaign/brand/analytics chạy với fixture parser được gắn nhãn; PostgreSQL integration được skip vì chưa cấu hình `POSTGRES_TEST_URL`.
- DONE: `npm run gen:api -- --from /private/tmp/page-workspaces-openapi.json`; spec được xuất từ ứng dụng hiện tại, không đọc secret.
- DONE: frontend `npm run lint`, `npm run typecheck -- --incremental false`, `npm test`, `npm run build`.
- DONE: Ruff `ruff check --no-cache` trên toàn bộ file Python thay đổi.
- NOT_RUN: trình duyệt thật, migration trên PostgreSQL, Redis/Celery integration, Meta live, DeepSeek/Gemini/Qwen live. Build chỉ kiểm tra artifacts trong worktree; không thay preview.
- BLOCKED: chạy test Docling thật do worker thiếu dependency/model runtime trong môi trường hiện tại.
- Vận hành: đã báo người dùng rằng đầu ra chẩn đoán trước đó vô tình chứa chuỗi kết nối DB; giá trị không được lưu trong repo/docs. Xoay vòng credential DB trong cửa sổ vận hành an toàn trước khi rollout tiếp theo.

### 2026-09-30 03:47 Asia/Ho_Chi_Minh — Cập nhật fixture Page và browser E2E

- DONE: TypeScript workspace fixture có Page ID, avatar nullable và trạng thái kết nối; demo doanh nghiệp chính ở trạng thái Page đã xác minh, workspace rỗng vẫn `connection_required`.
- DONE: E2E đăng nhập chọn doanh nghiệp qua nút hiện hành “Mở không gian làm việc”, bỏ giả định nút cũ “Tiếp tục tới tài liệu”. Test tab Nghiên cứu dùng nhãn “Phân tích & hướng viết” và xác nhận legacy route `/fanpages` chuyển tiếp sang `/research`.
- PASS: frontend lint; typecheck với `--incremental false`; unit tests 50/50.
- PASS (fixture/MSW): Playwright desktop 26 passed, 1 skipped; mobile 26 passed, 1 skipped. Test chụp ảnh UI được skip có chủ đích khi không đặt thư mục screenshot. E2E server build standalone ở cổng test `13107` trước mỗi lượt.
- NOT_RUN: các E2E trên không gọi API thật, PostgreSQL/Redis, DeepSeek, Gemini, Qwen hoặc Meta; không phải bằng chứng Page onboarding thật hoặc dữ liệu Research live.

### 2026-09-30 01:38 Asia/Ho_Chi_Minh — Commit và push

- DONE: commit `d2ad5dddf7ef4055a1941d69c32a67d5d93ecf4a` được push lên `codex/page-workspaces-research`.
- DONE: `git ls-remote` xác nhận SHA trên origin khớp commit vừa push.
- NOT_RUN: chưa rollout frontend/backend lên preview; cần chạy migration và nghiệm thu PostgreSQL/Redis/browser trước khi thay dịch vụ đang dùng.

### 2026-09-30 01:47 Asia/Ho_Chi_Minh — PostgreSQL/Redis thật trong môi trường tạm

- DONE: PostgreSQL 18.3 cluster tạm tại `/private/tmp` chạy fresh migration từ đầu đến `0021_page_workspace_identity`.
- DONE: upgrade từ revision `0020` trên database synthetic: Page đơn được map sang `needs_reconnect`; company nhiều Page, Page trùng giữa workspace và workspace không có Page không bị map.
- DONE: PostgreSQL/Redis integration suite đạt `6 passed`; test production Celery dispatcher đặt đúng job ID synthetic vào queue Redis `agent`, sau đó dọn message và bản ghi test.
- DONE: cập nhật test PostgreSQL để kiểm tra schema head `0021`, index Page duy nhất, dispatcher thật và worker claim fixture dùng Page active theo gate sản phẩm.
- NOT_RUN: chưa chạy worker crawl, Meta live hoặc UI real browser. Không thử dispatch task nào có thể gọi crawl/provider.
- TODO: dùng một môi trường test Redis/worker chuyên dụng cho recovery khi broker thực sự ngắt và chạy browser end-to-end sau khi migration được áp dụng ở preview riêng.

### 2026-09-30 01:53 Asia/Ho_Chi_Minh — Kiểm tra dispatch Celery thật

- DONE: mở rộng `tests/test_postgres_database_integration.py` để dispatch research job đã commit qua production Celery app tới Redis test; test giải mã message xác nhận job ID, sau đó dọn message và dữ liệu test.
- PASS: cả sáu test trong file PostgreSQL/Redis chạy trên PostgreSQL 18.3 và hai Redis test riêng.
- NOT_RUN: không có Celery worker chạy job crawl; live Meta/provider và browser vẫn chưa nghiệm thu.

### 2026-09-30 01:54 Asia/Ho_Chi_Minh — Push kiểm chứng PostgreSQL/Redis

- DONE: commit `6bb99106d689444cfb1b2acc6e5ea467a8e553cc` gồm integration test PostgreSQL/Redis và cập nhật runbook/verification đã push.
- DONE: SHA trên origin được xác minh khớp commit này.

### 2026-09-30 02:21 Asia/Ho_Chi_Minh — Ledger ngân sách AI tự động

- DONE: Thêm migration `0022_ai_usage_budget` với bộ đếm ngân sách ngày theo workspace và ledger idempotent; tiền lưu bằng integer micro-USD, có usage, model, pricing version, trạng thái uncertain và structured result để replay.
- DONE: Reservation khóa hàng workspace trước khi kiểm tra `spent + reserved`, cap cứng 2.000.000 micro-USD/ngày theo Asia/Ho_Chi_Minh; không gọi nếu ngân sách thiếu hoặc model chưa có giá trong bảng.
- DONE: Tích hợp báo cáo Nghiên cứu tự động với DeepSeek. Một research cycle chỉ có một request key; provider timeout/exception giữ reservation và không tự gửi lại. Kết quả thành công được lưu trong ledger để worker replay mà không gọi model lần hai.
- DONE: Giá DeepSeek dùng mức peak/cache-miss đã ghi phiên bản; reservation tính trường hợp tối đa một lần repair. Provider/model chưa có giá đã xác minh bị từ chối trước khi gửi.
- PASS: Unit pricing and worker guard `tests/test_ai_budget.py`: 9 passed, including no provider call for deferred/uncertain reservations.
- PASS: PostgreSQL 18.3 migration fresh đến `0022`, cùng đường upgrade `0021` → `0022` trên database tạm riêng.
- PASS: PostgreSQL/Redis integration `tests/test_postgres_database_integration.py tests/test_ai_budget.py`: 16 passed; gồm race 6 reservations chỉ cấp 2 request trong hạn mức 40.000 micro-USD, replay và settlement.
- PASS: Regression không cần Docling runtime: 236 passed, 14 skipped, 1 deselected.
- BLOCKED: Full suite phát hiện 11 test parser hiện có không khởi tạo được Docling subprocess trong virtualenv API hiện tại; lỗi độc lập với ledger và cần worker Docling runtime/model để nghiệm thu.
- NOT_RUN: Không gọi DeepSeek/Gemini/Qwen live; không chạy crawl worker hoặc Meta live; không rollout preview.
- PARTIAL: Hiện chỉ báo cáo Nghiên cứu tự động DeepSeek dùng ledger. Qwen/Gemini adapters fixture-only, chưa có media/comment pipeline và chưa có ngân sách chung cho các tác vụ tự động khác.
- DONE: Commit ngân sách `2b3cb9283e9f512b9aa288ecf48af4437cde9a1f` đã push; SHA trên origin được đối chiếu khớp.

### 2026-09-30 02:35 Asia/Ho_Chi_Minh — Trạng thái ngân sách trong API và Nghiên cứu

- DONE: Thêm `GET /api/v1/workspaces/{workspace_id}/market-research/ai-budget` để trả hạn mức, đã dùng, đang giữ chỗ, còn lại, số lượt chưa quyết toán và số báo cáo chờ do giới hạn/cấu hình. Ngày/ngày reset tính theo `Asia/Ho_Chi_Minh`; endpoint kiểm tra membership workspace.
- DONE: Trang Nghiên cứu hiển thị mức dùng ngân sách tự động, đơn vị USD, thời điểm reset và thông báo báo cáo/lượt gọi đang chờ. Trạng thái làm mới mỗi 15 giây; chưa có chức năng tự lên lịch chạy lại các báo cáo bị hoãn.
- PASS: `tests/test_market_research_api.py -k research_ai_budget` đạt 1 passed, kiểm tra số dư mặc định, reservation/spent, unsettled request và report `deferred_budget`.
- PASS: `tests/test_market_research_api.py tests/test_ai_budget.py` đạt 18 passed trước khi thêm assertion cho report pending; targeted budget API test đạt lại sau thay đổi.
- PASS: OpenAPI export và `--check` khớp. TypeScript declarations được sinh lại bằng `openapi-typescript 7.13.0`.
- PASS: Frontend lint và unit tests: lint đạt, 50 tests passed.
- FAIL (contract mismatch): Typecheck toàn app lỗi ở nhiều màn hình do `@agentic/contracts` không export các kiểu/field frontend đã dùng (`CampaignContentSlot`, `content_plan`, `document_ids`, `MediaAsset`, ...). Typecheck không nêu lỗi mới trong trang Nghiên cứu; toàn app chưa thể xác nhận PASS.
- NOT_RUN: production build, browser thật, provider live, migration/runtime rollout. Không thay preview hoặc cấu hình key/provider.

### 2026-09-30 02:50 Asia/Ho_Chi_Minh — Ghim bằng chứng khi chọn hướng viết

- DONE: Campaign tạo từ báo cáo giữ chính xác `report_id`, `evidence_version_id`, `observation_id`, content hash, thời điểm quan sát và metrics; snapshot website chỉ được nhận nếu đã gắn với report đó.
- DONE: Worker dùng version/observation được ghim và kiểm tra tenant, report cùng source còn active. Nếu report cũ thiếu pin hoặc nguồn đã mất/tắt, job dừng với `market_research_context_stale`, không thay bằng dữ liệu mới nhất.
- DONE: Bỏ comment text khỏi Content Agent context. Mask email/số điện thoại không còn được coi là đủ để cho phép gửi bình luận; trạng thái vẫn `privacy_hold`.
- PASS: `tests/test_campaign_workflows.py -k content_generation_job_persists_cited_draft_and_is_idempotent` xác nhận báo cáo cũ vẫn dùng text/metrics cũ dù evidence hiện tại đã đổi, và comment PII không đi vào model input.
- PASS: `tests/test_market_research_api.py` đạt 10 passed, gồm endpoint ghim IDs/metrics vào campaign draft; `tests/test_ai_budget.py` đạt 9 passed.
- PASS: OpenAPI cập nhật cho evidence version/observation; TypeScript declaration sinh bằng `openapi-typescript 7.13.0`.
- NOT_RUN: PostgreSQL migration/browser real/provider live; không dùng website hoặc Facebook live.

### 2026-09-30 03:00 Asia/Ho_Chi_Minh — Nối snapshot website tới Content Agent

- DONE: Campaign worker lấy đúng `web_snapshot_ids` đã ghim vào báo cáo; tenant, báo cáo, nhóm nguồn và trạng thái nguồn phải khớp.
- DONE: Nội dung website gửi model chỉ gồm các trường được cho phép, tối đa 10 offer; URL ảnh/tài nguyên có thể chứa chữ ký không đi vào input.
- DONE: Worker đọc lại cả nguồn bài và snapshot website trước khi lưu draft; nếu nguồn đã bị tắt/xóa hoặc pin đổi thì dừng với `market_research_context_stale`.
- PASS: Test worker dùng website snapshot cố định, giá USD, xác nhận signed image URL bị loại khỏi model input; report bài cũ tiếp tục dùng version/observation đã ghim.
- PASS: Ruff và `git diff --check` trên các file Python thay đổi.
- PASS: `tests/test_campaign_workflows.py tests/test_market_research_api.py tests/test_ai_budget.py` đạt 30 passed; Ruff và `scripts/export_openapi.py --check` cũng đạt.
- PASS: Incremental provenance commit `ae58f91966939df45851256e0a7a042e74cebb61` đã push; remote SHA khớp.
- NOT_RUN: Provider live, media analysis, browser real, preview rollout; Qwen adapter chưa nối pipeline, Gemini adapter chưa có ở mốc này.

### 2026-09-30 03:05 Asia/Ho_Chi_Minh — Adapter Qwen text có cấu hình vùng tường minh

- DONE: Thêm Qwen structured text adapter dùng OpenAI-compatible JSON-object endpoint; model ID và HTTPS endpoint theo vùng phải được khai báo, không tự chọn region/model.
- DONE: Adapter giới hạn đầu vào và validate output bằng Pydantic; comment summary chỉ nhận batch đã có privacy decision, không gửi author/profile hoặc decision ID tới model và kiểm tra citations thuộc đúng batch.
- DONE: Qwen tắt repair call cho tới khi có reservation ledger; không có retry ẩn của SDK.
- PASS: Qwen + DeepSeek provider fixtures đạt 21 passed ở mốc này; Ruff đạt.
- BLOCKED: Pytest thông thường không vào được fixtures vì môi trường hiện thiếu `pgvector`; Qwen factory integration cũng cần cài dependency `openai` theo manifest. Không lấy lượt fixture riêng làm bằng chứng integration.
- PARTIAL: Chưa có QWEN key/region/model của deployment, chưa nối vào pipeline comment vì comment text vẫn `privacy_hold`, chưa tích hợp pricing/budget ledger chung.
- NOT_RUN: Alibaba/Gemini live, media, comment analysis, provider budget end-to-end.

### 2026-09-30 03:22 Asia/Ho_Chi_Minh — Ràng buộc batch bình luận Qwen

- DONE: Thêm contract batch chỉ nhận excerpt đã sàng lọc, policy decision/version và evidence refs theo run; không có author/profile field.
- DONE: Qwen summary phải trích refs có trong batch; không gửi ID/quyết định nội bộ provider và không tạo repair request khi chưa có budget reservation.
- DONE: Tắt đường `generate` tổng quát của Qwen; adapter chỉ nhận `summarize_screened_comments`.
- PASS: Provider fixtures Qwen/Gemini/DeepSeek đạt 31 passed; Ruff và diff check đạt.
- PARTIAL: Contract không phải bằng chứng căn cứ pháp lý; comment collection vẫn `privacy_hold`, adapter chưa được worker gọi.

### 2026-09-30 03:14 Asia/Ho_Chi_Minh — Gemini inline media adapter

- DONE: Thêm adapter Gemini nhận byte ảnh/video inline, model/key tường minh, MIME allowlist, SHA-256/provenance và yêu cầu trạng thái `approved`; trạng thái mặc định là `privacy_hold`.
- DONE: Không nhận URL, không upload qua Files API, không retry/repair tự động. Tổng request tối đa 20 MiB; asset mặc định tối đa 10 MiB.
- PASS: Fixture xác nhận ảnh/video JSON, Pydantic validation, chặn privacy hold/hash/MIME/kích thước trước mạng và chỉ có một request khi output sai schema; bộ provider tests tổng cộng 27 passed.
- PARTIAL: Adapter chưa nối vào worker/media pipeline; cờ approved không thay thế quyết định căn cứ xử lý ở tầng nghiệp vụ. Chưa có pricing/budget ledger cho Gemini.
- NOT_RUN: Gemini live, media thật, privacy/deletion/retention end-to-end, browser real.

## Nhật ký

### 2026-09-30 — Baseline

- TODO → IN_PROGRESS: tạo worktree riêng từ nhánh UI đã chọn và đọc AGENTS.md/skills áp dụng.
- Kết quả: nhánh mới `codex/page-workspaces-research` bắt đầu từ SHA nêu trên; lệnh `git fetch` trong worktree chỉ cập nhật metadata Git, không sửa checkout preview hay shared working tree.
- Kiểm tra tiếp theo: hoàn tất truy vết route/session, Page model, nghiên cứu và worker trước khi chỉnh schema.

### 2026-09-30 05:58 Asia/Ho_Chi_Minh — Kiểm tra real-mode login shell

- DONE: Sửa test service worker cũ để chờ lượt reload do ứng dụng thực hiện, chỉ chấp nhận `ERR_ABORTED` khi navigation của Playwright bị lượt reload đó thay thế; cập nhật assertion theo heading login hiện tại.
- PASS: Playwright chạy trên preview real-mode hiện có tại `127.0.0.1:13104`, chế độ external server: test `/login` đạt `1 passed`; service worker mock không còn đăng ký/điều khiển trang.
- PASS: Frontend typecheck (`--incremental false`), ESLint và `git diff --check` sau khi sửa test.
- BLOCKED: Build/start server mới từ worktree riêng bị chặn quyền ghi sandbox vào `apps/web/.next/trace`; lần chạy E2E độc lập không sử dụng preview thất bại ở khâu khởi chạy Chromium trong sandbox. Không thay artifact hoặc restart preview để vượt qua.
- NOT_RUN: Không gửi form đăng nhập/đăng ký, không ghi dữ liệu ứng dụng; real API → worker → PostgreSQL, Meta live và provider live chưa được kiểm tra.
- TODO: Chạy lại real API → worker → PostgreSQL bằng tài khoản/workspace disposable và worker test được cô lập trước khi nghiệm thu toàn luồng.

### 2026-09-30 06:04 Asia/Ho_Chi_Minh — Bổ sung bảng giá provider có thời hạn

- DONE: Ghim giá công khai cho `gemini-3.8-flash` ($0.75/$3.75 mỗi triệu token, chỉ đến 2026-12-31) và `qwen3.8-27b` ($0.50/$3 mỗi triệu token, Singapore International); không trừ ưu đãi/free quota.
- DONE: Qwen yêu cầu vùng Singapore tường minh; Gemini tự khóa giá sau ngày hiệu lực; provider ngoài DeepSeek phải có upper bound token rõ ràng trước reservation. Bảng giá có version mới `provider-public-pricing-2026-09-30-v2`.
- PASS: Pricing-focused pytest `9 passed, 2 deselected` trên bản sao test cô lập trong `/private/tmp`; gồm micro-USD, region mismatch, ngày hết giá Gemini và từ chối reservation Gemini khi thiếu token bounds. Test database integration không chạy.
- PARTIAL: Chỉ bảng định giá/helper được thêm. Gemini/Qwen chưa nối worker, chưa có provider key/model deployment đã xác minh và chưa thuộc thống kê chi phí pipeline.
- NOT_RUN: Không gọi DeepSeek/Gemini/Qwen live hoặc gửi dữ liệu bình luận/media.

### 2026-09-30 06:14–06:20 Asia/Ho_Chi_Minh — Giới hạn raw quarantine và giữ comment import

- DONE: Research raw payload dùng helper `raw_quarantine_expiry`, expiry đặt tối đa 24 giờ từ lúc worker lưu metadata. DB ghi key/expiry trước object upload để purge scheduler còn biết key nếu storage trả timeout hoặc worker dừng.
- DONE: Manual import không lưu comment text dựa trên regex che email/điện thoại; aggregate comment metric vẫn giữ, response báo `privacy_hold` và số lượng bình luận bỏ qua. Test API cập nhật theo hành vi này.
- PASS: Unit test helper kiểm tra timestamp timezone-aware, đúng thời điểm hết hạn sau 24 giờ và comment text bị giữ lại trong khi count được giữ; Ruff và `git diff --check` đạt.
- BLOCKED: Test API manual-import không thu thập được vì Python runtime hiện tại thiếu dependency `pgvector`; chưa kiểm thử PostgreSQL/object storage cho purge thật hoặc storage timeout.
- PARTIAL: Chưa có retention 90 ngày cho nội dung chuẩn hóa, deletion ledger/propagation hoặc legal review.
- NOT_RUN: Không chạy crawl live, không tạo/đọc dữ liệu Facebook hoặc website.
