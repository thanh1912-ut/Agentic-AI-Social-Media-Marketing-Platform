# Backend slice 1 — auth, tenant, ingestion và jobs

## Trạng thái

Đã triển khai nền tảng tuần 1–2 trong `services/api`, `services/ingestion`,
`services/worker`, `database` và root Compose.

### Bàn giao

- Pydantic/FastAPI là nguồn OpenAPI; lỗi dùng envelope lồng `error` có `request_id`.
- Access token ngắn hạn; refresh token trong cookie HttpOnly; CSRF cookie riêng cho browser.
- Membership được kiểm trên mọi endpoint workspace/document/job. Client không thể tự gửi `company_id` để được cấp quyền.
- Password, refresh session, invitation và reset token đều được hash; token social chưa được lưu vì Meta OAuth chưa triển khai.
- Migration `0001_backend_foundation` tạo users, companies, memberships, invitations, auth lifecycle, brands, documents, chunks, jobs, steps, events, deduplication và audit events.
- Upload PDF text, DOCX, XLSX, CSV, TXT, image; parser chạy trong Celery worker. PDF scan/mật khẩu, file hỏng/empty có mã lỗi + hint.
- Hash + parser version deduplicate nội dung; job ledger nằm trong DB, dispatcher chỉ gửi sau commit; scheduler quét job queued để recovery.
- Worker xuất `NormalizedDocument` và lưu text/table chunks có locator, sẵn sàng giao cho M3.

## Lệnh chạy

```bash
cp .env.example .env
docker compose up --build
```

Local kiểm tra nhanh (SQLite + chạy job trong process):

```bash
AUTO_CREATE_SCHEMA=1 INLINE_JOBS=1 python -m services.api
```

OpenAPI:

```bash
python scripts/export_openapi.py
```

## Blocker / chưa làm trong slice này

- API OAuth/Meta publish/metrics chưa bật. Vui lòng xem `docs/meta-feasibility-spike.md`;
  mọi endpoint, permission, version, expiry và metric chưa có bằng chứng xác minh đều
  được đánh dấu `VERIFY CURRENT META API`.
- Email provider chưa nối; invitation vẫn được lưu và trả `invite_url` để pilot gửi tay.
- Vector embedding chưa chạy trong M2; M3 nhận normalized chunks và sở hữu chunk/embed/retrieve.
- Publication/version/approval là slice kế tiếp; chưa được coi scaffold hiện tại là đã hoàn thành.
