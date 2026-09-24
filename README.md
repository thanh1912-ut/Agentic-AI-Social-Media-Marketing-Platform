# Nền tảng Agentic AI marketing mạng xã hội

Sản phẩm v1 hỗ trợ SME Việt Nam xây hồ sơ thương hiệu từ tài liệu, lập campaign, soạn nội dung, duyệt phiên bản và theo dõi kết quả. Tác vụ AI dùng DeepSeek ở phía server. Người dùng luôn duyệt bài trước khi đăng.

## Phạm vi v1

- Tạo workspace, mời thành viên và phân quyền Owner, Editor, Viewer.
- Nhập tài liệu PDF, DOCX, XLSX, CSV và TXT để tạo nguồn tri thức có locator.
- Tạo, chỉnh sửa và xác nhận Brand Profile có trích dẫn nguồn.
- Lập campaign strategy và content slots; sinh hoặc sửa bài bằng DeepSeek.
- Lưu lịch sử phiên bản, duyệt đúng nội dung/media hash và tải CSV/XLSX.
- Nhập metrics thủ công, xem dashboard và nhận recommendation có bằng chứng.
- Đăng Facebook thủ công từ file export khi chưa có Meta connector được cấp quyền.

Automatic Facebook publishing và metrics sync đang `BLOCKED_EXTERNAL`: dự án chưa có Meta app, Page, token, quyền hoặc App Review đã xác minh. Video, AI tạo ảnh/video, Google OAuth, ads và các mục deferred khác chưa thuộc v1.

## Thành phần

| Thư mục | Vai trò |
|---|---|
| `apps/web` | Next.js frontend, chế độ API thật hoặc MSW mock |
| `services/api` | FastAPI, xác thực, tenant permissions, campaign, nội dung và analytics |
| `services/ingestion` | Trích xuất, chuẩn hóa tài liệu và lưu knowledge chunks |
| `services/agents` | LangGraph workflows, retrieval, DeepSeek adapter và Brand Profile/content handlers |
| `services/worker` | Celery jobs và recovery |
| `database` | PostgreSQL models và Alembic migrations |
| `packages/contracts` | Pydantic nội bộ, OpenAPI và generated TypeScript types |
| `packages/prompts` | Prompt templates |

PostgreSQL giữ dữ liệu nghiệp vụ và job ledger. Redis làm queue. Compose dùng MinIO cho file. FastEmbed chạy local; có thể chọn lexical retrieval trong môi trường dev.

## Chạy local bằng Docker Compose

Bạn cần Docker Compose v2. Để dùng DeepSeek, provision `DEEPSEEK_API_KEY` trong `.env` ở máy chạy server. Không commit file này hoặc gửi key qua chat. Nếu thiếu key, API vẫn khởi động nhưng tác vụ AI kết thúc với `ai_not_configured`.

```bash
cp .env.example .env
docker compose up --build
```

Mở giao diện tại `http://localhost:3000`. Kiểm tra API tại `http://localhost:8000/healthz` và `http://localhost:8000/readyz`. Lần chạy đầu có thể tải model FastEmbed vào cache. Xem [runbook](docs/runbook.md) để cấu hình, migration, test, backup/restore và xử lý lỗi.

## Tài liệu dự án

- [Kế hoạch và phạm vi v1](docs/implementation-plan.md)
- [Tiến độ và blocker](docs/progress.md)
- [Task board](docs/task-board.md)
- [Báo cáo kiểm thử](docs/test-report.md)
- [Runbook](docs/runbook.md)
- [Security review](docs/security-review.md)
- [Quyết định kỹ thuật](docs/decisions.md)
- [Kiến trúc](docs/architecture.md)
- [API contracts](docs/api-contracts.md)
- [Workflows](docs/workflows.md)
