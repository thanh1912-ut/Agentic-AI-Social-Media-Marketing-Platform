# API Contracts

Nguồn sự thật cho schema dùng chung nằm ở `packages/contracts`.

## Quy ước

- Base path: `/api/v1`
- Auth: `Authorization: Bearer <access_token>`
- Lỗi: `{ "detail": string, "code"?: string }`

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
