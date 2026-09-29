# Tiến độ đăng ký và đăng nhập thật

Thời điểm cập nhật: 2026-09-29 10:18 UTC

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
- [x] Rà soát diff/secret, commit và push feature branch; SHA remote đã xác minh khớp.

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

## Bàn giao

- Branch: `codex/auth-registration-login`.
- Commit đã push: `4cd0a06dbcec387266b34e6f0a05c785aabd53cd`.
- Remote SHA khớp với commit local.

## Tiếp tục: giữ DeepSeek qua lần khởi động (2026-09-29)

- [x] Xác nhận nguyên nhân preview: launcher tạm gán `DEEPSEEK_API_KEY` rỗng và model khác; secret gốc vẫn được lưu ngoài repo.
- [x] Xác nhận `deepseek-flash` khả dụng bằng `GET /models`; key không xuất hiện trong output.
- [x] Đưa Python runtime, Docling models và file storage ra khỏi `/private/tmp`, giữ bản nguồn để rollback.
- [x] Thêm runtime launcher dùng allowlist env; API/agent worker nạp DeepSeek từ secret file khi start, ingestion/Beat không nhận key.
- [x] Cô lập auth preview khỏi các dịch vụ dùng chung: DB thử nghiệm hiện tại và Redis database `/4`.
- [x] Thêm LaunchAgent manager cho API, frontend, hai worker và Celery Beat; không đụng LaunchAgent PostgreSQL/Redis.
- [x] 6 test unit, Ruff và kiểm tra whitespace đã pass.
- [x] Cài/khởi động 5 LaunchAgents: API, frontend, worker `default,agent`, worker `ingestion`, Beat. Tất cả báo `running`; `/readyz` trả `200 ready`, frontend `/login` trả `200`.
- [x] Celery Beat recovery đã nhận job ingestion tồn trong PostgreSQL; job đạt `succeeded`, có một document record. UI sau khi kết nối hiển thị CSV với `41.188` dòng và `4.029.468` ký tự; worker ingestion không nhận DeepSeek key.
- [x] Một job campaign-plan dùng workspace/prose tổng hợp đã dispatch qua Redis/Celery và ghi kết quả vào PostgreSQL: `succeeded`, model `deepseek-flash`, ba concept, 1.129 input tokens, 4.431 output tokens, 19.995 ms. Workspace tổng hợp được xóa sau khi đọc kết quả.
- [x] Xác nhận tải lại frontend vẫn vào workspace đã đăng nhập, không bị chuyển về login.
- [x] 6 test runtime, Ruff check/format, Python compile và `git diff --check` đều đạt.
- [ ] Review diff/secrets, commit và push feature branch; xác minh SHA remote.

Lượt cài LaunchAgent đầu tiên gặp lỗi bootstrap thoáng qua sau khi thay API cũ. Installer được bổ sung retry có giới hạn và kiểm tra trạng thái thực; lượt cài lại thành công cho cả 5 service. Key vẫn chỉ nằm trong secret store, không được in ra.
