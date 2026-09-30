# Kiểm chứng Page workspace và Nghiên cứu

## Rollout frontend real mode — 2026-09-30 20:32 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Production build của feature branch | PASS | `NEXT_PUBLIC_USE_MOCKS=0`, API origin `http://127.0.0.1:8001`; Next.js 15.5.26 hoàn tất, có route `/research` và compatibility route `/fanpages`. |
| Frontend lint/typecheck/unit | PASS | ESLint đạt; `tsc --noEmit --incremental false` đạt; Vitest `52 passed`. Typecheck thường và build thường trong sandbox vướng ghi cache `.next`/`tsbuildinfo`, chạy lại đúng worktree với quyền build cần thiết. |
| Real browser login view | PASS (read-only smoke) | `tests/e2e/creative-studio-preview.real.spec.ts` — 1 passed qua external server `13104`; chỉ chụp login, không submit. |
| Real API research route | PASS (read-only browser inspection) | In-app browser trên `13104` hiển thị navigation/page “Nghiên cứu”, tab thu thập/phân tích; workspace đang mở yêu cầu Owner kết nối Page trước khi dùng agentic. Không tạo dữ liệu hoặc crawl. |
| Health và release | PASS | `creative-studio-preview.py status`: API, login, font và LaunchAgent đều ready. Release `codex-page-workspaces-research-2acabb13ae48-20260930T132926Z`; release trước được lưu cùng backup plist. |
| End-to-end đăng ký → Page → crawl → báo cáo | NOT_RUN | Smoke hiện chỉ đọc trạng thái; không tạo tài khoản/workspace, gửi Page token, crawl, gọi AI hoặc đăng Facebook. Tab cũ có thể cần refresh để tải JS release mới. |

## PostgreSQL + Redis/Celery integration — 2026-09-30 20:38 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| PostgreSQL, Redis queue/cache riêng | PASS | PostgreSQL 18.3 disposable `127.0.0.1:15559`; Redis 8.6.3 disposable queue `16481` và cache `16482`, cùng bind localhost. Cả ba service đã dừng sau test. |
| Queue/cache TTL | PASS | `test_queue_and_cache_use_distinct_redis_instances_with_ttl` kết nối hai Redis khác nhau và xác nhận key/TTL trên đúng từng instance. |
| Durable job dispatch | PASS | `test_production_dispatcher_places_durable_job_on_isolated_redis_queue` dùng production dispatcher, đối chiếu Celery envelope với job ID đã lưu PostgreSQL. |
| Worker consume → PostgreSQL | PASS | `test_postgres_celery_worker_consumes_committed_research_job` chạy Celery worker trên Redis, claim job PostgreSQL và ghi trạng thái/result cuối. Job không có nguồn, không gọi crawler hay AI. |
| Toàn bộ integration module | PASS | `tests/test_postgres_database_integration.py` — `15 passed`, không skip khi cấu hình đúng ba dịch vụ test. |
| Faults chưa thử | NOT_RUN | Không dừng Redis sau commit trong lúc có job thật, không làm đầy Redis, không kill worker giữa crawl, không chạy Beat hoặc Meta/AI live. |

