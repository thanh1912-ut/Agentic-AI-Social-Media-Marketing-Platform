# Fanpage, nhóm thị trường và nghiên cứu định kỳ

Cập nhật: 2026-09-25

## Chức năng nền tảng hiện có

- Đăng ký/đăng nhập, đặt lại mật khẩu, mời thành viên và phân quyền theo workspace.
- Tải tài liệu lên, chạy xử lý nền, theo dõi job, lưu tri thức và lập/xác nhận Brand Profile.
- Tạo chiến dịch và lịch bài, dùng AI tạo/sửa bản nháp, lưu phiên bản và yêu cầu con người duyệt đúng phiên bản.
- Tải ảnh lên, gắn ảnh vào bài, xuất nội dung để đăng thủ công.
- Kết nối Meta theo cấu hình pilot hiện có, xem bài cũ của Page, đồng bộ bài và số liệu Meta có quyền trả về, đăng bài chữ/ảnh đã duyệt, đối soát khi kết quả gửi chưa rõ.
- Dashboard, nhập snapshot số liệu thủ công, gợi ý dựa trên bằng chứng và lưu đánh giá kết quả.

## Phần đang được bổ sung trên branch này

### Quản lý Page và nhóm

- Màn hình `Fanpage và nghiên cứu thị trường` nằm trong workspace sau đăng nhập.
- Tạo tối đa 10 nhóm; mỗi nhóm có ngành, khu vực, ngôn ngữ và từ khóa riêng. Brand Profile vẫn dùng chung workspace.
- Chủ workspace nhập Page ID và Page Access Token trong form. Backend xác minh Page qua Meta, mã hóa token bằng Fernet trước khi lưu, chỉ giữ dấu vân tay để audit và không trả token lại API/UI.
- Một workspace được kết nối tối đa 5 Page. Mỗi Page thuộc một nhóm tại một thời điểm; có thể ngắt kết nối rồi kết nối lại. Đăng bài tiếp tục qua luồng duyệt hiện có và yêu cầu chọn Page đích khi có nhiều Page.

### Nguồn dữ liệu và chu kỳ

- Lưu tối đa 20 URL nguồn trong workspace, gắn mỗi nguồn với một nhóm.
- Website công khai: đọc HTML hoặc RSS/XML, cùng host, tối đa 25 trang và 2 MiB mỗi response; kiểm tra `robots.txt`, chặn địa chỉ mạng riêng, URL chứa credential/token, chuyển hướng HTTPS xuống HTTP và response ngoài giới hạn.
- Fanpage thuộc workspace: đọc tối đa 300 bài mỗi chu kỳ từ Page đã xác minh. Với tối đa 25 bài đầu, backend thử đọc tối đa 50 bình luận/bài; chỉ yêu cầu nội dung bình luận, không lấy tên/ID tác giả. Email và số điện thoại trong phần bình luận được ẩn trước khi lưu và gửi cho model.
- Fanpage đối thủ và nhóm Facebook: lưu URL và cho phép nhập dữ liệu thủ công. Không tự scrape hoặc giả vờ lấy được dữ liệu; Meta có thể giới hạn dữ liệu theo quyền của app/Page. Tự động hóa những nguồn này cần quyền/API chính thức phù hợp.
- Worker và scheduler tạo job bền vững, chạy chu kỳ đầu khi có nguồn và lặp lại sau mỗi 12 giờ. Có nút chạy ngay. Nội dung response web thô trong object storage được lên lịch xóa sau 30 ngày; bản trích xuất, snapshot số liệu và báo cáo được giữ trong DB.
- Báo cáo DeepSeek gồm tóm tắt, xu hướng, độ tin cậy, ID bằng chứng, gợi ý góc bài và coverage/quyền số liệu. Nếu không gọi được model, hệ thống tạo kết quả fallback có trạng thái lỗi phân tích thay vì coi là phân tích thành công.
- Người dùng tự chọn gợi ý để tạo campaign nháp. Dữ liệu bên ngoài được ghi rõ là chưa xác minh và không được chuyển thành tuyên bố về sản phẩm/thương hiệu. AI tạo bài tiếp theo và người duyệt vẫn qua luồng campaign/approval hiện có; báo cáo không tự đăng bài.

