# Runbook: crawl website thật

Hướng dẫn chạy luồng website công khai qua API, Redis/Celery, PostgreSQL và giao diện Next.js. Chỉ chạy migration trên database local/test đã xác nhận; không trỏ vào production.

## Điều kiện cần

- Python 3.11, Node.js theo `package.json` (Node 22 trở lên), PostgreSQL có extension `vector`, Redis queue và một Redis cache riêng.
- Cài package trong môi trường dự án: `python -m venv .venv`, kích hoạt virtualenv, rồi `python -m pip install -e '.[dev]'`.
- Tại thư mục repo, chạy `npm ci` để cài frontend theo lockfile.
- API và worker phải có cùng `DATABASE_URL`, `REDIS_URL`, `REDIS_CACHE_URL`, storage backend và storage root.

## Cấu hình local

Đặt các biến trong môi trường riêng của từng process hoặc secret manager; tiến trình Python không tự động đọc `.env` nếu repo chưa cấu hình việc đó. Không commit `.env`, token hay key.

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://<user>:<password>@127.0.0.1:5432/<test_db>
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_CACHE_URL=redis://127.0.0.1:6380/0
STORAGE_BACKEND=local
STORAGE_ROOT=/absolute/path/shared-crawl-storage
AUTO_CREATE_SCHEMA=0
INLINE_JOBS=0
MARKET_CRAWL_MAX_PAGES=3
WEB_BASE_URL=http://127.0.0.1:3100
CORS_ALLOWED_ORIGINS=http://127.0.0.1:3100
NEXT_PUBLIC_USE_MOCKS=0
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

`NEXT_PUBLIC_API_BASE_URL` là origin API, không thêm `/api/v1`. Hai biến `NEXT_PUBLIC_*` được nhúng lúc chạy frontend; cần restart dev server hoặc build lại sau khi đổi.

Chỉ cấu hình `DEEPSEEK_API_KEY` và `LLM_DEFAULT_MODEL` ở backend nếu muốn chạy phân tích. Không cần key để crawl và lưu bằng chứng. Không đưa key sang frontend.

## Migration và khởi động

Trỏ `DATABASE_URL` đến database test riêng; kiểm tra extension `vector`, rồi chạy:

```sh
python -m alembic upgrade head
python -m alembic current
```

Chạy mỗi lệnh dưới đây trong terminal riêng, với cùng cấu hình backend:

```sh
python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
```

```sh
python -m celery -A services.worker.celery_app:celery_app worker --loglevel=INFO --queues=default,agent --pool=solo --concurrency=1
```

```sh
python -m celery -A services.worker.celery_app:celery_app beat --loglevel=INFO --schedule=/absolute/path/celerybeat-schedule
```

`--pool=solo` phù hợp kiểm tra local trên macOS; chọn pool và concurrency production sau khi kiểm tra môi trường triển khai. Scheduler lấy lịch đến hạn từ PostgreSQL, không giữ task chờ 12 giờ trong Redis.

Chạy frontend từ thư mục `apps/web`, với `NEXT_PUBLIC_*` đã đặt:

```sh
npx next dev --hostname 127.0.0.1 --port 3100
```

Kiểm tra readiness API ở `http://127.0.0.1:8000/readyz`, rồi mở `http://127.0.0.1:3100`. Nếu API prefix khác, lấy endpoint từ OpenAPI của chính backend đang chạy.

## Crawl từ giao diện

1. Đăng nhập vào workspace test; vào **Fanpage & thị trường**.
2. Tạo/chọn nhóm test và thêm URL website công khai làm nguồn.
3. Nhấn **Crawl ngay**. Giao diện nhận job ID và liên kết theo dõi tiến độ; worker chạy bất đồng bộ.
4. Chờ job hoàn tất, kiểm tra báo cáo và tình trạng phân tích. Crawl thành công không đồng nghĩa DeepSeek phân tích thành công.
5. Tải lại trang. Report và evidence phải vẫn hiển thị từ PostgreSQL.

## Phân loại kết quả

- `succeeded` + `analysis_status=completed`: crawl lưu được và phân tích AI hoàn tất.
- `succeeded` + `analysis_status=deepseek_not_configured`: crawl/lưu thành công; chưa cấu hình DeepSeek.
- `succeeded` + `analysis_status=deepseek_failed`: dữ liệu crawl được giữ lại; lời gọi AI thất bại.
- `no_evidence`: không thu thập được evidence dùng được; xem `source_results` và log worker.
- Job không kết thúc: kiểm tra API readiness, Redis queue, worker, lease/recovery và log theo job ID. Job phải được ghi PostgreSQL trước khi đưa vào queue.

Giữ chỉ số không có nguồn là `NULL`/thiếu; không biến thành 0. Nếu một nguồn lỗi nhưng nguồn khác thành công, đọc `source_results` theo từng source.

## Dừng phiên local

Dừng bằng `Ctrl-C` trong đúng terminal đã khởi động API, worker, scheduler và frontend. Chỉ dừng PostgreSQL/Redis test nếu chúng thuộc phiên test này; không kill process theo cổng chung nếu chưa xác nhận tiến trình đó. Không xóa thư mục storage/database đang chứa dữ liệu người dùng.

## Đã/Chưa nghiệm thu

Lượt kiểm chứng taphoammo ngày 2026-09-26 chạy qua UI, PostgreSQL, Redis/Celery và local storage; chi tiết và giới hạn nằm trong [báo cáo xác minh](real-crawl-verification.md). MinIO/S3, Compose, DeepSeek live call, trình duyệt JavaScript cho crawler và production concurrency chưa được xác minh trong lượt đó.
