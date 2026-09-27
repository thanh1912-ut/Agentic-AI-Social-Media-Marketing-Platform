# MailGuard pilot — tiến độ triển khai

Ngày cập nhật: 2026-09-27 (Asia/Ho_Chi_Minh)

## Trạng thái tổng thể

**IN_PROGRESS — code pilot đã commit và push; remote SHA đã xác minh. Provider live và browser workflow sau xác nhận Brand Profile vẫn chưa nghiệm thu.**

- Nhánh: `codex/mailguard-pilot`
- Commit triển khai: `5434dc5` (`feat: complete MailGuard pilot workflows`).
- Commit triển khai và các commit cập nhật báo cáo đều đã được push lên nhánh này.
- Base: `origin/codex/project-database-hardening` tại `79e23ce759f4cd32d64d6f61e3961cf9c106ae51`
- Worktree: `/Users/lethanh/.codex/worktrees/mailguard-pilot/agent`, tách biệt checkout dùng chung và preview.
- Tài liệu đầu vào: `/Users/lethanh/Downloads/MGAI - AI Agent.docx`.
- Database kiểm thử: PostgreSQL 18.3 + pgvector, database riêng; Redis queue/cache riêng.
- Secret được kiểm tra theo trạng thái có/thiếu trong môi trường tiến trình này, không đọc hoặc ghi giá trị vào log/docs. DeepSeek key/model và Meta Page token/App Secret không có trong môi trường kiểm thử này.

## Đối chiếu nhiệm vụ

| Phạm vi | Trạng thái | Ghi chú |
|---|---|---|
| Thương hiệu MailGuard, nguồn và claim | DONE (phần thiết lập) | Không tự đặt website/logo/CTA/claim chính thức. Brand Profile tiếp tục cần người dùng xác nhận trước khi dùng cho generation. |
| Prompt → brief và 3 concept | DONE (code/test) | Job bền vững, tenant-scoped; người dùng chọn concept và xác nhận mới tạo campaign. DeepSeek live: BLOCKED/NOT_RUN do thiếu secret/model trong tiến trình này. |
| Review, provenance, version/hash và approval guard | DONE (code/test) | Lưu review theo post version/hash/rule; blocking tách warning; publish/approve cần review hiện hành. DeepSeek semantic pass chỉ bổ sung cảnh báo cho Owner, không quyết định duyệt. |
| Đăng ngay và publish guards | DONE (code/test) | Dùng adapter Meta hiện có; không thực hiện bài đăng công khai trong nghiệm thu. |
| Lên lịch/hủy/lỡ lịch Meta | DONE (code/PostgreSQL test) | Lịch bền vững trong PostgreSQL; scheduler tạo job đến hạn, hủy trước khi gửi, quá hạn >15 phút yêu cầu Owner chọn lại. Meta live: NOT_RUN. |
| Lịch đồng bộ Page metrics | DONE (code/PostgreSQL test) | Owner bật/tắt; mặc định tắt, mặc định 6 giờ; nút đồng bộ hiện có được giữ. Meta permissions/live sync: NOT_RUN. |
| Analytics conversion MailGuard | DONE (code/test) | Integration key băm/revoke, chỉ nhận hai event, chống replay và actor trùng, analytics/cohort có trạng thái thiếu dữ liệu. Website chưa có; trạng thái `INTEGRATION_READY`, conversion live `NOT_RUN`. |
| Frontend real-mode | PARTIAL PASS | API/UI/worker/Beat chạy ở cổng riêng; login thật, analytics `INTEGRATION_READY`, workspace đọc lại sau reload đều hiển thị. Chưa upload/tự xác nhận hồ sơ MailGuard hoặc chạy flow AI/publish. |
| Migration/schema | DONE (PostgreSQL) | Migration `0018_mailguard_pilot_workflows`; fresh upgrade, upgrade từ `0017`, downgrade/upgrade và Alembic parity đã kiểm tra. |
| DeepSeek / Meta thật | BLOCKED/NOT_RUN | Không có credentials trong tiến trình này; model giả dùng riêng trong test; không gọi model thật và không đăng bài. |
| Commit/push và preview | PASS | Feature branch đã push và SHA remote xác nhận; preview cô lập ở cổng 3101, không tác động main/preview khác. |

