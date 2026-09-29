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
| Worker/scheduler Page activation gate | PARTIAL | PostgreSQL test thật xác nhận worker claim chỉ thành công với workspace có Page active; Redis/Celery được thử riêng trên instance tạm; browser end-to-end NOT_RUN |
| Nghiên cứu không cần người dùng chọn nhóm | PARTIAL | UI facade workspace; nhóm legacy vẫn là FK persistence/report |
| Page công ty Meta collection | PARTIAL; live NOT_RUN | Existing Meta post/metrics path; bounded posts; không thêm comment bodies |
| Public Page Tier 0 | PARTIAL; live NOT_RUN | Existing facebook-cli pipeline; không chứng minh lịch sử đầy đủ |
| Public Group Tier 0 | UNSUPPORTED/PARTIAL | Status `unsupported_tier0`; Group discussions không được hỗ trợ ở Tier 0 |
| Comment text / replies | PRIVACY_HOLD | Không tải comment text mới; report bỏ comment text legacy khỏi model context; aggregate count riêng |
| Media download/analysis | NOT_IMPLEMENTED | Có Gemini inline adapter fixture; chưa có asset pipeline hoặc worker routing |
| Qwen / Gemini / DeepSeek routing | PARTIAL | DeepSeek giữ luồng hiện có; Qwen text JSON-mode và Gemini inline media adapters có fixture nhưng chưa nối comment/media pipeline hoặc unified budget; không tự fallback |
| AI budget $2/workspace/day | PARTIAL | PostgreSQL reservation/ledger hiện bao phủ báo cáo Nghiên cứu DeepSeek tự động; chưa áp dụng chung cho các agent, Gemini/Qwen hoặc media |
| Ngân sách API/UI | PASS theo API fixture và frontend lint/unit; browser real NOT_RUN | `GET .../market-research/ai-budget`; `test_research_ai_budget_is_workspace_scoped_and_reports_reserved_cost` |
| Pin bằng chứng cho hướng viết | PASS (API + worker fixture) | `test_market_suggestion_draft_pins_report_observation_and_version`, `test_content_generation_job_persists_cited_draft_and_is_idempotent` |
| Privacy retention/deletion | BLOCKED | Chưa có policy version, deletion ledger/propagation hoặc legal review; không tuyên bố tuân thủ đầy đủ |
| PostgreSQL migration fresh/upgrade | PASS (test cluster tạm) | Fresh migration đạt `0022`; database riêng đã nâng `0021` → `0022`; legacy mapping của `0021` được kiểm tra trước đó |
| PostgreSQL/Redis integration | PASS (test services tạm) | `tests/test_postgres_database_integration.py tests/test_ai_budget.py`: 16 passed; queue/cache TTL, fencing/claim, Celery dispatch và reservation race |
| Budget pricing + no-provider fallback | PASS (unit) | 9 test; tiền micro-USD, upper bound một repair, worker không gọi provider khi deferred/uncertain |
| DeepSeek live billing and replay | NOT_RUN | Không gọi live provider; reservation/settlement dùng usage fixture trên PostgreSQL thật |
| Full Python suite with Docling | FAIL / ENVIRONMENT BLOCKED | 11 parser tests không khởi tạo được Docling subprocess trong API venv hiện tại; không liên quan ledger |
| Celery dispatch | PASS (integration test, không chạy crawl worker) | Production dispatcher đưa đúng synthetic job ID vào Redis queue `agent`; test dọn message và bản ghi synthetic; worker xử lý end-to-end NOT_RUN |
| Browser reload | NOT_RUN | Chưa chạy pipeline thật từ UI đến worker rồi reload trong commit hiện tại |
| Facebook avatar URL | PASS (HTTP fixture) | `test_verify_page_uses_bearer_header_and_returns_verified_identity` kiểm tra Meta CDN, giữ chữ ký CDN cần thiết và loại API token; test host ngoài bị loại |
| Frontend lint | PASS | `npm run lint` |
| Frontend typecheck | PASS (2026-09-30 latest) | `npm --workspace @agentic/web run typecheck -- --incremental false` |
| Frontend unit tests | PASS | `npm test` — 50 tests |
| Frontend production build | PASS | `npm run build` trong worktree riêng, không thay preview |
| Browser E2E fixture desktop | PASS | 26 passed, 1 skipped; MSW/demo only; server build ở cổng test `13107` |
| Browser E2E fixture mobile | PASS | 26 passed, 1 skipped; MSW/demo only; server build ở cổng test `13107` |
| Python regression | PASS (fixtures) | 75 passed, 6 skipped, 1 deselected; Docling runtime test deselected do dependency/model thiếu |
| Python lint | PASS | `ruff check --no-cache` trên các file Python của nhiệm vụ |

