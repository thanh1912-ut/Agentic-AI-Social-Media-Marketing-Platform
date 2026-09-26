# Tiến trình hoàn thiện PostgreSQL/Redis

Cập nhật: 2026-09-27 01:14 Asia/Ho_Chi_Minh

## Phạm vi và baseline

- Branch: `codex/project-database-hardening`.
- Base: `4fcda2042d9709d84bab42afd27d01b8131d32c3` (`codex/website-catalog-intelligence`).
- Checkout thực hiện trong managed worktree riêng; shared `/Users/lethanh/agent` giữ nguyên.
- Baseline có 48 bảng model, migration `0014_website_catalog_intelligence`; migration hiện tại `0017_web_entity_snapshot_immutability`.
- Hạ tầng kiểm thử riêng: PostgreSQL 18.3 + pgvector tại `127.0.0.1:15432`, Redis queue `16379`, Redis cache `16380`. Listener cũ `5432/6379` không bị thay đổi.
- Test project chạy trong `/private/tmp/agentic-marketing-py311`. Không có DeepSeek key trong môi trường kiểm thử; không gọi Meta live.

## Checklist

| Trạng thái | Công việc | Bằng chứng / bước tiếp theo |
|---|---|---|
| DONE | Khảo sát repo, branch, dependency, schema và tạo checkout biệt lập | Base/branch ghi trên; thay đổi staged và unstaged trong shared checkout không bị đụng tới. |
| DONE | Dựng PostgreSQL và hai Redis instance loopback cùng LaunchAgents | Installer xác nhận cả ba service ready; sửa thứ tự shutdown để LaunchAgent không khởi động lại PostgreSQL giữa lúc dừng. |
| DONE | Fresh migration và upgrade database cũ | Fresh, upgrade từ `0013`, integration DB và owner-restored backup đều ở `0017`; `alembic check` sạch trên các database xác minh khi chạy bằng migration owner. |
| DONE | Ràng buộc crawl và phiên bản bằng chứng theo workspace | `0015` thêm FK ghép, check constraint và snapshot guard; `0016` sửa cột thiếu lịch sử; `0017` chặn sửa/xóa snapshot đang được dùng làm bản mới nhất. |
| DONE | Fencing worker, gia hạn lease khi commit và telemetry dispatch | Test PostgreSQL chứng minh worker cũ không commit, hai claim cạnh tranh chỉ có một worker thắng, và job vẫn còn sau lỗi dispatch rồi được gửi lại. |
| DONE | Kiểm tra module backend hiện có và frontend | 215 test backend pass, một DeepSeek live smoke bị skip; frontend lint, typecheck, 47 unit tests và build pass. PostgreSQL module smoke bao phủ API lưu brand, Page, market evidence, nội dung/approval, analytics và document/RAG persistence. |
| DONE | Crawl website từ frontend real mode và kiểm tra sau reload | `taphoammo.vn`, 10 trang; job thành công, run báo `partial` đúng budget, 9 entity và 10 report evidence đã lưu. Lịch nguồn test đã tắt. |
| DONE | Backup, checksum và restore PostgreSQL + storage | Bundle `20260926T170759Z`; checksum hợp lệ; restore ở DB/storage mới; API login và web-items đọc được 9 entity. |
| DONE | Chạy và bàn giao frontend real mode | API `/readyz` trả ready cho DB, schema, Redis queue/cache và storage; trang Fanpage trả HTTP 200 ở cổng 3100. API, worker và beat đang chạy từ worktree này. |
| IN_PROGRESS | Commit và push feature branch | Backend suite trên head `0017`: 215 passed, 1 skipped; frontend checks, compileall, shell syntax và readiness pass. Đã stage riêng 26 file thuộc nhiệm vụ; commit/push và xác minh SHA là bước cuối. |
| NOT RUN | DeepSeek và Meta live, MinIO/S3 | Không có credential được dùng trong nghiệm thu; object storage local đã được backup/restore. |
| NOT RUN | Thử rút Redis thật giữa khi job đang chờ hoặc chạy | Không dừng Redis dùng bởi frontend. Thay bằng kiểm thử dispatch-failure deterministic trên PostgreSQL và stale-fence/lease integration; CI có thể bổ sung service-chaos job sau này. |
| NOT RUN | Bản sao backup ngoài máy và kiểm tra restore định kỳ tự động | Bundle hiện cùng máy; LaunchAgent chạy khi user session hoạt động, không thay thế disaster recovery ngoài máy. |

