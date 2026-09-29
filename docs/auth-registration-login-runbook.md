# Runbook đăng ký và đăng nhập

## Trải nghiệm người dùng

1. Mở `/register`, nhập họ tên, email, tên thương hiệu/workspace và tự đặt mật khẩu từ 8 đến 200 ký tự.
2. Tài khoản mới được đưa vào workspace riêng với vai trò Owner. Không cần DeepSeek hoặc SMTP để đăng ký.
3. Sau khi vào workspace, tự viết hồ sơ thương hiệu. Hệ thống không sinh hồ sơ trong lúc đăng ký.
4. Đăng xuất từ thanh điều hướng; đăng nhập lại bằng chính email và mật khẩu đó. Dữ liệu workspace được giữ trong PostgreSQL.
5. Người đã có tài khoản muốn vào workspace khác cần lời mời. Đăng nhập bằng đúng email được mời, rồi mở lại link lời mời.

Mật khẩu không được gửi trong email hoặc chat và không thể xem lại sau khi tạo. Nếu quên mật khẩu, dùng trang quên mật khẩu khi backend đã cấu hình SMTP.

## Chạy local

Tạo môi trường riêng và không ghi secret vào Git:

```sh
export DATABASE_URL='postgresql+asyncpg://<app-user>:<password>@127.0.0.1:<port>/<database>'
export REDIS_URL='redis://127.0.0.1:<queue-port>/0'
export REDIS_CACHE_URL='redis://127.0.0.1:<cache-port>/0'
export JWT_SECRET='<random-secret-from-secret-store>'
export COOKIE_SECURE=0
export COOKIE_SAMESITE=lax
export CORS_ALLOWED_ORIGINS='http://127.0.0.1:3100'
export WEB_BASE_URL='http://127.0.0.1:3100'
export AUTO_CREATE_SCHEMA=0
export INLINE_JOBS=0
```

Chạy migration bằng cơ chế Alembic hiện có, sau đó chạy API và frontend:

```sh
uvicorn services.api.main:app --host 127.0.0.1 --port 8000
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 NEXT_PUBLIC_USE_MOCKS=0 \
  npm run dev --workspace @agentic/web -- --hostname 127.0.0.1 --port 3100
```

Truy cập `http://127.0.0.1:3100/register` để tạo tài khoản hoặc `/login` để đăng nhập. API base URL chỉ là origin, không thêm `/api/v1`.

Trên HTTPS production, bật `COOKIE_SECURE=1`, cấu hình domain/CORS đúng và giữ `JWT_SECRET` trong secret store. Không dùng cấu hình cổng thử nghiệm trong tài liệu này như cấu hình triển khai công khai.

## SMTP và đặt lại mật khẩu

- SMTP không bắt buộc cho đăng ký, đăng nhập hoặc đăng xuất.
- Nếu SMTP chưa cấu hình, `POST /api/v1/auth/forgot-password` trả `503 password_reset_unavailable`; UI phải thông báo rằng dịch vụ chưa sẵn sàng.
- Khi SMTP được cấu hình, link reset dùng token một lần, hết hạn theo cấu hình hiện có. Đổi mật khẩu thu hồi các phiên refresh cũ.
- Không đưa URL reset hoặc token vào log, chat hay tài liệu bàn giao.

## Phiên và xử lý lỗi

- Access/refresh token nằm trong cookie HttpOnly; cookie CSRF được gửi qua header cho thao tác thay đổi dữ liệu.
- Email được chuẩn hóa; mật khẩu giữ nguyên cả khoảng trắng đầu/cuối.
- Email đã tồn tại nhận mã `409 already_exists`; đăng ký không tạo workspace thứ hai.
- Nếu mất mạng ngay sau khi bấm đăng ký, kiểm tra đăng nhập trước khi thử đăng ký lại vì máy chủ có thể đã commit.
- Nếu đăng nhập thất bại, kiểm tra email và mật khẩu. Không có mật khẩu mặc định.
- Lỗi Redis hoặc API phải hiển thị là lỗi dịch vụ; không tự retry đăng ký khi kết quả request chưa rõ.
- Logout chỉ xóa cache phía trình duyệt sau khi API xác nhận thu hồi phiên.

## Preview kiểm thử hiện tại

Branch preview riêng: `http://127.0.0.1:13104/register` (frontend) và API `http://127.0.0.1:8001`. Preview này dùng PostgreSQL thử nghiệm `agentic_marketing_auth_test_20260929`, không dùng chung dữ liệu đăng nhập/workspace của preview cũ ở cổng 13103/8000. Tài khoản tạo tại đây chỉ nằm trong database thử nghiệm.
