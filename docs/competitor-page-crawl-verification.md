# Xác minh: tự thu thập Fanpage đối thủ

Ngày kiểm thử: 2026-09-27 (Asia/Ho_Chi_Minh)
Branch base: `5a72991`; thay đổi kiểm thử trên nhánh `codex/competitor-page-autocrawl` trước commit cuối.

| Kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Unit/fixture crawler và API | PASS | 14 test ở `tests/test_facebook_public_crawler.py` và `tests/test_market_research_api.py`. Bao gồm parse post/metric, URL validation, login/challenge/policy gate, settings/crawl và lịch source. |
| OpenAPI | PASS | `scripts/export_openapi.py --check`; OpenAPI và client API types sinh lại. |
| PostgreSQL migration | PASS | Fresh PostgreSQL 18.3 + pgvector đến `0019`; downgrade về `0018` rồi upgrade lại đến head. |
| Redis queue/cache | PASS | Hai Redis instance tách riêng: queue `noeviction`, cache `allkeys-lru`; readiness cả hai đạt. |
| Celery | PASS | Worker kết nối Redis, nhận `market_research_task` từ queue và hoàn tất job policy-block. |
| Frontend unit tests | PASS | 47 test trên 4 file. |
| ESLint | PASS | File Fanpage và API client liên quan, không warning sau chỉnh hook dependencies. |
| TypeScript | PASS | `tsc --noEmit --incremental false`. |
| Next production build | PASS | `next build` hoàn tất, route Fanpage được build. |
| Browser real-mode smoke | PASS | Tài khoản/workspace test riêng; thao tác qua UI lưu nguồn và bấm Crawl ngay. Job ID `e5ac6fdf-8e4e-4c31-8b6f-bc4daf1d1a89` được poll đến trạng thái cuối; reload thấy run đã lưu. |
| PostgreSQL persistence | PASS | Query sau UI smoke cho kết quả: 1 nguồn public_web, 1 run blocked, 0 market evidence. Không có dữ liệu giả. |
| Live Facebook competitor Page | BLOCKED_EXTERNAL / NOT_RUN | Không có cho phép bằng văn bản từ Meta; hệ thống chặn trước request nội dung. Không kiểm thử URL Page thật. |
| DeepSeek live analysis | NOT_RUN | Không có evidence mới và không cần gọi model để ghi nhận trạng thái block. |
| Playwright renderer | NOT_RUN | V1 chỉ dùng HTTP; không có egress-isolated renderer. |
| Meta Graph API competitor access | NOT_RUN | Không có cơ sở coi Page token của workspace là quyền đọc đối thủ; không gọi API này. |
| Push remote | PASS | Nhánh `codex/competitor-page-autocrawl` được tạo và push lên origin sau review staged diff. |

## Diễn giải

UI/API/worker/database pipeline được xác minh cho nhánh policy-blocked. Chưa được nghiệm thu thu bài thật từ Facebook. Meta nói rõ trong [robots.txt](https://www.facebook.com/robots.txt) rằng hoạt động thu thập tự động cần có sự cho phép bằng văn bản. Ứng dụng mặc định `FACEBOOK_PUBLIC_AUTOMATION_AUTHORIZED=0`, không fetch Page khi chưa có xác nhận phù hợp. Khi được phép, vẫn cần kiểm chứng Page mẫu và các trường thực sự công khai; coverage V1 là partial vì hiện chỉ đọc snapshot trang, không phải toàn bộ feed.
