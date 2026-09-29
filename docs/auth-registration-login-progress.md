# Tiến độ đăng ký và đăng nhập thật

Thời điểm cập nhật: 2026-09-29 10:15 UTC

## Checklist

- [x] Kiểm tra baseline `codex/manual-brand-content-context` tại `cf8f41e` và tạo worktree riêng `codex/auth-registration-login`.
- [x] Giữ nguyên preview hiện hữu trên `127.0.0.1:13103` và API `127.0.0.1:8000`.
- [x] Nối trang `/register` vào API đăng ký thật; đăng ký tạo tài khoản, workspace mới, Owner membership và brand trống.
- [x] Thêm link đăng ký từ trang đăng nhập; sau đăng ký xác nhận phiên rồi mở Brand Profile để người dùng tự nhập.
- [x] Làm mới đăng nhập: đọc phiên `/me`, xóa cache tài khoản trước và chỉ điều hướng tới đường dẫn nội bộ an toàn.
- [x] Giữ mật khẩu nguyên văn, không trim khoảng trắng; thêm xử lý trùng email đồng thời và khóa phiên/token dùng một lần.
- [x] Yêu cầu tài khoản đã tồn tại đăng nhập đúng email trước khi nhận lời mời workspace.
- [x] Khi thiếu SMTP, API quên mật khẩu trả lỗi cấu hình rõ ràng; đăng ký dùng lại `RegisterRequest` đã sinh từ OpenAPI, không đổi payload.
- [x] Chạy backend tests, frontend tests/lint/typecheck, build và browser acceptance trên PostgreSQL thử nghiệm riêng.
- [x] Tạo runbook và ma trận nghiệm thu.
- [ ] Rà soát cuối, commit feature branch và push; xác minh SHA remote.

## Kết quả kiểm chứng

- `tests/test_account_lifecycle.py`: 7 passed.
- Frontend Vitest: 48 passed; ESLint, Ruff và formatter sạch.
- TypeScript strict check: pass với alias tạm trỏ vào `packages/contracts` của branch. Alias tạm đã được gỡ; cần dùng workspace install sạch để chạy lệnh chuẩn trực tiếp.
- Playwright real-mode: đăng ký → workspace Owner → reload → đăng xuất → đăng nhập lại: 1 passed.
- API readiness trên PostgreSQL/Redis và storage thử nghiệm: ready.
- Đối chiếu database kiểm thử: một tài khoản E2E có một workspace, một Owner membership, một brand và hai phiên được cấp qua đăng ký/đăng nhập.

## Giới hạn đang theo dõi

- Chưa gửi email thật; đăng ký không yêu cầu xác minh email theo phạm vi đã chọn.
- Gửi reset password cần cấu hình SMTP. Khi thiếu SMTP, hệ thống trả `password_reset_unavailable` thay vì giả báo đã gửi thư.
- Đăng ký đồng thời được bảo vệ bằng unique constraint và xử lý `409`; tình huống tải cạnh tranh PostgreSQL chưa chạy riêng.
- Redis queue/cache đã qua readiness. Rate-limit và lỗi Redis chưa diễn tập vì môi trường Redis hiện có được preview khác dùng chung.
- Chưa triển khai công khai, OAuth, OTP hoặc MFA.
