# Architecture

## Tổng quan

<!-- Sơ đồ tổng thể: web → api → agents → worker → integrations -->

## Thành phần

| Thành phần | Vai trò | Công nghệ |
| --- | --- | --- |
| `apps/web` | Giao diện người dùng | Next.js |
| `services/api` | REST API, auth, quản lý campaign/post/approval | FastAPI |
| `services/ingestion` | Chuẩn hoá tài liệu đầu vào | PDF / Excel / Doc / Image / Video / URL |
| `services/agents` | Agentic workflow | LangGraph |
| `services/worker` | Job nền: publish, monitor, schedule | Queue worker |

## Luồng dữ liệu

<!-- ingestion → knowledge base → agents → nội dung nháp → approval → publish → analytics -->

## Quyết định thiết kế

<!-- ADR ngắn gọn: lý do chọn monorepo, LangGraph, queue, storage -->
