# Creative Studio UI — kiểm chứng

Ngày kiểm thử: 2026-09-29. Branch `codex/creative-studio-ui`. Frontend release đang chạy từ commit `db2238c6fbb6f3281378c049981f9c2d2fef520a`; SHA cuối của branch sẽ bao gồm commit tài liệu và ảnh đăng nhập thật.

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
| Preview 13104 | PASS | LaunchAgent mục tiêu đang chạy; `/login` HTTP 200; font local HTTP 200; rollback plist cũ được lưu ngoài repo |
| API/PostgreSQL/Redis readiness | PASS | API `/readyz` báo database, schema, Redis, cache và object storage sẵn sàng sau rollout |
| Real API acceptance | PASS | Browser đăng ký tài khoản/workspace test riêng, reload, logout/login, tải TXT+CSV tổng hợp, đợi ingestion, xem lại và lưu hồ sơ thủ công qua API thật |
| DeepSeek, Facebook/Meta live | NOT_RUN | Không gọi provider hoặc đăng bài khi đổi giao diện |

Lần chạy đầu phát hiện các E2E cũ trông đợi inspector editor luôn mở và tab keyboard điều hướng từ tab được chọn thay vì tab focus. Test và hành vi bàn phím đã được cập nhật; desktop suite cuối cùng PASS. Lần chạy đầu còn phát hiện dashboard fixture giữ dãy chỉ số cũ; trang tổng quan đã được làm đồng nhất với real mode và chỉ hiển thị dữ liệu workspace.

## Kiểm tra trực quan

Ảnh desktop/mobile trong `screenshots/` được chụp từ Playwright mock fixture và mang nhãn **Bản demo**. Đây là fixture để review bố cục, không phải bằng chứng dữ liệu thật. Trang đăng nhập sẽ được chụp riêng từ real preview sau khi kích hoạt, không điền email/mật khẩu. Không chụp token, cookie hoặc nội dung tài liệu người dùng.

Các màn hình fixture đã chụp: tổng quan, tài liệu, chiến dịch, biên tập bài, xuất bản và Fanpage/thị trường ở 1440×960 / 390×844; chúng được gắn nhãn “Bản demo”. Ảnh đăng nhập desktop/mobile được chụp sau rollout từ preview real mode, để trống thông tin đăng nhập. Đã tự review editor desktop/mobile, trang tài liệu mobile và phần xuất bản/thị trường desktop/mobile. Tài liệu mobile giữ bảng trong vùng cuộn riêng, có hướng dẫn cuộn ngang và có thể nhận focus bàn phím.

### Bằng chứng luồng thật

- Preview: `http://127.0.0.1:13104/login`; API origin: `http://127.0.0.1:8001`.
- Build thật với `NEXT_PUBLIC_USE_MOCKS=0`, sau đó đóng gói standalone và triển khai bằng LaunchAgent `com.agentic-marketing.auth-preview-web`.
- Real browser test `self registration, document-only ingestion, manual profile, logout and login persist`: PASS, 1/1. Test tạo user/workspace kiểm thử ngẫu nhiên, tải một TXT và một CSV tổng hợp, chờ trạng thái hoàn tất, reload kiểm tra tài liệu, lưu hồ sơ văn bản tự nhập, rồi logout/login và xác nhận lại dữ liệu. Không ghi email test hoặc nội dung file vào báo cáo.
- Screenshot test trang đăng nhập real mode: PASS, 1/1; không điền email/mật khẩu.
- Tài khoản/workspace test và tài liệu synthetic vẫn được giữ trong DB local để tránh xóa dữ liệu bằng tay; không phải dữ liệu workspace của người dùng.

## Giới hạn xác nhận

- Các trạng thái AI, Meta và số liệu trong ảnh giao diện là dữ liệu fixture.
- Chưa nghiệm thu gọi DeepSeek, đăng Facebook/Meta hoặc crawl trực tiếp; các mục đó chủ ý không được kích hoạt trong đợt đổi giao diện.
- Thay đổi code chỉ ở frontend, test, docs và rollout frontend; không sửa API, schema hoặc cấu hình dịch vụ. E2E đã ghi một tài khoản/workspace và hai tài liệu synthetic riêng vào database local như nêu ở trên; không thay đổi workspace có sẵn. Không đọc hoặc sửa secret DeepSeek.
