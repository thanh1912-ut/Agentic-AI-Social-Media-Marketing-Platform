# Architecture

## Tổng quan

```text
web → api → PostgreSQL + pgvector (source of truth)
             ├── commit job/domain update → Redis queue / Celery → worker / agent-worker
             ├── derived API response ← Redis cache (best effort, separate instance)
             └── MinIO/S3-compatible object storage
```

## Thành phần

| Thành phần | Vai trò | Công nghệ |
| --- | --- | --- |
| `apps/web` | Giao diện người dùng | Next.js |
| `services/api` | REST API, auth, quản lý campaign/post/approval | FastAPI |
| `services/ingestion` | Chuẩn hoá tài liệu đầu vào | PDF / Excel / Doc / Image / Video / URL |
| `services/agents` | Agentic workflow | LangGraph |
| `services/worker` | Job nền: publish, monitor, schedule | Queue worker |

`services/agents` và `services/ingestion` là Python modules được worker gọi; không
có Agent HTTP Service riêng trong MVP. PostgreSQL lưu lịch, trạng thái job, nghiệp
vụ và vectors. Redis queue chỉ vận chuyển job/rate-limit keys; Redis cache là
instance riêng có thể bị eviction và không làm mất dữ liệu nghiệp vụ.

## Luồng dữ liệu

<!-- ingestion → knowledge base → agents → nội dung nháp → approval → publish → analytics -->

## Quyết định thiết kế

- Modular monolith giữ transaction nghiệp vụ, job ledger và tenant isolation ở cùng
  một boundary; Redis/Celery chỉ nhận job sau khi transaction DB đã commit.
- PostgreSQL dùng pgvector-capable image; MinIO là storage local tương thích S3.
- Mọi quan hệ nghiệp vụ quan trọng gắn tenant qua `company_id`; migration 0013
  bổ sung khóa ngoại ghép để PostgreSQL chặn link chéo workspace.
- Cache key gồm môi trường, workspace và signature của tham số/phiên bản dữ liệu;
  cache lỗi là cache miss. Queue Redis dùng `noeviction` + AOF `everysec`, còn
  cache Redis dùng `allkeys-lru` với TTL ngắn.
- File gốc và raw crawl ở object storage; PostgreSQL giữ object key, checksum,
  parser/model version và metadata truy vấn.
