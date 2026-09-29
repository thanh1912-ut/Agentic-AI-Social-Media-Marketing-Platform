# Kiểm chứng hồ sơ tự nhập và tài liệu cho Content Agent

## Phạm vi

Yêu cầu là lưu prose thương hiệu do Owner tự viết, không dùng AI để tạo/sửa hồ sơ; ingestion chỉ lưu knowledge; tài liệu được chọn theo từng yêu cầu viết; có thể tạo bài không tài liệu; citations phải khớp nguồn thực.

## Kết quả

| Kiểm tra | Trạng thái | Ghi chú |
|---|---|---|
| Owner-only save/apply, văn bản nguyên văn và version conflict | PASS | `test_manual_profile_is_unchanged_by_document_ingestion`: Owner áp dụng xuống dòng tiếng Việt; Editor bị 403; cùng văn bản không tạo revision; version cũ trả 409. |
| Lưu hồ sơ không gọi model | PASS | Test thay model factory bằng fail-fast; thao tác lưu thành công mà factory không được gọi. |
| Upload/reprocess không tạo hồ sơ | PASS | Ingestion hoàn tất với knowledge ready, `profile_status=not_applicable`; revision và văn bản Owner không đổi; legacy `profile_only` trả 410 `brand_profile_generation_removed`. |
| Tài liệu chỉ truy xuất khi người dùng chọn | PASS | Content integration test chọn một document và kiểm tra nguồn document gửi cho agent đúng ID đó; retrieval không được gọi khi `document_ids=[]`. |
| Tạo bài không đính kèm tài liệu | PASS | Worker lưu draft từ hồ sơ Owner và brief với selection rỗng, không truy vấn knowledge store. |
| Revise kế thừa lựa chọn trước | PASS | Bản revise giữ lại document ID/note trong metadata phiên bản và dùng đúng nguồn đã chọn. |
| Prompt, citation và nguồn ngoài | PASS | Citation được kiểm tra theo source/version/locator/excerpt; market research vẫn được phân biệt là dữ liệu ngoài chưa xác minh. |
| OpenAPI / TypeScript contract | PASS | Export `--check` đạt; `schema.d.ts` sinh lại bằng `npm run gen:api -- --from ../../packages/contracts/openapi.json`. |
| Backend suite đầy đủ | PARTIAL PASS | 228 passed, 12 skipped, 1 failed. Lỗi duy nhất là `test_pdf_text_has_page_locator`: runner báo thiếu model Docling; môi trường không có `DOCLING_ARTIFACTS_PATH` và manifest model `layout`/`tableformer`. |
| Frontend typecheck / tests / lint | PASS | `npm run typecheck`, `npm test` (47 tests) và `npm run lint` đạt. |
| Frontend production build | PASS | `npm run build` đạt trên nhánh feature. |
| PostgreSQL/Redis thật và tenant integration trên dịch vụ thật | NOT_RUN | Các test PostgreSQL tự skip vì `POSTGRES_TEST_URL` chưa cấu hình; không dùng DB/Redis preview khác thay thế. |
| Browser UI → API → Redis/worker → PostgreSQL → reload | NOT_RUN | Chưa dựng preview/API/worker riêng cho feature; không dùng tab cũ làm bằng chứng. |
| DeepSeek live | NOT_RUN | Không gửi dữ liệu ra provider trong lượt nghiệm thu này; lưu hồ sơ/ingestion không cần DeepSeek, content dùng model fixture. |
| Facebook publish | OUT OF SCOPE | Không thay publisher và không đăng bài. |

## Môi trường/commit

- Nhánh: `codex/manual-brand-content-context`.
- Commit nền: `1f0e933acdb331410a7cb7ec0c2ecf6a652ad351`.
- Runtime Python kiểm thử: `/private/tmp/docling-ingestion-venv/bin/python` (Python 3.14); test chạy từ `/private/tmp` để không ghi cache vào checkout.
- Frontend dùng Node dependencies qua overlay tạm trong `/private/tmp`; overlay được gỡ trước khi commit.
- Commit thay đổi: chưa tạo.
- PostgreSQL/Redis/browser: chưa nghiệm thu trong nhánh feature.

Không dùng fixture làm bằng chứng provider live. Test PDF còn thiếu model artifacts là giới hạn môi trường đã xác định; không coi nó là PASS.
