# Architecture

## Tổng quan

```text
web → api → PostgreSQL (source of truth)
             ├── commit job/domain update
             ├── dispatcher → Redis/Celery → worker / agent-worker
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
có Agent HTTP Service riêng trong MVP. Redis chỉ làm queue/cache, không là nơi duy
nhất giữ lịch hoặc trạng thái job.

## Luồng dữ liệu

<!-- ingestion → knowledge base → agents → nội dung nháp → approval → publish → analytics -->

## Quyết định thiết kế

- Modular monolith giữ transaction nghiệp vụ, job ledger và tenant isolation ở cùng
  một boundary; Redis/Celery chỉ nhận job sau khi transaction DB đã commit.
- PostgreSQL dùng pgvector-capable image; MinIO là storage local tương thích S3.
