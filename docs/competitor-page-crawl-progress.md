# Tiến độ tự thu thập Fanpage đối thủ

Cập nhật: 2026-09-27 20:26 Asia/Ho_Chi_Minh
Nhánh: `codex/competitor-page-autocrawl`
Base: `5a72991` (`origin/codex/mailguard-pilot` tại thời điểm bắt đầu)

| Hạng mục | Trạng thái | Bằng chứng / bước tiếp theo |
|---|---|---|
| Kiểm tra chính sách trước khi crawl | DONE | `https://www.facebook.com/robots.txt` thông báo cần có sự cho phép bằng văn bản cho hoạt động thu thập tự động. Chưa gửi request tới Page đối thủ. |
| Collector Page công khai | DONE | Collector HTTP riêng, giới hạn hostname Facebook, kiểm tra robots/redirect, nhận diện login/challenge/rate limit, parser có phiên bản, không dùng cookie đăng nhập. Mọi lần chạy báo độ phủ một trang là partial. |
| Gate quyền nền tảng | DONE | Mặc định `FACEBOOK_PUBLIC_AUTOMATION_AUTHORIZED=0`; worker từ chối trước khi fetch nội dung, lưu run blocked. Chỉ cấu hình sau khi có văn bản cho phép áp dụng đúng cho mục đích này. |
| API và quyền workspace | DONE | Thêm API cài đặt collector, crawl theo nguồn, lịch sử run và bài đã lưu; xác minh tenant/quyền qua các endpoint hiện có. |
| Database và migration | DONE | Migration `0019_competitor_page_public_collection`; migration mới trên PostgreSQL 18.3 và downgrade/upgrade từ `0018` đều chạy được. |
| Job, Redis và lịch | DONE | Job commit trước dispatch; Celery nhận task từ queue `agent`; lịch nguồn lọc theo `schedule_enabled`; throttling dùng PostgreSQL. |
| Frontend | DONE | Thêm public_web mặc định cho Page đối thủ mới, nút Crawl ngay, bật/tắt lịch, bài viết/lịch sử, trạng thái quyền bị chặn. Reload vẫn tải lại trạng thái từ API. |
| Kiểm thử tự động | DONE | `tests/test_facebook_public_crawler.py` và `tests/test_market_research_api.py`: 14 test pass; frontend: 47 test pass; ESLint, TypeScript và `next build` pass. |
| PostgreSQL/Redis kiểm thử | DONE | Hạ tầng tạm riêng: migrations lên `0019`, readiness database/Redis/cache/storage đạt; Celery nhận và chạy job. DB xác nhận 1 nguồn public, 1 run blocked, 0 evidence giả. |
| UI end-to-end | DONE | Trình duyệt real mode `http://127.0.0.1:13101`; tạo workspace/nhóm/Page test, Crawl ngay, worker hoàn tất `platform_permission_required`, reload vẫn thấy run. |
| Crawl Page Facebook thật | BLOCKED_EXTERNAL | Không có xác nhận bằng văn bản từ Meta. Không tải nội dung Page thật và không đánh dấu live crawl pass. |
| DeepSeek phân tích | NOT_RUN | Không có evidence mới; worker chủ ý không gọi model. |
| Push nhánh | DONE | `codex/competitor-page-autocrawl` đã được push; SHA ban đầu `ba606e0`, sau đó cập nhật tài liệu bàn giao. |

## Kết quả UI smoke

- Workspace tạm: `7a8381ff-96ec-404b-a23d-8ebc3eaf1f8c`.
- Nhóm tạm: `Crawl Smoke`.
- Page URL giả định cho test UI: `https://www.facebook.com/example`; không có request nội dung tới host này.
- Job: `e5ac6fdf-8e4e-4c31-8b6f-bc4daf1d1a89`.
- Database: một `web_crawl_runs` với status `blocked`, không có evidence.

Smoke này chứng minh trạng thái chặn được đưa qua API → Redis/Celery → PostgreSQL → UI. Nó không chứng minh Facebook đã được crawl.
