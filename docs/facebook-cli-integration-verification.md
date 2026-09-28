# Kết quả nghiệm thu facebook-cli

## Trạng thái

**Phần code, migration và kiểm tra tự động đã qua; chưa tuyên bố live collection
hoàn tất.** Database/Redis bên dưới là disposable local test services. Chưa có
API/frontend/worker từ checkout này đang chạy, và database kiểm thử chưa có URL
Page đối thủ để thử live.

| Phần | Trạng thái | Bằng chứng / giới hạn |
|---|---|---|
| Upstream source/license pin | PASS | `facebook-cli` v0.3.0, commit `8e251abf0bc6fd28acca9b9fa1cafbd07ccae39`, Apache-2.0 |
| Go runner: Page identity, host allowlist, DNS/IP pinning, redirect, body/request budgets | PASS | `go test ./...` trên runner hiện tại; test redirect qua `http.Client` với fixture, gồm mirror `www` → `web`, không gọi Facebook live |
| Python adapter, API, crawler website regression, module persistence | PASS | 33 tests qua trong Python 3.13, gồm `test_facebook_cli_collector.py`, `test_market_research_api.py`, `test_market_research_sources.py`, `test_facebook_public_crawler.py`, `test_postgres_application_modules.py` |
| PostgreSQL/Redis durability tests | PASS | `tests/test_postgres_database_integration.py`: 5 tests trên PostgreSQL 18 và 2 Redis disposable instances |
| Migration 0020: fresh install | PASS | Database riêng migrate từ đầu tới `0020_facebook_cli_public_collector` |
| Migration 0020: upgrade từ 0019 | PASS | Nguồn bật lịch được đánh giá lại; nguồn tắt lịch giữ nguyên trạng thái/lỗi/`next_due_at`; group due được cập nhật |
| OpenAPI và TypeScript generation | PASS | `scripts/export_openapi.py` cập nhật `packages/contracts/openapi.json`; `apps/web/scripts/gen-api.mjs` sinh `schema.d.ts` |
| Frontend lint, typecheck, unit tests, production build | PASS | `npm run lint`, `npm run typecheck`, `npm test` (47 tests), `npm run build` |
| Python lint / API contract consistency | PASS | Ruff trên file Python đã sửa; `scripts/export_openapi.py --check` |
| Go runner test và build | PASS | `go test ./...` và build executable trong `/private/tmp` |
| Docker worker image build | NOT_RUN | Docker CLI/runtime không cài trên máy |
| Pipeline UI → Redis/Celery → PostgreSQL → reload | NOT_RUN | Docker không có; app/worker không chạy từ checkout này. Test persistence riêng không chứng minh thao tác browser end-to-end |
| Live competitor Page qua facebook-cli Tier 0 | NOT_RUN | Chưa có Page URL mẫu trong database test; không dùng Meta API/fixture thay bằng chứng live |
| DeepSeek analysis | NOT_RUN | Không cần để chứng minh crawler lưu dữ liệu; chưa có live evidence để phân tích |

## Môi trường và lệnh kiểm tra

- Branch: `codex/facebook-cli-collector`; base đã xác minh là
  `4326e34baec20a37b01bb79ce5a77b08a0909d39`; commit triển khai:
  `136d8ad99e237687abd2de823991acf075df0048`.
- PostgreSQL disposable: `127.0.0.1:15434`; queue Redis:
  `127.0.0.1:16381`; cache Redis: `127.0.0.1:16382`.
- Go: `go test -count=1 ./...`; `go build -o /private/tmp/facebook-cli-runner .`.
- Python: 33 regression/API/application tests; PostgreSQL/Redis durability: 5 tests.
- Frontend: OpenAPI export/generation, lint, typecheck, 47 unit tests, production build.
- Docker unavailable. Ports `13101` and `3101` không có listener thuộc checkout này.
- Không có secrets được in hoặc thêm vào docs. PostgreSQL/Redis test data và
  binary đặt ngoài Git trong `/private/tmp`.

## Cách đọc kết quả live

Live PASS chỉ khi có job ID và run ID, engine version đúng pin, bài/permalink
được đối chiếu với dữ liệu Facebook trả trong cùng lượt, observation được đọc lại
từ PostgreSQL và còn xuất hiện sau reload UI. Một lượt rỗng, login wall, CAPTCHA,
access denied, fixture hoặc Meta API là `LIVE_BLOCKED`, `LIVE_EMPTY` hoặc không
chạy; không phải `LIVE_PASS`.

Mọi số liệu không được engine cung cấp giữ `NULL` kèm lý do. Tier 0 luôn ghi
`history_complete=false`; số bài nhận được không được diễn giải là toàn bộ Page.
