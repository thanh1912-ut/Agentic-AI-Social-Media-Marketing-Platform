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
- Fanpage thuộc workspace: đọc tối đa 300 bài mỗi chu kỳ từ Page đã xác minh. Với tối đa 25 bài đầu, backend thử đọc tối đa 50 bình luận/bài và `post_media_view`; đọc `followers_count` một lần cho Page. Chỉ yêu cầu nội dung bình luận, không lấy tên/ID tác giả. Email và số điện thoại được ẩn trước khi lưu/gửi model. `interactions` chỉ tính khi reactions, comments và shares đều có; giá trị thiếu vẫn là null.
- Fanpage đối thủ: lưu URL để tái sử dụng. Nếu backend có `META_PUBLIC_CONTENT_ACCESS_TOKEN`, worker dùng Graph API để phân giải Page và đọc bài công khai; ứng dụng Meta phải được duyệt Page Public Content Access hoặc quyền công khai tương ứng. Nếu thiếu quyền/token, nguồn chuyển sang `needs_access` và vẫn cho nhập số liệu được phép dùng thủ công.
- Nhóm Facebook: lưu URL và hỗ trợ nhập dữ liệu thủ công, gồm views và follower count. Không scrape hoặc dùng browser automation để lấy nội dung nhóm. Meta đã bỏ Groups API/permissions khỏi Graph API từ v19 (có hiệu lực trên mọi version ngày 2024-04-22); Content Library có dữ liệu nhóm công khai nhưng Meta giới hạn công cụ này cho nghiên cứu khoa học/lợi ích công cộng của tổ chức học thuật/phi lợi nhuận đủ điều kiện, không phải connector thương mại cho SME. Xem [Graph API changelog v19](https://developers.facebook.com/docs/graph-api/changelog/version19.0) và [Meta Content Library announcement](https://about.fb.com/news/2023/11/new-tools-to-support-independent-research/).
- Worker và scheduler tạo job bền vững, chạy chu kỳ đầu khi có nguồn và lặp lại sau mỗi 12 giờ. Có nút chạy ngay. Nội dung response web thô trong object storage được lên lịch xóa sau 30 ngày; bản trích xuất, snapshot số liệu và báo cáo được giữ trong DB.
- Báo cáo DeepSeek phân tích tối đa 40 bằng chứng gần nhất (mỗi trích đoạn tối đa 1.200 ký tự, tối đa 3 bình luận ngắn), gồm metrics và thay đổi so với snapshot trước; đây là tín hiệu tăng/giảm giữa hai lần crawl, không chứng minh quan hệ nhân quả. Follower count là số cấp Page, có thể lặp trên nhiều bài và không được cộng. UI hiển thị nguồn, metrics, mẫu bình luận, thay đổi và coverage/metrics thiếu một phần. Nếu không gọi được model, hệ thống tạo kết quả fallback có trạng thái lỗi phân tích thay vì coi là phân tích thành công.
- Người dùng tự chọn gợi ý để tạo campaign nháp. Khi chủ động yêu cầu sinh bài theo slot, worker lấy tối đa 5 bằng chứng đã chọn, gồm trích nội dung, snapshot tương tác và tối đa 4 bình luận đã lọc email/số điện thoại, rồi gửi chúng cùng ngữ cảnh thương hiệu tới DeepSeek. Nguồn bên ngoài được đánh dấu `market_research`/`external_unverified`: chúng chỉ gợi ý chủ đề, định dạng và tín hiệu tương tác, không làm căn cứ cho tuyên bố về sản phẩm/thương hiệu; bài vẫn phải trích nguồn xác nhận của workspace cho tuyên bố sản phẩm. AI tạo bài nháp và người duyệt vẫn qua luồng campaign/approval hiện có; báo cáo không tự đăng bài.

### Những chỉ số chưa được cam kết

Đường đọc Page workspace thử `post_media_view` cho tối đa 25 bài và `followers_count` cho Page; Meta có thể không trả metric theo quyền, loại Page, loại bài hoặc version. Các tên/field này mới được kiểm tra bằng contract fixture, chưa xác minh trên Page thật. Với đối thủ, follower count chỉ được lưu khi Graph API trả field đó; views vẫn null và có thể được nhập tay nếu người dùng có số liệu được phép sử dụng. Không nội suy số thiếu thành 0.

## Cấu hình backend

Migration mới là `0012_market_research_and_page_groups`; chạy `alembic upgrade head` trước khi mở UI với DB hiện có. Cần cấu hình secret mã hóa token trong môi trường backend, không đặt biến này ở frontend:

```bash
META_TOKEN_ENCRYPTION_KEY="$(.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
```

Lưu giá trị qua secret store của runtime. Khi xoay khóa, đặt khóa mới vào `META_TOKEN_ENCRYPTION_KEY`, khóa cũ vào `META_TOKEN_ENCRYPTION_KEY_PREVIOUS`, kết nối lại Page để mã hóa token bằng khóa mới, rồi gỡ khóa cũ sau khi xác nhận không còn token cũ. Không ghi Page Access Token hoặc khóa mã hóa vào log, file docs, frontend env hay Git.

Worker, Redis, database và Celery Beat cần chạy để thực hiện lịch nền. `DEEPSEEK_API_KEY` và `LLM_DEFAULT_MODEL` được đọc riêng bởi backend/worker; không gửi key lên trình duyệt. Tác vụ tự động dùng DeepSeek nếu key/model sẵn sàng, còn không thì báo fallback.

Trong `NEXT_PUBLIC_USE_MOCKS=1`, trang hiển thị nhóm, link và báo cáo mẫu để xem bố cục. Mock không lưu Page Access Token và không gọi Meta; kết nối thật chỉ chạy khi frontend dùng API backend thật.

Để tự đọc Page đối thủ, cấp `META_PUBLIC_CONTENT_ACCESS_TOKEN` trong secret store backend/worker. Đây phải là app/user access token thuộc Meta App đã qua App Review và có quyền Page Public Content Access/Metadata phù hợp. Sau khi cài token, chạy một chu kỳ bằng nút **Crawl ngay** cho những link đối thủ đã lưu ở chế độ nhập tay; nếu API trả quyền hợp lệ, các chu kỳ sau sẽ tự chạy mỗi 12 giờ. Token này khác Page Access Token dùng cho Page của workspace. Nếu chưa được Meta duyệt, để trống biến và dùng nhập dữ liệu thủ công. Không cấu hình secret này trong trình duyệt hoặc gửi qua chat.

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

Phần này ở branch `codex/page-groups-market-research`. Implementation và fixture tests có cho lưu Page ID/token mã hóa, nhóm, nguồn, scheduler 12h, crawler website, Pages được Meta cấp quyền, báo cáo, import tay và tạo campaign. Backend snapshot hiện tại đạt **185 passed, 1 skipped** trên Python 3.13.9 với pgvector shim và SQLite/fake providers; frontend đạt **47 Vitest**, ESLint và TypeScript check pass. OpenAPI check pass. Production build đã compile/typecheck nhưng không hoàn tất do ổ đĩa đầy (`ENOSPC`); không ghi nhận lỗi build từ source. Crawl website `taphoammo.vn` đã lấy 4 trang công khai trực tiếp, nhưng lượt thử không lưu workspace, không gọi DeepSeek.

Chưa có PostgreSQL migration/runtime, Redis worker/Beat, Meta Page thật hoặc DeepSeek request cho tính năng này. Contract cho `post_media_view`/`followers_count` mới được test bằng fixture; cần Page token, encryption key và quyền Meta phù hợp để xác minh live. Nhóm Facebook tự động là `BLOCKED_EXTERNAL`: API chính thức đã bị gỡ và Content Library không dành cho connector thương mại của SME. Các file test/crawler không thay thế xác minh Meta/DeepSeek hoặc boot Compose.
