# API Contracts

Nguồn sự thật cho schema dùng chung nằm ở `packages/contracts`.

## Quy ước

- Base path: `/api/v1`
- Auth: `Authorization: Bearer <access_token>`
- Lỗi: `{ "error": { "code", "message", "field_errors", "request_id", "retryable", "details?" } }`
- JSON dùng `snake_case`; request dài trả `202` với `{ "job_id", "job" }`.
- Tài nguyên tenant không thuộc workspace của người dùng trả `404`, không để lộ sự tồn tại.

## Nhóm endpoint

### Auth — `services/api/auth`

| Method | Path | Mô tả |
| --- | --- | --- |
| POST | `/auth/register` | Đăng ký |
| POST | `/auth/login` | Lấy access token |
| GET | `/auth/me` | Thông tin user hiện tại |

### Campaigns — `services/api/campaigns`

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/campaigns` | Danh sách campaign |
| POST | `/campaigns` | Tạo campaign |
| GET | `/campaigns/{id}` | Chi tiết campaign |

### Posts — `services/api/posts`

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/posts` | Danh sách post |
| POST | `/posts` | Tạo post nháp |
| PATCH | `/posts/{id}` | Cập nhật post |

### Approvals — `services/api/approvals`

| Method | Path | Mô tả |
| --- | --- | --- |
| POST | `/approvals/{post_id}/approve` | Duyệt nội dung |
| POST | `/approvals/{post_id}/reject` | Từ chối nội dung |

### Exports — `services/api/exports`

| Method | Path | Mô tả |
| --- | --- | --- |
| POST | `/exports` | Yêu cầu export |
| GET | `/exports/{id}` | Trạng thái file export |

### Integrations — `services/api/integrations`

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/integrations` | Danh sách kênh đã kết nối |
| POST | `/integrations/{provider}/connect` | Kết nối kênh |
| DELETE | `/integrations/{provider}` | Ngắt kết nối |

### Meta Page pilot — `services/api/meta`

| Method | Path | Mô tả |
| --- | --- | --- |
| GET | `/workspaces/{id}/meta/connection` | Trạng thái cấu hình và xác minh Page; token không trả về client |
| POST | `/workspaces/{id}/meta/connection/verify` | Owner xác minh Page ID/name và quyền đọc feed bằng request chỉ đọc |
| GET | `/workspaces/{id}/meta/publications` | Lịch sử đăng text/ảnh của sản phẩm và trạng thái đối soát |
| POST | `/workspaces/{id}/meta/publications` | Owner gửi đúng version đã duyệt; trả `202 AcceptedResponse` |
| POST | `/workspaces/{id}/meta/publications/{publication_id}/reconcile` | Owner xác nhận bài đã/chưa xuất hiện khi kết quả gửi chưa rõ |
| GET | `/workspaces/{id}/meta/page-posts` | Danh sách bài Page đã đồng bộ, gồm bài ngoài sản phẩm |
| POST | `/workspaces/{id}/meta/metrics/sync` | Owner đồng bộ tối đa 500 bài/lượt; cursor giữ tiến độ lịch sử |

## Lát cắt backend đã triển khai

Lát cắt đầu tiên hiện có trong FastAPI:

- `POST /api/v1/auth/register`, `login`, `refresh`, `logout`, `forgot-password`, `reset-password`.
- `GET /api/v1/me`, `GET /api/v1/workspaces`, `GET /api/v1/workspaces/{id}/members`.
- `POST /api/v1/workspaces/{id}/members` tạo invitation bền vững; email provider là adapter chưa nối.
- `GET /api/v1/workspaces/{id}/documents/limits`, danh sách/chi tiết và upload multipart nhiều tệp.
- `GET /api/v1/jobs/{id}`, events, cancel và retry cho ingestion.

OpenAPI nguồn thật được FastAPI phục vụ tại `/api/openapi.json`; cập nhật file sinh bằng:

```bash
python scripts/export_openapi.py
npm run gen:api
python scripts/export_openapi.py --check
```
