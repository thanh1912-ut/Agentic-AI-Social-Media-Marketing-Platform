# Tiến độ nghiệm thu crawl website thật

Cập nhật lần cuối: 2026-09-26 18:47 (Asia/Ho_Chi_Minh)

## Tiến độ

- [x] Tạo checkout biệt lập trên nhánh `codex/real-market-crawl`, từ `origin/codex/page-groups-market-research` ở commit gốc `d462883`.
- [x] Tạo virtualenv Python 3.11 và cài dependencies dự án; cài dependencies frontend bằng lockfile.
- [x] Thêm regression test tái hiện lỗi `og:description` làm mất thân bài ở trang gốc và trang con; sửa parser để ưu tiên article/main, rồi fallback body và metadata/JSON-LD đã deduplicate.
- [x] Thêm giới hạn số trang có thể cấu hình qua `MARKET_CRAWL_MAX_PAGES`; smoke test giới hạn 3 trang.
- [x] Khởi động PostgreSQL 18 + pgvector, hai Redis tách biệt, FastAPI, Celery worker, scheduler và frontend real mode. Readiness trả database, Redis queue/cache và object storage đều sẵn sàng.
- [x] Alembic `upgrade head` hoàn tất đến `0013_metric_history_and_tenant_integrity` trên database test mới.
- [x] Bấm **Crawl ngay** trong giao diện real mode cho `https://taphoammo.vn/`; job đi qua API → Redis/Celery → PostgreSQL và kết thúc `succeeded`.
- [x] Tải lại trang và thấy báo cáo/lượt crawl mới nhất vẫn còn trong database/API.
- [x] So khớp đoạn thân bài trong PostgreSQL với HTML thô cùng lượt đã lưu trong local object storage: response 362,759 byte, câu thân bài có trong HTML gốc.
- [x] Crawl lặp lại giữ 3 evidence và 3 evidence version, không nhân bản; tạo observation và report cho mỗi lượt.
- [x] Chạy test Python, lint/typecheck/test frontend; kết quả chi tiết ở [báo cáo xác minh](real-crawl-verification.md).
- [x] Viết runbook và báo cáo kiểm chứng.
- [x] Frontend production build pass ở real mode; server dev được khởi động lại để giữ trang test mở cho người dùng.
- [x] Rà diff/secret; commit implementation `aeca283` đã push lên `codex/real-market-crawl`; runbook và báo cáo này được đưa vào nhánh trước khi kết thúc.

## Mốc của lượt crawl UI cuối

- Thời gian: `2026-09-26 18:39` giờ Việt Nam.
- URL nguồn: `https://taphoammo.vn/`; giới hạn cấu hình 3 trang.
- Job: `616afe3b-63e5-42a8-8d45-b612d04b57cb` — `succeeded`.
- Cycle: `d4a3c446-9748-4159-ad88-7b59fa769b72` — `succeeded`.
- Report: `f34a8422-03e3-4b6d-bf44-b1034acf60c5`.
- Kết quả: 3 trang thu thập, 3 evidence lưu; `analysis_status=deepseek_not_configured`.
- PostgreSQL sau ba lượt tổng cộng: 3 evidence duy nhất, 3 phiên bản nội dung duy nhất, 9 observations và 3 reports.

## Môi trường và giới hạn

- Các dịch vụ chạy trong môi trường test cô lập dưới `/private/tmp`; PostgreSQL 15 và Redis 6379 có sẵn trên máy không bị thay đổi.
- Docker, Podman và `uv` không có sẵn. PostgreSQL/pgvector và Redis được khởi chạy riêng; object storage dùng thư mục local chung cho API/worker. MinIO/S3 và Compose chưa được nghiệm thu.
- `DEEPSEEK_API_KEY` không có trong môi trường của các process test. Crawl và lưu dữ liệu vẫn thành công; phân tích AI chưa chạy. Không có secret nào được ghi vào repo.
- Worker chạy Celery `solo` cho test trên macOS. Đây không phải kiểm chứng throughput/concurrency production.
- Đã kiểm tra UI với tài khoản/workspace test riêng; không dùng workspace sản xuất.
