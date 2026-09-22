# Meta feasibility spike — tuần 1

## Quyết định an toàn cho pilot

Khi quyền Meta cho khách ngoài team chưa được xác nhận, product phải dùng export,
đăng thủ công và import metrics có nguồn. Không dùng scraping hoặc browser-login
automation để thay API permission.

## Ma trận kiểm chứng

| Hạng mục | Trạng thái | Ghi chú kiểm chứng |
| --- | --- | --- |
| Graph API version dùng cho production | **VERIFY CURRENT META API** | Không hard-code version từ blog, SDK hoặc ví dụ cũ. Chốt version tại Meta App Dashboard và tài liệu Graph API hiện hành trước khi bật connection. |
| OAuth flow / app type | **VERIFY CURRENT META API** | Chưa chốt Facebook Login for Business hay flow khác; phải đối chiếu app thật, redirect URI, access level và App Review. |
| Page discovery / tasks | **VERIFY CURRENT META API** | Chưa coi `/{user-id}/accounts` hay Page tasks là contract cho production. Test bằng app thật và Page thật. |
| Text publishing | **VERIFY CURRENT META API** | Chưa bật worker POST nào. Cần xác minh endpoint, token type, permission, scheduling và response external ID. |
| Image publishing | **VERIFY CURRENT META API** | Cần xác minh endpoint, media hosting requirement, permission và timeout/reconcile behavior. |
| Metrics, period, breakdown | **VERIFY CURRENT META API** | Chưa map metric definitions. Không suy ra 0 khi API trả unavailable; lưu source/window/as_of/fetched_at. |
| Token expiry / revocation | **VERIFY CURRENT META API** | Không ghi nhận thời hạn token từ trí nhớ. Cần test revoke, invalid token, permission loss và app mode. |
| Rate limits / webhooks | **VERIFY CURRENT META API** | Cần đọc response headers/error codes và quyết định retry/backoff. Webhook chỉ thêm khi có use case và quyền đã được duyệt. |

## Capability contract

Mỗi connection/page phải lưu riêng:

```text
can_publish: boolean
can_read_metrics: boolean
verified_at: timestamp | null
api_version: string | null
unavailable_reason: string | null
```

Token chỉ nằm server-side, mã hóa khi lưu, không vào frontend, prompt, output LLM,
request log hoặc job error. Owner là vai trò duy nhất được quản lý connection.

## Tài liệu cần đối chiếu trước khi bật

- [Meta Pages API posts](https://developers.facebook.com/docs/pages-api/posts/) — **VERIFY CURRENT META API**.
- [Graph API access tokens](https://developers.facebook.com/docs/graph-api/overview/access-tokens) — **VERIFY CURRENT META API**.
- [Graph API rate limiting](https://developers.facebook.com/docs/graph-api/overview/rate-limiting) — **VERIFY CURRENT META API**.
- [Graph API changelog](https://developers.facebook.com/docs/graph-api/changelog/) — **VERIFY CURRENT META API**.

Kết quả spike hiện tại là blocker được ghi nhận, không phải tuyên bố rằng các quyền
trên đã được duyệt cho production.
