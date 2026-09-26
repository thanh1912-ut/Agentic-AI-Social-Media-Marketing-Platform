# Báo cáo xác minh crawl website thật

Ngày chạy: 2026-09-26 (Asia/Ho_Chi_Minh). Code được kiểm thử trên nhánh `codex/real-market-crawl`, từ commit gốc `d462883` với implementation commit `aeca283`. Commit implementation đã được push lên nhánh riêng; docs bàn giao nằm cùng nhánh.

## Môi trường

- Python 3.11.16 trong virtualenv cô lập; frontend dependencies cài bằng `npm ci`.
- PostgreSQL 18.3 + pgvector 0.8.2, database test riêng trên loopback port 15432; Alembic đến `0013_metric_history_and_tenant_integrity`.
- Redis 8.6.3: queue riêng trên 16379 với persistence/noeviction; cache riêng trên 16380.
- FastAPI `127.0.0.1:8000`, Celery worker queues `default,agent` dùng pool `solo`, Celery beat, Next.js real mode `127.0.0.1:3100`.
- Local object storage dùng chung root cho API và worker. Docker/Podman không có trong môi trường này.
- Không có `DEEPSEEK_API_KEY` trong môi trường backend của test; chỉ kiểm tra sự vắng mặt, không ghi secret vào báo cáo.

## Luồng website thật

Đã đăng nhập workspace test, lưu nguồn `https://taphoammo.vn/`, rồi nhấn nút **Crawl ngay** bằng giao diện. Lượt crawl UI cuối:

| Hạng mục | Kết quả |
|---|---|
| Job | `616afe3b-63e5-42a8-8d45-b612d04b57cb` — `succeeded` |
| Research cycle | `d4a3c446-9748-4159-ad88-7b59fa769b72` — `succeeded` |
| Report | `f34a8422-03e3-4b6d-bf44-b1034acf60c5` |
| Source result | `collected`; 3 trang thấy, 3 evidence lưu |
| AI | `deepseek_not_configured`; không coi là phân tích hoàn tất |
| Sau reload | UI hiện report mới lúc 18:39 và lịch kế tiếp lúc 06:39 ngày hôm sau |

Worker log ghi task market research thành công. Database test giữ ba evidence duy nhất và ba phiên bản nội dung duy nhất qua ba lượt; mỗi lượt tạo ba observations và một report (9 observations, 3 reports tổng cộng). Điều này xác nhận crawl lặp cùng nội dung không nhân bản evidence/version.

Đã đọc raw object của trang gốc từ local storage: 362,759 byte và là HTML. Đoạn “shop thương mại bán lẻ” có trong cả HTML thô và text của evidence trong PostgreSQL. Test fixture riêng còn xác nhận metadata SEO ngắn không thay thế body ở cả trang gốc và trang con.

## Kiểm thử

| Kiểm tra | Kết quả |
|---|---|
| Regression crawler: thân bài so với `og:description` cho root/child | PASS |
| Python toàn bộ `tests` | PASS — 195 passed, 1 skipped, 1 warning |
| Skip | Test gọi DeepSeek thật; thiếu key trong môi trường test |
| Ruff trên file Python đã sửa | PASS |
| Frontend Vitest | PASS — 47 tests |
| Frontend TypeScript typecheck | PASS |
| Frontend ESLint | PASS |
| Alembic fresh PostgreSQL + pgvector | PASS — đến revision 0013 |
| API/Redis/cache/object-storage readiness | PASS |
| UI real mode → API → Redis/Celery → PostgreSQL → reload | PASS |
| Production build frontend (`NEXT_PUBLIC_USE_MOCKS=0`) | PASS — Next.js 15.5.26, build tối ưu và type validation hoàn tất |

Lệnh Python toàn bộ suite:

```sh
python -m pytest -p no:cacheprovider --basetemp=/private/tmp/agentic-market-crawl-pytest-all tests -q
```

Lệnh lint/test/typecheck chạy bằng script/package đã khai báo; xem lịch sử terminal của nhánh nếu cần đối chiếu log chi tiết.

## Chưa chạy hoặc giới hạn

- DeepSeek live analysis: NOT RUN, vì process backend test không có key/model cấu hình. Dữ liệu crawl được lưu độc lập.
- MinIO/S3 và Compose: NOT RUN; local storage và dịch vụ loopback cô lập được dùng.
- Test làm Redis hỏng/worker chết để thử recovery, hai worker cạnh tranh và scheduler time travel: NOT RUN trong runtime này; không dừng Redis/worker dùng chung của người dùng.
- Crawler không chạy JavaScript; kết quả chỉ phản ánh nội dung lấy được từ HTTP response công khai.
- Chạy worker `solo` không chứng minh tải đồng thời hoặc hành vi production.
- Chưa xác nhận metrics do website không trả về; trường thiếu vẫn để trống.