Không xem fixture, HTTP 202 hoặc status job đơn lẻ là nghiệm thu pipeline.
Không tuyên bố đã crawl hết Page/Group hoặc đạt chứng nhận pháp lý.

## Bằng chứng code trong lượt triển khai

- Baseline branch/SHA: `codex/creative-studio-ui` @ `b769097bfdb3568889d974c6def95bb944559113`.
- Implementation commit: `d2ad5dddf7ef4055a1941d69c32a67d5d93ecf4a`.
- Commit integration test PostgreSQL/Redis: `6bb99106d689444cfb1b2acc6e5ea467a8e553cc` trên `codex/page-workspaces-research`.
- Commit ledger AI tự động: `2b3cb9283e9f512b9aa288ecf48af4437cde9a1f`; `git ls-remote` xác nhận SHA trên origin khớp.
- Remote SHA được xác minh lúc `2026-09-30 01:54 Asia/Ho_Chi_Minh`: `origin/codex/page-workspaces-research` khớp commit `6bb99106d689444cfb1b2acc6e5ea467a8e553cc`.
- Đã thêm migration `0021_page_workspace_identity`. Fresh migration chạy trên PostgreSQL 18.3 test cluster tạm, từ database mới đến `0021`.
- Upgrade migration được thử trên database riêng ở `0020`. Vì migration `0001` của checkout mới tạo metadata hiện tại, test đã gỡ riêng ba cột/index mới để mô phỏng schema cũ, seed dữ liệu synthetic và áp dụng `0021`: workspace một Page được map với `needs_reconnect`; workspace nhiều Page, Page trùng giữa workspace và không Page giữ `page_id=NULL`/`connection_required`.
- PostgreSQL/Redis integration chạy trên test services tạm ở loopback: `tests/test_postgres_database_integration.py` đạt 6 passed. Test production Celery dispatcher đưa đúng job ID synthetic vào Redis `agent` queue; message và bản ghi test được dọn sau kiểm tra. Không chạy worker xử lý research để tránh crawl hoặc gọi provider.
- Migration `0022_ai_usage_budget` được thêm sau head thực tế. Fresh migration trên PostgreSQL 18.3 test cluster đạt `0022`; database thứ hai đã nâng từ `0021` lên `0022`.
- AI budget test chạy với PostgreSQL/Redis isolation: tổng `tests/test_postgres_database_integration.py tests/test_ai_budget.py` đạt 16 passed. Sáu reservations đồng thời chỉ hai lượt được cấp trong budget 40.000 micro-USD; cùng request key không mở reservation/call khác; settlement ghi chi phí tính từ fixture token usage.
- Regression hiện tại bỏ qua Docling tests cần runtime riêng: `pytest tests --ignore=tests/test_ingestion_parsers.py -k 'not test_parser_returns_locators_and_rejects_scan_pdf'` đạt 236 passed, 14 skipped, 1 deselected. Full `pytest tests` có 11 lỗi vì Docling subprocess không khởi tạo trong API venv; Docling chưa được nghiệm thu.
- Giá DeepSeek pin cho budget là peak/cache-miss theo [bảng giá chính thức](https://api-docs.deepseek.com/quick_start/pricing/); model ngoài bảng không được gọi. Smoke provider live chưa chạy.
- OpenAPI được xuất vào `/private/tmp/page-workspaces-openapi.json` và frontend types sinh bằng `npm run gen:api`; stub pgvector chỉ dùng để import schema, không được tính là backend runtime/test.
- Cập nhật ngân sách API/UI trong lượt tiếp: endpoint trả số dư ngày `Asia/Ho_Chi_Minh`, fixture seed ledger/report và xác nhận workspace totals; frontend hiển thị số liệu USD, trạng thái pending và reset time. OpenAPI export/`--check` đạt; dùng `openapi-typescript 7.13.0` sinh declarations.
- Latest frontend checks: lint PASS, typecheck PASS, unit tests 50/50. Playwright fixture E2E desktop và mobile đều 26 passed, 1 skipped mỗi project; test screenshot skip có chủ đích khi không đặt output directory. Các suite dùng MSW/demo data, không gọi backend thật.
- E2E xác nhận login demo → chọn Page fixture đã active → mở workspace, trạng thái brand/documents, và tab Research query được giữ sau reload. Đây là browser fixture PASS, không chứng minh Meta/Page token hoặc crawler live.
- Report-to-draft fixture có evidence mới hơn với text/metrics khác; campaign giữ pin của report cũ, worker chỉ dùng version/observation đó. Website snapshot được truy xuất đúng theo report link, nội dung được allowlist và signed image URL bị loại; worker kiểm tra lại source/pins trước khi lưu. Comment text không gửi cho model. Nếu pin mất/source inactive, worker từ chối context thay vì query latest.
- Latest focused backend checks: `tests/test_campaign_workflows.py` 11 passed, `tests/test_market_research_api.py` 10 passed, `tests/test_ai_budget.py` 9 passed. Đây là SQLite API/worker fixtures, không thay cho PostgreSQL/Redis end-to-end.
- Report provenance/website pin tests: 30 passed ở ba nhóm worker/API/budget; provider fixture suite (Qwen + Gemini + DeepSeek) 31 passed khi bỏ `conftest.py`. Chưa có provider live call.
- Gemini fixture kiểm tra privacy hold, SHA, MIME, inline size, structured validation và không retry; chưa xác minh Gemini API live. Pytest chuẩn hiện bị chặn khi setup vì thiếu `pgvector`; Qwen SDK integration cần package `openai` theo manifest.
- `alembic upgrade head --sql` vẫn không hỗ trợ do migration cũ `0002_profile_knowledge` gọi schema inspector; online fresh/upgrade trên PostgreSQL test thật đã đạt. Không chạy migration lên database preview.
- Từng phát sinh đầu ra có URL kết nối DB trong một lượt rà cấu hình. Không lặp lại hoặc commit thông tin đó; cần xoay mật khẩu sau khi có cửa sổ vận hành an toàn.

### Cập nhật browser fixture — 2026-09-30 03:47 Asia/Ho_Chi_Minh

- E2E cũ chờ CTA onboarding trước khi Page activation được thêm; fixture workspace thiếu `page_connection_state`, nên luồng demo dừng ở chooser. Đồng bộ lại seed fixture với contract hiện tại và cập nhật helper để chọn workspace đã kích hoạt.
- Test tab cũ còn chờ nhãn “Báo cáo”; đổi sang “Phân tích & hướng viết”, đồng thời kiểm tra legacy `/fanpages` redirect.
- Sau sửa: Playwright desktop 26 passed/1 skipped; mobile 26 passed/1 skipped. Lỗi cũ không được giữ làm kết quả cuối.
- Mọi kết quả trong mục này là fixture/MSW; real browser → API → worker → PostgreSQL vẫn NOT_RUN.

## Trạng thái pháp lý và xử lý bình luận/media

Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP có hiệu lực từ 2026-01-01 theo cổng văn bản Chính phủ/Công báo. Đây là ghi nhận ngày hiệu lực, không phải kết luận tư vấn pháp lý hoặc chứng nhận tuân thủ. Chưa có cấu hình mục đích/căn cứ, retention/deletion ledger và propagation đầy đủ; vì vậy comment text ở `privacy_hold`, còn media chưa gửi sang provider.

- [Luật 91/2025/QH15 — Cổng văn bản Chính phủ](https://vanban.chinhphu.vn/?docid=214590&pageid=27160&typegroupid=3)
- [Nghị định 356/2025/NĐ-CP — Công báo Chính phủ](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-356-2025-nd-cp-468371/61065.htm)