## Nhật ký và bằng chứng

### 2026-09-27 — Triển khai và kiểm thử

- Thêm migration `0018_mailguard_pilot_workflows` cùng review, scheduled publication, conversion integration/event và Page metric schedule.
- Thêm campaign planning async; kết quả lưu trong job và chỉ tạo campaign sau khi người dùng chọn concept.
- Nối frontend với planning, review, scheduled publication, metric sync setting và MailGuard conversions; OpenAPI TypeScript sinh bằng script của repo.
- PostgreSQL 18.3 + pgvector: migrate mới tới `0018`, downgrade `0017` rồi nâng lại tới head; `alembic check` không phát hiện khác biệt model/schema.
- `tests/test_postgres_database_integration.py`: **5 passed** trên PostgreSQL/Redis test instance.
- `tests/test_postgres_application_modules.py`: **1 passed** riêng trên PostgreSQL thật; bao gồm các luồng tài liệu/RAG hiện có và các assertion mới cho review/approval, schedule/cancel, metric schedule và MailGuard events.
- `tests/test_campaign_workflows.py tests/test_mailguard_pilot.py`: **19 passed**, gồm model giả semantic review và kiểm tra CTA; không gửi request ra ngoài.
- Frontend: lint PASS, typecheck PASS, **47 tests passed**, production build PASS.
- Python syntax AST: **56 files** parse thành công. `ruff` không có trong virtualenv nên Python lint: NOT_RUN.
- Một lượt unit test ban đầu bị sandbox chặn lúc tạo `.data` trước khi test chạy; sau đó sửa session handling của semantic review và chạy lại trong worktree: 19/19 pass.
- API `/readyz` trả `ready`; database/schema/Redis/cache/object storage đều healthy. Browser đăng nhập tài khoản pilot riêng tại cổng 3101; workspace và role Owner vẫn hiện sau reload. Analytics hiển thị `INTEGRATION_READY · live NOT_RUN`, không có conversion giả.
- Campaign UI hiện đúng guard: planning/campaign tạo mới bị khóa tới khi hồ sơ thương hiệu được hoàn tất/xác nhận. Chưa xác nhận thay người dùng và chưa gửi nội dung tới DeepSeek.
- DeepSeek live, Meta Page read/publish, browser upload/AI/publish end-to-end và website MailGuard event live chưa chạy.

## Checklist bàn giao

- [x] Khảo sát checkout, base SHA, tài liệu nguồn và migration.
- [x] Campaign planning bền vững, ba concept và bước xác nhận người dùng.
- [x] Review phiên bản/hash và chặn approval/publish khi review thiếu hoặc cũ.
- [x] Meta publish scheduling, cancel, missed-state và metric sync schedule.
- [x] Server-to-server tracking events, dedup và conversion cohort.
- [x] Frontend/API schemas/OpenAPI types, lint, typecheck, unit tests, build.
- [x] PostgreSQL migration/fresh/upgrade/downgrade parity và application flow tests.
- [x] Chạy API/frontend/worker/Beat trên port riêng; browser login, workspace reload và analytics tracking state đã xác minh.
- [ ] Người dùng tải nguồn MailGuard, rà/xác nhận Brand Profile để bật planning/generation.
- [ ] DeepSeek live, Meta live và website conversion live (cần secret/quyền/website thật).
- [x] Final diff/secret scan; commit `5434dc5` trên `codex/mailguard-pilot`.
- [x] Push `codex/mailguard-pilot`; GitHub remote ref đã được xác minh sau các cập nhật báo cáo.
- [x] Mở frontend real mode và xác minh login/workspace; giữ tab pilot mở cho người dùng.

## Tiếp theo

1. Người dùng tải nguồn MailGuard, rà/xác nhận Brand Profile để mở planning.
2. Khi có DeepSeek secret/model hợp lệ, chạy một lượt thử giới hạn; không seed MailGuard conversion giả.
3. Chỉ kiểm thử Meta publish sau khi Owner cấu hình Page và chọn/xác nhận bài cụ thể.
4. Giữ service pilot test đang chạy để người dùng xem; không dừng dịch vụ preview.