## Browser real mode: chọn doanh nghiệp và Page gate — 2026-09-30 20:40 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Chọn doanh nghiệp sau đăng nhập | PASS (read-only live UI/API) | In-app browser mở `/` trên `13104`; session thật tải danh sách workspace và hiển thị vai trò cùng trạng thái Page. Không ghi dữ liệu. |
| Bắt buộc xác minh Page trước khi dùng agentic | PASS (read-only live UI/API) | Workspace chưa có Page hiển thị Page ID + Page Access Token form và nút xác minh; Nghiên cứu bị khóa với link Cài đặt. Token không được nhập trong smoke. |
| Bảo vệ token ở giao diện | PARTIAL | Form nói token được gửi tới backend và mã hóa; do không submit nên chưa xác minh network request, response, audit hoặc Meta live. |
| Tạo workspace từ Page qua UI thật | NOT_RUN | Chưa dùng Page ID/token thật hoặc gọi Meta; test PostgreSQL/API trước đó dùng Meta fixture. |
| Tài khoản đăng ký mới qua UI | NOT_RUN | PostgreSQL TestClient/API test xác nhận registration tạo user/session không workspace; browser real signup chưa chạy để tránh tạo thêm account test không được yêu cầu. |

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
| Chống Page token tự cấp membership / race cùng Page | PASS (SQLite fixture + PostgreSQL API) | API smoke tài khoản thứ hai nhận 409, workspace list rỗng; race test đồng bộ hai request sau cùng truy vấn xác nhận chưa có Page và xác nhận kết quả một workspace/Owner, một non-member nhận 409 |
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
| Qwen / Gemini / DeepSeek routing | PARTIAL | DeepSeek giữ luồng hiện có; Qwen text JSON-mode và Gemini inline media adapters có fixture nhưng chưa nối comment/media pipeline; không tự fallback |
| AI budget $2/workspace/day | PARTIAL | PostgreSQL reservation/ledger dùng chung provider đã được kiểm tra trên dữ liệu tổng hợp; worker vẫn chỉ route DeepSeek research report, chưa gọi Gemini/Qwen hoặc media |
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
| Gemini/Qwen worker routing | NOT_RUN | Chưa có callsite worker an toàn cho comments/media; reservation/ledger chung đã được kiểm chứng riêng trong mục “Ngân sách chung ba provider” ở cuối báo cáo. |
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
| PostgreSQL purge worker | PASS (storage fake) | `test_postgres_research_source_erasure_worker_deletes_raw_and_source_rows` chạy worker với `SessionLocal` trỏ PostgreSQL thật; job hoàn tất, source bị tombstone, evidence/version/observation bị xóa. Object storage là recording fake, nên không chứng minh xóa trên MinIO/S3/local adapter thật. Migration/schema/fencing + purge worker: 2 passed. |
| PostgreSQL API + Docling ingestion smoke | PASS (Meta/AI mock; temp storage) | `test_postgres_api_persists_existing_product_modules` — 1 passed trên PostgreSQL 18.3 disposable, chạy trong ingestion virtualenv Docling `2.130.0` cùng 66 model files đã xác minh. Đăng ký trả workspace rỗng; sau xác minh Page, response có đúng tên/Page ID, active state và avatar placeholder. Profile text, nguồn/policy, review/approval, conversion, upload TXT và knowledge được lưu/đọc lại. Ingestion gọi trực tiếp, không qua Redis/Celery; Meta, DeepSeek, embeddings mock/tắt; object storage là thư mục tạm. |
| Redis/Celery recovery, storage thật, API/browser UI | PARTIAL | Dispatcher và một worker Celery thật trên job không có nguồn đã PASS ở 18:15 qua Redis + PostgreSQL disposable; Beat recovery, source crawl thực, object storage production, browser UI và preview cho source purge vẫn NOT_RUN. |
| Phạm vi xóa | PARTIAL | Xóa dữ liệu nghiên cứu do ứng dụng quản lý theo source và vô hiệu báo cáo/brief đang chờ. Không xóa bản đã xuất/đăng, post versions/campaign copy đã tạo, provider ngoài, backup ngoài cơ chế này hoặc dữ liệu ngoài ứng dụng; không phải chứng nhận tuân thủ pháp luật. |

## PostgreSQL + Redis/Celery dispatch — 2026-09-30 18:05 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| PostgreSQL schema, vector extension và lease fencing | PASS | `test_postgres_migrations_constraints_vector_and_job_fencing` chạy trên PostgreSQL 18.3 disposable, database `page_erasure_fresh`, cổng `15447`. `pgvector` shim chỉ phục vụ Python import; database và extension là PostgreSQL thật. |
| Queue/cache tách riêng | PASS | `test_queue_and_cache_use_distinct_redis_instances_with_ttl` ghi/đọc key riêng qua Redis 8.6.3 ở `16389` và `16390`, xác nhận hai URL khác nhau và TTL còn hiệu lực. |
| Hai worker claim cùng durable job | PASS | `test_postgres_competing_workers_only_claim_a_research_job_once`: hai lời gọi claim cạnh tranh trên PostgreSQL; chính xác một thành công, attempts vẫn bằng 1. |
| Redis dispatch hỏng rồi phục hồi | PASS (dispatcher fault injected) | `test_postgres_committed_job_survives_queue_dispatch_failure`: job đã commit vẫn `queued` khi dispatcher trả unavailable, lưu lỗi/attempt, rồi được dispatch lại sau khi lease hết hạn. Phần outage được mô phỏng bằng dispatcher giả; không tắt Redis khác. |
| Production Celery dispatcher → Redis | PASS | `test_production_dispatcher_places_durable_job_on_isolated_redis_queue`: production `job_service.dispatch_research_job` gửi job ID đã commit vào list `agent` của Redis test; test đọc Celery envelope, đối chiếu ID và dọn message/test rows. |
| Celery worker consume → PostgreSQL result | PASS (empty-source research job) | `test_postgres_celery_worker_consumes_committed_research_job`: worker thật nhận task trên Redis `agent`, claim durable job bằng lease/fencing, chạy chu kỳ không có nguồn và lưu `succeeded`/`completed_no_data` vào PostgreSQL. Không gọi crawler/provider; không phải crawl thành công. |
| Kết quả nhóm test | PASS | Sáu test trên chạy cùng lượt bằng `/private/tmp/docling-ingestion-venv/bin/python -m pytest ...` — `6 passed in 2.02s`. Hạ tầng disposable được dừng sau test. |
| Beat recovery, API/browser end-to-end, storage thật và provider live | NOT_RUN | Chưa kiểm tra Celery Beat recovery, UI → API, storage production, Meta, DeepSeek, Gemini hoặc Qwen. |

