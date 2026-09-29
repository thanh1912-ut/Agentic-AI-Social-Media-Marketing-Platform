# Creative Studio UI — kiểm chứng

Ngày kiểm thử: 2026-09-29. Branch `codex/creative-studio-ui`; SHA sẽ được ghi sau commit release.

## Kiểm tra tự động

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| ESLint | PASS | Toàn bộ frontend và Playwright tests trong `apps/web` |
| TypeScript | PASS | `tsc --noEmit --incremental false` |
| Vitest | PASS | 4 test files, 48 tests |
| Playwright desktop | PASS | 27 tests trên mock fixture có nhãn |
| Playwright mobile | PASS | 5 tests; 1 bài chụp ảnh bỏ qua có chủ đích trong lượt mobile-only |
| Responsive overflow | PASS | 390, 768, 1024 và 1440px; thêm editor, hồ sơ và các màn hình nghiệp vụ |
| Mobile menu | PASS | Mở bằng nút, đóng với Escape, focus quay lại nút mở |
| URL tabs | PASS | Tab khôi phục sau reload; bàn phím mũi tên đi từ tab đang focus |
| Zoom/reduced motion | PASS | Kiểm tra zoom 200% và `prefers-reduced-motion` trong browser fixture |
| Contrast | PASS | Màu chữ thường đã đo; muted/primary trên nền trắng lần lượt 6.55:1 và 6.40:1 |
| Production real-mode build | PASS | `NEXT_PUBLIC_USE_MOCKS=0`, API origin `http://127.0.0.1:8001`; standalone assets được chuẩn bị |
| API/PostgreSQL/Redis readiness | PASS | API `/readyz` báo database, schema, Redis, cache và object storage sẵn sàng |
| Preview 13104 | IN_PROGRESS | Frontend cũ vẫn chạy; chưa kích hoạt release mới. Trước triển khai font local chưa được phục vụ |
| Tài khoản thật/API ghi dữ liệu | NOT_RUN | Chỉ chạy sau khi preview mới được kích hoạt, với tài khoản/workspace kiểm thử dùng riêng |
| DeepSeek, Facebook/Meta live | NOT_RUN | Không gọi provider hoặc đăng bài khi đổi giao diện |

Lần chạy đầu phát hiện các E2E cũ trông đợi inspector editor luôn mở và tab keyboard điều hướng từ tab được chọn thay vì tab focus. Test và hành vi bàn phím đã được cập nhật; desktop suite cuối cùng PASS. Lần chạy đầu còn phát hiện dashboard fixture giữ dãy chỉ số cũ; trang tổng quan đã được làm đồng nhất với real mode và chỉ hiển thị dữ liệu workspace.

## Kiểm tra trực quan

Ảnh desktop/mobile trong `screenshots/` được chụp từ Playwright mock fixture và mang nhãn **Bản demo**. Đây là fixture để review bố cục, không phải bằng chứng dữ liệu thật. Trang đăng nhập sẽ được chụp riêng từ real preview sau khi kích hoạt, không điền email/mật khẩu. Không chụp token, cookie hoặc nội dung tài liệu người dùng.

Các màn hình fixture đã chụp: tổng quan, tài liệu, chiến dịch, biên tập bài, xuất bản và Fanpage/thị trường ở 1440×960 / 390×844. Ảnh đăng nhập fixture sẽ được thay bằng ảnh từ preview thật sau kích hoạt. Đã tự review editor desktop/mobile, trang tài liệu mobile và phần xuất bản/thị trường desktop/mobile. Tài liệu mobile giữ bảng trong vùng cuộn riêng, có hướng dẫn cuộn ngang và có thể nhận focus bàn phím.

## Giới hạn xác nhận

- Các trạng thái AI, Meta và số liệu trong ảnh giao diện là dữ liệu fixture.
- Chưa xác nhận đăng nhập, tạo nội dung hoặc đọc dữ liệu doanh nghiệp thật trên API; phần đó cần dùng tài khoản/workspace test riêng.
- Thay đổi chỉ ở frontend, test, docs và rollout frontend. Không sửa API, PostgreSQL, Redis, worker, tài khoản hay secret DeepSeek.
