# Kiểm chứng Page workspace và Nghiên cứu

## Chuẩn hóa nhãn Nghiên cứu — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Loại bỏ copy cũ “Fanpage & thị trường” trên trang nghiên cứu | PASS (code + frontend checks) | Nhãn route, tab và nguồn Page công ty khớp tên “Nghiên cứu”. |
| Frontend lint/typecheck/unit | PASS | ESLint, TypeScript, Vitest 50/50; không đổi contract. |
| Production build sau chỉnh sửa copy | NOT_RUN | Build production thành công ngay trước lát cắt copy; bản copy đã qua lint/typecheck/unit. |
| Browser real preview | NOT_RUN | Bản preview hiện hành chưa được thay. |

## Hiển thị Page gate toàn ứng dụng — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| `connection_required`/`needs_reconnect` hiển thị hướng xử lý trên mọi trang | PASS (code/build) | AppShell có thông báo dùng chung, giữ dữ liệu đọc được và link tới Cài đặt doanh nghiệp. |
| Gate backend, worker và scheduler | PASS ở các kiểm tra trước trên cùng nhánh | `PAGE_GATED_PERMISSIONS`, `services/worker/page_gate.py`, scheduler yêu cầu workspace/Page active; cần chạy lại integration sau khi rollout runtime. |
| Frontend checks | PASS | ESLint, TypeScript `--noEmit --incremental false`, Vitest 50/50, production build. |
| Hiển thị trực tiếp với token/page state hết hạn | NOT_RUN | Preview 13104 chưa được thay bằng build này; sandbox không truy cập local API. |

## UI Page identity và điều hướng Nghiên cứu — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Sidebar dùng avatar URL từ workspace đã xác minh | PASS (build/typecheck) | `AppShell` hiển thị `page_avatar_url` với fallback chữ cái; không lấy ảnh từ người dùng khác. |
| Shortcut tới Nghiên cứu | PASS (code/build) | Tổng quan dùng `/research`; đường dẫn `/fanpages` còn redirect để tương thích. |
| Quản lý kết nối Page | PASS (code/build) | CTA Xuất bản và thông báo Analytics mở Cài đặt doanh nghiệp, nơi có reconnect Page. |
| Frontend checks | PASS | ESLint, `tsc --noEmit --incremental false`, Vitest 50/50, production build. |
| Preview hiện tại / real API | NOT_RUN | Tab browser có phiên người dùng nhưng đang chạy bundle cũ. Curl từ sandbox tới `13104`/`8001` bị từ chối; không coi đó là bằng chứng service đã tắt, và bản mới chưa được triển khai. |

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
| Page read và publish capabilities tách riêng | PASS (SQLite API fixture) | `test_page_read_verification_does_not_claim_publish_permission`: đọc bài `verified`; quyền đăng `not_tested`; `can_publish=false` cho tới khi có publish thành công sau lần xác minh token. Live Meta chưa chạy |
| Frontend sau thay đổi capability | PASS | Typecheck, ESLint, 50 Vitest tests và `next build` trong worktree riêng; không restart preview hoặc gửi bài thật. |
| API Page activation gate | PASS (SQLite API fixture) | `test_legacy_workspace_requires_page_before_agentic_writes` trả 409 khi workspace chưa có Page |
| Worker/scheduler Page activation gate | PARTIAL | PostgreSQL test thật xác nhận worker claim chỉ thành công với workspace có Page active; Redis/Celery được thử riêng trên instance tạm; browser end-to-end NOT_RUN |
| Nghiên cứu không cần người dùng chọn nhóm | PARTIAL | UI facade workspace; nhóm legacy vẫn là FK persistence/report |
| Page công ty Meta collection | PARTIAL; live NOT_RUN | Existing Meta post/metrics path; bounded posts; không thêm comment bodies |
| Public Page Tier 0 | PARTIAL; live NOT_RUN | Existing facebook-cli pipeline; không chứng minh lịch sử đầy đủ |
| Public Group Tier 0 | PARTIAL | Đọc metadata nhóm public; không đọc GroupFeed/thảo luận; coverage `tier0_group_shell_only`, 0 posts/evidence |
| Comment text / replies | PRIVACY_HOLD | Không tải comment text mới; report bỏ comment text legacy khỏi model context; aggregate count riêng |
| Media download/analysis | NOT_IMPLEMENTED | Có Gemini inline adapter fixture; chưa có asset pipeline hoặc worker routing |
| Qwen / Gemini / DeepSeek routing | PARTIAL | DeepSeek giữ luồng hiện có; Qwen text JSON-mode và Gemini inline media adapters có fixture nhưng chưa nối comment/media pipeline hoặc unified budget; không tự fallback |
| AI budget $2/workspace/day | PARTIAL | PostgreSQL reservation/ledger hiện bao phủ báo cáo Nghiên cứu DeepSeek tự động; chưa áp dụng chung cho các agent, Gemini/Qwen hoặc media |
| Ngân sách API/UI | PASS theo API fixture và frontend lint/unit; browser real NOT_RUN | `GET .../market-research/ai-budget`; `test_research_ai_budget_is_workspace_scoped_and_reports_reserved_cost` |
| Pin bằng chứng cho hướng viết | PASS (API + worker fixture) | `test_market_suggestion_draft_pins_report_observation_and_version`, `test_content_generation_job_persists_cited_draft_and_is_idempotent` |
| Privacy policy record | PARTIAL; chỉ là cấu hình do Owner ghi nhận | Bảng revision bất biến và Owner-only API/UI lưu mục đích, tham chiếu căn cứ, version và thời hạn dự kiến. Không xác minh tính hợp lệ của căn cứ; comments `privacy_hold`, retention `not_enforced`; chưa có deletion ledger/propagation hoặc legal review |
| Privacy policy run snapshot | PASS (SQLite API/worker fixture) | `test_collection_run_pins_policy_snapshot_without_verifying_legal_basis`: run giữ policy revision `PR-1` sau khi source đổi sang `PR-2`; API trả `legal_basis_verified=false`, `not_enforced` và `privacy_hold`. Chỉ kiểm tra provenance |
| Raw research quarantine TTL | PARTIAL | PostgreSQL integration test xác nhận pointer+24h expiry đã commit trước storage `put`; simulated timeout giữ pointer. Object storage thật và purge scheduler end-to-end chưa chạy. |
| Manual comment import privacy hold | PASS (SQLite API fixture) | `tests/test_market_research_api.py` — 12 passed trong lượt mới nhất; endpoint không lưu/trả comment text, giữ metrics và trả count/status. |
| Privacy policy record | PASS (SQLite API fixture; legal basis unverified) | Tests `tests/test_market_research_api.py`: save/reload, immutable revision/idempotency, `legal_basis_verified=false`, `not_enforced`, `privacy_hold`, Editor bị từ chối |

