# Runbook: tự thu thập Fanpage đối thủ

## Cấu hình

Page đối thủ mới dùng collector `public_web`, mặc định bật lịch 12 giờ. Không cần Page Access Token của workspace. Meta Page Access Token thuộc kết nối Page mà workspace sở hữu và không cấp quyền đọc Page đối thủ.

Biến môi trường liên quan:

```dotenv
FACEBOOK_PUBLIC_AUTOMATION_AUTHORIZED=0
DATABASE_URL=postgresql+asyncpg://<app-user>:<password>@<postgres-host>:<port>/<database>
REDIS_URL=redis://<queue-host>:<port>/0
REDIS_CACHE_URL=redis://<cache-host>:<port>/0
AUTO_CREATE_SCHEMA=0
INLINE_JOBS=0
NEXT_PUBLIC_USE_MOCKS=0
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

`FACEBOOK_PUBLIC_AUTOMATION_AUTHORIZED` phải giữ `0` trừ khi đơn vị vận hành có xác nhận bằng văn bản của Meta áp dụng cho ứng dụng, dữ liệu và mục đích thu thập này. Không bật biến chỉ vì Page URL xem được bằng trình duyệt. Ngay cả khi gate được bật, collector vẫn kiểm tra robots.txt, redirect, hostname, login wall và challenge; các giới hạn nguồn tiếp tục áp dụng.

Không lưu token, cookie, API key hoặc mật khẩu trong Git. Collector công khai không dùng cookie trình duyệt. Không bật renderer JavaScript trong bản này; nếu HTTP không thể đọc nội dung thì kết quả phải phản ánh thiếu hoặc bị chặn.

## Khởi chạy

1. Cài dependency theo lockfile/README của repo và đặt biến môi trường từ secret store.
2. Chạy migration trước khi khởi động API:

   ```bash
   alembic upgrade head
   ```

3. Khởi động PostgreSQL, Redis queue và Redis cache theo cấu hình triển khai.
4. Chạy API, worker (`default,agent`) và Celery Beat theo lệnh trong README/deployment hiện hành.
5. Khởi chạy Next.js với `NEXT_PUBLIC_USE_MOCKS=0` và API base URL không có hậu tố `/api/v1`.
6. Mở Fanpage & thị trường, chọn nhóm, lưu Page đối thủ một lần. Nguồn mới mặc định public_web và lịch 12 giờ.
7. Dùng **Crawl ngay** để tạo durable job. Mở **Bài viết & lịch sử** để xem run, bài lưu, coverage và lý do bị chặn.

Endpoint mới dưới prefix `/api/v1/workspaces/{workspace_id}/market-research`:

- `PATCH /sources/{source_id}/collection-settings`
- `POST /sources/{source_id}/crawl`
- `GET /sources/{source_id}/collection-runs`
- `GET /sources/{source_id}/posts`

## Vận hành và giới hạn

- Mỗi lượt tối đa 50 bài trong cửa sổ 90 ngày, cấu hình 1–100; lấy được bao nhiêu phụ thuộc trang công khai và chính sách nền tảng.
- V1 đọc HTTP snapshot của Page; không có pagination/feed checkpoint đầy đủ. Coverage luôn là partial.
- Không thu hồ sơ/người bình luận; số liệu thiếu được lưu NULL và có lý do. Followers thuộc Page, không nhân lên từng post.
- Run blocked do yêu cầu quyền, robots, đăng nhập hoặc challenge không được retry liên tục. Lịch người dùng vẫn được lưu; trạng thái giải thích tại nguồn. Crawl thủ công có thể thử lại khi điều kiện thay đổi.
- Tắt lịch ngăn scheduler đưa nguồn vào lượt định kỳ; Crawl ngay vẫn khả dụng.
- Lỗi DeepSeek không làm mất evidence đã lưu; AI chỉ phân tích khi có bằng chứng mới và cấu hình phù hợp.

## Dừng tiến trình

Dừng tiến trình API, Celery worker và Beat đúng theo process manager mà bạn đã dùng (ví dụ `Ctrl+C` trong terminal tương ứng hoặc `launchctl`/Compose service cụ thể). Không dừng Redis/PostgreSQL dùng chung trước khi xác định chúng chỉ phục vụ ứng dụng này. Không dùng `killall`.

## Khôi phục sự cố

- `platform_permission_required`: hệ thống chưa có xác nhận quyền tự động bằng văn bản; không bật gate để thử vận may. Liên hệ Meta hoặc dùng collector Meta API chỉ khi Page Access Public Content được Meta cấp cho app.
- `blocked_robots`: tôn trọng robots; không đổi User-Agent, không bỏ qua robots.
- `login_required` / `challenge_required`: nguồn không đọc công khai được; không dùng cookie, tài khoản, CAPTCHA bypass hoặc proxy né chặn.
- `rate_limited`: đợi đến thời điểm retry sau theo response; không bấm lặp liên tục.
- `renderer_unavailable`: renderer không nằm trong V1; trạng thái này không được coi là crawl thành công.
- Lượt mới lỗi: dữ liệu cũ vẫn được giữ và hiển thị thời điểm cập nhật cuối.

## Môi trường smoke tạm của bản triển khai

Trong quá trình nghiệm thu, frontend chạy ở `http://127.0.0.1:13101`, API ở `http://127.0.0.1:18000`, PostgreSQL/Redis là các instance tạm trong `/private/tmp` trên các socket/port riêng. Đây là dữ liệu test, không phải deployment bền vững; không dùng làm nơi lưu dữ liệu người dùng lâu dài.
