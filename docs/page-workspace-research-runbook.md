# Runbook Page workspace và Nghiên cứu

## Onboarding doanh nghiệp

1. Đăng ký/đăng nhập bằng tài khoản Agentic Marketing. Đăng ký tạo tài khoản và phiên, chưa tạo doanh nghiệp.
2. Ở màn hình chọn doanh nghiệp, Owner nhập Page ID và Page Access Token thuộc đúng Page.
3. Backend đọc Page identity và thử đọc một trang bài công khai; không đăng bài thử. Khi thành công, workspace lấy tên Page, lưu avatar an toàn nếu URL ảnh phù hợp, mã hóa token và tạo Owner/Brand trống.
4. Brand Profile vẫn do Owner tự viết. Page name/avatar chỉ là nhận diện workspace.
5. Thành viên khác tham gia bằng lời mời. Có token không tự cấp quyền thành viên.

API dùng trong vận hành:

- `POST /api/v1/auth/register` — tài khoản/session, không tạo workspace.
- `POST /api/v1/workspaces/from-page` — xác minh Page và tạo workspace.
- `PATCH /api/v1/workspaces/{workspace_id}/page-connection` — Owner thay token cho cùng Page ID; đổi Page cần workspace khác.
- `GET /api/v1/workspaces` — danh sách workspace đã được cấp membership.

Không đưa token vào tài liệu, ticket, browser storage, query string hoặc log. Chỉ nhập trên giao diện kết nối hoặc gửi request qua kênh bảo mật.

## Secrets

- Không dán API key, Page Access Token hoặc cookie vào chat, frontend bundle, Git hay log.
- DeepSeek/Gemini/Qwen chỉ được nạp từ backend secret store/runtime environment.
- Page Access Token phải được mã hóa server-side bằng `META_TOKEN_ENCRYPTION_KEY`.
- Mẫu biến cấu hình sẽ dùng placeholder; file này không chứa giá trị bí mật.

`META_TOKEN_ENCRYPTION_KEY` phải được cấu hình ở backend trước khi Owner kết nối Page. Thiếu khóa trả `token_encryption_unavailable`; không tắt mã hóa để vượt lỗi.

## Kết nối lại Page

- Khi token hết hạn/thu hồi, workspace chuyển `needs_reconnect`; dữ liệu lịch sử vẫn đọc được, tác vụ mới bị chặn.
- Owner mở Cài đặt doanh nghiệp, nhập token mới và giữ nguyên Page ID. Backend xác minh lại trước khi thay token mã hóa.
- Nếu một nguồn đang chạy khi mất kết nối, kết quả dở dang không được coi là hoàn thành. Sau kết nối lại, scheduler có thể phục hồi lịch theo idempotency.
- Lịch đăng đã quá hạn tuân thủ trạng thái missed hiện có; không gửi bù hàng loạt.

## Nghiên cứu

- Mở mục **Nghiên cứu**. Các nhóm database cũ vẫn được giữ; UI/API facade tự đặt nguồn mới vào nhóm nội bộ của workspace.
- Page doanh nghiệp được thêm tự động khi workspace kích hoạt. Các nguồn khác: website công khai, Page Facebook công khai và Group Facebook công khai.
- Bấm Crawl ngay cho nguồn hoặc nhóm nội bộ. Lịch nguồn có thể bật/tắt riêng; mở trang không tự chạy crawl.
- Public Page chạy collector `facebook-cli` Tier 0 hiện có; không đăng nhập. Public Group chỉ có thể trả thông tin nhóm, không có thảo luận Tier 1. Không báo hoàn thành toàn bộ lịch sử.
- Bình luận hiện ở trạng thái `privacy_hold`: chỉ số tổng hợp có thể lưu, nhưng text bình luận mới không tải/lưu/gửi cho agent. Media chưa có pipeline tải/phân tích.
- Lỗi nguồn mới không được xóa kết quả nguồn thành công trước đó.

## Trạng thái ban đầu

- Account-only registration, Page-based workspace activation và reconnect được triển khai trong nhánh này; vẫn cần kiểm chứng migration trên PostgreSQL thật.
- UI Nghiên cứu không yêu cầu người dùng chọn nhóm. Cấu trúc lưu trữ legacy vẫn group-scoped.
- Gemini/Qwen adapters, video/image analysis, comment processing/erasure chưa triển khai.

## Thao tác vận hành

Không bật xử lý comment/media từ cờ thủ công. Trước khi mở các chức năng này cần xác định mục đích/căn cứ xử lý, thời hạn, quy trình quyền xóa, vùng provider và kiểm thử deletion end-to-end. Đây là yêu cầu vận hành/pháp lý, không thể thay bằng regex hoặc checkbox.