## Gate cấu hình privacy trước thu thập Facebook — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Nguồn Facebook mới | PASS (SQLite/API fixture) | Page công ty, Page công khai và Group công khai bắt đầu ở `needs_privacy_policy`; collector chưa được gọi khi thiếu mục đích/tham chiếu. |
| Worker/group crawl | PASS (SQLite worker fixture) | `test_research_worker_blocks_facebook_fetch_until_policy_fields_are_recorded` xác nhận worker trả `privacy_policy_required`, không gọi collector, không giữ lịch tự chạy và lưu `legal_basis_verified=false` vào kết quả. |
| Manual import | PASS (SQLite/API fixture) | Import Facebook trả 409 `privacy_policy_required` trước khi có cấu hình; sau revision Owner, import tiếp tục qua privacy filter hiện có. |
| Resume lịch | PASS (SQLite/API fixture) | Ghi policy revision đưa nguồn từ `needs_privacy_policy` về `active`; chỉ đặt nguồn/group due nếu lịch Owner đang bật. |
| Chất lượng | PASS | 41 backend focused tests; Ruff; OpenAPI export/check; TypeScript generation; ESLint; `tsc --noEmit --incremental false`; Vitest 50/50; Next production build. |
| Căn cứ pháp lý / deletion / retention | NOT_RUN | `collection_ready` chỉ xác nhận đủ trường text; không xác minh căn cứ, đồng ý hay tuân thủ. `legal_basis_verified` luôn false; retention `not_enforced`, comments `privacy_hold`, chưa có deletion propagation. |
| Live systems | NOT_RUN | Không gọi Facebook, provider AI, PostgreSQL/Redis preview hoặc browser real. Văn bản tham khảo chính thức có hiệu lực từ 01-01-2026; việc áp dụng cho tổ chức cần rà soát riêng. |
| PostgreSQL migration fresh/upgrade | PASS (disposable PG 18.3) | Fresh migration tới `0023_research_privacy_policy_records`; DB thứ hai chạy từ đầu tới `0022` rồi upgrade `0022` → `0023`; `test_postgres_migrations_constraints_vector_and_job_fencing` 1 passed, kiểm tra composite tenant FK. |
| PostgreSQL/Redis integration | PASS at `0022`; PARTIAL for `0023` | Combined focused suite trước đó: 32 passed, fresh migration to `0022`, schema/vector, fencing/claim, Redis queue/cache, dispatch, reservation race và raw-expiry ordering. Migration mới được kiểm tra trên PG tới `0023`, nhưng lượt PG/Redis kết hợp đầy đủ chưa chạy lại sau `0023`. Test services đã dừng sau lượt chạy. |
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
- Latest policy slice (2026-09-30 10:21 Asia/Ho_Chi_Minh): `PYTHONPATH=/private/tmp/page-workspace-python-deps python -m pytest -p no:cacheprovider tests/test_market_research_api.py tests/test_research_privacy.py -q` — 15 passed. Current migration reached `0023` in a disposable PostgreSQL 18.3 cluster; its schema/fencing integration test passed. The cluster was stopped afterward.
- Frontend after privacy-policy UI/API typing: `npm --workspace @agentic/web run typecheck -- --incremental false`, `npm --workspace @agentic/web run lint`, `npm --workspace @agentic/web test` — all passed, 50 Vitest tests.
- Production frontend build passed in the feature worktree. Default sandbox execution could not write `apps/web/.next/trace`; retry in the isolated worktree with filesystem permission completed successfully and did not touch the active preview.
- Updated OpenAPI was exported from current FastAPI app and generated through repository `gen:api` using `openapi-typescript 7.13.0`. No provider, Meta, website crawl or user preview call was made for this slice.
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

