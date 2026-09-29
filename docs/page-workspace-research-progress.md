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
- [PARTIAL] Ledger ngân sách tự động PostgreSQL và mức trần $2/workspace/ngày đã được thêm cho báo cáo Nghiên cứu chạy DeepSeek. Gemini/Qwen, media và các call AI tự động khác chưa nối vào ledger.
- [PARTIAL] Worker không gửi comment text cũ/mới cho agent. Chưa có pipeline nhận dạng/redact toàn diện, retention/deletion ledger hoặc quy trình pháp lý; không được coi là chứng nhận tuân thủ.
- [DONE] Regenerate OpenAPI TypeScript từ OpenAPI hiện tại; frontend lint/typecheck/unit/build.
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
- TODO: Playwright thật, Gemini/Qwen adapters, media pipeline, privacy/retention/deletion và mở rộng ledger cho mọi AI tự động.
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
- PARTIAL: Hiện chỉ báo cáo Nghiên cứu tự động DeepSeek dùng ledger. Gemini/Qwen adapters, media/comment pipeline, ngân sách các tác vụ tự động khác và UI xem ngân sách chưa làm.

## Nhật ký

### 2026-09-30 — Baseline

- TODO → IN_PROGRESS: tạo worktree riêng từ nhánh UI đã chọn và đọc AGENTS.md/skills áp dụng.
- Kết quả: nhánh mới `codex/page-workspaces-research` bắt đầu từ SHA nêu trên; lệnh `git fetch` trong worktree chỉ cập nhật metadata Git, không sửa checkout preview hay shared working tree.
- Kiểm tra tiếp theo: hoàn tất truy vết route/session, Page model, nghiên cứu và worker trước khi chỉnh schema.
