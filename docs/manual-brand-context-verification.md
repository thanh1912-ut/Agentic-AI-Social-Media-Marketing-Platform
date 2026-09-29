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
| Feature UI preview, mocks tắt | PARTIAL PASS | Giao diện ở `http://127.0.0.1:13103` kết nối API và hiện form đăng nhập; `/api/v1/me` trả 401 do phiên cũ hết hạn. Chưa nhập email/mật khẩu, nên chưa xác nhận đăng nhập. |
| Migration và dịch vụ local | PASS | Backup runtime được tạo trước khi migrate `0017` → `0020`; `/readyz` trả `ready` với PostgreSQL, schema, Redis queue/cache và storage đều true. CORS từ `13103` đạt. |
| PostgreSQL/Redis integration tests và tenant cases | NOT_RUN | Health check thật đạt; test suite tự skip vì `POSTGRES_TEST_URL` chưa cấu hình. |
| Browser UI → API → Redis/worker → PostgreSQL → reload | NOT_RUN | Chưa đăng nhập và chưa chạy worker; không dùng fixture làm bằng chứng pipeline. |
| DeepSeek live | NOT_RUN | Không gửi dữ liệu ra provider trong lượt nghiệm thu này; lưu hồ sơ/ingestion không cần DeepSeek, content dùng model fixture. |
| Facebook publish | OUT OF SCOPE | Không thay publisher và không đăng bài. |

## Môi trường/commit

- Nhánh: `codex/manual-brand-content-context`.
- Commit triển khai: `5f168a672f883fe64aa7be27fe20084d3be6256f`.
- Commit tài liệu bàn giao cuối: `290d251752555efe65b3f41c59724a405ffa9c2e`; SHA này đã xác minh trùng với remote branch.
- Commit nền: `1f0e933acdb331410a7cb7ec0c2ecf6a652ad351`.
- Runtime Python kiểm thử: `/private/tmp/docling-ingestion-venv/bin/python` (Python 3.14); test chạy từ `/private/tmp` để không ghi cache vào checkout.
- Frontend dùng Node dependencies qua overlay tạm trong `/private/tmp`; overlay được gỡ trước khi commit.
- PostgreSQL runtime schema hiện ở revision `0020`; backup trước migration được tạo trong backup directory đã cấu hình, bundle `agentic-agentic_marketing_fresh-20260929T091307Z`.
- API preview đang chạy trên `127.0.0.1:8000`, frontend real-mode/mocks-off trên `127.0.0.1:13103`. Celery worker/Beat chưa khởi động.
- API session check đã tới backend; `401` là phiên browser hết hạn, không còn là `network_error`. Cần Owner tự đăng nhập để tiếp tục UI tests.

Không dùng fixture làm bằng chứng provider live. Test PDF còn thiếu model artifacts là giới hạn môi trường đã xác định; không coi nó là PASS.
