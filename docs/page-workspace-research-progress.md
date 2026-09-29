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
- [BLOCKED] Gemini/Qwen adapter, phân tích media, pricing validation và ledger $2/workspace/ngày chưa được triển khai.
- [PARTIAL] Worker không gửi comment text cũ/mới cho agent. Chưa có pipeline nhận dạng/redact toàn diện, retention/deletion ledger hoặc quy trình pháp lý; không được coi là chứng nhận tuân thủ.
- [DONE] Regenerate OpenAPI TypeScript từ OpenAPI hiện tại; frontend lint/typecheck/unit/build.
- [PARTIAL] Test API/worker fixtures đạt; migration PostgreSQL, Redis/Celery thật, browser real mode và Meta live chưa chạy.

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
- TODO: Migration fresh/upgrade PostgreSQL thật, Redis worker/recovery, Playwright thật, Gemini/Qwen/budget ledger và media pipeline.
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

## Nhật ký

### 2026-09-30 — Baseline

- TODO → IN_PROGRESS: tạo worktree riêng từ nhánh UI đã chọn và đọc AGENTS.md/skills áp dụng.
- Kết quả: nhánh mới `codex/page-workspaces-research` bắt đầu từ SHA nêu trên; lệnh `git fetch` trong worktree chỉ cập nhật metadata Git, không sửa checkout preview hay shared working tree.
- Kiểm tra tiếp theo: hoàn tất truy vết route/session, Page model, nghiên cứu và worker trước khi chỉnh schema.
