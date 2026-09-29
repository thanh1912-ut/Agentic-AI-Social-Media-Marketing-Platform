# Kiểm chứng Page workspace và Nghiên cứu

## Baseline

- SHA: `b769097bfdb3568889d974c6def95bb944559113`
- Branch triển khai: `codex/page-workspaces-research`
- Runtime/test DB: chưa kiểm tra trong lượt triển khai.

## Trạng thái triển khai hiện tại

| Hạng mục | Kết quả | Bằng chứng |
|---|---|---|
| Đăng ký tài khoản không tạo workspace | PASS (SQLite API fixture) | `test_register_creates_user_only_and_preserves_password_exactly` |
| Xác minh Page token → workspace | PARTIAL; live Meta NOT_RUN | Fixture xác nhận Page activation; `/me` identity phải trùng Page ID và read-only post call; chưa gọi Meta live |
| Chống Page token tự cấp membership | PASS (SQLite API fixture) | `test_page_activation_owns_workspace_and_token_does_not_grant_membership` trả 409 cho non-member |
| Token reconnect giữ cùng Page/data | PASS (SQLite API fixture) | `test_page_token_is_encrypted_and_same_page_can_reconnect`; reconnect cùng Page, token mã hóa thật trong test |
| API Page activation gate | PASS (SQLite API fixture) | `test_legacy_workspace_requires_page_before_agentic_writes` trả 409 khi workspace chưa có Page |
| Worker/scheduler Page activation gate | PARTIAL; PostgreSQL/Redis NOT_RUN | Guard được gọi ở các claim/scheduler/preflight path; chưa có integration cạnh tranh/recovery trên dịch vụ thật |
| Nghiên cứu không cần người dùng chọn nhóm | PARTIAL | UI facade workspace; nhóm legacy vẫn là FK persistence/report |
| Page công ty Meta collection | PARTIAL; live NOT_RUN | Existing Meta post/metrics path; bounded posts; không thêm comment bodies |
| Public Page Tier 0 | PARTIAL; live NOT_RUN | Existing facebook-cli pipeline; không chứng minh lịch sử đầy đủ |
| Public Group Tier 0 | UNSUPPORTED/PARTIAL | Status `unsupported_tier0`; Group discussions không được hỗ trợ ở Tier 0 |
| Comment text / replies | PRIVACY_HOLD | Không tải comment text mới; report bỏ comment text legacy khỏi model context; aggregate count riêng |
| Media download/analysis | NOT_IMPLEMENTED | Không có asset pipeline; Gemini chưa nối |
| Qwen / Gemini / DeepSeek routing | NOT_IMPLEMENTED except existing DeepSeek | Không có adapter mới, model/cost validation hoặc fallback |
| AI budget $2/workspace/day | NOT_IMPLEMENTED | Chưa có reservation/actual usage ledger; không cho rằng đã được giới hạn |
| Privacy retention/deletion | BLOCKED | Chưa có policy version, deletion ledger/propagation hoặc legal review; không tuyên bố tuân thủ đầy đủ |
| PostgreSQL migration fresh/upgrade | NOT_RUN | Chưa cấu hình database test riêng; không chạy migration vào DB preview |
| Redis jobs/browser reload | NOT_RUN | Chưa chạy pipeline thật trên Redis/Celery và browser cho commit hiện tại |
| Facebook avatar URL | PASS (HTTP fixture) | `test_verify_page_uses_bearer_header_and_returns_verified_identity` kiểm tra Meta CDN, giữ chữ ký CDN cần thiết và loại API token; test host ngoài bị loại |
| Frontend lint | PASS | `npm run lint` |
| Frontend typecheck | PASS | `npm run typecheck -- --incremental false` (tránh tạo tsbuildinfo trong worktree được bảo vệ) |
| Frontend unit tests | PASS | `npm test` — 50 tests |
| Frontend production build | PASS | `npm run build` trong worktree riêng, không thay preview |
| Python regression | PASS (fixtures) | 75 passed, 6 skipped, 1 deselected; Docling runtime test deselected do dependency/model thiếu |
| Python lint | PASS | `ruff check --no-cache` trên các file Python của nhiệm vụ |

Không xem fixture, HTTP 202 hoặc status job đơn lẻ là nghiệm thu pipeline.
Không tuyên bố đã crawl hết Page/Group hoặc đạt chứng nhận pháp lý.

## Bằng chứng code trong lượt triển khai

- Baseline branch/SHA: `codex/creative-studio-ui` @ `b769097bfdb3568889d974c6def95bb944559113`.
- Branch hiện tại: `codex/page-workspaces-research`; test SHA và remote SHA sẽ ghi sau commit.
- Đã thêm migration `0021_page_workspace_identity`; migration thật chưa chạy.
- OpenAPI được xuất vào `/private/tmp/page-workspaces-openapi.json` và frontend types sinh bằng `npm run gen:api`; stub pgvector chỉ dùng để import schema, không được tính là backend runtime/test.
- `alembic upgrade head --sql` chưa chạy hết được vì migration cũ `0002_profile_knowledge` gọi schema inspector, không hỗ trợ Alembic offline SQL; không chạy migration lên database preview.
- Từng phát sinh đầu ra có URL kết nối DB trong một lượt rà cấu hình. Không lặp lại hoặc commit thông tin đó; cần xoay mật khẩu sau khi có cửa sổ vận hành an toàn.

## Trạng thái pháp lý và xử lý bình luận/media

Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP có hiệu lực từ 2026-01-01 theo cổng văn bản Chính phủ/Công báo. Đây là ghi nhận ngày hiệu lực, không phải kết luận tư vấn pháp lý hoặc chứng nhận tuân thủ. Chưa có cấu hình mục đích/căn cứ, retention/deletion ledger và propagation đầy đủ; vì vậy comment text ở `privacy_hold`, còn media chưa gửi sang provider.

- [Luật 91/2025/QH15 — Cổng văn bản Chính phủ](https://vanban.chinhphu.vn/?docid=214590&pageid=27160&typegroupid=3)
- [Nghị định 356/2025/NĐ-CP — Công báo Chính phủ](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-356-2025-nd-cp-468371/61065.htm)
