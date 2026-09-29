# Nghiệm thu đăng ký và đăng nhập

Ngày chạy: 2026-09-29 10:18 UTC. Base code: `cf8f41e`; branch triển khai: `codex/auth-registration-login`.
Commit đã push: `4cd0a06dbcec387266b34e6f0a05c785aabd53cd` (remote SHA khớp).

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

## Khôi phục cấu hình DeepSeek preview (2026-09-29)

| Hạng mục | Trạng thái | Bằng chứng |
|---|---|---|
| Nguyên nhân key không tới API | PASS | Launcher kiểm thử cũ gán key rỗng và model khác; key trong secret store vẫn hiện diện, không cần người dùng cung cấp lại |
| Secret bền vững và không lộ giá trị | PASS | Runtime đọc `deepseek-docling.env` ở mỗi lần start; mode `0600`; status chỉ báo present/missing |
| Cấu hình model | PASS | `deepseek-flash` xuất hiện trong response `GET /models`; probe không in key |
| Cách ly preview | PASS | Runtime cố định database auth test và Redis queue/cache DB `/4`; API port `8001`, web port `13104` |
| Tách quyền provider khỏi ingestion | PASS | API/worker agent nhận key; worker ingestion và Beat không nhận key; unit test xác nhận |
| Runtime ngoài `/private/tmp` | PASS | Hai Python env, Docling models và storage đã được sao chép vào `~/.local/share/agentic-marketing/auth-preview/`; nguồn cũ được giữ để rollback |
| Cấu hình launcher có kiểm tra | PASS | 6 test unit cho env parsing, AI injection, Redis/database isolation, ingestion, dispatch và beat; Ruff/format pass |
| API/worker/Beat LaunchAgents và readiness | PASS | Năm service (API, web, worker `default,agent`, worker `ingestion`, Beat) đều `running`; `/readyz` trả `200 ready`, `/login` trả `200` |
| DeepSeek key/model sau khi restart | PASS | Safe probe xác nhận key `present; value hidden`; `deepseek-flash` khả dụng qua `GET /models` |
| Job ingestion đã chờ | PASS | Celery Beat recovery dispatch job durable; PostgreSQL thống kê `document_ingest: succeeded=1`, document record=1; UI đọc được CSV `41.188` dòng, `4.029.468` ký tự |
| Ingestion không gọi DeepSeek | PASS | Env của worker ingestion chủ động loại `DEEPSEEK_API_KEY`; tài liệu hoàn tất bằng Docling/knowledge pipeline |
| Một job AI tổng hợp qua Redis và ghi PostgreSQL | PASS | Campaign-plan job synthetic thành công, model `deepseek-flash`, 3 concept, 1.129 input / 4.431 output tokens, latency 19.995 ms; output đã được đọc từ PostgreSQL rồi workspace tổng hợp được xóa |
| Giới hạn provider requests | PASS WITH LIMITATION | Adapter chỉ cho một repair tối đa, nên một generation job phát sinh tối đa 2 request. Số repair thực tế không được lưu trong Job result; không khẳng định chính xác 1 hay 2 request |
| Giữ phiên và dữ liệu qua reload | PASS | Browser sau restart vẫn mở workspace có phiên Owner; tài liệu đã xử lý đọc được từ API. Không có redirect về login |
| Redis isolation | PASS | Queue và cache preview dùng database `/4`; readiness đạt, worker và Beat chạy trên cùng cấu hình |
| Runtime unit tests/lint | PASS | 6 passed; Ruff check/format, compile scripts và `git diff --check` sạch |
| Upload tài liệu không gọi tạo Brand Profile | PASS | Worker hiện tại không còn `_run_brand_profile`; ingestion chỉ dùng Docling/knowledge pipeline |

**Quan trọng:** kết quả đăng ký/đăng nhập ở phần trên vẫn áp dụng cho auth feature branch. Phần DeepSeek này nghiệm thu cấu hình local preview riêng, không đổi database/tài khoản đã tạo. Chi tiết dịch vụ và lệnh phục hồi nằm trong runbook.

Thời điểm kiểm tra DeepSeek preview: 2026-09-29 11:33 UTC. Không ghi key, prompt raw, tài liệu người dùng hoặc nội dung output model vào báo cáo. Smoke AI chỉ dùng hồ sơ giả; job/workspace tổng hợp đã được xóa sau khi xác nhận output được commit vào PostgreSQL.

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