## Rà metadata văn bản pháp luật và retry raw retention — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Metadata Luật 91/2025/QH15 | PASS (official-source metadata only) | Cổng Thông tin điện tử Chính phủ ghi ngày ban hành 26-06-2025, hiệu lực 01-01-2026: [trang văn bản](https://vanban.chinhphu.vn/?classid=1&docid=214590&pageid=27160&typegroupid=3). Không rà soát toàn bộ điều khoản hoặc đưa kết luận pháp lý. |
| Metadata Nghị định 356/2025/NĐ-CP | PASS (official-source metadata only) | Cổng Chính phủ ghi ngày ban hành 31-12-2025, hiệu lực 01-01-2026: [trang văn bản](https://vanban.chinhphu.vn/?classid=1&docid=216387&orggroupid=2&pageid=27160). Không rà soát toàn bộ điều khoản hoặc đưa kết luận pháp lý. |
| Xóa raw thành công/storage lỗi | PASS (unit fixture) | `tests/test_scheduled_raw_retention.py` xác nhận chỉ object xóa thành công mới bị gỡ DB pointer và được tính vào kết quả; lỗi storage giữ key/expiry để scheduler retry. Không thay thế kiểm thử adapter object storage thật. |
| Retention nội dung chuẩn hóa/media và xóa lan truyền | NOT_RUN / NOT_IMPLEMENTED | Policy retention do Owner nhập vẫn chưa được scheduler thi hành; comment/media tiếp tục privacy hold. Xóa nguồn hiện có phạm vi ứng dụng hạn chế đã nêu ở phần Purge. |
| Kết luận tuân thủ luật | BLOCKED | Chưa có đánh giá pháp lý/tổ chức, xác định căn cứ xử lý/chuyển dữ liệu theo tình huống thật hoặc deletion propagation đầy đủ. Metadata ngày hiệu lực không phải chứng nhận tuân thủ. |

## Ledger cho lời gọi AI interactive — 2026-09-30 18:58 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Campaign planning DeepSeek | PASS (code + test) | Reservation `interactive` trước request; settlement ghi provider/model/tokens/cost; job retry phát lại kết quả đã lưu. Không tính vào hạn mức tự động. Provider live NOT_RUN. |
| Content generate/revise DeepSeek | PASS (code + unit/workflow tests) | Mỗi lời gọi được gắn key theo job/call index; worker thread gọi adapter, DB accounting chạy về event loop; request chưa rõ không gửi lại. Thành công lưu usage vào job và `ContentGenerationRun`, rồi xóa bản sao output trong ledger. Provider live NOT_RUN. |
| Interactive không làm thay đổi cap tự động | PASS (PostgreSQL 18.3 disposable) | Toàn bộ `tests/test_postgres_database_integration.py` — 7 passed, 3 skipped sau fresh migration đến `0026`; assertion xác nhận `ai_usage_budget_days` reserved/spent giữ nguyên sau reserve + settle interactive. Ba test Redis được skip vì URL Redis bị đặt trống; cụm disposable cổng `15557` đã dừng. |
| Regression workflow và API | PASS (fixture) | `tests/test_ai_budget.py tests/test_interactive_ai_accounting.py tests/test_mailguard_pilot.py tests/test_campaign_workflows.py tests/test_market_research_api.py` — 65 passed. Không có provider live call. |
| Pricing / provider availability | PARTIAL | Chỉ model DeepSeek có giá được kiểm tra ở các callsite này; provider/model ngoài bảng bị chặn trước request. Gemini/Qwen chưa được route qua worker. |
| Tổng hợp chi phí interactive cho người dùng | NOT_RUN | API `/ai-budget` hiện chỉ phản ánh hạn mức và usage tự động; chi phí tương tác nằm ở durable job/`ContentGenerationRun`, chưa có tổng hợp UI/API độc lập. |

## Chốt privacy tại persistence Facebook — 2026-09-30 19:08 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Tái lọc text/title trước khi ghi evidence | PASS (SQLite API-worker fixture) | `protect_facebook_evidence` được gọi tại `_persist_evidence` cho Page công ty, Page công khai và Group. Test truyền trực tiếp email, số điện thoại và địa chỉ vào persistence, rồi xác nhận các chuỗi không còn trong `MarketEvidence`. |
| Bình luận/raw payload không lưu | PASS (SQLite API-worker fixture) | Test xác nhận comment text không vào `comments_json`, metadata giữ `privacy_hold`, raw body không gọi storage adapter và không có `raw_object_key`. |
| Ghi rõ giới hạn nhận diện | PASS (unit + persistence fixture) | Metadata vẫn đánh dấu `names_not_detected`, `not_anonymization` và `manual_review_may_be_required`. Không tuyên bố dữ liệu đã ẩn danh hay có căn cứ xử lý. |
| Regression tests | PASS | `tests/test_research_privacy.py tests/test_market_research_api.py` — 33 passed; Ruff, Python compile và `git diff --check` đạt. |
| PostgreSQL persistence boundary | PASS (PostgreSQL 18.3 disposable) | Fresh migration tới `0026_research_source_erasure`; `test_postgres_facebook_evidence_persistence_enforces_privacy_boundary` — 1 passed trên cổng test `15558`. Cụm đã dừng; không dùng database preview. |
| Redis/Celery/browser/Meta/provider live | NOT_RUN | Không phát request ra Facebook/AI provider trong lát cắt này. |
| Nhận diện tên người và retention nội dung chuẩn hóa | NOT_IMPLEMENTED / BLOCKED FOR LEGAL REVIEW | Redactor hiện chỉ bắt một số pattern liên hệ; bình luận/media vẫn privacy hold. `requested_retention_days` chưa được scheduler thi hành. Cần đánh giá pháp lý và thiết kế retention/deletion lan truyền riêng. |

## Allowlist metadata Facebook tại persistence — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Metric/provenance và attachment metadata | PASS (unit + API-worker fixture) | `protect_facebook_evidence` chỉ giữ metric số đã allowlist; nested author/comment/raw fields bị bỏ; provenance locator/counter được lọc; URL mất query/fragment; attachment title/description bị bỏ. `tests/test_research_privacy.py` bao gồm 1.2K, 100+, bare phone-like count và locator giả. |
| PostgreSQL persistence | PASS (PostgreSQL 18.3 disposable) | Fresh migration đến `0026`; `test_postgres_facebook_evidence_persistence_enforces_privacy_boundary` — 1 passed, trong đó metadata đầu vào chứa author/comment/raw fields cố tình lẫn vào metrics. Test cluster đã dừng. |
| Regression backend | PASS (fixtures) | Working tree dựa trên SHA `1c54ee1296d1055c1525e95f1383eba65a738748`; `tests` bỏ `test_ingestion_parsers.py` và test scan-PDF cần Docling — **301 passed, 18 skipped, 1 deselected**; Ruff, `py_compile` và `git diff --check` đạt. |
| Giới hạn | PARTIAL | Đây là allowlist/giảm rò rỉ ở persistence, không phát hiện đầy đủ danh tính hoặc chứng minh ẩn danh/căn cứ pháp lý. Bình luận/media chưa được lưu hay gửi provider; retention nội dung chuẩn hóa chưa được thực thi. |

## Regression backend sau persistence privacy guard — 2026-09-30

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Regression backend trong phạm vi dependency khả dụng | PASS (fixtures) | Trên SHA `158e44e9dbc22395a87d26090092f28090214095`, `tests` bỏ `test_ingestion_parsers.py` và test scan-PDF cần Docling đạt **300 passed, 18 skipped, 1 deselected**. |
| Privacy, Research API và AI budget | PASS (fixtures) | `tests/test_research_privacy.py tests/test_market_research_api.py tests/test_ai_budget.py` đạt **47 passed**. |
| Phạm vi chưa chạy | NOT_RUN | Docling parser runtime, một số PostgreSQL integration cần `POSTGRES_TEST_URL`, Redis/Celery source-run, browser thật, Meta, DeepSeek, Gemini và Qwen live. PostgreSQL persistence guard riêng đã PASS ở mục trước. |
| Kết luận | PARTIAL | Đây không phải nghiệm thu account/Page → Research → provider → UI. Bình luận/media vẫn bị giữ và chưa có khẳng định tuân thủ pháp lý. |

## Ngân sách chung ba provider — 2026-09-30 19:55 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Cùng hạn mức workspace/ngày | PASS (PostgreSQL 18.3 disposable) | Migration fresh đến `0026`; toàn bộ `tests/test_postgres_database_integration.py` — `9 passed, 3 skipped`. Test mới `test_automatic_ai_budget_is_shared_across_deepseek_gemini_and_qwen` xác nhận hai provider đầu ghi reservation vào chung ngày/company; yêu cầu thứ ba bị `deferred_budget`, tổng reservation không vượt cap. |
| Unit pricing/reservation | PASS | `tests/test_ai_budget.py` — `14 passed`; model ID/region chưa được duyệt, pricing hết hạn và thiếu explicit token bound tiếp tục fail closed. |
| Provider call | NOT_RUN | Không gọi DeepSeek/Gemini/Qwen; payload chỉ synthetic. Đây là kiểm tra database reservation, chưa chứng minh Gemini/Qwen có callsite worker. |
| Redis | SKIPPED | Ba test Redis trong module bị skip vì `REDIS_QUEUE_TEST_URL`/`REDIS_URL` chưa được cấu hình cho disposable suite này. |
| Dịch vụ test | DONE | PostgreSQL test cluster riêng ở loopback port `15559` đã dừng. Không thay database/Redis preview. |

## Page gate trong worker claim và scheduler — 2026-09-30 20:23 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Workspace chưa kết nối Page | PASS (PostgreSQL worker integration) | Hai trường hợp của `test_postgres_research_worker_blocks_queued_job_without_active_page` xác nhận claim dừng, job/cycle/step/event lưu mã lỗi tương ứng, không tăng attempts hoặc cấp lease. |
| Page cần kết nối lại | PASS (PostgreSQL worker integration) | Cùng test với trạng thái `needs_reconnect` xác nhận mã `page_needs_reconnect` và không claim job cũ. |
| Scheduler khi Page cần reconnect | PASS (PostgreSQL scheduler integration) | `test_postgres_research_scheduler_does_not_enqueue_when_page_needs_reconnect` xác nhận scheduler không tạo job/cycle, trả `0`; group due bị dừng trong khi due time của source giữ lại. |
| PostgreSQL integration regression | PASS | `tests/test_postgres_database_integration.py` — `12 passed, 3 skipped` sau migration head `0026` trên PostgreSQL 18.3 disposable. Ba bài cần Redis test được skip do URL Redis không cấu hình. |
| Hạn mức thử | PASS | Ruff, `py_compile`, `git diff --check`; cụm test port `15559` đã dừng. Không gọi Meta hoặc provider AI. |
| Worker kind khác, Redis/Celery Beat, reconnect → phục hồi lịch qua UI | NOT_RUN | Lượt này gọi market-research claim và scheduler function trực tiếp trên PostgreSQL; không chạy Redis/Celery Beat hoặc browser. |

## Page token không tự cấp membership — PostgreSQL API — 2026-09-30 20:05 Asia/Ho_Chi_Minh

| Kiểm tra | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| Đăng ký tài khoản thứ hai | PASS (PostgreSQL/TestClient) | API đăng ký trả danh sách workspace rỗng; không tạo Company khi chưa kích hoạt Page. |
| Gửi lại Page đã thuộc workspace khác | PASS (PostgreSQL/TestClient) | `test_postgres_api_persists_existing_product_modules` trả `409 page_already_connected`; tài khoản thứ hai vẫn có workspace list rỗng. Fake Meta client, không gọi Meta live. |
| PostgreSQL integration smoke | PASS | `1 passed`; PostgreSQL 18.3 disposable port `15559`, migration schema đến `0026`; test cluster đã dừng. Ruff, `py_compile`, `git diff --check` đạt. |
| Cạnh tranh đồng thời hai request kích hoạt | PASS (PostgreSQL API) | `test_postgres_concurrent_page_activation_creates_one_workspace` — `1 passed`; barrier test buộc cả hai request đọc “chưa có Page” trước khi insert. Một request tạo workspace; request unique-conflict được ánh xạ về 409, không lỗi ORM và không thêm membership. Đây là race regression có điều phối, không phải stress/load test. |
| Root cause/fix | PASS | Test ban đầu tái hiện `MissingGreenlet` trong IntegrityError handler vì đọc thuộc tính ORM sau rollback. Endpoint lưu `requester_id` trước transaction và dùng lại sau rollback; race test sau fix đạt. |