## Nhật ký tiến trình

- 2026-09-26: Xác minh máy có PostgreSQL 18.3, Redis 8.6.3 và pgvector; không lấy listener 5432/6379 làm môi trường test. Điều này hiệu chỉnh nhận xét cũ “thiếu PostgreSQL/Redis”: dịch vụ có sẵn, nhưng luồng database/worker chưa được nghiệm thu trong phạm vi đó. :codex-annotation{index="1"}
- 2026-09-26: Tạo branch từ catalog HEAD trong managed worktree riêng; cài dependency trong Python 3.11 virtualenv và dựng DB/queue/cache riêng.
- 2026-09-26: Chạy migration mới từ đầu và nâng database legacy từ `0013`; phát hiện database tạo mới từ lịch sử không có `market_report_evidence.created_at`, thêm forward migration `0016` và xác nhận model/schema parity.
- 2026-09-26: Thêm fencing claim token cho document ingestion, content generation, research và Meta sync; thêm dispatch telemetry để job đã commit vẫn có thể được scheduler phục hồi.
- 2026-09-26: Smoke qua trình duyệt thật, đăng nhập workspace test, tạo source website, tắt lịch, bấm Crawl ngay. Job `823cd4ac-4117-4c8d-b0a3-4e061addd9f2` đi qua Redis/Celery và PostgreSQL. Run `915e6ba6-8aba-4837-918a-2f1c8a93e1fe` lưu 10/10 trang được xử lý trong giới hạn; cycle `b5c14a2b-70a6-4af1-be67-5af60ae2179c`, report `8f586b89-1edc-4762-b5da-841880ca784a` giữ 10 bằng chứng. Kết quả catalog: một sản phẩm, bảy bài viết, một mục thông tin website; giá là “liên hệ báo giá”, sold count thiếu được giữ `NULL`.
- 2026-09-26: Bắt và sửa thứ tự cập nhật crawl-page để cả ba tham chiếu evidence/observation/version được ghi cùng lúc, tránh ORM autoflush vi phạm check constraint.
- 2026-09-27: Sửa lịch nguồn bị tắt vẫn còn `next_due_at`; kiểm thử API và PostgreSQL xác nhận cả nguồn và group đều không còn lịch tiếp theo khi không còn source bật lịch.
- 2026-09-27: PostgreSQL application-module smoke bắt lỗi ở fenced worker commit: ORM autoflush cập nhật trạng thái job trước khi kiểm tra lease. Chuyển fenced session sang explicit flush có kiểm tra claim; test xác nhận tài liệu/chunks vẫn lưu khi DeepSeek chưa cấu hình và job kết thúc đúng trạng thái.
- 2026-09-27: Full backend suite trên PostgreSQL/Redis riêng: 215 passed, 1 skipped (DeepSeek live), 1 warning. PostgreSQL API-module smoke và các test cạnh tranh/recovery đều pass.
- 2026-09-27: Xác nhận fresh/upgrade/test/restore schema parity; backup checksum pass; restore và app-role API read pass.
- 2026-09-27: Thêm forward migration `0017` sau khi rà thấy cần chặn cả cập nhật snapshot latest; chạy upgrade/check trên fresh, upgrade, test, verify và owner-restored database. Full suite sau migration cuối tiếp tục 215 passed, 1 skipped.
- 2026-09-27: Restart API, worker, beat sau migration `0017`; `/readyz` trả tất cả dependency `true`, trang Fanpage test trả HTTP 200. Frontend được mở trong Codex để người dùng kiểm tra.
- 2026-09-27: Compile Python, kiểm tra cú pháp backup/installer, và `git diff --check` pass. Tiếp: commit/push branch và xác minh SHA remote.
