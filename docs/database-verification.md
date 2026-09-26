# Báo cáo nghiệm thu PostgreSQL/Redis

Cập nhật: 2026-09-27 01:15 Asia/Ho_Chi_Minh

## Môi trường và phiên bản

- Branch: `codex/project-database-hardening`, base `4fcda2042d9709d84bab42afd27d01b8131d32c3`.
- PostgreSQL 18.3 + pgvector; Redis 8.6.3 queue/cache trên cổng riêng 15432/16379/16380, chỉ loopback.
- CI Compose dùng PostgreSQL 16 + pgvector và Redis 7.4.
- Backend chạy bằng Python 3.11 venv `/private/tmp/agentic-marketing-py311`.
- Database `fresh`, `upgrade`, `test` và database restore mới đều ở revision `0017_web_entity_snapshot_immutability`; `alembic check` sạch khi chạy migration-owner credentials.
- DeepSeek/Meta secrets không dùng và không ghi vào báo cáo.

## Kết quả kiểm tra

| Khu vực | Trạng thái | Bằng chứng / giới hạn |
|---|---|---|
| Fresh migration và upgrade | PASS | PostgreSQL database mới migrate từ đầu; database lịch sử ở `0013` upgrade đến `0017`; model/schema parity sạch trên fresh, upgrade, test và restore owner database. |
| Schema và tenant constraints | PASS | `0015` thêm constraint crawl run/job, crawl page/evidence/version và deferred latest snapshot guard; `0017` ngăn sửa/xóa snapshot đang được tham chiếu. PostgreSQL inspector kiểm tra FK ghép và all-or-none check; API smoke xác nhận pointer không hợp lệ bị từ chối. |
| Sửa sai lệch lịch sử | PASS | `0016` thêm `market_report_evidence.created_at` cho database cũ, backfill từ report hoặc thời điểm migration, rồi đặt NOT NULL. Không xóa dữ liệu. |
| Bảo vệ snapshot mới nhất | PASS | `0017` thay đổi trigger trong transaction riêng; snapshot được tham chiếu không thể bị sửa hoặc xóa. `alembic check` không báo lệch metadata. |
| Fencing và cạnh tranh worker | PASS | PostgreSQL integration chứng minh stale claim không commit; hai claim đồng thời cho một job chỉ có một claim thành công. API-module smoke cũng kiểm tra terminal worker error được commit sau khi lease được xác thực; fenced session chặn autoflush trước điểm kiểm tra claim. |
| Job sau dispatch lỗi | PASS | Integration test để dispatch adapter báo queue unavailable; job vẫn `queued` trong PostgreSQL, có error telemetry, và scheduler dispatch lại sau khi lease hết hạn. Đây là lỗi dispatch deterministic, không phải phép thử dừng Redis live. |
| Redis queue/cache | PASS | Hai instance thật riêng; test kết nối hai Redis và TTL. Queue AOF/noeviction, cache ephemeral/allkeys-lru. Cache lỗi được xác minh qua test adapter optional-cache. |
| Backend | PASS | Full suite trên PostgreSQL/Redis riêng: 215 passed, 1 skipped, 1 warning. DeepSeek live smoke bị skip vì không bật secret runtime; không gọi Meta live. |
| API lưu dữ liệu nhiều module | PASS | PostgreSQL TestClient smoke đăng ký workspace, xác nhận Brand Profile, tạo nhóm và mã hóa Page token, lưu market evidence/version/observation, tạo campaign/post/approval, ghi metrics và upload tài liệu. Worker parser lưu knowledge chunks; khi DeepSeek không cấu hình, dữ liệu giữ nguyên và job báo lỗi AI có thể xử lý. |
| Frontend | PASS | `npm run lint`, `npm run typecheck`, 47 frontend tests và `npm run build` đều pass trong checkout này. |
| Readiness | PASS | Sau khi nạp code cuối, `/readyz` trên cổng 8000 trả `ready`, database/schema/Redis queue/cache/object storage đều true. Trang Fanpage real mode trên cổng 3100 trả HTTP 200; API, worker và beat hiện chạy từ branch checkout này. |
| Crawl qua UI real mode | PASS có giới hạn | Người dùng test đăng nhập, thêm `https://taphoammo.vn`, tắt lịch và bấm Crawl ngay. Redis/Celery xử lý job; PostgreSQL giữ kết quả sau reload. Crawl giới hạn 10 trang, báo `partial` thay vì giả định quét toàn site. |
| Dữ liệu crawl | PASS có giới hạn | Job `823cd4ac-4117-4c8d-b0a3-4e061addd9f2` succeeded, progress 100; run `915e6ba6-8aba-4837-918a-2f1c8a93e1fe` partial, 10/10 trang lưu; cycle `b5c14a2b-70a6-4af1-be67-5af60ae2179c`; report `8f586b89-1edc-4762-b5da-841880ca784a`; 10 report evidence, 1 product, 7 articles, 1 business-info entity. Giá sản phẩm hiển thị là liên hệ báo giá, sold count giữ thiếu. |
| AI phân tích | NOT RUN | Report có `deepseek_not_configured`; dữ liệu crawl vẫn lưu. Không có DeepSeek API call hay số đo chi phí/latency. |
| Page/Facebook live | NOT RUN | Không có Page token nào được dùng. Các luồng metric được kiểm thử bằng adapter/fixtures. |
| Backup checksums | PASS | Bundle `/Users/lethanh/.local/share/agentic-marketing/backups/agentic-agentic_marketing_fresh-20260926T170759Z`; `postgres.dump` và `storage.tar.gz` checksum hợp lệ. |
| Restore và API read | PASS | Restore vào database/storage riêng; revision `0017`, 1 user test, crawl/run/entity snapshot/report và 10 report evidence còn nguyên. Storage restore có 13 file. App-role login và GET `web-items` trả HTTP 200 với 9 entity. |
| Lịch backup local | PASS | PostgreSQL/Redis/backup LaunchAgents được nạp lại. Backup chạy mỗi ngày 03:00 và bù khi đăng nhập nếu bundle mới nhất quá 24 giờ. |
| Chất lượng mã và tài liệu | PASS | Python `compileall`, `bash -n` cho installer/backup và `git diff --check` pass. Frontend lint/typecheck/47 tests/build đã pass trên cùng checkout. |
| Nhánh GitHub | PASS | `codex/project-database-hardening` đã push; `git ls-remote` xác nhận remote ref trùng local HEAD sau lần push cuối. |
| Redis bị dừng thật, worker bị kill giữa transaction | NOT RUN | Không dừng queue mà frontend đang sử dụng. Đã kiểm thử queue-dispatch failure, lease expiry logic hiện có, claim race và stale fencing trên PostgreSQL thật. |
| MinIO/S3, backup ngoài máy | NOT RUN | Đợt local dùng storage filesystem và bundle cùng máy; cần môi trường triển khai riêng để nghiệm thu. |