## Kiểm tra real-mode bổ sung — 2026-09-30 05:58 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Dọn service worker demo trước khi hiển thị login real-mode | PASS | Playwright external-server trên `http://127.0.0.1:13104`; `removes a stale mock service worker` — 1 passed. Chỉ mở `/login`, đăng ký service worker mock trong browser context cô lập, xác nhận nó được gỡ và trang hiện form login. Không gửi thông tin xác thực, không tạo session hoặc ghi dữ liệu ứng dụng. |
| Frontend typecheck/lint sau cập nhật E2E | PASS | `npm --workspace @agentic/web run typecheck -- --incremental false`; `npm --workspace @agentic/web run lint`; `git diff --check`. |
| Browser E2E khởi chạy server riêng từ worktree | BLOCKED | Next build không ghi được `apps/web/.next/trace` trong worktree managed; một lần chạy trực tiếp Chromium bị macOS bootstrap permission trong sandbox. Không thay build hoặc restart preview đang dùng. |
| Đăng ký/login thật, UI → API → Redis/Celery → PostgreSQL | NOT_RUN | Test real-mode trên chỉ xác nhận login shell và cleanup service worker; không submit form hay gọi API nghiệp vụ. |

Lần chạy đầu phát hiện thêm assertion cũ tìm heading “Đăng nhập” trong khi giao diện hiện dùng “Chào mừng trở lại”; sửa assertion và xác nhận lại PASS. `ERR_ABORTED` phát sinh khi lượt reload của ứng dụng thay thế navigation của Playwright, không phải lỗi xác thực.

## Bảng giá provider — 2026-09-30 06:04 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Giá Gemini exact model | PASS (unit; suite cô lập `9 passed, 2 deselected`) | `gemini-3.8-flash` Standard: $0.75 input/$3.75 output mỗi 1M token; bảng tự từ chối từ 2027-01-01 cho tới khi rate được review lại. |
| Giá Qwen theo region | PASS (unit; suite cô lập `9 passed, 2 deselected`) | `qwen3.8-27b` Singapore International: $0.50 input/$3 output mỗi 1M token; thiếu/sai region fail closed. Tính theo list price, không trừ free quota. |
| Reservation token bound | PASS (unit; suite cô lập `9 passed, 2 deselected`) | Helper yêu cầu explicit input/output token bounds cho Gemini/Qwen; không dùng số ký tự làm đại diện cho token media. Test được chạy từ bản sao trong `/private/tmp` để tránh `tests/conftest.py` import `pgvector` thiếu ở runtime hiện tại. |
| Gemini/Qwen worker routing và unified ledger | NOT_RUN | Chưa có callsite trong worker; hiện ledger pipeline chỉ bao phủ DeepSeek Research report. |
| Provider credentials/live usage | NOT_RUN | Không gọi dịch vụ live, không đọc hay yêu cầu secret trong lượt này. |

