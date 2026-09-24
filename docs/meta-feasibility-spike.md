# Meta feasibility spike — Facebook Page pilot

## Phạm vi pilot

Connector đang được triển khai cho **một workspace và một Facebook Page do owner
quản lý**. Server đọc `META_WORKSPACE_ID`, `META_PAGE_ID`,
`META_PAGE_ACCESS_TOKEN` và `META_GRAPH_VERSION` từ môi trường; mặc định của
`META_GRAPH_VERSION` là `v26.0`. Đây là cấu hình pilot, không phải bằng chứng rằng
phiên bản, quyền hoặc thời hạn token đã được Meta xác nhận cho Page thật.

Trước khi bật đồng bộ, backend xác minh token thuộc đúng Page và thử đọc tối đa
một bài để xác nhận quyền đọc feed. Bước này không thử đăng; quyền publish sẽ do
Meta kiểm tra trên từng yêu cầu gửi bài và còn phải được nghiệm thu với app/Page
thật. Backend báo trạng thái/lỗi rõ cho owner. Mỗi lần đăng cần thao
tác tường minh của owner trên một bài có **đúng phiên bản đã duyệt**. Backend
kiểm lại trạng thái duyệt và SHA-256 của nội dung/ảnh trong `PostVersion` ngay
trước khi gửi. Lưu lần gửi, Page, phiên bản, external post ID/permalink và kết
quả để đối soát. Khi request có thể đã tới Meta nhưng kết quả chưa rõ, đánh dấu
`outcome_unknown`; không tự thử lại POST. Owner phải kiểm tra Page và đối soát
trước khi quyết định bước tiếp theo.

Đồng bộ chỉ chạy khi owner yêu cầu. Pilot đọc các bài trên Page, gồm bài cũ đã
đăng ngoài nền tảng và bài được nền tảng đăng thành công.
`POST /api/v1/workspaces/{workspace_id}/meta/metrics/sync` lấy tối đa 5 trang,
mỗi trang tối đa 100 bài trong một lượt; lưu cursor để lần bấm tiếp theo tiếp tục
đọc lịch sử. Không có bộ lọc ngày hoặc tự tải toàn bộ lịch sử trong một lần.
`GET /api/v1/workspaces/{workspace_id}/meta/page-posts` trả các bài đã nhập với
phân trang. Mỗi bản ghi giữ Page/external post ID, thời điểm đăng, thời điểm đồng
bộ và các count `reactions`, `comments`, `shares` có thể thiếu. `engagements`
chỉ được tính khi cả ba count khả dụng; không suy giá trị thiếu thành 0. Endpoint này
chỉ chứa dữ liệu Meta; chưa có reach, views, clicks hoặc chuỗi metric snapshots
theo cửa sổ đo. Bài lịch sử chỉ là dữ liệu phân tích, không được biến thành bản
nháp đã duyệt hoặc bài do nền tảng đăng.

Export → đăng thủ công → nhập metrics có nguồn vẫn là đường vận hành khi
connector chưa đủ quyền hoặc chưa qua nghiệm thu. Không dùng scraping hoặc
browser-login automation để thay API permission. Pilot hỗ trợ text và tối đa
một ảnh nếu Page capability đã kiểm chứng; video/carousel, OAuth cho nhiều khách
hàng, Page discovery, App Review cho người ngoài team, scheduled publishing và
webhooks nằm ngoài pilot hiện tại.

## Ma trận kiểm chứng trước khi bật trên Page thật

| Hạng mục | Trạng thái | Việc cần xác minh |
| --- | --- | --- |
| Graph API version | **VERIFY CURRENT META API** | `v26.0` là default cấu hình; thử với app/Page thật và chốt phiên bản đang được hỗ trợ trước khi vận hành. |
| Page identity và token | **VERIFY CURRENT META API** | Xác minh Page ID/name trả về đúng Page cấu hình, loại token, quyền, thời hạn và hành vi khi token bị thu hồi/hết hạn. Không coi việc có chuỗi token là kết nối hợp lệ. |
| Quyền publish | **VERIFY CURRENT META API** | Kiểm tra permission/task/access level trên app và Page thật; xác nhận cả test user lẫn đối tượng dùng ngoài team theo yêu cầu App Review. |
| Đăng bài và ảnh | **VERIFY CURRENT META API** | Kiểm chứng endpoint/Graph fields, giới hạn nội dung/media, response external ID, timeout và cách đối soát trước khi bật từng định dạng. Không suy ra quyền đăng ảnh từ quyền đăng text. |
| Page posts và metrics | **VERIFY CURRENT META API** | Xác minh quyền đọc Page feed, phân trang/cursor, bài ngoài nền tảng và sự sẵn có/ý nghĩa của `reactions`, `comments`, `shares` trên Page thật. Pilot không tuyên bố có reach/views/clicks. |
| Rate limits và lỗi | **VERIFY CURRENT META API** | Đọc response/header/error codes trên app thật; phân biệt lỗi chắc chắn chưa gửi với kết quả gửi chưa rõ trước khi retry. |
| OAuth/App Review cho nhiều khách | **Ngoài pilot** | Thiết kế và nghiệm thu riêng khi sản phẩm cần kết nối Page của SME khác. |

Ngày 2026-09-24, các trang developer chính thức cho Page Feed, Page Insights,
permissions và access tokens trả HTTP 429 khi thử truy cập. Lần đọc lại Pages
API/Graph token guide cũng chưa cung cấp được nội dung có thể xác minh. Bộ
[Facebook API trên Postman do Meta xuất bản](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api)
có trang collection, nhưng trang công khai chưa hiển thị đủ nội dung request để
xác nhận version, fields hay permissions. Vì vậy bảng trên không dựa vào ví dụ
API cũ hoặc nguồn không thuộc Meta.

## Capability và bí mật

Mỗi Page/connection cần trình bày riêng cho owner:

```text
can_publish: boolean
can_read_metrics: boolean
verified_at: timestamp | null
api_version: string | null
unavailable_reason: string | null
```

Token chỉ tồn tại trong môi trường backend/worker hoặc deployment secret store;
không trả về browser, prompt, output LLM, request log, job error hoặc tài liệu.
`.env` local đã nằm trong `.gitignore`; không dán token vào chat hay commit file
này. Nếu sau pilot lưu token trong database, phải mã hóa khi lưu và thiết kế luồng
xoay/thu hồi token. Owner là vai trò duy nhất được quản lý cấu hình và gửi bài.

## Nguồn Meta cần đối chiếu

- [Pages API posts](https://developers.facebook.com/docs/pages-api/posts/) — **VERIFY CURRENT META API**.
- [Page Feed](https://developers.facebook.com/docs/graph-api/reference/page/feed/) — **VERIFY CURRENT META API**.
- [Page Insights](https://developers.facebook.com/docs/graph-api/reference/page/insights/) — **VERIFY CURRENT META API**.
- [Permissions](https://developers.facebook.com/docs/permissions/) — **VERIFY CURRENT META API**.
- [Access tokens](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/) — **VERIFY CURRENT META API**.
- [Graph API rate limiting](https://developers.facebook.com/docs/graph-api/overview/rate-limiting) — **VERIFY CURRENT META API**.
- [Graph API changelog](https://developers.facebook.com/docs/graph-api/changelog/) — **VERIFY CURRENT META API**.
