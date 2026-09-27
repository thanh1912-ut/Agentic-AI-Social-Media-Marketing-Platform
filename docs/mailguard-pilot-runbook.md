# Runbook — MailGuard pilot local

Runbook này dành cho checkout `codex/mailguard-pilot` và database **kiểm thử riêng**. Không trỏ lệnh migration hoặc worker vào database production. Các tiến trình preview cũ trên cổng 8000/3100 thuộc checkout khác; pilot dùng API 8101 và web 3101.

## Phạm vi và cấu hình

- PostgreSQL + pgvector test: `127.0.0.1:25432/mailguard_pilot`.
- Redis queue test: `redis://127.0.0.1:26379/0`.
- Redis cache test: `redis://127.0.0.1:26380/0`.
- Local object storage: `/private/tmp/mailguard-pilot-storage`.
- API: `http://127.0.0.1:8101`; frontend: `http://127.0.0.1:3101`.
- Môi trường hiện tại là disposable/local. Không lưu dữ liệu cần giữ duy nhất tại `/private/tmp`.

API, worker và Beat phải nhận cùng `DATABASE_URL`, `REDIS_URL`, `REDIS_CACHE_URL`, `STORAGE_BACKEND` và `STORAGE_ROOT`. Repo không tự nạp `.env` cho mọi process; đặt biến cho từng terminal/process hoặc dùng secret manager. Không đưa `.env` chứa secret vào Git.

Các biến local cần có:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+asyncpg://<user>:<password>@127.0.0.1:25432/mailguard_pilot
REDIS_URL=redis://127.0.0.1:26379/0
REDIS_CACHE_URL=redis://127.0.0.1:26380/0
STORAGE_BACKEND=local
STORAGE_ROOT=/private/tmp/mailguard-pilot-storage
AUTO_CREATE_SCHEMA=0
INLINE_JOBS=0
JWT_SECRET=<local-secret-generated-outside-git>
META_TOKEN_ENCRYPTION_KEY=<persistent-fernet-key-generated-outside-git>
ALLOWED_HOSTS=127.0.0.1,localhost
CORS_ALLOWED_ORIGINS=http://127.0.0.1:3101
WEB_BASE_URL=http://127.0.0.1:3101
NEXT_PUBLIC_USE_MOCKS=0
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8101
```

Đặt `DEEPSEEK_API_KEY` và model hợp lệ chỉ trong backend secret store nếu muốn gọi DeepSeek. Không đặt chúng trong `NEXT_PUBLIC_*`, không in trong log. Để trống thì campaign planning trả trạng thái thiếu cấu hình nhưng không làm mất dữ liệu. Page token và khóa mã hóa Meta cũng chỉ ở backend; kiểm thử này không có Meta credentials và không tự đăng bài.

### Cấu hình riêng đã chuẩn bị trên máy pilot

Từ 2026-09-27, cấu hình của API/worker/Beat được giữ tại
`/Users/lethanh/.local/share/agentic-marketing/mailguard-pilot/runtime.json`,
ngoài Git và chỉ chủ tài khoản đọc/ghi (0600). File này chứa khóa mã hóa token,
cấu hình database và khóa phiên đăng nhập; không đưa nội dung vào log hoặc Git.
Giữ nguyên khóa mã hóa qua các lần restart và sao lưu riêng khi cần giữ token
đã kết nối. Không tạo khóa mới tùy ý sau khi đã lưu token thật.

Launcher local dưới đây nạp cùng cấu hình cho cả ba tiến trình và kiểm tra
mã hóa/giải mã trước khi chạy. Chạy mỗi lệnh `api`, `worker`, `beat` trong
một terminal riêng, sau khi dừng đúng tiến trình pilot cũ:

```sh
/private/tmp/mailguard-pilot-venv/bin/python /Users/lethanh/.local/share/agentic-marketing/mailguard-pilot/run_pilot.py check
/private/tmp/mailguard-pilot-venv/bin/python /Users/lethanh/.local/share/agentic-marketing/mailguard-pilot/run_pilot.py api
/private/tmp/mailguard-pilot-venv/bin/python /Users/lethanh/.local/share/agentic-marketing/mailguard-pilot/run_pilot.py worker
/private/tmp/mailguard-pilot-venv/bin/python /Users/lethanh/.local/share/agentic-marketing/mailguard-pilot/run_pilot.py beat
```

Launcher cũng đọc các giá trị provider không rỗng trong
`.env.providers.local` của worktree. File này được Git bỏ qua. Lưu DeepSeek
key vào file chưa làm thay đổi process đang chạy; cần restart bằng launcher.
Các file runtime và launcher là cấu hình riêng trên máy này, không có trong
repository khi clone sang máy khác; máy mới dùng biến môi trường ở trên.

Nếu nhận lỗi `token_encryption_unavailable`, kiểm tra cấu hình backend trước;
đó chưa phải kết quả kiểm tra Page Access Token với Meta. Sau khi backend có
khóa hợp lệ, người dùng nhập lại token và bấm **Xác minh và lưu Fanpage**.

## Khởi động

Từ thư mục worktree `/Users/lethanh/.codex/worktrees/mailguard-pilot/agent`:

1. Xác nhận đúng PostgreSQL/Redis test instance trước khi khởi động. Không dừng process chỉ dựa vào số cổng.
2. Với biến backend ở trên, kiểm tra schema rồi migrate database test:

   ```sh
   /private/tmp/mailguard-pilot-venv/bin/python -m alembic current
   /private/tmp/mailguard-pilot-venv/bin/python -m alembic upgrade head
   ```

3. Mở terminal API:

   ```sh
   /private/tmp/mailguard-pilot-venv/bin/python -m uvicorn services.api.main:app --host 127.0.0.1 --port 8101
   ```

4. Mở terminal worker để xử lý job thật từ Redis:

   ```sh
   /private/tmp/mailguard-pilot-venv/bin/python -m celery -A services.worker.celery_app:celery_app worker --loglevel=INFO --queues=default,agent --pool=solo --concurrency=1
   ```

5. Mở terminal Beat để quét lịch bền vững mỗi phút:

   ```sh
   /private/tmp/mailguard-pilot-venv/bin/python -m celery -A services.worker.celery_app:celery_app beat --loglevel=INFO --schedule=/private/tmp/mailguard-pilot-celerybeat-schedule
   ```

6. Trong terminal frontend:

   ```sh
   cd apps/web
   NEXT_PUBLIC_USE_MOCKS=0 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8101 NEXT_PUBLIC_ENVIRONMENT_LABEL='MailGuard pilot local' npm run dev -- --hostname 127.0.0.1 --port 3101
   ```

7. Mở `http://127.0.0.1:3101/login`. Xác nhận `/readyz` tại `http://127.0.0.1:8101/readyz`. Các biến Next.js được nhúng lúc khởi động; restart frontend sau khi đổi.

