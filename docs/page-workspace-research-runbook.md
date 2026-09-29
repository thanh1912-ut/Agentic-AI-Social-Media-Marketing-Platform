# Runbook Page workspace và Nghiên cứu

## Onboarding doanh nghiệp

1. Đăng ký/đăng nhập bằng tài khoản Agentic Marketing. Đăng ký tạo tài khoản và phiên, chưa tạo doanh nghiệp.
2. Ở màn hình chọn doanh nghiệp, Owner nhập Page ID và Page Access Token thuộc đúng Page.
3. Backend đọc Page identity và thử đọc một trang bài công khai; không đăng bài thử. Khi thành công, workspace lấy tên Page, lưu avatar an toàn nếu URL ảnh phù hợp, mã hóa token và tạo Owner/Brand trống.
4. Brand Profile vẫn do Owner tự viết. Page name/avatar chỉ là nhận diện workspace.
5. Thành viên khác tham gia bằng lời mời. Có token không tự cấp quyền thành viên.

API dùng trong vận hành:

- `POST /api/v1/auth/register` — tài khoản/session, không tạo workspace.
- `POST /api/v1/workspaces/from-page` — xác minh Page và tạo workspace.
- `PATCH /api/v1/workspaces/{workspace_id}/page-connection` — Owner thay token cho cùng Page ID; đổi Page cần workspace khác.
- `GET /api/v1/workspaces` — danh sách workspace đã được cấp membership.

Không đưa token vào tài liệu, ticket, browser storage, query string hoặc log. Chỉ nhập trên giao diện kết nối hoặc gửi request qua kênh bảo mật.

## Secrets

- Không dán API key, Page Access Token hoặc cookie vào chat, frontend bundle, Git hay log.
- DeepSeek/Gemini/Qwen chỉ được nạp từ backend secret store/runtime environment.
- Page Access Token phải được mã hóa server-side bằng `META_TOKEN_ENCRYPTION_KEY`.
- Mẫu biến cấu hình sẽ dùng placeholder; file này không chứa giá trị bí mật.

`META_TOKEN_ENCRYPTION_KEY` phải được cấu hình ở backend trước khi Owner kết nối Page. Thiếu khóa trả `token_encryption_unavailable`; không tắt mã hóa để vượt lỗi.

## Kết nối lại Page

- Khi token hết hạn/thu hồi, workspace chuyển `needs_reconnect`; dữ liệu lịch sử vẫn đọc được, tác vụ mới bị chặn.
- Owner mở Cài đặt doanh nghiệp, nhập token mới và giữ nguyên Page ID. Backend xác minh lại trước khi thay token mã hóa.
- Nếu một nguồn đang chạy khi mất kết nối, kết quả dở dang không được coi là hoàn thành. Sau kết nối lại, scheduler có thể phục hồi lịch theo idempotency.
- Lịch đăng đã quá hạn tuân thủ trạng thái missed hiện có; không gửi bù hàng loạt.

## Nghiên cứu

- Mở mục **Nghiên cứu**. Các nhóm database cũ vẫn được giữ; UI/API facade tự đặt nguồn mới vào nhóm nội bộ của workspace.
- Page doanh nghiệp được thêm tự động khi workspace kích hoạt. Các nguồn khác: website công khai, Page Facebook công khai và Group Facebook công khai.
- Bấm Crawl ngay cho nguồn hoặc nhóm nội bộ. Lịch nguồn có thể bật/tắt riêng; mở trang không tự chạy crawl.
- Public Page chạy collector `facebook-cli` Tier 0 hiện có; không đăng nhập. Public Group chỉ có thể trả thông tin nhóm, không có thảo luận Tier 1. Không báo hoàn thành toàn bộ lịch sử.
- Bình luận hiện ở trạng thái `privacy_hold`: chỉ số tổng hợp có thể lưu, nhưng text bình luận mới không tải/lưu/gửi cho agent. Media chưa có pipeline tải/phân tích.
- Lỗi nguồn mới không được xóa kết quả nguồn thành công trước đó.

## Trạng thái ban đầu

- Account-only registration, Page-based workspace activation và reconnect được triển khai trong nhánh này; vẫn cần kiểm chứng migration trên PostgreSQL thật.
- UI Nghiên cứu không yêu cầu người dùng chọn nhóm. Cấu trúc lưu trữ legacy vẫn group-scoped.
- Gemini/Qwen adapters, video/image analysis, budget ledger, comment processing/erasure chưa triển khai.

## Thao tác vận hành

Không bật xử lý comment/media từ cờ thủ công. Trước khi mở các chức năng này cần xác định mục đích/căn cứ xử lý, thời hạn, quy trình quyền xóa, vùng provider và kiểm thử deletion end-to-end. Đây là yêu cầu vận hành/pháp lý, không thể thay bằng regex hoặc checkbox.

## Phần chưa sẵn sàng

- Gemini và Qwen chưa có adapter/model ID được xác minh; DeepSeek vẫn là adapter hiện có. Không tự fallback giữa provider.
- Không có ledger chi phí chung; hạn mức 2 USD/ngày chưa được thực thi.
- Chưa tải hay gửi ảnh/video đến provider; không tuyên bố media analysis đã chạy.
- Không có full comment pagination/replies hoặc database checkpoint mới. Coverage là `privacy_hold`/Tier 0 partial.
- Không tự nhận hệ thống tuân thủ đầy đủ Luật 91/2025/QH15 hoặc Nghị định 356/2025/NĐ-CP.

## Kiểm thử/deploy

- Backend API: dùng lệnh service/test đã cấu hình của checkout, không bật `AUTO_CREATE_SCHEMA` hay inline jobs để nghiệm thu.
- Migration phải chạy `alembic upgrade head` trên database test riêng trước rollout; không chạy rollback phá lịch sử.
- Đừng thay API/workers đang phục vụ preview. Drain worker cũ trước khi thay backend và giữ snapshot/rollback tương thích Page gate.
- Cấu hình key dạng placeholder trong secret store: `DEEPSEEK_API_KEY=<secret>`, `GEMINI_API_KEY=<secret>`, `QWEN_API_KEY=<secret>`; hiện chỉ DeepSeek adapter cũ tồn tại, còn Gemini/Qwen chưa được nối.
