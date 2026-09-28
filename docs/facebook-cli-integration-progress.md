# Tiến độ tích hợp facebook-cli

Nhánh triển khai: `codex/facebook-cli-collector`
Base commit: `4326e34baec20a37b01bb79ce5a77b08a0909d39`
Upstream pin: `tamnd/facebook-cli v0.3.0`, commit
`8e251abf0bc6fd28acca9b9fa1cafbd07ccae39`.

## Checklist

- [x] Kiểm tra nhánh nền và tách managed worktree riêng; giữ nguyên `/Users/lethanh/agent`.
- [x] Truy vết API → job → worker → evidence/observation → UI và xác nhận gate quyền/robots cũ.
- [x] Đọc source/package/license upstream; upstream dùng Apache-2.0.
- [x] Thêm Go runner Tier 0: không cookie/cache, giới hạn host, HTTPS/443, DNS pin tới IP công cộng, redirect, request, response, timeout và stdout.
- [x] Thêm Python subprocess adapter: môi trường sạch, giới hạn output, schema/version check, status và coverage một phần.
- [x] Nối worker vào evidence/version/observation, snapshot follower, advisory lock, heartbeat job fence và giữ Meta API cho Page sở hữu.
- [x] Bổ sung migration 0020 để đánh giá lại nguồn `public_web` bị gate cũ nhưng chỉ khi lịch đã bật; không đổi lịch tắt hay lịch sử.
- [x] Thêm engine/version/access tier vào response API và sửa thông báo Fanpage cho Tier 0/partial/block.
- [x] Tạo runbook và verification matrix.
- [x] Sinh lại OpenAPI/TypeScript từ script repository; chạy frontend lint/typecheck/tests/build.
- [x] Chạy migration và kiểm thử PostgreSQL/Redis trên hạ tầng disposable.
- [ ] Nghiệm thu bấm UI → worker → PostgreSQL → reload; hiện không có app/worker chạy từ checkout này.
- [ ] Kiểm tra Page đối thủ live Tier 0; chưa có URL Page mẫu trong database test.
- [ ] Rà diff/secret, commit, push nhánh và xác minh SHA remote.

## Nhật ký

### 2026-09-29 05:27 +07 — baseline

- Checkout bắt đầu ở `codex/facebook-cli-collector` tại base `4326e34`.
- Shared worktree `/Users/lethanh/agent` không bị đổi branch/index.
- `POSTGRES_TEST_URL`, `DATABASE_URL` và `FACEBOOK_CLI_RUNNER_PATH` không có trong process environment tại thời điểm kiểm tra; preview ports chưa được xác nhận đang phục vụ từ worktree này.
- `pg_isready 127.0.0.1:15432` không phản hồi. `initdb` trong sandbox bị chặn bởi System V shared memory; PostgreSQL integration chưa được chạy.

### 2026-09-29 05:28 +07 — kiểm thử mục tiêu

- `go test ./...` chạy trên runner sau `gofmt`: PASS. Bảo vệ gồm Page URL/identity, host/redirect allowlist, IP riêng/đặc biệt, body/request budget, metric parse, quyền sở hữu post và failure mapping.
- `tests/test_facebook_cli_collector.py` + `tests/test_market_research_api.py`: PASS, 11 tests, Python 3.13 với `pgvector` trong virtualenv tạm `/private/tmp/facebook-cli-test-venv`; không cài package vào Python hệ thống.
- Cần tiếp tục kiểm tra Docker, generated OpenAPI/types và frontend checks; kết quả live Facebook chưa có.

### 2026-09-29 05:53 +07 — integration và frontend

- PostgreSQL 18 disposable tại `127.0.0.1:15434`: migration mới tạo database từ đầu tới `0020` thành công. Database riêng nâng từ `0019` lên `0020` cũng thành công; migration chỉ đưa nguồn có `schedule_enabled=true` ra khỏi trạng thái gate cũ, giữ nguyên nguồn tắt lịch và lịch sử run.
- PostgreSQL/Redis disposable: `tests/test_postgres_database_integration.py` PASS, 5 tests. Kiểm tra migration head, fencing, cạnh tranh claim/recovery và phân biệt queue/cache.
- Python 3.13, PostgreSQL/Redis disposable: collector/API/crawler regression và `test_postgres_application_modules.py` PASS, 33 tests.
- OpenAPI xuất lại vào `packages/contracts/openapi.json`; TypeScript được sinh bởi `apps/web/scripts/gen-api.mjs`.
- Frontend PASS: ESLint, TypeScript typecheck, 47 Vitest tests và `next build`.
- Ruff trên file Python đã sửa và `scripts/export_openapi.py --check`: PASS.
- Go runner PASS: `go test ./...` và build executable; upstream giữ pin v0.3.0/full SHA.
- Implementation commit: `136d8ad99e237687abd2de823991acf075df0048`; push vẫn đang chờ kiểm tra remote.
- Docker không cài trên máy; không có API/frontend/worker đang chạy từ worktree này. Chưa chạy được UI → Celery → PostgreSQL → reload hay Facebook Page live. Không có Page URL mẫu trong database kiểm thử.
- Kết quả chi tiết và giới hạn được ghi tại `docs/facebook-cli-integration-verification.md`.
