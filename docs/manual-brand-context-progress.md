# Tiến độ hồ sơ tự nhập và tài liệu cho Content Agent

Ngày bắt đầu: 2026-09-29 (Asia/Ho_Chi_Minh)
Nhánh: `codex/manual-brand-content-context`
Commit nền: `1f0e933acdb331410a7cb7ec0c2ecf6a652ad351` (`codex/docling-document-ingestion`)

## Trạng thái

| Hạng mục | Trạng thái | Bằng chứng / việc kế tiếp |
|---|---|---|
| Kiểm kê luồng Brand Profile, ingestion và tạo/sửa bài | DONE | Đã truy vết API hồ sơ, worker ingestion, planning, generation/revision, review và UI trong checkout riêng. |
| Hồ sơ văn bản tự nhập, chỉ Owner áp dụng | DONE | API lưu nguyên văn với version guard; Owner-only, revisions bất biến, cùng nội dung không tạo revision mới; UI textarea và lịch sử read-only. |
| Tách ingestion khỏi tạo Brand Profile | DONE | Worker chỉ chạy Docling/chuẩn hóa/chunk/index; `profile_only` trả 410; không còn M2 worker callable tạo hồ sơ. |
| Chọn tài liệu theo từng yêu cầu tạo bài | DONE | API/worker kiểm tra tenant, trạng thái và readiness; retrieval rỗng khi không chọn; chọn tài liệu lưu cùng input snapshot. |
| Giữ nguồn đã chọn khi sửa bài | DONE | Revise kế thừa danh sách trước nếu không gửi trường; `[]` bỏ nguồn; lựa chọn hiển thị/lưu theo phiên bản. |
| Prompt, semantic review và provenance | DONE | Content/planning/review nhận prose Owner-authored; citation kiểm tra đúng nguồn; market research giữ nhãn nguồn ngoài không xác minh. |
| OpenAPI và TypeScript | DONE | OpenAPI mới sinh lại; `scripts/export_openapi.py --check` đạt; frontend dùng `schema.d.ts` sinh tự động. |
| Backend/frontend kiểm thử | DONE WITH LIMITATION | Frontend typecheck/test/lint/build đạt. Backend suite: 228 passed, 12 skipped; một test PDF không chạy được vì thiếu model artifacts Docling cục bộ. |
| PostgreSQL/Redis và API readiness | PASS | Runtime DB `agentic_marketing_fresh` đã backup, migrate từ `0017` lên `0020`; `/readyz` xác nhận database, schema, Redis, cache và storage sẵn sàng. |
| DeepSeek live và browser pipeline sau đăng nhập | NOT_RUN | Chưa gọi provider; chưa đăng nhập bằng thông tin của Owner hoặc chạy UI → worker → database. `POSTGRES_TEST_URL` cũng chưa có nên suite PostgreSQL vẫn skip. |
| Review, commit và push nhánh feature | DONE | Diff/staged diff và secret scan đã rà; remote SHA mới nhất được ghi trong verification. |
| Mở preview giao diện | PARTIAL | Frontend real-mode/mocks-off ở `http://127.0.0.1:13103` đã kết nối API và hiện form đăng nhập. Phiên cũ hết hạn; chưa nhập thông tin đăng nhập. |

## Nhật ký

- 2026-09-29: Tạo worktree riêng từ commit Docling đã kiểm tra; nhánh feature không dùng chung working tree/index của `/Users/lethanh/agent`.
- 2026-09-29: Thay Brand Profile UI/API sang prose tự nhập; bỏ bước Brand Profile khỏi worker ingestion; thêm phạm vi tài liệu chọn lọc vào request và worker.
- 2026-09-29: Đồng bộ OpenAPI và type sinh; thêm trạng thái hồ sơ chưa áp dụng, lưu nguồn khi revise, cho phép sinh bài không đính kèm tài liệu; gỡ worker bridge AI tạo Brand Profile.
- 2026-09-29: Backend tests liên quan, frontend typecheck/tests/lint/build và OpenAPI check chạy trong worktree feature; xem `manual-brand-context-verification.md` để biết kết quả cuối.
- 2026-09-29: Commit triển khai `5f168a672f883fe64aa7be27fe20084d3be6256f`; staged diff sạch và chỉ gồm 36 file thuộc luồng này.
- 2026-09-29: Tạo backup runtime trước migration; nâng `agentic_marketing_fresh` từ `0017` lên `0020` bằng role migration. API `/readyz` báo đủ database/schema/Redis/cache/storage; CORS cho cổng 13103 đạt.
- 2026-09-29: Preview ở cổng 13103 chuyển từ lỗi kết nối sang form đăng nhập. API nhận `/api/v1/me` và trả 401 vì phiên browser đã hết hạn; không nhập email/mật khẩu.

## Giới hạn hiện tại

- PostgreSQL/Redis service health đã đạt, nhưng integration suite dùng `POSTGRES_TEST_URL` và pipeline sau đăng nhập chưa chạy.
- Chưa gọi DeepSeek live. Lưu hồ sơ và ingest không cần model; content tests dùng model fixture.
- Một test PDF yêu cầu `DOCLING_ARTIFACTS_PATH` có manifest/model `layout` và `tableformer`; môi trường này chưa có cấu hình đó. Xem verification.