Giá lấy từ [Google Gemini model update](https://ai.google.dev/gemini-api/docs/latest-model), [Google Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Alibaba Model Studio pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing) và [Qwen3.8-27B model page](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen3-8-27b). Đây là snapshot giá theo ngày kiểm tra; không phải giá đảm bảo về sau.

## Kiểm thử provenance policy trong source-run — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Policy revision được chụp khi mở run | PASS (SQLite API/worker fixture) | `test_collection_run_pins_policy_snapshot_without_verifying_legal_basis`: run giữ `PR-1` sau khi nguồn được cập nhật thành `PR-2`, đồng thời báo căn cứ chưa xác minh. |
| Không mở comment processing hoặc retention | PASS (contract assertion) | Lịch sử trả `comments_content_status=privacy_hold`, `retention_enforcement_status=not_enforced`; UI hiện hai giới hạn này. |
| OpenAPI / generated TypeScript | PASS | Xuất bằng `scripts/export_openapi.py`; kiểm tra `--check` đạt; sinh bằng `npm run gen:api -- --from ../../packages/contracts/openapi.json`. Generator sắp lại nhiều declaration do export OpenAPI canonical; thay đổi type vẫn là output tự sinh. |
| Backend focused | PASS | `tests/test_market_research_api.py tests/test_research_privacy.py`: 16 passed. |
| Frontend quality | PASS | Typecheck, ESLint, Vitest: 50 passed; `next build` trong worktree riêng đạt. |
| Python lint / whitespace | PASS | Ruff trên file Python đã sửa và `git diff --check`. |
| Database migration / live source run / UI reload | NOT_RUN | Không có migration trong lát cắt này; không chạy Facebook live hoặc pipeline worker thật. |

## Checkpoint research source recovery — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Kết quả nguồn được commit vào research cycle | PASS (SQLite worker fixture) | Worker ghi `source_results_json` ngay sau mỗi nguồn, cùng transaction cập nhật trạng thái nguồn. |
| Worker bị hủy rồi chạy lại | PASS (SQLite worker fixture) | Test hủy worker sau khi nguồn thứ nhất đã commit. Lần chạy lại bỏ qua nguồn thứ nhất, tiếp tục nguồn thứ hai và kết thúc với hai kết quả. |
| Retryable result | PASS (unit fixture) | Kết quả đánh dấu `retryable=true` không được tính là checkpoint hoàn tất; các kết quả khác được giữ để tránh thu thập lại. |
| Policy snapshot | PASS (fixture) | Cùng revision snapshot gắn vào kết quả nguồn và WebCrawlRun; ghi rõ `privacy_hold` và `not_enforced`. |
| Backend focused | PASS | `tests/test_market_research_api.py tests/test_research_privacy.py`: 20 passed; Ruff và `git diff --check` đạt. |
| PostgreSQL/Redis recovery thật | NOT_RUN | Test phục hồi này dùng SQLite fixture; không chứng minh Redis dispatch hoặc PostgreSQL lease recovery. |
| Post/comment cursors, media, public Group discussions | NOT_RUN | Chưa có checkpoint cấp post/comment/reply, xử lý media hoặc quyền Tier 0 để đọc thảo luận nhóm. |

## Đồng bộ metadata Page — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Owner đồng bộ tên/ảnh bằng token đã lưu | PASS (API fixture) | `test_refresh_page_metadata_uses_stored_token_without_touching_brand`: token chỉ materialize ở backend; Meta fixture trả Page identity mới; Company, connection, source Page và avatar được cập nhật. |
| Hồ sơ thương hiệu không bị sửa | PASS (API fixture) | Test lưu `profile_text`/version trước thao tác và xác nhận giữ nguyên sau refresh metadata. |
| Token không lộ qua HTTP response | PASS (API fixture) | Response `WorkspaceOut` không chứa plaintext Page token. |
| Token hết hạn | PASS (API fixture) | `test_metadata_refresh_expired_token_pauses_page_work_but_keeps_workspace`: workspace còn dữ liệu, state thành `needs_reconnect`, lịch được dừng bằng cách bỏ due time trong khi giữ lại lựa chọn bật/tắt của Owner. |
| Auth, permission, contract | PASS | Route dùng `connection:manage`, CSRF và rate limit; OpenAPI được xuất lại từ FastAPI, TypeScript được sinh bằng `openapi-typescript`. |
| Chất lượng code | PASS | Account/market focused pytest sau test mới: 28 passed; frontend typecheck, ESLint, Vitest (50 passed), production build, Ruff và `git diff --check` đạt. |
| Meta live / preview deployment | NOT_RUN | Adapter được fixture; không dùng Page token thật và không thay preview đang chạy. |

## Khôi phục lịch sau reconnect — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Giữ lịch khi Page token mất hiệu lực | PASS (API lifecycle fixture) | `tests/test_account_lifecycle.py -k metadata_refresh`: schedule intent vẫn bật, còn due time bị xóa khi `needs_reconnect`; Page gate tiếp tục chặn chạy. |
| Reconnect đúng Page phục hồi lịch | PASS (API lifecycle fixture) | Test xác minh cùng Page, đặt lại research due time và metrics sync theo interval; group due time theo source. Lịch vốn tắt không tự bật. |
| Chất lượng code | PASS | Ruff và `git diff --check`; adapter Meta là fixture và DB của test là SQLite. |
| PostgreSQL/Redis, scheduler thật, Meta live | NOT_RUN | Chưa chứng minh recovery ở hạ tầng chạy thật; không thay preview. |

## Facebook Group public Tier 0 metadata — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| URL nguồn và lịch | PASS (API fixture) | Chỉ nhận trang chủ `/groups/{id-or-slug}` trên Facebook; nguồn chuyển sang `public_web`, Crawl ngay/lịch sử hoạt động và lịch có thể tắt. Nguồn sai loại bị từ chối; Group không cho đổi sang Meta API. |
| Runner Tier 0 | PASS (Go unit/build) | `go test ./...`; runner gọi `Engine.Group`, yêu cầu privacy công khai và chỉ phát metadata/provenance. Code không gọi `GroupFeed`; không trả description/address/avatar/tabs/join state/member identities/posts. |
| Collector protocol | PASS (fixture) | `tests/test_facebook_cli_collector.py` chạy bản sao cô lập do runtime đang load `tests/conftest.py`; 6 passed. Xác nhận response `partial`, `history_complete=false`, no discussions và private group bị từ chối. |
| Worker persistence | PASS (SQLite API/worker fixture) | Group run lưu metadata/coverage vào `WebCrawlRun`, `status=partial`, 0 evidence, không tạo report; source vẫn active và lịch sau 12 giờ. |
| API/worker test env | PARTIAL | Ba test API/worker đạt với SQLite fixture và shim `pgvector` tạm trong `/private/tmp`; package khai báo còn thiếu trong Python runtime. Đây không phải PostgreSQL/Redis test. |
| Frontend | PASS | ESLint, typecheck và Vitest: 50 passed. UI giải thích chỉ đọc metadata, không đọc thảo luận; lịch có thể bật/tắt. |
| Live public group, database broker, preview | NOT_RUN | Không gọi Facebook, không có bằng chứng live. PostgreSQL/Redis và preview người dùng không bị chạm. |

Lát cắt này không đáp ứng thu thập nội dung Group discussions, bài viết, bình luận, ảnh hoặc video. Tình trạng là metadata-only/partial Tier 0, không phải hoàn tất nghiên cứu nhóm.

## Metadata link/media của owned Page posts — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Attachment/link metadata qua collector | PASS (HTTP fixture) | Metadata có giới hạn, URL đích được làm sạch và host nội bộ bị chặn; binary media và signed media URL không được lưu. |
| Fallback khi field Meta không được hỗ trợ | PASS (HTTP fixture) | Lượt thử lại dùng fields ổn định; bài vẫn được trả và attachment status là `not_returned`. |
| Lưu/API/UI | PASS (code + SQLite/API fixture) | Migration `0024_page_post_media_references` thêm link/attachments/status. API, research observation, Analytics và Research UI có metadata-only state. Chưa thử ORM write/read trên PostgreSQL qua worker. |
| Meta live / media analysis | NOT_RUN | Không dùng Page token thật; không tải ảnh/video và không gọi Gemini. Comment body vẫn `privacy_hold`. |
| Backend test | PASS | `tests/test_meta_client.py tests/test_market_research_api.py`: 57 passed. Runtime thiếu `pgvector`; pytest dùng SQLite fixtures và import shim tạm ngoài repo. |
| PostgreSQL migration | PASS | PostgreSQL 18.3 riêng: fresh upgrade tới `0024`, downgrade về `0023`, rồi upgrade lại; kiểm tra cột/default. Đây không phải API/worker integration test. |
| Frontend quality | PASS | OpenAPI export/type generation, typecheck, lint, Vitest 50 passed, production build. |
| Privacy deletion/retention propagation | NOT_RUN | Chưa chứng minh purge raw/media, cascade xóa provider/cache/index hoặc deletion ledger. |

## Owned Page research pagination — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Checkpoint schema | PASS (SQLite/API fixture) | `ResearchSource` giữ cursor, Page ID, cửa sổ 90 ngày, completion và page count; `ResearchCycle` pin observed-at cho retry. Migration mới `0025_owned_page_research_backfill`. |
| Tiếp tục lịch sử | PASS (fixture) | `tests/test_market_research_api.py -k owned_page`: lượt kế tiếp nhận `history-2`, tiến số trang và dừng khi provider hết cursor. Fixture kết thúc ở bài 89 ngày nên kết quả ghi `provider_history_exhausted_before_90_days`, `window_coverage_complete=false`. |
| Giới hạn và trạng thái lịch | PASS (SQLite/API fixture) | Mỗi lượt giới hạn 100 bài; during backfill 50+50; nguồn chỉ chấp nhận `meta_api`. Owner bật/tắt lịch 12 giờ bằng API hiện có; schedule mặc định vẫn tắt cho Page mới. |
| Chất lượng code | PASS | API/privacy suites: 24 passed; Ruff, whitespace, typecheck, ESLint và Vitest 50 passed. |
| PostgreSQL migration fresh/upgrade | PASS | PostgreSQL 18.3 riêng trên loopback 15435: database mới migrate từ đầu tới `0025`; database thứ hai migrate tới `0024`, sau đó nâng lên `0025`. Import shim `pgvector` chỉ nằm trong `/private/tmp`; không kết nối preview. |
| PostgreSQL integration schema/fencing | PASS | `tests/test_postgres_database_integration.py`: 6 passed, 2 skipped do Redis integration URL không được cấu hình. Test kiểm tra cột cursor/window và timestamp schema 0025. |
| Page thật, Redis worker, UI reload, comments/media/providers | NOT_RUN | Không gọi Meta, không chạy worker thật hoặc browser; comments còn `privacy_hold`, media chưa tải/phân tích. |

## Owner profile context trong Research report — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Chỉ dùng hồ sơ Owner đang áp dụng | PASS (fixture) | `_active_owner_brand_context` yêu cầu `manual_text_v1`, brand profile đã áp dụng và revision hiện tại cùng text/actor; legacy AI profile bị loại. |
| DeepSeek nhận hướng dẫn thương hiệu đúng nguồn | PASS (unit fixture) | `test_research_report_uses_only_applied_owner_profile_and_explicit_market_scope` kiểm tra payload chỉ có hồ sơ user-authored cùng brand/revision ID. |
| Báo cáo/draft giữ revision đã dùng | PASS (API fixture) | `business_profile_context` nằm trong report JSON, coverage và `market_research_context` của campaign draft. |
| Placeholder thị trường không thành audience | PASS (API/unit fixtures) | `Chưa xác định` và `unknown` bị loại; draft audience để rỗng nếu không có industry/region được khai báo rõ. |
| Backend focused | PASS | `tests/test_ai_budget.py tests/test_market_research_api.py`: 33 passed; Ruff và `git diff --check` đạt. Tests API dùng SQLite fixture, không phải PostgreSQL integration. |
| Frontend quality | PASS | TypeScript typecheck với incremental tắt, ESLint và Vitest: 50 passed. Chưa chạy production build cho thay đổi này. |
| DeepSeek/Gemini/Qwen live, browser và PostgreSQL/Redis | NOT_RUN | Không gọi provider, không dùng nguồn/Page thật, không triển khai preview; Gemini/Qwen routing và chi phí dùng chung vẫn chưa được nối. |

## Bộ lọc tiếp xúc cá nhân rõ ràng trong văn bản Facebook — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Bộ lọc pattern trước lưu | PASS (unit/API fixture) | `facebook-contact-patterns-v1` che email, số điện thoại và các cụm địa chỉ nhà được gắn nhãn rõ; áp dụng cho Page công ty, Page công khai Meta API, Page Tier 0 và manual import. |
| Nội dung lưu và provenance | PASS (SQLite/API fixture) | Evidence/version và owned Page post giữ bản đã che; observation ghi phiên bản, loại trường và số lượng đã che, không lưu nguyên giá trị bị thay. |
| Comment và media | BLOCKED / privacy_hold | Comment text vẫn không được thu/lưu/gửi Qwen; media chỉ còn metadata và không gửi Gemini. |
| Phạm vi bộ lọc | PARTIAL | Không nhận diện tên hoặc mọi dạng địa chỉ/PII; metadata ghi `not_anonymization` và `names_not_detected`. Không phải kết luận dữ liệu đã vô danh hoặc tuân thủ luật. |
| Backend focused | PASS | `tests/test_research_privacy.py tests/test_market_research_api.py`: 25 passed. Ruff và `git diff --check` chạy lại trước commit. |
| Live sources/providers and erasure | NOT_RUN | Không có Page/Meta/provider live; chưa triển khai retention/deletion propagation hoặc quy trình pháp lý. |

## Chặn gửi nội dung Facebook chưa rà soát sang nhà cung cấp AI — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Evidence boundary | PASS (SQLite worker fixture) | Owned Page evidence giữ metric/provenance nhưng `text` rỗng và title được thay bằng thông báo khi thiếu trạng thái `approved_for_provider`. |
| Chỉ có Facebook | PASS (unit fixture) | `_make_report` trả `deferred_privacy_review`; test thay factory bằng lỗi nếu provider được gọi, xác nhận không có lời gọi AI. |
| Nguồn trộn | PARTIAL (code path) | Prompt chỉ đạo model dùng metrics từ evidence đang giữ và không suy chủ đề; website snapshot vẫn có thể chạy report. Chưa kiểm thử provider thật. |
| Regression | PASS | `tests/test_market_research_api.py tests/test_research_privacy.py`: 26 passed; Ruff đạt. |
| Mở lại xử lý text Facebook | BLOCKED | Chưa có screening/phê duyệt thực tế để cấp `approved_for_provider`; không có cách bật bằng cách nhập checkbox hoặc policy reference hiện tại. |
| Frontend build | PASS | `npm --workspace @agentic/web run build` hoàn tất; typecheck, ESLint và Vitest 50 tests cũng đạt. |
| Mixed-source và cache replay | PASS | `tests/test_ai_budget.py tests/test_market_research_api.py tests/test_research_privacy.py`: 40 passed; nội dung Facebook bị giữ vắng mặt trong provider payload, cached report có fingerprint evidence/version khác bị defer. |

## Page gate trong Nghiên cứu — 2026-09-30 16:05 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| UI khi Page chưa active | PASS (browser fixture) | Trên `http://127.0.0.1:13106/w/ws_tap_hoa_an/research`, Crawl ngay, lưu nguồn, crawl nguồn và bật thu thập bị disabled; banner chỉ đường tới Cài đặt. Nguồn/báo cáo hiện có vẫn đọc được. Đây là MSW/demo fixture, không phải API thật. |
| Tắt lịch khi Page chưa active | PASS (code path/UI fixture; API test NOT_RUN) | UI để chủ nguồn tắt lịch đang bật; lịch đã tắt không thể bật lại. API cho phép duy nhất `schedule_enabled=false` nếu collector, giới hạn và cấu hình khác giữ nguyên. |
| Crawl/thêm nguồn/bật lịch khi Page chưa active | PASS (code guard; API test NOT_RUN) | Frontend disable CTA và mutation có guard; backend vẫn Page-gated. Test API mới bao phủ `409` cho bật lịch, đổi config, crawl và thêm nguồn nhưng chưa chạy trong lượt này. |
| Dừng theo dõi nguồn | PASS (code review; API test NOT_RUN) | `DELETE /sources/{id}` chỉ soft-disable, giữ bằng chứng và snapshots. UI đổi nhãn thành “Ngừng theo dõi”; đây không phải yêu cầu xóa dữ liệu đã thu thập. |
| Frontend checks | PASS | ESLint, TypeScript, Vitest 50/50 và Next production build trên worktree riêng. |
| Python syntax | PASS | `ast.parse` cho API module và test file. |
| Backend pytest/Ruff | NOT_RUN | Python hiện hành không có `pytest`/FastAPI/SQLAlchemy; `uv` và project virtualenv không có trong checkout/runtime. Lệnh thử `uv run pytest ...` thất bại vì không tìm thấy `uv`. |
| PostgreSQL/Redis, browser real API, provider/live Page | NOT_RUN | Không dịch vụ thật nào được gọi; preview `13104` không bị restart hoặc thay đổi. |

## Page gate cho các thao tác thương hiệu, nội dung và xuất bản — 2026-09-30 16:22 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Hồ sơ và tài liệu | PASS (code + UI tests) | Hồ sơ vẫn xem/sửa nháp được nhưng không áp dụng khi Page chưa active. Upload/reprocess bị khóa; dữ liệu cũ vẫn xem được. |
| Chiến dịch và biên tập | PASS (code + UI tests) | Planning AI, tạo campaign, lưu phiên bản, upload media, review và approval dùng Page gate ở UI và handler. |
| Xuất bản/đối soát mới | PASS (code) | UI từ chối publish và đối soát `outcome_unknown` khi Page chưa active; API publication/reconcile vẫn dùng permission Page-gated hiện có. |
| Hủy lịch chưa bắt đầu | PASS (code; PostgreSQL test authored, NOT_RUN) | Owner có thể hủy lịch đã xếp khi token cần reconnect. Endpoint bỏ Page-gated dependency nhưng kiểm tra membership, quyền Owner, CSRF và trạng thái job/schedule trước khi hủy. |
| Frontend quality | PASS | ESLint, TypeScript, Vitest 52/52, Next production build và `git diff --check`. |
| Backend syntax/integration | PARTIAL | `py_compile` và Ruff đạt. `tests/test_postgres_application_modules.py` kiểm tra cancellation khi trạng thái Page là `needs_reconnect`, nhưng pytest không collect được do Python Anaconda thiếu `pgvector`; chưa xác nhận `POSTGRES_TEST_URL`. |
| Browser/API thật và preview | NOT_RUN | Không dùng API hoặc browser thật; preview `13104` chưa được thay. |

## Page gate ở chi tiết chiến dịch và Analytics — 2026-09-30 16:29 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Chi tiết chiến dịch | PASS (code/build) | Khi Page chưa active, UI khóa lưu brief, tạo bài thủ công/AI, sinh bài theo slot và xuất file; handler có guard và campaign cũ vẫn xem được. |
| Analytics | PASS (code/build) | Đồng bộ Page, nhập metrics, lưu/apply recommendation và ghi outcome bị khóa. Có thể xem dữ liệu cũ; lịch Meta đang bật có nút tắt khi Page disconnected. |
| Lịch Meta qua API | PARTIAL (code; PostgreSQL test authored, BLOCKED) | GET đọc lịch theo tenant mà không cần token active; PATCH cho Owner tắt lịch khi disconnected nhưng chỉ bật với workspace/Page/connection đã active và khớp Page chính. Test PostgreSQL bị chặn lúc collection vì thiếu `pgvector`; database test chưa xác minh. |
| Frontend quality | PASS | ESLint, TypeScript `--noEmit --incremental false`, Vitest 52/52, Next production build, `git diff --check`. |
| Python lint/syntax | PASS | Ruff và `py_compile` đạt cho API/test files liên quan. |
| Backend integration / real browser | NOT_RUN | Python syntax đạt; PostgreSQL/API/browser preview không chạy trong lượt này. |

## Không coi Group Tier 0 metadata là nội dung thu thập thành công — 2026-09-30 16:40 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Trạng thái Group metadata-only | PASS (code change) | Worker giữ `collection_status=partial`, lưu coverage/lần thử và không cập nhật `last_collection_success_at` khi `items_saved=0`. |
| Regression and collector fixtures | PASS (SQLite/fixture only) | `tests/test_market_research_api.py tests/test_facebook_cli_collector.py` — 30 passed với shim `pgvector` tạm ở `/private/tmp`, không được dùng làm bằng chứng cho vector behavior hay PostgreSQL. Regression kiểm tra `last_collection_success_at is None`. |
| Static checks | PASS | Ruff cho `services/worker/research_tasks.py` và test; `py_compile`; `git diff --check`. |
| PostgreSQL integration | BLOCKED | Python hiện hành không có package `pgvector` thật; `POSTGRES_TEST_URL` chưa xác minh. Không chạy test PostgreSQL/Redis bằng shim SQLite. |
| Live Group discussions | NOT_RUN / không hỗ trợ ở Tier 0 hiện tại | Không có bài/bình luận nhóm được thu thập; fixture hay metadata shell không được tính là crawl nội dung nhóm. |

## Purge dữ liệu nghiên cứu theo nguồn — 2026-09-30 17:23 Asia/Ho_Chi_Minh

Commit triển khai: `0d95d9b5704ee6fa37f31ae237d522795a08a304` trên `codex/page-workspaces-research`; `git ls-remote` xác nhận remote ref khớp SHA này.

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Owner-only, tenant lookup, durable job, commit-before-dispatch | PASS (SQLite/API fixture) | `tests/test_market_research_api.py::test_source_purge_is_owner_only_durable_and_idempotent`: request lặp trả cùng job; dispatch thất bại giữ job queued; Editor bị từ chối; source và lịch bị tắt. |
| Xóa raw object/evidence/report và tombstone source | PASS (SQLite/worker fixture) | `tests/test_market_research_api.py::test_source_purge_removes_collected_rows_raw_object_and_tombstones_report`: object fixture bị xóa; evidence/version/observation và report links bị xóa; report giữ tombstone; source được làm sạch metadata và đánh dấu erased. |
| Ngăn brief cũ được áp dụng lại | PASS (SQLite/worker fixture) | Campaign research context bị gỡ; brief revision đang `pending_review` chuyển `invalidated`, changes/note được gỡ. Không thay đổi post/campaign content đã phát hành. |
| Raw put lease và late upload retry | PASS (SQLite/worker fixture) | Test raw upload xác nhận lease được xóa sau put; purge bị trì hoãn khi lease còn hiệu lực. Sau khi purge hoàn tất, mô phỏng object upload muộn và storage delete thất bại; worker phục hồi thêm pending key và đưa job đã xong về queued để scheduler retry. Không phải concurrency test nhiều worker trên PostgreSQL. |
| Backend focused | PASS | `PYTHONPATH=/private/tmp/page-workspace-test-shim pytest -q -p no:cacheprovider tests/test_market_research_api.py tests/test_market_research_sources.py tests/test_facebook_cli_collector.py tests/test_research_privacy.py tests/test_website_entities.py` — 57 passed. Shim chỉ xử lý import dependency còn thiếu; API/worker fixture DB vẫn SQLite. Ruff, OpenAPI `--check`, Python AST parse và `git diff --check` đạt. |
| Migration 0026 trên SQLite | PASS (migration syntax/order only) | Database tạm `/private/tmp/page-workspaces-erasure-migration.db` nâng mới từ base tới head, downgrade từ `0026` về `0025`, nâng lại tới `0026`; `alembic current` xác nhận head. Đây không xác minh PostgreSQL FK/index/locking semantics. |
| Migration 0026 trên PostgreSQL | PASS (PostgreSQL 18.3 disposable) | Trên cụm test riêng `127.0.0.1:15447`, Alembic nâng fresh DB đến `0026`, downgrade `0026` → `0025`, rồi nâng lại đến `0026`; `alembic current` xác nhận head. Cụm dừng sau kiểm tra. Shim `pgvector` chỉ dùng cho import Python, không thay PostgreSQL. Đây không kiểm tra API/worker hoặc concurrency. |
| PostgreSQL schema/job-fencing regression | PASS | `test_postgres_migrations_constraints_vector_and_job_fencing` — 1 passed trên cùng cụm disposable; xác nhận migration head `0026`, các bảng/FK tenant của purge, vector extension và stale-worker fencing. |
| PostgreSQL purge worker | PASS (storage fake) | `test_postgres_research_source_erasure_worker_deletes_raw_and_source_rows` chạy worker với `SessionLocal` trỏ PostgreSQL thật; job hoàn tất, source bị tombstone, evidence/version/observation bị xóa. Object storage là recording fake, nên không chứng minh xóa trên MinIO/S3/local adapter thật. Tổng lượt PostgreSQL mới nhất: 2 passed. |
| Redis/Celery recovery, storage thật, API/browser UI | NOT_RUN | Chưa chạy worker/Beat thật, Redis recovery, object storage, real browser hoặc preview cho source purge. |
| Phạm vi xóa | PARTIAL | Xóa dữ liệu nghiên cứu do ứng dụng quản lý theo source và vô hiệu báo cáo/brief đang chờ. Không xóa bản đã xuất/đăng, post versions/campaign copy đã tạo, provider ngoài, backup ngoài cơ chế này hoặc dữ liệu ngoài ứng dụng; không phải chứng nhận tuân thủ pháp luật. |