## Phần chưa sẵn sàng

- Gemini và Qwen chưa có adapter/model ID được xác minh; DeepSeek hiện là adapter cho báo cáo Nghiên cứu. Không tự fallback giữa provider.
- Ledger hiện áp dụng cho báo cáo Nghiên cứu DeepSeek tự động; chưa bao phủ Gemini/Qwen, media hoặc mọi call AI tự động khác. Trang Nghiên cứu đọc số liệu qua `GET .../market-research/ai-budget`; báo cáo hoãn hiện chỉ được hiển thị, chưa có tác vụ tự lên lịch chạy lại.
- Chưa tải hay gửi ảnh/video đến provider; không tuyên bố media analysis đã chạy.
- Không có full comment pagination/replies hoặc database checkpoint mới. Coverage là `privacy_hold`/Tier 0 partial.
- Không tự nhận hệ thống tuân thủ đầy đủ Luật 91/2025/QH15 hoặc Nghị định 356/2025/NĐ-CP.

## Kiểm thử/deploy

- Backend API: dùng lệnh service/test đã cấu hình của checkout, không bật `AUTO_CREATE_SCHEMA` hay inline jobs để nghiệm thu.
- Migration phải chạy `alembic upgrade head` trên database test riêng trước rollout; không chạy rollback phá lịch sử.
- Đừng thay API/workers đang phục vụ preview. Drain worker cũ trước khi thay backend và giữ snapshot/rollback tương thích Page gate.
- Cấu hình key dạng placeholder trong secret store: `DEEPSEEK_API_KEY=<secret>`, `GEMINI_API_KEY=<secret>`, `QWEN_API_KEY=<secret>`; hiện chỉ adapter DeepSeek đang được dùng.

### Ngân sách AI tự động hiện có

- Mặc định `AUTO_AI_DAILY_BUDGET_MICRO_USD=2000000` (2 USD/workspace/ngày Việt Nam); cấu hình thấp hơn được phép, cao hơn cap sản phẩm bị từ chối khi nạp settings.
- Ledger nằm trong `ai_usage_budget_days` và `ai_usage_ledger`. Mỗi research cycle có idempotency key; worker không gọi lại khi kết quả đã lưu hoặc kết quả provider trước chưa rõ.
- Structured report chỉ được giữ trong ledger như recovery copy cho tới khi `MarketReport` commit; cùng transaction đó xóa bản sao ledger.
- Reservation dùng giá peak/cache-miss và tính upper bound cho đầu vào cùng một lần repair. Phiên bảng giá là `provider-public-pricing-2026-09-30-v1`; cần review và bump version trước khi đổi model hoặc giá upstream.
- Hiện chỉ có giá đã khai báo cho `deepseek-flash` và `deepseek-v4-pro`; model khác trả `pricing_unavailable` và không được gửi. Giá tham khảo từ [bảng giá DeepSeek chính thức](https://api-docs.deepseek.com/quick_start/pricing/). Đây là bảng giá đã ghi nhận, không phải đảm bảo giá nhà cung cấp không đổi.
- Nếu usage thiếu hoặc không xác định được model trả về, ledger giữ reservation ở `unknown`; không tự nhả ngân sách hay gọi lặp. Đối soát hiện chưa có giao diện.
- Đây chưa phải cap chung cho mọi agent: chỉ báo cáo nghiên cứu tự động đã nối; tác vụ người dùng, Gemini, Qwen và media chưa thuộc ledger.

### PostgreSQL/Redis test cách ly của lần xác minh này

Các lần test integration dùng cluster tạm dưới `/private/tmp/agentic-page-workspaces-it-20260930`, chỉ bind loopback; không dùng database/queue của preview. PostgreSQL nghe cổng `15433`; cluster riêng cho đường upgrade `0021 → 0022` nghe cổng `15543`; Redis queue `26379` và cache `26380`. Redis test không bật persistence và không chạy worker. Các tiến trình này đã được dừng sau kiểm thử.

Khi không còn cần chạy integration trong phiên làm việc, dừng đúng các tiến trình test bằng:

```bash
/opt/homebrew/bin/pg_ctl -D /private/tmp/agentic-page-workspaces-it-20260930/pgdata -m fast -w stop
/opt/homebrew/bin/pg_ctl -D /private/tmp/agentic-page-workspaces-it-20260930/pgdata-budget -m fast -w stop
/opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 26379 shutdown
/opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 26380 shutdown
```

Không dùng các lệnh này nếu đã tái sử dụng các cổng cho tiến trình khác; xác minh tiến trình/cổng trước khi dừng.
