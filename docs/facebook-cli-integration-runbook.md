# Vận hành collector Facebook bằng facebook-cli

## Phạm vi

Collector này dành cho **Fanpage đối thủ** ở chế độ `public_web`. Nó chạy
`facebook-cli` v0.3.0 với Tier 0, không đăng nhập, không nhận cookie, token Meta,
khóa DeepSeek hoặc thông tin database. Fanpage do workspace sở hữu vẫn dùng Meta
API; crawler website giữ kiểm tra robots riêng.

Tier 0 có thể chỉ trả một phần bài gần nhất. Giao diện phải hiển thị số bài thực
nhận và trạng thái truy cập; không coi `completed` là đã đọc hết lịch sử.

## Build và cấu hình

Trong local development, build runner từ thư mục Go của nó:

```sh
cd services/research/facebook_cli_runner
go build -trimpath -o /absolute/path/facebook-cli-runner .
```

Đặt `FACEBOOK_CLI_RUNNER_PATH` thành đường dẫn tuyệt đối của binary trong môi
trường API/worker. Dockerfile backend tự build runner ở stage Go và đặt đường dẫn
`/usr/local/bin/facebook-cli-runner`. API và worker phải dùng cùng image/config.
Không đặt cookie Facebook hoặc export biến `FB_COOKIES` cho worker.

Upstream được ghim trong `go.mod` ở `github.com/tamnd/facebook-cli v0.3.0`;
`go.sum` kiểm tra checksum module. Runner trả engine version gồm full commit
`8e251abf0bc6fd28acca9b9fa1cafbd07ccae39`. Dự án giữ license Apache-2.0 của
upstream theo source distribution.

## Cấu hình nguồn và chạy

Fanpage đối thủ mới chọn `public_web` mặc định. Có thể chọn **Crawl ngay** mà
không bật lịch. Nếu bật lịch, scheduler dùng PostgreSQL và chạy lại sau 12 giờ.
Một source-run đang hoạt động sẽ không tạo lượt trùng. Việc tắt lịch không chặn
nút Crawl ngay.

Giới hạn mỗi lượt: tối đa 100 bài theo cấu hình (mặc định 50), cửa sổ 90 ngày khi
có ngày đăng, 20 HTTP request kể cả retry/chuyển hướng, 5 phút, 30 giây mỗi
request, response 4 MiB và stdout 16 MiB. URL nguồn/bài chỉ nhận
`facebook.com`, `www.facebook.com`, `m.facebook.com`. `facebook-cli` Tier 0 có
thể chuyển từ `www.facebook.com` sang `web.facebook.com`; runner chỉ cho phép
host mirror này bên trong chuỗi redirect từ `www`/`web`, không nhận nó làm URL
nguồn. Runner khóa DNS tới IP công cộng đã kiểm tra, tối đa 5 redirect, không
tải media và không đọc bình luận.

Nếu Facebook trả login wall, security challenge hoặc từ chối truy cập, lịch tự
động được tạm ngưng cho nguồn đó; **Crawl ngay** cho phép chủ động thử lại. Không
nhập cookie, không dùng tài khoản đăng nhập và không tự đổi sang Meta API.
`rate_limited`/lỗi mạng có thể thử lại theo trạng thái job; các dữ liệu đã lưu
trước đó vẫn được giữ.

## Theo dõi và xử lý lỗi

- `engine_unavailable`: build runner và kiểm tra đường dẫn ở API lẫn worker.
- `login_required`, `access_denied`, `challenge`: Facebook không cấp nội dung cho
  lần truy cập Tier 0 này; không có bước vượt qua, chỉ có thể thử lại sau.
- `no_posts_returned`: Page nhận diện được nhưng lượt đó không trả bài.
- `partial`: đã lưu được bài nhưng timeline không đầy đủ; xem coverage và
  `history_complete=false`.
- `rate_limited`: đợi retry hoặc dùng Crawl ngay sau khi hết giới hạn.
- `parser_error`: kiểm tra engine version/fixture, không ghi raw response vào log.

Lịch sử mỗi source lưu collector, engine/version, Tier 0, số bài và coverage.
DeepSeek chỉ chạy sau khi có bằng chứng hợp lệ; thiếu DeepSeek không chặn việc
crawl và lưu bài.

## Rollback / nâng phiên bản

Để ngừng collector mới cho một nguồn, đổi `collection_mode` qua UI sang `meta_api`
hoặc `manual`, hoặc tắt lịch. Không xóa `WebCrawlRun`, evidence, observation hay
snapshot lịch sử. Để rollback toàn service, deploy lại image/commit trước đó và
giữ PostgreSQL migrations tương thích; migration 0020 chỉ đánh giá lại lịch của
nguồn đã bật, không xóa dữ liệu.

Khi nâng upstream: kiểm tra release/source và license, pin tag cùng full commit,
chạy `go mod tidy`, review `go.sum`, test parser/HTTP transport, cập nhật engine
version, build Docker và nghiệm thu Tier 0 lại. Không tải `@latest` trong job.