## Dữ liệu dùng cho giao diện kiểm thử

- Frontend: `http://127.0.0.1:3100/w/0a7358b2-ad17-4fba-b310-4c2ced38f43e/fanpages`.
- API: `http://127.0.0.1:8000`.
- Workspace test: `0a7358b2-ad17-4fba-b310-4c2ced38f43e`; group test: `80f2e49c-3517-47e9-87e0-8c179966d1a3`.
- Nguồn website test có `schedule_enabled=false`, `next_due_at=NULL`; group không còn lịch tiếp theo khi không có nguồn scheduled khác.
- Không ghi mật khẩu test vào repo/docs. Tài khoản test chỉ tồn tại trong database local `agentic_marketing_fresh`.

## Giới hạn và kết luận

PostgreSQL/Redis và luồng database cho các module backend hiện có đã chạy được trong local real mode. Kiểm thử chứng minh migration, tenant constraints, lưu lịch sử, dispatch recovery, worker fencing, catalog crawl, reload, backup và restore API read.

Chưa đủ bằng chứng để tuyên bố mọi failure mode và tích hợp ngoài đều đã nghiệm thu: chưa rút Redis thật hoặc kill worker giữa lượt chạy; DeepSeek, Meta live, MinIO/S3 và backup off-machine chưa được kiểm tra. Lượt crawl website đạt giới hạn 10 trang và được đánh dấu partial; điều đó không đồng nghĩa quét hết website.