Đăng ký tài khoản workspace hiện qua API `/api/v1/auth/register` (giao diện đăng nhập không phải trang self-signup). Dùng database test riêng và thông tin test không được ghi vào docs/Git. Khi bắt đầu thao tác, chọn/tạo workspace pilot riêng, tải tài liệu MailGuard có quyền dùng, rà nội dung trích xuất rồi xác nhận Brand Profile. Không nhập logo/website/claim chưa được xác thực.

## Kiểm tra pilot

1. Upload tài liệu và theo dõi job đến khi dữ liệu còn đọc được sau reload.
2. Xác nhận Brand Profile trước khi dùng planning/generation.
3. Tạo yêu cầu campaign, xem brief và ba concept; chọn concept rồi xác nhận tạo campaign.
4. Tạo bài, lưu/sửa phiên bản; chạy review. Chỉ phiên bản/hash được review `ready` mới đủ điều kiện Owner approval.
5. Để kiểm tra hẹn giờ mà không phát bài thật: dùng Page test đã được xác minh và thời gian tương lai, rồi hủy trước due time. Không dùng production Page cho test tự động.
6. Analytics conversion ban đầu phải là `INTEGRATION_READY` / `not_connected` hoặc `no_data`, không phải conversion 0 giả. Receiver chỉ dùng server-to-server.

Không tạo event conversion bằng đăng nhập hệ thống marketing. Không giả lập `first_analysis_completed` từ một lượt thất bại hoặc fixture. Website MailGuard chưa có nên không thể nghiệm thu live conversion.

## Backup, restore và vận hành

- Dùng `docs/database-runbook.md` cùng `scripts/backup_postgres.sh` cho PostgreSQL. Backup file storage riêng theo chính sách deployment; khóa mã hóa Fanpage được sao lưu riêng khỏi DB.
- Thử restore vào database/storage khác, xác minh checksum và mở dữ liệu qua API trước khi gọi là có backup usable.
- Backup trên cùng máy không thay thế bản sao ngoài máy.
- Máy local phải đang chạy để Beat phát lịch. Nếu lỡ quá 15 phút, schedule chuyển `missed`; Owner phải chọn giờ mới.
- Kết quả publish không rõ chuyển sang đối soát; không retry gửi bài tự động.

## Dừng phiên

Dừng bằng `Ctrl-C` trong đúng terminal API, worker, Beat và frontend của worktree pilot. Dừng PostgreSQL/Redis chỉ khi xác nhận đó là test instance trên cổng 25432/26379/26380. Không dừng API/Redis/PostgreSQL preview ở cổng 8000/3100/15432/16379/16380. Xóa database/storage test chỉ sau khi đã xác nhận không còn cần bằng chứng.