### Những chỉ số chưa được cam kết

Đường đọc Page lưu reaction, comment count, share count và nội dung bình luận nếu quyền cho phép. Lượt xem và số người theo dõi được để trống vì chưa xác minh quyền/field Meta trả về cho app này. Số liệu của Page đối thủ/nhóm chỉ có nếu người dùng nhập dữ liệu có quyền sử dụng. Không nội suy số thiếu thành 0.

## Cấu hình backend

Migration mới là `0012_market_research_and_page_groups`; chạy `alembic upgrade head` trước khi mở UI với DB hiện có. Cần cấu hình secret mã hóa token trong môi trường backend, không đặt biến này ở frontend:

```bash
META_TOKEN_ENCRYPTION_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

Lưu giá trị qua secret store của runtime. Khi xoay khóa, đặt khóa mới vào `META_TOKEN_ENCRYPTION_KEY`, khóa cũ vào `META_TOKEN_ENCRYPTION_KEY_PREVIOUS`, kết nối lại Page để mã hóa token bằng khóa mới, rồi gỡ khóa cũ sau khi xác nhận không còn token cũ. Không ghi Page Access Token hoặc khóa mã hóa vào log, file docs, frontend env hay Git.

Worker, Redis, database và Celery Beat cần chạy để thực hiện lịch nền. `DEEPSEEK_API_KEY` và `LLM_DEFAULT_MODEL` được đọc riêng bởi backend/worker; không gửi key lên trình duyệt. Tác vụ tự động dùng DeepSeek nếu key/model sẵn sàng, còn không thì báo fallback.

## API chính

Prefix: `/api/v1/workspaces/{company_id}/market-research`.

| Method | Endpoint | Mục đích |
|---|---|---|
| GET/POST | `/groups` | Liệt kê/tạo nhóm thị trường |
| PATCH | `/groups/{group_id}` | Sửa cấu hình nhóm |
| GET/POST | `/groups/{group_id}/pages` | Liệt kê/kết nối Page |
| GET | `/pages` | Liệt kê Page đang kết nối trong workspace |
| DELETE | `/pages/{connection_id}` | Ngắt Page và xóa ciphertext token đang hoạt động |
| GET/POST | `/sources` | Liệt kê/lưu URL nguồn |
| DELETE | `/sources/{source_id}` | Tắt URL nguồn |
| POST | `/sources/{source_id}/import` | Nhập quan sát/bài viết, số liệu và bình luận đã được phép dùng |
| POST | `/groups/{group_id}/crawl` | Xếp job thu thập ngay |
| GET | `/groups/{group_id}/reports` | Xem báo cáo gần nhất |
| POST | `/reports/{report_id}/draft` | Tạo campaign nháp từ một gợi ý đã chọn |

## Tiến độ và kiểm chứng

Phần này đang ở branch `codex/page-groups-market-research`, chưa merge/push. Đã có test crawler/SSRF/robots/RSS, mã hóa/đổi khóa token, kết nối/ngắt/kết nối lại Page qua API SQLite với Meta client giả lập, che PII khi nhập đối thủ, và kiểm tra Meta client chỉ yêu cầu trường bình luận `message`. Lượt kiểm tra gần nhất: Python mục tiêu **24 passed**, frontend **47 Vitest passed**, typecheck/lint/build pass, Playwright **42/42** desktop/mobile pass; `compileall`, OpenAPI `--check` và `git diff --check` pass. Migration SQLite mới nâng từ đầu lên head, downgrade về 0011 rồi nâng lại pass; `alembic check` không phát hiện schema lệch. SQLite migration dùng shim `pgvector` chỉ để tạo kiểu vector trong test cô lập.

Chưa xác minh migration trên PostgreSQL thật vì môi trường kiểm tra thiếu package `pgvector` và không có dịch vụ PostgreSQL sẵn sàng; mạng chặn tải package. Không có live request Meta, live crawl hoặc DeepSeek cho chức năng mới. Cần kiểm tra worker/Beat/Redis và làm smoke test với Page/nguồn do chủ workspace cho phép trước khi coi là sẵn sàng triển khai.
