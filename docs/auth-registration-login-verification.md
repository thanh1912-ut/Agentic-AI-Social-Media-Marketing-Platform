# Nghiệm thu đăng ký và đăng nhập

Ngày chạy: 2026-09-29 10:15 UTC. Base code: `cf8f41e`; branch triển khai: `codex/auth-registration-login`.

## Ma trận

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Đăng ký tạo tài khoản + workspace + Owner + brand trống | PASS | Browser real-mode và truy vấn chỉ đọc trên database PostgreSQL thử nghiệm |
| Phiên sau đăng ký và reload | PASS | Playwright real-mode trên API branch |
| Đăng xuất rồi đăng nhập lại cùng workspace | PASS | Playwright real-mode; URL cuối cùng là workspace vừa tạo |
| Mật khẩu giữ nguyên khoảng trắng | PASS | API lifecycle test: mật khẩu đã trim bị từ chối, giá trị nguyên văn đăng nhập thành công |
| Email trùng và không tạo workspace mồ côi | PASS | Lifecycle test, API trả `409` và chỉ có một workspace |
| User đã có tài khoản nhận lời mời | PASS | Test API: anonymous bị từ chối; sai tài khoản nhận `403`; tài khoản đúng nhận đúng membership |
| Reset password khi SMTP thiếu | PASS | Lifecycle test xác nhận `503 password_reset_unavailable`, không báo đã gửi thư |
| Contract đăng ký | PASS | Tái sử dụng `RegisterRequest` hiện có từ OpenAPI; payload đăng ký không đổi |
| SMTP gửi email thật | NOT_RUN | SMTP chưa cấu hình trong môi trường thử nghiệm |
| Migration và readiness | PASS | PostgreSQL thử nghiệm đã ở Alembic head `0020_facebook_cli_public_collector`; `/readyz` báo database, schema, Redis, cache và storage sẵn sàng |
| Backend auth tests | PASS | 7 passed |
| Frontend tests | PASS | 48 passed |
| Frontend lint / Python lint / format | PASS | ESLint, Ruff check và Ruff format check sạch |
| Frontend typecheck | PASS | TypeScript strict check với alias tạm trỏ vào package contracts của branch; workspace dependency symlink mặc định trên máy đang trỏ tới repo dùng chung khác |
| Production build | PASS | Playwright real config build + prepare standalone hoàn tất trước browser test |
| Browser real flow | PASS | 1 test đăng ký → reload → logout → login đã pass |
| Rate-limit, lỗi Redis và registration concurrency trên PostgreSQL | NOT_RUN | Không diễn tập trên Redis dùng chung preview; xử lý unique constraint/row lock có unit/API coverage nhưng chưa chạy tải cạnh tranh |
| Email xác minh, OAuth, OTP, MFA, public deployment | DEFERRED | Ngoài phạm vi đã chọn |

## Đối chiếu database E2E

Truy vấn chỉ đếm dữ liệu tài khoản thử nghiệm, không in thông tin cá nhân:

```text
  users=2, workspaces=2, owners=2, brands=2, refresh_sessions=4
```

Bốn hàng refresh session tương ứng hai lần chạy browser, mỗi lần cấp một phiên lúc đăng ký và một phiên khi đăng nhập lại; mỗi test đã hoàn tất thao tác đăng xuất giữa hai lần cấp.

## Lệnh kiểm tra đã chạy

```sh
pytest -p no:cacheprovider -q tests/test_account_lifecycle.py
ruff check --no-cache services/api/auth.py services/api/dependencies.py services/api/schemas.py tests/test_account_lifecycle.py
ruff format --check --no-cache services/api/auth.py services/api/dependencies.py services/api/schemas.py tests/test_account_lifecycle.py
npm run test --workspace @agentic/web
npm run lint --workspace @agentic/web
E2E_REAL_API_BASE_URL=http://127.0.0.1:8001 E2E_REAL_PORT=13104 E2E_REAL_AUTH_TESTS=1 npm run test:e2e:real --workspace @agentic/web -- --grep 'self registration creates'
```

Không có DeepSeek hoặc Meta API call trong đăng ký. Tài khoản E2E dùng PostgreSQL riêng, không phải tài khoản của người dùng.
