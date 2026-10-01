# Tiến độ Page workspace và Nghiên cứu

Ngày bắt đầu: 2026-09-30 (Asia/Ho_Chi_Minh)
Nhánh: `codex/page-workspaces-research`
Base đã kiểm tra: `codex/creative-studio-ui` @ `b769097bfdb3568889d974c6def95bb944559113`

## 2026-10-01 14:43 Asia/Ho_Chi_Minh — Xóa bình luận và ngăn nhập lại

- DONE: Owner có thao tác xóa bình luận và mọi phiên bản/replies đã biết. Xóa ciphertext, metadata nội dung/tương tác; ledger hạn chế giữ tenant/source, hash permalink và ID bình luận để ngăn nhập lại. Không xóa bình luận trên Facebook hoặc lập danh sách người tương tác.
- DONE: Collector public và Meta kiểm tra ledger trong transaction commit dưới source lock/fencing. Lượt mới hoặc nội dung nguồn thay đổi không phục hồi bình luận đã loại. Frontier replies bị dừng; API xóa vẫn dùng được khi Page cần reconnect.
- DONE: Migration bổ sung `0029_comment_suppression`, tenant FK/unique guards, receipt suppressed count riêng. Không sửa migration đã phát hành. Downgrade cố ý chặn để không bỏ ledger và tái nhập dữ liệu.
- PASS: 85 backend tests; 57 frontend tests/6 files; Ruff, lint/typecheck, OpenAPI export/check và generation TypeScript. PostgreSQL18.3/Redis8.6.3 disposable: 10 integration tests, không skip; so sánh fresh/upgrade constraint/index/type và restore thật bằng pg_dump/pg_restore.
- PASS: Browser riêng web13108/API18011 → Redis/Celery → PostgreSQL → xóa → reload → crawl lại. Hai bình luận tổng hợp trước xóa, còn một sau xóa; không nhập lại bình luận bị loại. Test1 passed/5.2s; không gọi provider/Facebook live.
- PASS: CLI export ledger ra file0600 rồi apply lại có inserted0/versions_erased0. Export bị xóa sau kiểm tra. Ledger cần lưu riêng và áp vào database restore trước khi phục vụ; chưa có tích hợp tự động với lịch backup.
- PASS: Production build real API8001/mocks0; code đã commit `c221b01cd38b129f29650fe5edd8608cf8dde0d6`.
- DONE rollout 14:48: Backup `page-comment-suppression-maintenance-20261001T074755Z`, drain0 queued/running, upgrade0028→0029, counts64 bảng lịch sử giữ nguyên. API/worker/ingestion/Beat phục hồi; Page active/lịch owned tắt/key Gemini và encryption giữ nguyên. Frontend real `codex-page-workspaces-research-b96e785ffe5d-20261001T074846Z`, API8001, compiled fixture origin18011 không có trong release.
- PASS: Browser context mới đọc login/register/OpenAPI/readiness, không lỗi script, không đăng nhập hoặc đổi phiên người dùng.
- PASS restore: Backup maintenance mới khôi phục DB/storage riêng, schema0029; checksum bundle, counts64 bảng và hash53 file khớp. Browser login restored NOT_RUN.
- DONE cleanup: Process/tenant/credential fixture và DB/storage restore đã xóa; PG15559/Redis16481/16482 đã dừng. Preview người dùng giữ chạy.
- NOT_RUN: Bình luận Fanpage thật, Gemini analysis, media, tự động xóa dữ liệu provider. Comment candidates tiếp tục privacy_hold/tối đa24giờ. Không thay cấu hình lịch, token, model hoặc quyền người dùng.
- TODO toàn goal: Review/release comment sang Gemini, media pipeline, retention/erasure toàn luồng, owned comment UI, provider live và Research→hướng viết→brief có comment/media citations. Các mục lịch sử phía dưới không thay thế trạng thái này.

## 2026-10-01 02:18 — Giới hạn response Meta và tên worker riêng

- DONE: Code `96a88b29af6c2844936e9830faa567c0eb52cb8b` sửa transport Meta và launcher, không đổi HTTP schema/migration/frontend. Response Graph đọc stream tối đa2 MiB cả wire và sau giải nén; gzip/deflate giải nén có bound, encoding khác bị từ chối. Giữ không redirect/proxy môi trường; deadline toàn request30 giây và read timeout15 giây.
- DONE: 408/5xx/redirect đóng response không đọc body; 4xx vẫn là rejection có mã sạch. Publish timeout/response quá lớn/JSON lỗi vẫn outcome_unknown, không trở thành retry gửi bài. JSON quá sâu, compressed response hỏng và stream gián đoạn không log payload/token.
- DONE: Default/agent và ingestion chạy với hai nodename riêng. Control inspect sau restart nhận đúng hai worker và đúng queue, không còn cảnh báo duplicate nodename ở lượt kiểm tra này.
- PASS: Backend source cuối405 passed/32 skipped/1 deselected,21 dependency warnings; vẫn loại Docling parser module và một scan-PDF runtime test. Ruff, Python3.11 compile, OpenAPI unchanged và whitespace đạt. PostgreSQL/Redis25 tests của commit `3bfd1b8` là kết quả bước trước, không ghi như lượt chạy mới của commit này.
- FIXED/OPS: Lần bootstrap ngay sau bootout bị launchd từ chối đăng ký lại; cả bốn label đã được khôi phục bằng bootstrap sau khi hoàn tất unload. API/web readiness, queue routes, task registry, Page active/lịch tắt và key presence kiểm tra lại đạt. Không đổi database/storage/secret hoặc dừng hạ tầng test/chung.
- NOT_RUN: Không có Meta/provider live call mới, không bật comment decision/lịch hoặc publish. Workflow assessment/review, media, erasure và Gemini analysis vẫn cần hoàn thiện; goal tổng thể còn active.

## 2026-10-01 01:47 — Worker bình luận/replies và vùng xử lý mã hóa

- DONE: Code `3bfd1b8fcb6aab7ac6abb0b05fcaaea960803a6e` bổ sung migration `0028_comment_quarantine`, ba bảng decision/version/receipt và worker `research_comments`. Thay đổi thuộc backend/database/tests; frontend/HTTP schema/agent prompt không đổi.
- DONE/PARTIAL: Worker đọc từng edge tối đa100 bản ghi, tổng500 bản ghi/20 requests/5 phút mỗi batch. Receipt, phiên bản ứng viên và cursor/reply frontier được commit nguyên tử, có tenant/version FK và job fencing. Hết batch giữ checkpoint, trả durable job về queued; batch thành công không tính thành retry. Không gọi provider.
- DONE: Ứng viên chỉ lưu dạng mã hóa bằng khóa dẫn xuất riêng miền từ key token bền vững; không chứa author/profile/avatar hoặc plaintext column. Che pattern liên hệ, mention và tên có nhãn trước quarantine; tên không nhãn và PII khác vẫn có thể còn, nên trạng thái luôn privacy_hold. Không được gọi đây là vô danh/đã rà soát pháp lý.
- DONE: TTL tối đa24 giờ có check SQL PostgreSQL; Beat xóa ciphertext đến hạn hoặc decision đã bị thu hồi/hết hạn, ghi audit chỉ số lượng. Replay không phục hồi ciphertext đã xóa. Purge nguồn hiện có xóa thêm các bảng mới trong phạm vi nguồn được yêu cầu; chưa có cơ chế xóa từng cá nhân/provider/backup đầy đủ.
- DONE: Policy notes không tạo decision. Decision mặc định pending, chỉ dành cho local quarantine; worker kiểm tra decision mới nhất, Owner còn quyền, policy revision, Page/token/source và lease trước read/commit. Decision mới revoked/pending không làm fallback về assessment cũ. Không tạo decision active trên preview.
- PASS: Source cuối: backend380 passed/32 skipped/1 deselected,21 dependency warnings; vẫn bỏ module Docling parser và một scan-PDF runtime test. PostgreSQL18.3/Redis8.6.3 riêng:25 passed, không skip; gồm Celery nhận job thật qua Redis, root/reply fixture, queue dispatch lỗi sau commit, SQL tenant/24h guards, stale worker, concurrent replay và đối chiếu schema fresh/upgrade. Ruff, Python3.11 compile và OpenAPI unchanged check đạt.
- FIXED: Lượt test cleanup đầu phát hiện sai tên field audit (`actor_id`); sửa theo model thành `actor_user_id`, giữ nguyên assertion TTL và chạy lại các suite trên. Không ảnh hưởng dữ liệu preview vì chưa rollout khi test lỗi.
- PASS rollout: Drain0 queued/running, backup `page-comment-quarantine-maintenance-20260930T184019Z`, nâng0027→0028; counts61 bảng cũ giữ nguyên, ba bảng mới trống. API/workers/ingestion/Beat restart đúng label; frontend real13104, Page active, một owned source/lịch tắt và Gemini/encryption key presence giữ nguyên. Task mới có trong registry; control inspect cảnh báo trùng nodename của workers hiện có, cần chuẩn hóa tên vận hành ở bước tiếp theo.
- PASS restore có giới hạn: Backup mới restore vào PG15559/database và storage riêng; checksum bundle/counts61 bảng/hash3 file khớp, schema0028. Chưa mở/login ứng dụng restored.
- TODO: API/UI cho assessment/review ứng viên, dữ liệu bình luận đã screening cho Gemini, media worker và erasure/retention đầy đủ. Meta comments live chưa chạy; decision/quarantine fixture không phải bằng chứng có căn cứ xử lý dữ liệu thật. Gemini live generation vẫn HTTP503 từ hai smoke trước; không gọi lần thứ ba. Goal tổng thể còn active.

## 2026-10-01 00:28 — Phân trang bình luận và checkpoint metadata

- DONE: Code `918ffeb464d61f0f664743af385f2c6515861d92` thêm client đọc từng trang comments/replies bằng cursor. Không đi theo URL next trả về; kiểm tra host/path, ID, cursor đứng yên, response lỗi và record trùng. Không yêu cầu tên/ID/avatar tác giả hoặc nội dung attachment; private/hidden records bị loại. Nội dung quá20.000 ký tự có cờ truncated; wrapper legacy giữ tương thích.
- DONE/PARTIAL: Migration `0027_comment_frontier` và worker đăng ký root frontier trong cùng transaction lưu observation của bài Page sở hữu. FK ghép ràng buộc tenant/source/evidence/observation/version; replay giữ cursor/count cũ và không tạo root trùng. Table chỉ giữ metadata/cursor, không chứa text bình luận hoặc author. Status mặc định privacy_hold, không tự gọi collector hay provider.
- PASS: Native Graph fixture gồm500 root comments qua5 cursor pages, replies riêng, NULL/0, text hơn4.000 ký tự, private/hidden, malformed data/cursor và scope sai. Root exhaustion không được gọi là đã đọc replies.
- PASS: 98 focused tests; regression368 passed/29 skipped/1 deselected,21 dependency warnings, vẫn loại module Docling parser và một scan-PDF runtime test. Ruff/OpenAPI unchanged check đạt; frontend không đổi trong lát cắt này.
- PASS: PostgreSQL/Redis22 tests, không skip. Kiểm tra checkpoint tenant/version, chống replay, worker mất lease và schema fresh/upgrade so sánh type/default/constraint/index. Lần verifier đầu báo khác thứ tự cột id do metadata mixin; sửa so sánh semantic theo tên cột, vẫn giữ thứ tự trong FK/index và mọi assertion định nghĩa schema.
- DONE/PASS rollout: Drain được0 job queued/running, maintenance backup `page-comment-maintenance-20260930T172557Z`, nâng preview0026→0027, counts60 bảng lịch sử giữ nguyên. API/workers/ingestion/Beat restart; frontend13104, JWT, Page token, secret store và Redis preview giữ nguyên. Readiness/key presence đạt.
- PASS restore: Backup mới khôi phục vào PG15559/database/storage riêng, nâng0027; checksum bundle, counts60 bảng và hash3 storage files khớp. Chưa browser/login ứng dụng restored. Backup mới có dữ liệu Page đã kết nối, ngoài Git/quyền hạn chế.
- TODO: Chưa có executor paging bình luận production, bảng comment/version, screening review, receipt/replies progression hoặc phân tích comment/media. Chưa đọc bình luận thật; privacy_hold và Gemini live HTTP503 vẫn được báo đúng. Goal tổng thể còn active.

## 2026-09-30 23:48 — Page thật kết nối thành công và kiểm tra bản sửa cuối

- DONE: Backend `8640d266546ee83e976b225ff26631231ae0ba12` phân biệt token sai Page, token không phải Page, lỗi identity và lỗi đọc bài. Kích hoạt chỉ đọc identity có Page category và `posts?fields=id&limit=1`; không yêu cầu media/metrics hoặc đăng thử. Error/log chỉ có mã số và bước kiểm tra, không chứa token hay raw Meta response.
- PASS live Meta/UI-to-database: Sau khi Owner gửi lại form, preview có một workspace Page active, tên khớp metadata Meta, avatar đã lưu, token mã hóa và một nguồn Page công ty `meta_api`. Lịch nguồn vẫn tắt. Đọc lại bằng implementation xác minh hiện hành đạt; không crawl bài/bình luận/media hoặc publish trong bước này.
- PASS: API/worker đã restart trên source mới; readiness PostgreSQL/schema/queue/cache/storage đạt và Gemini key/model được nạp từ secret store. Key mã hóa Page hiện có được giữ nguyên; không có job queued/running tại thời điểm kiểm tra.
- PASS: Regression backend trên source cuối: 353 passed, 27 skipped, 1 deselected, 21 dependency warnings. Bỏ riêng module Docling parser và một scan-PDF runtime test; không gọi kết quả này là nghiệm thu năm định dạng Docling.
- PASS: PostgreSQL18.3/Redis8.6.3 disposable: 20 passed, không skip, provider/Meta fixture. Ruff và OpenAPI unchanged check đạt; frontend source `2fe9d0a` vẫn là release real đã kiểm tra52 tests/lint/typecheck/build.
- PASS restore rehearsal: Restore final maintenance bundle `page-workspace-maintenance-20260930T154320Z` vào database/storage riêng; checksum bundle, counts55 bảng lịch sử và hash3 file storage khớp, schema0026. Chưa đăng nhập ứng dụng trên bản restore; backup này được tạo trước lần Page activation mới.
- BLOCKED_EXTERNAL: Hai smoke Gemini trước đó chưa tạo được report, lượt thứ hai HTTP503. Không gọi lượt thứ ba hoặc tự đổi provider/model.
- TODO: Pipeline bình luận/replies, media worker, privacy/retention/deletion toàn luồng và nghiệm thu thu thập live. Page activation PASS không đồng nghĩa luồng crawl/phân tích tổng thể đã hoàn thành.

Các mục theo timestamp phía dưới là lịch sử kiểm tra, không thay thế trạng thái mới nhất.

## 2026-09-30 23:15 — Rollout và nghiệm thu tài khoản bằng browser thật

- DONE: Backup maintenance database/storage trước upgrade tại `backups/page-workspace-maintenance-20260930T154320Z`, ngoài Git, quyền hạn chế. Upgrade preview0020→0026, 55 bảng lịch sử giữ nguyên counts; API, worker, ingestion và Beat chuyển sang worktree nhiệm vụ. Preflight restore riêng trước đó đã đạt.
- DONE: API8001/readiness tất cả dependency ready; API/worker nạp Gemini3.8 từ secret store sau restart. Queue/cache `/4`, JWT, tài khoản và storage giữ nguyên. Không gọi lại Gemini sau HTTP503.
- DONE: Frontend real13104 release `codex-page-workspaces-research-2fe9d0a16f6a-20260930T160314Z`; bản trước/plist được giữ. Sửa thiếu nút Đăng xuất ở onboarding và bỏ tự mở workspace duy nhất, để người dùng chọn Page.
- PASS live UI/API/PostgreSQL: Account QA riêng đăng ký → reload → đăng xuất → đăng nhập lại → reload. SQL xác nhận một user, không membership/workspace; active refresh session 1→0→1. Không reset tài khoản người dùng hoặc dùng Page fixture trên preview.
- PASS: Onboarding390px không tràn ngang, nút đăng xuất và Page form nhìn thấy; desktop1440px được chụp riêng. Token để trống trên ảnh.
- PASS: Frontend lint/typecheck, Vitest52/52 và real production build trên source `2fe9d0a16f6ad43e2d7683a10782dccaff7265dc`.
- IN_PROGRESS: Owner thử reconnect Page thật, lỗi `meta_page_permission_missing`. Lỗi cũ gộp identity/posts/field permissions nên chưa đủ xác định nguyên nhân. Thay access check bằng `posts?fields=id&limit=1`, tách identity mismatch/expired/permission/rate/network và thêm numeric diagnostics không raw body/token. 102 focused tests đạt; đang chạy regression và PostgreSQL/Redis trước deploy.
- NOT_RUN/BLOCKED: Page activation live chưa đạt; Gemini live generation HTTP503; comments/media/privacy pipeline chưa hoàn chỉnh. Không tuyên bố pilot toàn bộ hoàn tất.

## 2026-09-30 22:40 — Gemini theo quyết định mới của Owner

- DONE: Thay mọi tác vụ LLM đang hoạt động sang Gemini `gemini-3.8-flash`: planning, content generate/revise, semantic review và research report. DeepSeek/Qwen giữ adapter lịch sử, không fallback.
- DONE: Comment contract trung lập provider, role tổng hợp chuyển Gemini, revalidate privacy và citation; chưa nối worker/persistence bình luận.
- DONE: Ledger dùng usage native gồm thinking; review cũng ghi interactive ledger và pin profile version. Gemini dùng reservation trần token bảo thủ, chưa có countTokens.
- DONE: File Gemini và Page encryption cấu hình bền vững, 0600. Owner đã nạp key Gemini, GET model thật available=yes. Key/token không được in hoặc commit.
- PASS: Regression cuối 328 passed/27 skipped/1 deselected (Docling runtime loại riêng); focused74 passed; PostgreSQL/Redis18 passed; Ruff và OpenAPI check; frontend52 tests/lint/typecheck/build.
- FIXED: Worker test thiếu DATABASE_URL đã dùng SQLite mặc định; thêm assertion setup, chạy lại đúng PostgreSQL thật. Hai lần thử sai tên file test không chạy test; không tính là kết quả PASS.
- BLOCKED_EXTERNAL: Hai smoke Gemini nhỏ chưa thành công, lượt thứ hai HTTP503; giữ reservation, không gọi lặp hoặc đổi provider. Không gửi tài liệu người dùng hoặc Facebook data tới Gemini.
- IN_PROGRESS: Preview backend vẫn schema0020/checkout cũ; cần backup, diễn tập upgrade rồi rollout để API/worker nạp Gemini/Page gate đúng. Preflight không có job queued/running hoặc Page token mã hóa.
- PASS: Backup online vào bundle riêng, restore PG disposable và upgrade0020→0026; 55 bảng lịch sử giữ nguyên số bản ghi, head mới có60 bảng. Chưa thay preview hoặc gọi lại Gemini.
- TODO: Comments/replies checkpoint/persistence, media worker, privacy/retention/deletion toàn luồng, Page/provider live và browser acceptance đầy đủ. Không tuyên bố mục tiêu tổng thể đạt.

## Checklist

- [DONE] Baseline repo, contract, auth, Page connection, Research, worker và collector.
- [DONE] Đăng ký chỉ tạo user; Page đã xác minh mới tạo workspace riêng.
- [DONE] Page identity/avatar fields, unique workspace binding, activation gate và reconnect cùng Page.
- [DONE] UI Nghiên cứu không hỏi tạo/chọn nhóm; backend giữ nhóm legacy nội bộ và facade workspace cho báo cáo.
- [PARTIAL] Page sở hữu lưu bài và chỉ số mà Meta trả. Nội dung bình luận đang `privacy_hold`; chỉ số đếm bình luận vẫn có thể được lưu.
- [PARTIAL] Nguồn Page sở hữu có checkpoint và tự nối các lô tối đa 100 bài/5 phút qua cùng job/cycle; báo cáo chỉ tạo cuối lượt, sau đó lịch 12 giờ tùy Owner. Pipeline PostgreSQL/Redis/Celery đã kiểm thử bằng Meta fixture; live backfill 90 ngày chưa chạy.
- [PARTIAL] Public Facebook Page dùng collector Tier 0. Nhóm hiện xác minh/lưu metadata công khai ở trạng thái `partial`; không lấy bài thảo luận.
- [PARTIAL] Ledger PostgreSQL và mức trần $2/workspace/ngày áp dụng báo cáo Nghiên cứu Gemini; tác vụ tương tác ghi chi phí riêng, review cũng có ledger. API/UI đọc số đã dùng/giữ chỗ/còn lại. Comments/media chưa có pipeline hoặc settlement production.
- [PARTIAL] Worker không gửi comment text cũ/mới cho agent. Chưa có pipeline nhận dạng/redact toàn diện, retention/deletion ledger hoặc quy trình pháp lý; không được coi là chứng nhận tuân thủ.
- [PARTIAL] Nội dung bài Facebook và manual import được che email, số điện thoại và cụm địa chỉ nhà rõ ràng trước khi lưu bằng `facebook-contact-patterns-v1`; bộ lọc không phát hiện tên và không phải cơ chế ẩn danh.
- [PARTIAL] Ranh giới gọi Gemini loại nội dung bài Facebook chưa qua rà soát đầy đủ; report chỉ có Facebook được ghi `deferred_privacy_review`, không gọi provider. Với nguồn web đủ điều kiện, Facebook cùng report chỉ gửi số liệu và nhãn nội dung đang giữ.
- [PARTIAL] Owner có thể ghi nhận mục đích, tham chiếu căn cứ, phiên bản chính sách và thời hạn dự kiến theo từng nguồn; nguồn Facebook mới bị chặn tới khi đủ trường cấu hình. Đây không phải xác minh căn cứ; retention chưa thi hành, comment/media tiếp tục `privacy_hold`.
- [PARTIAL] OpenAPI và TypeScript declarations đã được regenerate. Frontend lint, typecheck, 52 unit tests và production build đạt; real browser đã mở route Nghiên cứu với API thật, nhưng chưa chạy luồng ghi UI-to-worker.
- [PARTIAL] API/worker fixtures và PostgreSQL + Redis/Celery integration đã chạy trên môi trường disposable; Meta Page activation live đạt. Provider generation và worker crawl live chưa đạt/chưa chạy.
- [TODO] Cursor bình luận/replies, media analysis và deletion/retention propagation đầy đủ. Gemini text routing đã triển khai; Qwen không còn được chọn theo quyết định Owner.

### Trạng thái hiện tại — 2026-09-30 20:32 Asia/Ho_Chi_Minh

- DONE: Feature branch `codex/page-workspaces-research` @ `2acabb13ae48975f4f4f66614f81429bddfa919a` được đóng gói real mode và kích hoạt trên `http://127.0.0.1:13104` bằng LaunchAgent mục tiêu; release cũ và plist được giữ để rollback.
- PASS: Script health sau rollout báo LaunchAgent, API `/readyz`, `/login` và font local đều sẵn sàng. Metadata release: `codex-page-workspaces-research-2acabb13ae48-20260930T132926Z`.
- PASS: In-app browser dùng API thật mở route `/w/{workspace}/research`; menu và trang hiển thị “Nghiên cứu”, không yêu cầu tạo/chọn nhóm. Workspace hiện tại chưa có kết nối Page nên giao diện giữ dữ liệu cũ để xem và khóa thu thập, hướng Owner tới cài đặt kết nối.
- PASS: `tests/e2e/creative-studio-preview.real.spec.ts` — `1 passed`; chỉ mở/chụp màn hình đăng nhập, không nhập tài khoản. Chromium cần quyền runtime macOS bên ngoài sandbox; lần chạy có quyền đọc browser runtime đạt.
- PASS: Frontend ESLint, `tsc --noEmit --incremental false`, Vitest `52/52`, Next production build.
- LIMITATION: Tab cũ còn giữ bundle trong bộ nhớ; refresh/reopen mới tải release hiện tại. Không có Page reconnect, crawl, provider, publish hoặc thao tác ghi nào được thực hiện trong smoke browser.

### 2026-09-30 20:40 Asia/Ho_Chi_Minh — Browser thật kiểm tra chọn doanh nghiệp và Page gate

- PASS: In-app browser trên frontend real mode mở `/` bằng phiên đã đăng nhập và gọi API phiên thật; màn hình liệt kê workspace hiện có, vai trò Owner và trạng thái chưa kết nối Page.
- PASS: Form kết nối hiện đúng Page ID + Page Access Token, giải thích xác minh chỉ đọc và mã hóa backend. Chỉ quan sát; không nhập hoặc gửi token, không tạo Page workspace.
- PASS: Nghiên cứu vẫn ở trạng thái gate; thao tác thêm Page là bắt buộc trước khi agentic được mở cho workspace.
- NOT_RUN: Đăng ký tài khoản thật từ UI, gửi Page token thật, Meta verification live, tạo workspace từ Page và truy cập sau reload chưa thực hiện trong browser.

### 2026-09-30 20:38 Asia/Ho_Chi_Minh — PostgreSQL + Redis/Celery tích hợp cùng lúc

- PASS: Toàn `tests/test_postgres_database_integration.py` — `15 passed`, không skip, trên PostgreSQL 18.3 và hai Redis 8.6.3 disposable tách biệt (`16481` queue, `16482` cache).
- PASS: Các test Redis đã chạy thật: queue/cache có TTL riêng; production dispatcher ghi job đã commit vào Celery queue; worker nhận job, claim durable record và lưu kết quả về PostgreSQL.
- PASS: Worker test xử lý job nghiên cứu không có nguồn thành `completed_no_data`; đây không phải bằng chứng crawl website/Facebook hoặc gọi model.
- DONE: Dừng đúng PostgreSQL cổng `15559` và Redis test `16481/16482`; xác nhận các cổng test không còn listener. Không chạm Redis `16381/16382`, preview queue/cache, API hoặc frontend.
- NOT_RUN: Redis process outage thật giữa commit/dispatch, Redis đầy, worker chết/mất lease khi đang crawl, Celery Beat scheduler, Meta/provider live và browser ghi dữ liệu.

### 2026-09-30 — Rà nguồn pháp luật và retry xóa raw quarantine

- DONE: Đối chiếu metadata và ngày hiệu lực trên Cổng Thông tin điện tử Chính phủ/Công báo cho Luật 91/2025/QH15 và Nghị định 356/2025/NĐ-CP. Đây chỉ là xác minh nguồn và metadata văn bản, không phải phân tích pháp lý hoặc kết luận tuân thủ.
- DONE: Làm rõ retention: raw payload có lịch xóa kỹ thuật sau tối đa 24 giờ; thời hạn policy nhập theo nguồn cho dữ liệu chuẩn hóa chưa được thi hành. Comments vẫn `privacy_hold`; media pipeline chưa có.
- DONE: Cleanup raw chỉ đếm object storage xóa thành công; lỗi storage giữ DB pointer/expiry để scheduler retry. Unit regression và Ruff đạt.
- DONE: Nguồn chính thức và giới hạn của lần kiểm tra pháp luật được ghi trong runbook/verification.
- TODO: Thực thi retention cho dữ liệu chuẩn hóa/media và xóa lan truyền; cần thiết kế giữ tombstone, report provenance và xử lý bản sao ngoài ứng dụng.
- BLOCKED: Chưa có rà soát pháp lý/tổ chức đủ để bật xử lý comment/media hoặc gửi chúng tới provider ngoài Việt Nam.

### 2026-09-30 15:28 Asia/Ho_Chi_Minh — Gate cấu hình privacy trước thu thập Facebook

- DONE: Nguồn Page công ty, Page công khai và Group công khai mới khởi tạo `needs_privacy_policy`; worker kiểm tra mục đích/tham chiếu trước collector, nên gọi API/worker trực tiếp cũng không bỏ qua gate.
- DONE: Manual import Facebook bị từ chối khi thiếu hai trường. Lưu revision đủ trường đưa nguồn về active theo lịch Owner chọn; gửi lại cùng revision là idempotent.
- DONE: API/UI phân biệt `collection_ready` (đủ trường cấu hình) với `legal_basis_verified=false`. Cấu hình không được thể hiện như xác minh pháp lý hay đồng ý; comments tiếp tục `privacy_hold`, media chưa xử lý và retention tiếp tục `not_enforced`.
- PASS: `tests/test_market_research_api.py tests/test_ai_budget.py tests/test_research_privacy.py` — 41 passed; Ruff — all checks passed; TypeScript `tsc --noEmit --incremental false` — exit 0; `git diff --check` — đạt.
- PASS: OpenAPI xuất lại và `scripts/export_openapi.py --check` đạt; TypeScript declarations sinh bằng `npm --workspace @agentic/web run gen:api -- --from packages/contracts/openapi.json`.
- PASS: Frontend ESLint, typecheck (`tsc --noEmit --incremental false`), Vitest 50/50 và production build đạt.
- LIMIT: Test phần này dùng SQLite/API worker fixtures; không phải PostgreSQL/Redis, browser real hoặc live Meta/provider.
- NOT_RUN: Không xác minh căn cứ pháp lý, không bật comment/media, không chạy Facebook live, Meta/DeepSeek/Gemini/Qwen live, PostgreSQL/Redis worker integration hoặc browser real trong lát cắt này.

## Bằng chứng ban đầu

- Checkout triển khai là managed worktree riêng; checkout shared `/Users/lethanh/agent` đang có nhiều staged/unstaged changes và không được chỉnh.
- Preview hiện tại dùng worktree `creative-studio-ui`; không dùng checkout đó để triển khai.
- Alembic head trong source là `0020_facebook_cli_public_collector.py`.
- `POST /auth/register` hiện tạo đồng thời user, company, owner membership và brand; biểu mẫu yêu cầu tên workspace.
- `MetaPageConnection` hiện có unique `(company_id, page_id)` nhưng chưa có binding toàn hệ thống và chưa lưu avatar.
- Nguồn nghiên cứu vẫn gắn `group_id`; giao diện có tab Fanpage/nguồn/báo cáo và form nhóm.
- `facebook-cli` `v0.3.0` Tier 0 không phân trang timeline lịch sử; Group shell metadata có thể đọc không đăng nhập nhưng không dùng để tuyên bố thu thập discussions; public Page collector hiện lưu `comments=[]` và runner chưa đưa media ra schema.
- Provider AI hiện có adapter DeepSeek; chưa có ledger ngân sách tự động.
- Không kiểm tra/đọc giá trị API key, Page token, cookie hoặc DSN trong quá trình baseline.

## Tiến độ triển khai — 2026-09-30

- DONE: `POST /auth/register` giữ user/session nhưng không tạo Company, Brand hay Membership; form không hỏi tên workspace.
- DONE: `POST /workspaces/from-page` xác minh `/me` có ID khớp Page ID, yêu cầu một read-only page-post call, rồi tạo Company, Owner, Brand trống, encrypted connection, nhóm Research nội bộ và owned-Page source trong transaction.
- DONE: Page ID được unique toàn workspace. Token Page không tự tạo membership; workspace hiện có chỉ trả cho member đã được cấp quyền.
- DONE: Owner reconnect qua `PATCH /workspaces/{id}/page-connection`; chỉ chấp nhận đúng Page cũ. UI đặt luồng này trong Cài đặt doanh nghiệp.
- DONE: API permissions và worker claims chặn tác vụ ghi/AI/research/publish nếu Page chưa active; scheduler bỏ qua workspace cần reconnect.
- DONE: Research source có thể tạo không truyền group ID; Nghiên cứu tự chọn nhóm nội bộ cho dữ liệu legacy. UI gộp public Page đối thủ/tin tức và giải thích giới hạn Group Tier 0.
- DONE: Không lấy text bình luận mới cho đến khi có điều kiện xử lý phù hợp; report bỏ qua comment text legacy, trả coverage `privacy_hold`.
- TODO: Playwright thật, nối Qwen/Gemini vào comment/media pipeline, privacy/retention/deletion và mở rộng ledger cho mọi AI tự động.
- BLOCKED: Không có căn cứ trong repo cho phép kết luận việc xử lý dữ liệu cá nhân đã đáp ứng đầy đủ luật; cần đánh giá tổ chức/pháp lý và triển khai retention/erasure trước khi mở comment/media processing.

### 2026-09-30 14:24 Asia/Ho_Chi_Minh — Redaction giới hạn cho văn bản Facebook

- DONE: Page doanh nghiệp, Page công khai qua Meta API, Page Tier 0 và manual import đều áp dụng cùng bộ lọc `facebook-contact-patterns-v1` trước khi ghi evidence/version; Page doanh nghiệp cũng ghi nội dung đã lọc vào bản Page post.
- DONE: Observation lưu số lượng trường đã che và giới hạn bộ lọc; không lưu giá trị gốc bị thay thế. Bình luận tiếp tục `privacy_hold`.
- PASS: `tests/test_research_privacy.py tests/test_market_research_api.py` — 25 passed; regression kiểm tra email, điện thoại, cụm “địa chỉ nhà riêng” không còn trong nội dung Page đã lưu, đồng thời giữ ngày ISO và số tiền không giống số điện thoại.
- PARTIAL: Bộ lọc không nhận diện tên, không bao phủ hết cách viết địa chỉ hoặc dữ liệu cá nhân; chỉ xử lý rõ các mẫu đã kiểm tra, không được mô tả là ẩn danh hoặc chứng nhận tuân thủ.
- NOT_RUN: Meta live, Qwen/Gemini/DeepSeek live, browser real, deletion/retention propagation.

### 2026-09-30 14:32 Asia/Ho_Chi_Minh — Giữ nội dung Facebook khỏi provider khi còn privacy hold

- DONE: `_evidence_for_report` kiểm tra loại nguồn và trạng thái privacy; Page công ty, Page công khai/nhập tay chưa có `approved_for_provider` chỉ truyền số liệu, version/observation ID và nhãn nội dung đang giữ, không truyền tiêu đề/nội dung gốc.
- DONE: Nếu chỉ có evidence Facebook đang chờ rà soát và không có snapshot website, DeepSeek không được gọi; report ghi `deferred_privacy_review` và coverage rõ số bài bị giữ. Report hỗn hợp nhắc model chỉ dùng metrics từ evidence bị giữ.
- PASS: `tests/test_market_research_api.py tests/test_research_privacy.py` — 26 passed; kiểm tra bài Page không tới provider và Facebook-only report không gọi model.
- PARTIAL: Không có workflow/phê duyệt rà soát hoàn chỉnh để chuyển nội dung thành `approved_for_provider`; vì vậy Facebook-only AI reports hiện bị defer.
- NOT_RUN: Provider live, Meta live, browser real, deletion/retention propagation.

### 2026-09-30 14:47 Asia/Ho_Chi_Minh — Kiểm tra production build

- PASS: `npm --workspace @agentic/web run build` hoàn tất; route build chứa Fanpage/Nghiên cứu và các màn hình chính.
- PASS: `git diff --check`; frontend typecheck, lint và Vitest 50 tests đạt trên cùng thay đổi.
- NOT_RUN: Không triển khai preview và không gọi provider/Meta live.

### 2026-09-30 14:53 Asia/Ho_Chi_Minh — Ràng buộc report trộn nguồn và kết quả cache cũ

- DONE: Report hoàn tất giờ lưu `privacy_coverage`, để UI hiện đúng số bài Facebook đang bị giữ.
- DONE: Report trộn Facebook + website chỉ gửi nội dung website đủ điều kiện và số liệu Facebook; cache được ràng buộc bằng fingerprint của evidence/version/trạng thái Facebook nên không phát lại report thuộc tập bằng chứng khác.
- PASS: `tests/test_ai_budget.py tests/test_market_research_api.py tests/test_research_privacy.py` — 40 passed; regression kiểm tra payload trộn nguồn và cache có fingerprint lệch. Ruff và `git diff --check` đạt.
- BLOCKED: Không tự chuyển text Facebook sang provider; chưa có bước rà soát/ra quyết định đủ tin cậy.

### 2026-09-30 10:21 Asia/Ho_Chi_Minh — Ghi nhận policy theo nguồn

- DONE: Thêm bảng revision bất biến `research_privacy_policy_revisions` và migration `0023_research_privacy_policy_records`, tenant FK ghép từ `(company_id, source_id)` về nguồn.
- DONE: Owner dùng `GET/PUT .../sources/{source_id}/privacy-policy` để đọc/lưu mục đích, tham chiếu hồ sơ căn cứ, policy version và thời hạn dự kiến 1–365 ngày. Lặp lại cùng nội dung không tạo revision thừa; thay đổi tạo revision mới; audit log chỉ ghi version và số ngày, không ghi nội dung mục đích/căn cứ.
- DONE: Tab Nghiên cứu có form cho Owner. Response luôn ghi `retention_enforcement_status=not_enforced` và `comments_content_status=privacy_hold`; form giải thích rõ rằng việc nhập cấu hình không phải chứng nhận pháp lý hoặc quyền gửi bình luận/media tới AI.
- PASS: `tests/test_market_research_api.py tests/test_research_privacy.py` — 15 passed; kiểm tra lưu/reload, revision idempotency, status giữ privacy hold và Editor bị từ chối.
- PASS: PostgreSQL 18.3 disposable cluster: migration fresh tới `0023_research_privacy_policy_records`, đồng thời tạo DB khác ở `0022` rồi upgrade lên `0023`; kiểm tra FK/schema qua `test_postgres_migrations_constraints_vector_and_job_fencing` — 1 passed. Cluster đã dừng.
- PASS: Frontend typecheck, ESLint và Vitest — 50 passed; OpenAPI lấy từ ứng dụng Python và TypeScript sinh bằng script `gen:api`.
- PASS: Production build Next.js trong worktree riêng hoàn tất; preview người dùng không bị thay.
- NOT_RUN: Lịch sử policy chưa có endpoint xem riêng; source-run chưa pin policy revision; retention dữ liệu chuẩn hóa và xóa lan truyền chưa được thi hành; chưa có legal review.
- BLOCKED: Không cho phép xử lý comment text hoặc media từ bản ghi này. Cần quy trình retention/erasure, xác định căn cứ/mục đích ở cấp tổ chức và xem xét chuyển dữ liệu tới provider trước khi mở pipeline.

### 2026-09-30 01:28 Asia/Ho_Chi_Minh — Kiểm thử và rà contract

- DONE: backend regression suite chạy cùng nhau: 71 passed, 6 skipped, 1 test Docling được loại riêng vì runtime/model không sẵn có.
- DONE: sau khi thêm test worker, lượt backend regression cuối đạt 75 passed, 6 skipped, 1 test Docling được loại riêng vì runtime/model không sẵn có.
- DONE: nhóm regression backend foundation/campaign/brand/analytics chạy với fixture parser được gắn nhãn; PostgreSQL integration được skip vì chưa cấu hình `POSTGRES_TEST_URL`.
- DONE: `npm run gen:api -- --from /private/tmp/page-workspaces-openapi.json`; spec được xuất từ ứng dụng hiện tại, không đọc secret.
- DONE: frontend `npm run lint`, `npm run typecheck -- --incremental false`, `npm test`, `npm run build`.
- DONE: Ruff `ruff check --no-cache` trên toàn bộ file Python thay đổi.
- NOT_RUN: trình duyệt thật, migration trên PostgreSQL, Redis/Celery integration, Meta live, DeepSeek/Gemini/Qwen live. Build chỉ kiểm tra artifacts trong worktree; không thay preview.
- BLOCKED: chạy test Docling thật do worker thiếu dependency/model runtime trong môi trường hiện tại.
- Vận hành: đã báo người dùng rằng đầu ra chẩn đoán trước đó vô tình chứa chuỗi kết nối DB; giá trị không được lưu trong repo/docs. Xoay vòng credential DB trong cửa sổ vận hành an toàn trước khi rollout tiếp theo.

### 2026-09-30 03:47 Asia/Ho_Chi_Minh — Cập nhật fixture Page và browser E2E

- DONE: TypeScript workspace fixture có Page ID, avatar nullable và trạng thái kết nối; demo doanh nghiệp chính ở trạng thái Page đã xác minh, workspace rỗng vẫn `connection_required`.
- DONE: E2E đăng nhập chọn doanh nghiệp qua nút hiện hành “Mở không gian làm việc”, bỏ giả định nút cũ “Tiếp tục tới tài liệu”. Test tab Nghiên cứu dùng nhãn “Phân tích & hướng viết” và xác nhận legacy route `/fanpages` chuyển tiếp sang `/research`.
- PASS: frontend lint; typecheck với `--incremental false`; unit tests 50/50.
- PASS (fixture/MSW): Playwright desktop 26 passed, 1 skipped; mobile 26 passed, 1 skipped. Test chụp ảnh UI được skip có chủ đích khi không đặt thư mục screenshot. E2E server build standalone ở cổng test `13107` trước mỗi lượt.
- NOT_RUN: các E2E trên không gọi API thật, PostgreSQL/Redis, DeepSeek, Gemini, Qwen hoặc Meta; không phải bằng chứng Page onboarding thật hoặc dữ liệu Research live.

### 2026-09-30 01:38 Asia/Ho_Chi_Minh — Commit và push

- DONE: commit `d2ad5dddf7ef4055a1941d69c32a67d5d93ecf4a` được push lên `codex/page-workspaces-research`.
- DONE: `git ls-remote` xác nhận SHA trên origin khớp commit vừa push.
- NOT_RUN: chưa rollout frontend/backend lên preview; cần chạy migration và nghiệm thu PostgreSQL/Redis/browser trước khi thay dịch vụ đang dùng.

### 2026-09-30 01:47 Asia/Ho_Chi_Minh — PostgreSQL/Redis thật trong môi trường tạm

- DONE: PostgreSQL 18.3 cluster tạm tại `/private/tmp` chạy fresh migration từ đầu đến `0021_page_workspace_identity`.
- DONE: upgrade từ revision `0020` trên database synthetic: Page đơn được map sang `needs_reconnect`; company nhiều Page, Page trùng giữa workspace và workspace không có Page không bị map.
- DONE: PostgreSQL/Redis integration suite đạt `6 passed`; test production Celery dispatcher đặt đúng job ID synthetic vào queue Redis `agent`, sau đó dọn message và bản ghi test.
- DONE: cập nhật test PostgreSQL để kiểm tra schema head `0021`, index Page duy nhất, dispatcher thật và worker claim fixture dùng Page active theo gate sản phẩm.
- NOT_RUN: chưa chạy worker crawl, Meta live hoặc UI real browser. Không thử dispatch task nào có thể gọi crawl/provider.
- TODO: dùng một môi trường test Redis/worker chuyên dụng cho recovery khi broker thực sự ngắt và chạy browser end-to-end sau khi migration được áp dụng ở preview riêng.

### 2026-09-30 01:53 Asia/Ho_Chi_Minh — Kiểm tra dispatch Celery thật

- DONE: mở rộng `tests/test_postgres_database_integration.py` để dispatch research job đã commit qua production Celery app tới Redis test; test giải mã message xác nhận job ID, sau đó dọn message và dữ liệu test.
- PASS: cả sáu test trong file PostgreSQL/Redis chạy trên PostgreSQL 18.3 và hai Redis test riêng.
- NOT_RUN: không có Celery worker chạy job crawl; live Meta/provider và browser vẫn chưa nghiệm thu.

### 2026-09-30 01:54 Asia/Ho_Chi_Minh — Push kiểm chứng PostgreSQL/Redis

- DONE: commit `6bb99106d689444cfb1b2acc6e5ea467a8e553cc` gồm integration test PostgreSQL/Redis và cập nhật runbook/verification đã push.
- DONE: SHA trên origin được xác minh khớp commit này.

### 2026-09-30 02:21 Asia/Ho_Chi_Minh — Ledger ngân sách AI tự động

- DONE: Thêm migration `0022_ai_usage_budget` với bộ đếm ngân sách ngày theo workspace và ledger idempotent; tiền lưu bằng integer micro-USD, có usage, model, pricing version, trạng thái uncertain và structured result để replay.
- DONE: Reservation khóa hàng workspace trước khi kiểm tra `spent + reserved`, cap cứng 2.000.000 micro-USD/ngày theo Asia/Ho_Chi_Minh; không gọi nếu ngân sách thiếu hoặc model chưa có giá trong bảng.
- DONE: Tích hợp báo cáo Nghiên cứu tự động với DeepSeek. Một research cycle chỉ có một request key; provider timeout/exception giữ reservation và không tự gửi lại. Kết quả thành công được lưu trong ledger để worker replay mà không gọi model lần hai.
- DONE: Giá DeepSeek dùng mức peak/cache-miss đã ghi phiên bản; reservation tính trường hợp tối đa một lần repair. Provider/model chưa có giá đã xác minh bị từ chối trước khi gửi.
- PASS: Unit pricing and worker guard `tests/test_ai_budget.py`: 9 passed, including no provider call for deferred/uncertain reservations.
- PASS: PostgreSQL 18.3 migration fresh đến `0022`, cùng đường upgrade `0021` → `0022` trên database tạm riêng.
- PASS: PostgreSQL/Redis integration `tests/test_postgres_database_integration.py tests/test_ai_budget.py`: 16 passed; gồm race 6 reservations chỉ cấp 2 request trong hạn mức 40.000 micro-USD, replay và settlement.
- PASS: Regression không cần Docling runtime: 236 passed, 14 skipped, 1 deselected.
- BLOCKED: Full suite phát hiện 11 test parser hiện có không khởi tạo được Docling subprocess trong virtualenv API hiện tại; lỗi độc lập với ledger và cần worker Docling runtime/model để nghiệm thu.
- NOT_RUN: Không gọi DeepSeek/Gemini/Qwen live; không chạy crawl worker hoặc Meta live; không rollout preview.
- PARTIAL: Hiện chỉ báo cáo Nghiên cứu tự động DeepSeek dùng ledger. Qwen/Gemini adapters fixture-only, chưa có media/comment pipeline và chưa có ngân sách chung cho các tác vụ tự động khác.
- DONE: Commit ngân sách `2b3cb9283e9f512b9aa288ecf48af4437cde9a1f` đã push; SHA trên origin được đối chiếu khớp.

### 2026-09-30 02:35 Asia/Ho_Chi_Minh — Trạng thái ngân sách trong API và Nghiên cứu

- DONE: Thêm `GET /api/v1/workspaces/{workspace_id}/market-research/ai-budget` để trả hạn mức, đã dùng, đang giữ chỗ, còn lại, số lượt chưa quyết toán và số báo cáo chờ do giới hạn/cấu hình. Ngày/ngày reset tính theo `Asia/Ho_Chi_Minh`; endpoint kiểm tra membership workspace.
- DONE: Trang Nghiên cứu hiển thị mức dùng ngân sách tự động, đơn vị USD, thời điểm reset và thông báo báo cáo/lượt gọi đang chờ. Trạng thái làm mới mỗi 15 giây; chưa có chức năng tự lên lịch chạy lại các báo cáo bị hoãn.
- PASS: `tests/test_market_research_api.py -k research_ai_budget` đạt 1 passed, kiểm tra số dư mặc định, reservation/spent, unsettled request và report `deferred_budget`.
- PASS: `tests/test_market_research_api.py tests/test_ai_budget.py` đạt 18 passed trước khi thêm assertion cho report pending; targeted budget API test đạt lại sau thay đổi.
- PASS: OpenAPI export và `--check` khớp. TypeScript declarations được sinh lại bằng `openapi-typescript 7.13.0`.
- PASS: Frontend lint và unit tests: lint đạt, 50 tests passed.
- FAIL (contract mismatch): Typecheck toàn app lỗi ở nhiều màn hình do `@agentic/contracts` không export các kiểu/field frontend đã dùng (`CampaignContentSlot`, `content_plan`, `document_ids`, `MediaAsset`, ...). Typecheck không nêu lỗi mới trong trang Nghiên cứu; toàn app chưa thể xác nhận PASS.
- NOT_RUN: production build, browser thật, provider live, migration/runtime rollout. Không thay preview hoặc cấu hình key/provider.

### 2026-09-30 02:50 Asia/Ho_Chi_Minh — Ghim bằng chứng khi chọn hướng viết

- DONE: Campaign tạo từ báo cáo giữ chính xác `report_id`, `evidence_version_id`, `observation_id`, content hash, thời điểm quan sát và metrics; snapshot website chỉ được nhận nếu đã gắn với report đó.
- DONE: Worker dùng version/observation được ghim và kiểm tra tenant, report cùng source còn active. Nếu report cũ thiếu pin hoặc nguồn đã mất/tắt, job dừng với `market_research_context_stale`, không thay bằng dữ liệu mới nhất.
- DONE: Bỏ comment text khỏi Content Agent context. Mask email/số điện thoại không còn được coi là đủ để cho phép gửi bình luận; trạng thái vẫn `privacy_hold`.
- PASS: `tests/test_campaign_workflows.py -k content_generation_job_persists_cited_draft_and_is_idempotent` xác nhận báo cáo cũ vẫn dùng text/metrics cũ dù evidence hiện tại đã đổi, và comment PII không đi vào model input.
- PASS: `tests/test_market_research_api.py` đạt 10 passed, gồm endpoint ghim IDs/metrics vào campaign draft; `tests/test_ai_budget.py` đạt 9 passed.
- PASS: OpenAPI cập nhật cho evidence version/observation; TypeScript declaration sinh bằng `openapi-typescript 7.13.0`.
- NOT_RUN: PostgreSQL migration/browser real/provider live; không dùng website hoặc Facebook live.

### 2026-09-30 03:00 Asia/Ho_Chi_Minh — Nối snapshot website tới Content Agent

- DONE: Campaign worker lấy đúng `web_snapshot_ids` đã ghim vào báo cáo; tenant, báo cáo, nhóm nguồn và trạng thái nguồn phải khớp.
- DONE: Nội dung website gửi model chỉ gồm các trường được cho phép, tối đa 10 offer; URL ảnh/tài nguyên có thể chứa chữ ký không đi vào input.
- DONE: Worker đọc lại cả nguồn bài và snapshot website trước khi lưu draft; nếu nguồn đã bị tắt/xóa hoặc pin đổi thì dừng với `market_research_context_stale`.
- PASS: Test worker dùng website snapshot cố định, giá USD, xác nhận signed image URL bị loại khỏi model input; report bài cũ tiếp tục dùng version/observation đã ghim.
- PASS: Ruff và `git diff --check` trên các file Python thay đổi.
- PASS: `tests/test_campaign_workflows.py tests/test_market_research_api.py tests/test_ai_budget.py` đạt 30 passed; Ruff và `scripts/export_openapi.py --check` cũng đạt.
- PASS: Incremental provenance commit `ae58f91966939df45851256e0a7a042e74cebb61` đã push; remote SHA khớp.
- NOT_RUN: Provider live, media analysis, browser real, preview rollout; Qwen adapter chưa nối pipeline, Gemini adapter chưa có ở mốc này.

### 2026-09-30 03:05 Asia/Ho_Chi_Minh — Adapter Qwen text có cấu hình vùng tường minh

- DONE: Thêm Qwen structured text adapter dùng OpenAI-compatible JSON-object endpoint; model ID và HTTPS endpoint theo vùng phải được khai báo, không tự chọn region/model.
- DONE: Adapter giới hạn đầu vào và validate output bằng Pydantic; comment summary chỉ nhận batch đã có privacy decision, không gửi author/profile hoặc decision ID tới model và kiểm tra citations thuộc đúng batch.
- DONE: Qwen tắt repair call cho tới khi có reservation ledger; không có retry ẩn của SDK.
- PASS: Qwen + DeepSeek provider fixtures đạt 21 passed ở mốc này; Ruff đạt.
- BLOCKED: Pytest thông thường không vào được fixtures vì môi trường hiện thiếu `pgvector`; Qwen factory integration cũng cần cài dependency `openai` theo manifest. Không lấy lượt fixture riêng làm bằng chứng integration.
- PARTIAL: Chưa có QWEN key/region/model của deployment, chưa nối vào pipeline comment vì comment text vẫn `privacy_hold`, chưa tích hợp pricing/budget ledger chung.
- NOT_RUN: Alibaba/Gemini live, media, comment analysis, provider budget end-to-end.

### 2026-09-30 03:22 Asia/Ho_Chi_Minh — Ràng buộc batch bình luận Qwen

- DONE: Thêm contract batch chỉ nhận excerpt đã sàng lọc, policy decision/version và evidence refs theo run; không có author/profile field.
- DONE: Qwen summary phải trích refs có trong batch; không gửi ID/quyết định nội bộ provider và không tạo repair request khi chưa có budget reservation.
- DONE: Tắt đường `generate` tổng quát của Qwen; adapter chỉ nhận `summarize_screened_comments`.
- PASS: Provider fixtures Qwen/Gemini/DeepSeek đạt 31 passed; Ruff và diff check đạt.
- PARTIAL: Contract không phải bằng chứng căn cứ pháp lý; comment collection vẫn `privacy_hold`, adapter chưa được worker gọi.

### 2026-09-30 03:14 Asia/Ho_Chi_Minh — Gemini inline media adapter

- DONE: Thêm adapter Gemini nhận byte ảnh/video inline, model/key tường minh, MIME allowlist, SHA-256/provenance và yêu cầu trạng thái `approved`; trạng thái mặc định là `privacy_hold`.
- DONE: Không nhận URL, không upload qua Files API, không retry/repair tự động. Tổng request tối đa 20 MiB; asset mặc định tối đa 10 MiB.
- PASS: Fixture xác nhận ảnh/video JSON, Pydantic validation, chặn privacy hold/hash/MIME/kích thước trước mạng và chỉ có một request khi output sai schema; bộ provider tests tổng cộng 27 passed.
- PARTIAL: Adapter chưa nối vào worker/media pipeline; cờ approved không thay thế quyết định căn cứ xử lý ở tầng nghiệp vụ. Chưa có pricing/budget ledger cho Gemini.
- NOT_RUN: Gemini live, media thật, privacy/deletion/retention end-to-end, browser real.

## Nhật ký

### 2026-09-30 15:47 Asia/Ho_Chi_Minh — Chuẩn hóa nhãn Nghiên cứu

- DONE: Bỏ các thông báo/nhãn cũ “Fanpage & thị trường” trong route Nghiên cứu; tab và nhãn nguồn Page công ty thống nhất với mô hình workspace theo Page.
- PASS: ESLint, TypeScript, Vitest 50/50 và `git diff --check`; production build gần nhất trước chỉnh sửa copy vẫn đạt.
- NOT_RUN: Chưa triển khai bundle mới lên preview; browser thật còn bundle cũ.

### 2026-09-30 15:44 Asia/Ho_Chi_Minh — Trạng thái kết nối Page dùng chung

- DONE: Workspace `connection_required` và `needs_reconnect` hiện cảnh báo bền vững trên mọi trang trong AppShell, nêu dữ liệu vẫn xem được, thao tác Agentic/thu thập/xuất bản đang tạm khóa và liên kết đến Cài đặt doanh nghiệp.
- PASS: ESLint, TypeScript, Vitest 50/50 và production build trong managed worktree.
- PARTIAL: Chưa kiểm tra trạng thái cảnh báo trong browser real API; preview hiện phục vụ bundle cũ và kết nối local từ sandbox chưa dùng được.

### 2026-09-30 15:38 Asia/Ho_Chi_Minh — Khép đường dẫn Nghiên cứu và nhận diện Page

- DONE: Các shortcut Tổng quan dùng `/research`; route legacy `/fanpages` vẫn redirect bảo toàn query/hash.
- DONE: Kết nối Page từ Xuất bản/Analytics mở Cài đặt doanh nghiệp, nơi có thao tác reconnect; Nghiên cứu không còn là chỗ quản lý token công ty.
- DONE: Sidebar hiển thị ảnh Page đã xác minh khi API trả `page_avatar_url`, giữ chữ cái đầu làm fallback.
- PASS: Frontend ESLint, TypeScript (`tsc --noEmit --incremental false`), Vitest 50/50 và production build đạt.
- PARTIAL: Browser đang đăng nhập còn tải preview cũ (menu ghi “Fanpage & thị trường”); sandbox không kết nối được `13104`/`8001`, nên chưa xác minh bản mới trên API/browser thật hoặc thay preview.

### 2026-09-30 — Baseline

- TODO → IN_PROGRESS: tạo worktree riêng từ nhánh UI đã chọn và đọc AGENTS.md/skills áp dụng.
- Kết quả: nhánh mới `codex/page-workspaces-research` bắt đầu từ SHA nêu trên; lệnh `git fetch` trong worktree chỉ cập nhật metadata Git, không sửa checkout preview hay shared working tree.
- Kiểm tra tiếp theo: hoàn tất truy vết route/session, Page model, nghiên cứu và worker trước khi chỉnh schema.

### 2026-09-30 05:58 Asia/Ho_Chi_Minh — Kiểm tra real-mode login shell

- DONE: Sửa test service worker cũ để chờ lượt reload do ứng dụng thực hiện, chỉ chấp nhận `ERR_ABORTED` khi navigation của Playwright bị lượt reload đó thay thế; cập nhật assertion theo heading login hiện tại.
- PASS: Playwright chạy trên preview real-mode hiện có tại `127.0.0.1:13104`, chế độ external server: test `/login` đạt `1 passed`; service worker mock không còn đăng ký/điều khiển trang.
- PASS: Frontend typecheck (`--incremental false`), ESLint và `git diff --check` sau khi sửa test.
- BLOCKED: Build/start server mới từ worktree riêng bị chặn quyền ghi sandbox vào `apps/web/.next/trace`; lần chạy E2E độc lập không sử dụng preview thất bại ở khâu khởi chạy Chromium trong sandbox. Không thay artifact hoặc restart preview để vượt qua.
- NOT_RUN: Không gửi form đăng nhập/đăng ký, không ghi dữ liệu ứng dụng; real API → worker → PostgreSQL, Meta live và provider live chưa được kiểm tra.
- TODO: Chạy lại real API → worker → PostgreSQL bằng tài khoản/workspace disposable và worker test được cô lập trước khi nghiệm thu toàn luồng.

### 2026-09-30 06:04 Asia/Ho_Chi_Minh — Bổ sung bảng giá provider có thời hạn

- DONE: Ghim giá công khai cho `gemini-3.8-flash` ($0.75/$3.75 mỗi triệu token, chỉ đến 2026-12-31) và `qwen3.8-27b` ($0.50/$3 mỗi triệu token, Singapore International); không trừ ưu đãi/free quota.
- DONE: Qwen yêu cầu vùng Singapore tường minh; Gemini tự khóa giá sau ngày hiệu lực; provider ngoài DeepSeek phải có upper bound token rõ ràng trước reservation. Bảng giá có version mới `provider-public-pricing-2026-09-30-v2`.
- PASS: Pricing-focused pytest `9 passed, 2 deselected` trên bản sao test cô lập trong `/private/tmp`; gồm micro-USD, region mismatch, ngày hết giá Gemini và từ chối reservation Gemini khi thiếu token bounds. Test database integration không chạy.
- PARTIAL: Chỉ bảng định giá/helper được thêm. Gemini/Qwen chưa nối worker, chưa có provider key/model deployment đã xác minh và chưa thuộc thống kê chi phí pipeline.
- NOT_RUN: Không gọi DeepSeek/Gemini/Qwen live hoặc gửi dữ liệu bình luận/media.

### 2026-09-30 06:14–06:20 Asia/Ho_Chi_Minh — Giới hạn raw quarantine và giữ comment import

- DONE: Research raw payload dùng helper `raw_quarantine_expiry`, expiry đặt tối đa 24 giờ từ lúc worker lưu metadata. DB ghi key/expiry trước object upload để purge scheduler còn biết key nếu storage trả timeout hoặc worker dừng.
- DONE: Manual import không lưu comment text dựa trên regex che email/điện thoại; aggregate comment metric vẫn giữ, response báo `privacy_hold` và số lượng bình luận bỏ qua. Test API cập nhật theo hành vi này.
- PASS: Unit test helper kiểm tra timestamp timezone-aware, đúng thời điểm hết hạn sau 24 giờ và comment text bị giữ lại trong khi count được giữ; Ruff và `git diff --check` đạt.
- PARTIAL: Lượt đầu test API không thu thập được vì runtime thiếu `pgvector`; sau đó cài riêng đúng dependency khai báo vào `/private/tmp` và chạy lại thành công. Chưa kiểm thử object storage thật hoặc purge scheduler.
- PARTIAL: Chưa có retention 90 ngày cho nội dung chuẩn hóa, deletion ledger/propagation hoặc legal review.
- NOT_RUN: Không chạy crawl live, không tạo/đọc dữ liệu Facebook hoặc website.

### 2026-09-30 — Ghim policy revision vào lượt Facebook

- DONE: Khi mở `WebCrawlRun`, worker chụp revision chính sách mới nhất của nguồn vào `config_json`: revision ID/no, version và retention được yêu cầu. Snapshot chỉ ghi provenance; không cấp phép xử lý dữ liệu cá nhân.
- DONE: API lịch sử chạy trả snapshot chính sách; UI phân biệt revision được ghi nhận, lượt chưa có policy revision, `privacy_hold` cho bình luận và việc retention chưa được thực thi.
- PASS: Test regression tạo lượt với policy `PR-1`, sửa nguồn sang `PR-2`, rồi xác nhận lịch sử lượt cũ vẫn giữ `PR-1`/90 ngày và trạng thái `privacy_hold`/`not_enforced`.
- PASS: OpenAPI được xuất từ FastAPI và TypeScript được sinh bằng `npm run gen:api`; không sửa generated type bằng tay.
- PARTIAL: Provenance hiện gắn vào source-run Facebook công khai dùng `WebCrawlRun`; owned Page, website và group chưa có cùng pipeline comment policy.
- NOT_RUN: Không xử lý comment body/media, không kiểm thử retention/deletion end-to-end, không crawl Facebook live và không gọi provider.

### 2026-09-30 — Tách quyền đọc Page khỏi khả năng đăng

- DONE: Phát hiện API cũ đánh dấu `can_publish=true` sau khi chỉ xác minh Page metadata và đọc một bài. Điều này đã bị sửa vì không chứng minh quyền xuất bản.
- DONE: Meta connection contract phân biệt `read_posts_capability` và `publish_capability`. Publish chỉ được ghi `verified` khi có lần đăng thành công gắn cùng connection/token sau lần xác minh gần nhất; nếu chưa có, response là `not_tested`.
- DONE: Giao diện xuất bản vẫn cho Owner bắt đầu quy trình với Page đọc được, nhưng nói rõ Meta sẽ kiểm tra quyền khi gửi; không hiện nhãn “đã có quyền đăng” trước khi có bằng chứng.
- PASS: API fixture `test_page_read_verification_does_not_claim_publish_permission` xác nhận read=`verified`, publish=`not_tested`, `can_publish=false` sau Page activation fixture.
- PASS: Frontend production build sau khi đổi trạng thái và nhãn capability đạt trong managed worktree riêng.
- NOT_RUN: Không thử đăng thật hoặc kiểm tra live Meta; chưa có Page do Owner xác nhận để xuất bản.

### 2026-09-30 — Lưu checkpoint nguồn nghiên cứu theo chu kỳ

- DONE: Worker nạp các kết quả nguồn đã commit trong `research_cycles.source_results_json` khi phục hồi cùng job; nguồn đã hoàn tất được bỏ qua, lỗi retryable chưa được checkpoint thành hoàn tất.
- DONE: Sau mỗi nguồn, worker commit kết quả và trạng thái cùng nhau; không giữ transaction mở trong lúc gọi collector mạng.
- DONE: Ghim policy snapshot vào kết quả nguồn Facebook (Page công ty, Page công khai, Group) và chuyển cùng snapshot đó tới `WebCrawlRun`, tránh lệch revision nếu policy đổi khi worker đang chạy.
- PASS: SQLite API/worker fixture mô phỏng worker bị hủy sau nguồn thứ nhất; khi chạy lại, nguồn thứ nhất không bị gọi lại, nguồn dở được tiếp tục và chu kỳ lưu cả hai kết quả.
- PASS: `tests/test_market_research_api.py tests/test_research_privacy.py` đạt 20 passed; Ruff và `git diff --check` đạt.
- LIMIT: Đây là checkpoint cấp nguồn trong một research cycle, chưa phải cursor bền cho từng post/comment/reply. Worker hiện chưa tiếp tục phân trang comment hoặc thu thập media.
- NOT_RUN: PostgreSQL/Redis recovery thật, live crawl, provider live và browser real chưa chạy trong lát cắt này.

### 2026-09-30 — Đồng bộ lại nhận diện Page trong Cài đặt

- DONE: Thêm Owner-only `POST /api/v1/workspaces/{id}/page-connection/refresh-metadata`; server giải mã token đã lưu, xác minh lại cùng Page và thực hiện read-only post request trước khi cập nhật tên/ảnh.
- DONE: Tên được đồng bộ vào Company, kết nối Meta, nguồn Page công ty và trạng thái Meta sync; ảnh lấy từ Page metadata. Brand Profile/revision không bị thay đổi.
- DONE: So khớp lại Page và ciphertext sau request mạng để từ chối ghi nhận nếu Owner thay kết nối đồng thời. Token không trả về client.
- DONE: Token hết hạn/thu hồi chuyển workspace sang `needs_reconnect` và dừng thực thi bằng cách xóa thời điểm đến hạn; giữ nguyên lựa chọn bật lịch của Owner và giữ dữ liệu cũ. Giao diện Cài đặt có nút đồng bộ và lỗi có mã xử lý.
- PASS: API fixture xác nhận tên/ảnh đổi, token được lấy từ backend đã lưu, không xuất hiện trong response, Brand Profile giữ nguyên; reconnect đặt lại lượt nghiên cứu và đồng bộ metrics theo lịch đã lưu.
- PASS: OpenAPI export/check, TypeScript generation, 28 backend focused tests sau fixture mới, frontend typecheck/lint/50 unit tests và production build.
- NOT_RUN: Không gọi Meta thật hoặc thay preview; kiểm thử bằng Meta adapter fixture.

### 2026-09-30 11:21 Asia/Ho_Chi_Minh — Khôi phục lịch Page sau khi Owner kết nối lại

- DONE: Khi token mất hiệu lực, hệ thống giữ `schedule_enabled`/`metrics_schedule_enabled` theo lựa chọn Owner nhưng xóa `next_due_at`; Page gate vẫn chặn mọi lần chạy khi workspace chưa active.
- DONE: Khi Owner xác minh lại đúng Page, lịch Page đã bật được đặt đến hạn ngay để scheduler phục hồi một lượt nghiên cứu; lịch metrics được đặt theo interval đã cấu hình. Lịch chưa bật vẫn tắt.
- PASS: `tests/test_account_lifecycle.py -k metadata_refresh`: 1 passed; bao gồm expiry, dữ liệu được giữ, schedule intent còn nguyên, reconnect cùng Page và due time được phục hồi.
- PASS: Ruff và `git diff --check`.
- NOT_RUN: Không gọi Meta live, PostgreSQL/Redis production hoặc thay preview. Đây là API lifecycle test với Meta fixture/SQLite.

### 2026-09-30 — Public Group Tier 0 metadata shell

- DONE: API chỉ nhận URL trang chủ `/groups/{id-or-slug}` trên host Facebook đã cho phép; nguồn mới dùng `public_web`, có thể Crawl ngay và bật/tắt lịch 12 giờ.
- DONE: Go runner gọi `Engine.Group` ở Tier 0, yêu cầu upstream xác nhận privacy public, chỉ xuất ID/tên/URL/privacy và provenance. Không gọi `GroupFeed`; không xuất mô tả, địa chỉ, avatar, danh sách thành viên hoặc bài thảo luận.
- DONE: Worker lưu metadata và coverage trong `WebCrawlRun`, trạng thái `partial`, `items_saved=0`, `history_complete=false`; không tạo evidence/report từ metadata nhóm. Lịch tạm ngừng sau khi nhóm không được xác nhận public.
- DONE: UI có Crawl ngay, lịch 12 giờ, metadata/lịch sử và thông báo rõ không có thảo luận trong Tier 0.
- PASS: Go runner `go test ./...`; collector protocol fixtures 6 passed; API/worker SQLite fixture với `pgvector` test shim 3 passed; frontend lint, typecheck và Vitest 50 passed; Python AST parse và `git diff --check`.
- BLOCKED: Python runtime hiện tại thiếu dependency `pgvector` đã khai trong `pyproject.toml`; mạng không phân giải được package index. API fixture dùng shim tạm trong `/private/tmp`, không phải xác minh PostgreSQL/Redis.
- NOT_RUN: Không gọi Facebook thật, không gọi GroupFeed, không chạy PostgreSQL/Redis cho lát cắt này và không thay preview. Kết quả là fixture/pipeline code, không phải live Group crawl.

### 2026-09-30 10:02 Asia/Ho_Chi_Minh — PostgreSQL/Redis integration và raw retention

- PASS: Tạo PostgreSQL 18.3 riêng trong `/private/tmp`, hai Redis riêng trên loopback; chạy migration từ database rỗng tới `0022_ai_usage_budget`.
- PASS: `tests/test_postgres_database_integration.py` đạt **8 passed** trên PostgreSQL/Redis thật: schema/pgvector, lease fencing, reservation cạnh tranh/idempotency, dispatch queue/cache và raw-expiry persistence.
- PASS: Raw-retention test cho thấy key cùng expiry 24h đã đọc được từ một database connection khác trước khi storage `put` chạy; mô phỏng storage timeout vẫn giữ expiry pointer để purge scheduler xử lý.
- PASS: `tests/test_market_research_api.py` đạt **10 passed** và `tests/test_research_privacy.py` đạt **3 passed**; dependency `pgvector` chỉ được thêm trong `/private/tmp`, không sửa virtualenv hay manifest dự án.
- PASS: Chạy gộp `tests/test_ai_budget.py tests/test_market_research_api.py tests/test_research_privacy.py tests/test_postgres_database_integration.py`: **32 passed**. Sau đó dừng PostgreSQL/Redis test instance; preview và dịch vụ người dùng không bị chạm.
- DONE: Sửa integration harness để monkeypatch `services.api.db.SessionLocal`, đúng binding được import động trong budget service.
- PARTIAL: Object storage thật, purge scheduler end-to-end, xử lý xóa lan truyền và retention nội dung chuẩn hóa chưa được kiểm thử/triển khai.
- NOT_RUN: Không gọi Facebook, DeepSeek, Gemini hoặc Qwen live; không thao tác preview hay database của người dùng.

### 2026-09-30 13:14 Asia/Ho_Chi_Minh — Metadata link và media tham chiếu của bài Page

- DONE: Page post collector yêu cầu attachment metadata có giới hạn và link đích; không tải binary ảnh/video, không lưu URL media có thể chứa chữ ký truy cập, và gắn trạng thái `metadata_only_privacy_hold`.
- DONE: Link được lọc về HTTP(S), bỏ toàn bộ query/fragment có thể chứa chữ ký hoặc tracking và chặn host/IP nội bộ; attachment list có giới hạn để tránh response lớn.
- DONE: Nếu Meta không chấp nhận field mở rộng, collector thử lại tập field bài viết ổn định và đánh dấu attachment metadata là `not_returned`, không làm mất bài đọc được.
- DONE: Migration bổ sung `0024_page_post_media_references` lưu link và metadata an toàn cho owned Page posts; API, research observations và giao diện Nghiên cứu/Analytics hiển thị link/type cùng giới hạn xử lý.
- PASS: `tests/test_meta_client.py tests/test_market_research_api.py`: 57 passed; gồm fallback field, URL nguy hiểm/secret query, metadata không giữ title/description tự do, response giới hạn và API serialization.
- PASS: PostgreSQL 18.3 disposable: migrate database rỗng đến `0024`, downgrade `0023` rồi upgrade lại `0024`; kiểm tra cột và default mới. Không kết nối database preview.
- PASS: OpenAPI export và TypeScript generation; frontend typecheck, lint, Vitest (50 passed) và production build; Ruff và `git diff --check`.
- PARTIAL: Metadata chưa tương đương phân tích ảnh/video. Binary không tải; Gemini chưa nối vào pipeline. Comment body/replies tiếp tục `privacy_hold` và chưa có cursor pagination.
- NOT_RUN: Meta live, UI → Redis/Celery → PostgreSQL bằng Page thật, Gemini/Qwen/DeepSeek live, deletion/retention propagation và comment pagination.
- BLOCKED: Python runtime thiếu package `pgvector`; các API tests dùng SQLite fixture với import shim tạm ở `/private/tmp`. Migration chạy PostgreSQL thật với cùng shim import; chưa chứng minh ORM write/read qua API/worker trên PostgreSQL.

### 2026-09-30 13:39 Asia/Ho_Chi_Minh — Cá nhân hóa báo cáo bằng hồ sơ Owner và bỏ audience giả

- DONE: DeepSeek Research report chỉ nhận hồ sơ `manual_text_v1` hiện hành khi brand và revision đã xác nhận khớp nguyên văn; legacy/AI-generated profile không được gửi như hướng dẫn thương hiệu.
- DONE: Báo cáo và coverage ghim trạng thái, ID revision và số revision đã dùng. Draft được tạo từ hướng viết giữ provenance này trong `market_research_context`.
- DONE: Giá trị nội bộ `Chưa xác định`/`unknown` không còn được đưa thành phạm vi thị trường hoặc audience campaign giả. Chỉ dùng industry/region có nội dung rõ và từ khóa đã chuẩn hóa.
- PASS: `tests/test_ai_budget.py tests/test_market_research_api.py`: 33 passed; gồm xác thực profile revision, không có profile, payload model, group placeholder và pin vào draft.
- PASS: Ruff trên file Python thay đổi, `git diff --check`, frontend typecheck (không incremental), ESLint và Vitest (50 passed).
- PARTIAL: Lát cắt này sửa cá nhân hóa bản phân tích DeepSeek; chưa triển khai routing Qwen/Gemini cho comments/media hoặc ngân sách dùng chung cho các provider.
- NOT_RUN: Không gọi provider live, không crawl nguồn live, không chạy browser/PostgreSQL/Redis integration và không thay preview.

### 2026-09-30 14:09 Asia/Ho_Chi_Minh — Checkpoint Page công ty trong Nghiên cứu

- DONE: Nguồn Page công ty lưu Graph cursor, Page ID gắn với cursor, mốc đầu cửa sổ 90 ngày, trạng thái kết thúc và số trang lịch sử đã xử lý; migration mới là `0025_owned_page_research_backfill`.
- DONE: Mỗi source-run xử lý tối đa 100 bài; lúc backfill chia 50 bài mới và 50 bài lịch sử. Khi lịch sử đã hết, các lượt sau làm mới tối đa 100 bài mới nhất.
- DONE: Mỗi research cycle lưu `collection_observed_at` trước khi thu thập. Retry cùng cycle giữ observation time, tránh tạo snapshot thứ hai cho cùng lượt.
- DONE: Coverage phân biệt đã chạm mốc 90 ngày, Meta hết lịch sử trước mốc, backfill còn tiếp tục, refresh sau khi backfill xong và bài thiếu ngày đăng. Trạng thái thiếu 90 ngày vẫn được nhớ qua những lần refresh tiếp theo. Cursor không được trả qua API.
- DONE: Owner có thể bật/tắt lịch 12 giờ của nguồn Page; collector bị cố định ở Meta API. Trạng thái nguồn phản ánh `completed` hoặc `partial` cùng thời điểm thử/thành công.
- PASS: `tests/test_market_research_api.py tests/test_research_privacy.py` — 24 passed; fixture xác nhận cursor tiếp tục ở `history-2`, và lịch sử dừng tại 89 ngày không bị báo đủ 90 ngày.
- PASS: Ruff, `git diff --check`, frontend typecheck, ESLint và Vitest — 50 passed.
- PASS: PostgreSQL 18.3 disposable: migration fresh tới `0025_owned_page_research_backfill`; database thứ hai nâng từ `0024` tới `0025`; `tests/test_postgres_database_integration.py` đạt 6 passed, 2 Redis tests skipped do lượt này không cấu hình Redis test URL.
- NOT_RUN: Chưa có Meta live, Redis worker thật, browser reload hoặc provider live.
- PARTIAL: Thay đổi chỉ bao phủ bài Page công ty. Bình luận/replies vẫn `privacy_hold`; media và Gemini/Qwen chưa nối vào pipeline.

### 2026-09-30 16:05 Asia/Ho_Chi_Minh — Khóa thao tác Nghiên cứu khi Page mất kết nối

- DONE: Nút crawl nhóm/nguồn, lưu nguồn, đổi collector, bật lịch và tạo chiến dịch từ báo cáo bị khóa trên giao diện khi `page_connection_state` chưa `active`; giải thích và liên kết tới Cài đặt được hiển thị.
- DONE: API chỉ cho người có `market:manage` tắt lịch hiện có khi Page chưa active, nếu request không đổi collector/giới hạn/cấu hình crawl. Bật lịch, đổi cấu hình, crawl và thêm nguồn vẫn trả `409 page_connection_required`/`page_needs_reconnect`.
- DONE: Có thể ngừng theo dõi nguồn khi Page mất kết nối; thao tác này soft-disable nguồn, không xóa evidence, snapshots hay dữ liệu lưu trước đó.
- PASS: Frontend ESLint, TypeScript typecheck, Vitest — 50 passed; Next production build đạt; `git diff --check` đạt.
- PASS (fixture): In-app browser ở port `13106` xác nhận banner trạng thái, nút Crawl ngay/lưu nguồn bị disabled, và khả năng đọc dữ liệu cũ. Fixture cho thấy nguồn có lịch tắt hiển thị “Bật lịch 12 giờ” ở trạng thái disabled.
- NOT_RUN: API pytest mới được viết nhưng không chạy được vì checkout không có `uv`, virtualenv hoặc `pytest`/FastAPI/SQLAlchemy trong Python hiện hành. Python AST parse đạt; chưa coi đó là test hành vi backend.
- NOT_RUN: Không truy cập API thật, PostgreSQL/Redis, Meta hay provider live; không thay preview `13104`.

### 2026-09-30 16:22 Asia/Ho_Chi_Minh — Khóa các thao tác agentic khi Page cần kết nối lại

- DONE: Hồ sơ thương hiệu vẫn đọc được; Owner không thể áp dụng phiên bản mới khi Page chưa active.
- DONE: Tài liệu cũ vẫn xem được; upload và reprocess bị khóa bằng cùng lý do Page gate.
- DONE: Danh sách chiến dịch và bài viết cũ vẫn xem được; lập kế hoạch AI, tạo chiến dịch, lưu phiên bản, tải media, review, gửi duyệt và quyết định duyệt/từ chối bị khóa. Handler có guard ngoài trạng thái disabled của giao diện.
- DONE: Xuất bản mới bị khóa khi Page chưa active. Lịch đã xếp vẫn có thể được Owner hủy: endpoint kiểm tra membership và quyền Owner nhưng không yêu cầu Page active; đăng mới vẫn giữ Page-gated permission.
- DONE: Đối soát `outcome_unknown` yêu cầu Page hoạt động lại; không ghi kết quả giả khi ứng dụng không thể kiểm tra Fanpage.
- PASS: ESLint, TypeScript `--noEmit --incremental false`, Vitest 52/52, production build và `git diff --check`.
- PASS: Python `py_compile` cho `services/api/meta.py` và bài integration test.
- BLOCKED: Có `pytest` trong Anaconda, nhưng test PostgreSQL dừng lúc collection vì Python đó thiếu `pgvector`; `POSTGRES_TEST_URL` cũng chưa được xác nhận. API cancellation/lịch chưa được kiểm chứng bằng PostgreSQL/HTTP thật.
- NOT_RUN: Không thay preview `13104`, không gọi Meta hoặc provider AI thật.

### 2026-09-30 16:29 Asia/Ho_Chi_Minh — Hoàn tất rà soát Page gate ở trang công việc

- DONE: Trang chi tiết chiến dịch khóa lưu brief, tạo bài thủ công/AI, sinh bài theo slot và xuất file khi Page chưa active; bản ghi cũ vẫn đọc được.
- DONE: Analytics khóa đồng bộ/nhập dữ liệu, áp dụng recommendation và ghi outcome khi Page chưa active; lịch Meta đang bật vẫn có thể tắt.
- DONE: API đọc trạng thái lịch Meta kể cả khi Page connection chưa verified; Owner chỉ được tắt lịch khi inactive. Bật lịch yêu cầu Page active, đúng Page ID và connection đã verified.
- DONE: Nút đối soát publication `outcome_unknown` bị khóa khi Page mất kết nối; Owner phải reconnect trước khi xác nhận kết quả.
- PASS: ESLint, TypeScript, Vitest 52/52, production build và `git diff --check` sau thay đổi UI.
- PASS: Python `py_compile` cho các file backend/test liên quan.
- BLOCKED: PostgreSQL test xác nhận lịch Meta khi mất kết nối dừng lúc collection vì thiếu `pgvector`; cần cài bộ dependency dự án và cấu hình database test riêng trước khi chạy.
- PASS: Ruff check trên `services/api/meta.py` và `tests/test_postgres_application_modules.py` với cache chuyển sang `/private/tmp`.
- NOT_RUN: Browser/API real và preview `13104` chưa được thay.

### 2026-09-30 16:40 Asia/Ho_Chi_Minh — Phân biệt metadata Group với nội dung crawl thành công

- DONE: Group Facebook Tier 0 chỉ đọc được metadata shell; worker vẫn lưu trạng thái lượt `partial`, coverage và lần thử, nhưng không ghi `last_collection_success_at` khi không có bài viết/bình luận.
- DONE: Cập nhật regression test để metadata-only không bị tính là lần thu thập nội dung thành công.
- PASS: Ruff cho worker/test, Python `py_compile` và `git diff --check`.
- PASS (SQLite/fixture): `tests/test_market_research_api.py tests/test_facebook_cli_collector.py` — 30 passed khi dùng shim `pgvector` tạm ngoài repo; test kiểm tra hành vi logic, không xác nhận kiểu vector/PostgreSQL.
- BLOCKED: Không chạy được PostgreSQL integration trong môi trường hiện tại vì thiếu package `pgvector` thật và chưa xác nhận `POSTGRES_TEST_URL`.
- NOT_RUN: Không gọi facebook-cli live, PostgreSQL/Redis, browser/API thật hoặc provider AI; preview `13104` giữ nguyên.

### 2026-09-30 17:35 Asia/Ho_Chi_Minh — Hàng đợi xóa dữ liệu đã thu thập theo nguồn

- DONE: Thêm migration `0026_research_source_erasure` với yêu cầu purge và hàng đợi object key có trạng thái retryable, tenant FK ghép; không sửa migration cũ.
- DONE: Owner có thể yêu cầu purge qua `POST .../market-research/sources/{source_id}/purge-collected-data`. API tắt source/lịch và commit durable job trước khi dispatch; request lặp trả cùng job. Editor bị từ chối.
- DONE: Worker xóa object raw theo lô, xóa evidence/version/observation và catalog snapshot của source, tombstone các report tham chiếu nguồn, gỡ context khỏi brief campaign; brief revision còn chờ duyệt bị chuyển `invalidated`.
- DONE: Research worker kiểm tra source active trước persist. Observation giữ lease ngắn trong lúc object-store put; purge đợi lease đang hoạt động hết/được giải phóng, rồi xóa key. Sau put muộn, worker kiểm tra purge; nếu xóa object thất bại sau khi job đã hoàn tất thì tạo hàng pending và requeue durable job.
- PASS (SQLite/API-worker fixture): `tests/test_market_research_api.py -k 'source_purge or raw_research_upload_lease'` — 3 passed; kiểm tra Owner/idempotency/dispatch outage, purge evidence/raw/report, vô hiệu brief draft, late-object retry và put lease cleanup.
- PASS (regression): `tests/test_market_research_api.py tests/test_market_research_sources.py tests/test_facebook_cli_collector.py tests/test_research_privacy.py tests/test_website_entities.py` — 57 passed; Ruff, OpenAPI `--check` và `git diff --check` đạt.
- PASS (PostgreSQL migration): Cụm PostgreSQL 18.3 disposable riêng tại `127.0.0.1:15447`: fresh upgrade tới `0026`, downgrade `0026` → `0025`, upgrade lại tới `0026`; `alembic current` xác nhận `0026_research_source_erasure (head)`. Cụm đã được dừng sau test. Shim `pgvector` chỉ hỗ trợ import model trong môi trường test; migration chạy trên PostgreSQL thật. Đây chỉ là kiểm tra migration, chưa phải API/worker/Redis integration.
- PASS: Ruff cho các file Python đã sửa; `git diff --check` đạt.
- NOT_RUN: Redis/Celery recovery, object storage thật, Browser UI và test race đa-worker chưa chạy. Không đụng tới PostgreSQL khác đang dùng cổng `15434`.
- PARTIAL: Đây là purge dữ liệu nghiên cứu do ứng dụng quản lý theo một source, không phải xóa toàn bộ dữ liệu cá nhân hay chứng nhận pháp lý. Bản bài/approval/publication đã tạo, nội dung đã xuất/đăng, provider ngoài, cache/backup ngoài cơ chế này và deletion propagation toàn diện chưa được xử lý.

### 2026-09-30 17:40 Asia/Ho_Chi_Minh — Kiểm tra schema purge trên PostgreSQL

- DONE: Cập nhật regression `test_postgres_migrations_constraints_vector_and_job_fencing` theo migration head `0026_research_source_erasure`; bổ sung assertion cho bảng purge và composite tenant foreign keys.
- PASS: Test trên PostgreSQL 18.3 disposable đã migrate thật, xác nhận extension vector, schema, FK và job fencing. `pgvector` shim chỉ giải quyết import trong test environment.
- PASS: Ruff và `git diff --check`; cụm PostgreSQL riêng đã dừng sau test.
- NOT_RUN: Test này không chạy HTTP API, Redis/Celery, object storage, trình duyệt, race đa-worker hoặc Page/provider live.

### 2026-09-30 17:45 Asia/Ho_Chi_Minh — Chạy purge worker trên PostgreSQL thật

- PASS: `test_postgres_migrations_constraints_vector_and_job_fencing` và `test_postgres_research_source_erasure_worker_deletes_raw_and_source_rows` — `2 passed` trên PostgreSQL 18.3 disposable ở cổng `15447`.
- PASS: Worker thật trên PostgreSQL claim job, tạo/xóa hàng đợi raw-key, xóa evidence/version/observation, tombstone source và hoàn tất job; test xác nhận trạng thái sau commit.
- LIMITATION: Adapter object storage được thay bằng recording fake trong test; không kết nối storage ngoài. Chỉ `pgvector` import shim ngoài repo được dùng.
- PASS: Ruff, Python compile và `git diff --check`; cụm test đã dừng.
- NOT_RUN: Redis/Celery dispatch/recovery, HTTP API, browser, Meta/provider live, multi-worker race và object storage thật.

### 2026-09-30 17:57 Asia/Ho_Chi_Minh — PostgreSQL API và Docling smoke

- FIXED: PostgreSQL API smoke phát hiện Page activation flush `Brand` trước `Company` do các model không khai báo ORM relationships. Activation giờ flush Company trước khi insert Membership/Brand trong cùng transaction.
- DONE: Cập nhật PostgreSQL smoke theo contract mới: profile_text do Owner tự viết, Page workspace chỉ gắn một Page, dùng nhóm Nghiên cứu nội bộ, và policy fixture ghi rõ dữ liệu tổng hợp (không coi là xác minh căn cứ pháp lý).
- PASS: `test_postgres_api_persists_existing_product_modules` — `1 passed` trên PostgreSQL 18.3 disposable. Bao phủ đăng ký → xác minh Page mock → workspace/Brand/Owner → nguồn nghiên cứu → review/approval → analytics/conversion → upload và lưu kiến thức; sau job, API GET và session PostgreSQL đọc lại trạng thái đã lưu.
- PASS (Docling thật): Chạy test bằng `/private/tmp/docling-ingestion-venv` với Docling `2.130.0`, model local đã verify 66 files, OCR disabled; upload TXT được xử lý bởi Docling child process. `pgvector` chỉ cần shim import trong test process.
- LIMITATION: Meta Graph, DeepSeek, embedding và object storage production không được gọi; storage dùng thư mục tạm. Worker được gọi trực tiếp trong test, không qua Redis/Celery. Chưa phải browser/UI hoặc live Page nghiệm thu.
- PASS: Cụm PostgreSQL disposable đã dừng sau test.
- PASS (follow-up 18:00): Lặp lại PostgreSQL smoke sau khi bổ sung assertion đăng ký trả danh sách workspace rỗng, Page activation trả đúng tên/Page ID/state/ảnh placeholder — `1 passed`. SQLite auth/tenant regression `test_auth_and_tenant_isolation` — `1 passed`.

### 2026-09-30 18:05 Asia/Ho_Chi_Minh — PostgreSQL và Redis queue dispatcher

- PASS: Dùng PostgreSQL 18.3 disposable riêng tại `127.0.0.1:15447` và hai Redis 8.6.3 riêng tại `16389` (queue) / `16390` (cache); queue/cache không trỏ tới Redis preview dùng chung.
- PASS: Năm test integration — schema/job fencing, queue-cache TTL/isolation, hai worker cùng claim một job, job PostgreSQL còn queued sau dispatch outage và được dispatch lại, cùng production Celery dispatcher gửi job đã commit vào Redis `agent` queue — `5 passed`.
- LIMITATION: Test dispatcher xác nhận message thật vào Redis, nhưng không chạy Celery worker consume message để hoàn tất một source-run; test outage dùng dispatcher giả để kiểm tra recovery ledger. Đây chưa phải luồng UI → API → Redis → worker → kết quả hoàn chỉnh.
- DONE: Đã dừng cả PostgreSQL và hai Redis disposable sau test; không restart hay sửa preview `13104` hoặc Redis dùng chung.
- NOT_RUN: Browser UI, Meta/Page live, DeepSeek/Gemini/Qwen live, object storage production và worker consume qua Redis vẫn chưa nghiệm thu.

### 2026-09-30 18:15 Asia/Ho_Chi_Minh — Celery worker consume job đã commit

- PASS: Bổ sung `test_postgres_celery_worker_consumes_committed_research_job`: test tạo durable research job/cycle trong PostgreSQL, production dispatcher gửi qua Redis `agent`, Celery test worker thật nhận job, claim lease/fencing và ghi `succeeded` + `completed_no_data` trở lại PostgreSQL.
- PASS: Chạy lại nhóm PG/Redis — schema/fencing, queue-cache isolation, competing claims, dispatch outage recovery, dispatcher Redis và worker consume — `6 passed in 2.02s` trên PostgreSQL 18.3 + Redis 8.6.3 disposable.
- SCOPE: Job không có nguồn nghiên cứu; đây là kiểm thử queue/worker/persistence, không phải crawl nguồn, API/browser thật hoặc phân tích AI. DeepSeek tắt, không gọi Meta, Gemini hay Qwen.

### 2026-09-30 18:58 Asia/Ho_Chi_Minh — Ghi riêng chi phí AI do người dùng chủ động chạy

- DONE: Bổ sung `budget_class=interactive` cho lời gọi DeepSeek trong lập kế hoạch campaign, tạo bài và sửa bài. Mỗi provider request có reservation/usage ledger riêng; không cộng vào bộ đếm hạn mức tự động 2 USD/ngày.
- DONE: Tạo wrapper cho content agent: reservation được commit trước khi gọi model; kết quả hoàn tất có thể được phát lại nếu worker bị gián đoạn; trạng thái provider chưa rõ không bị gửi lại. Lỗi giới hạn đầu vào trước khi gửi giải phóng reservation. Reservation chưa tạo được được phân biệt với kết quả provider chưa rõ.
- LIMITATION: Job thành công xóa payload tạm khỏi ledger sau khi lưu bản chính vào job/post versions. Nếu job thất bại sau khi provider đã trả kết quả, cache ledger được giữ để retry an toàn; chưa có TTL riêng cho các cache output này.
- DONE: Ghi usage interactive vào kết quả durable job và `ContentGenerationRun`; API ngân sách tiếp tục chỉ báo quota tự động. Màn hình tổng hợp chi phí interactive chưa có.
- PASS: `tests/test_ai_budget.py tests/test_interactive_ai_accounting.py tests/test_mailguard_pilot.py tests/test_campaign_workflows.py tests/test_market_research_api.py` — 65 passed; bao gồm replay không gọi model lần hai, ngăn gửi lại request uncertain, phân biệt reservation chưa tạo với kết quả chưa rõ, budget API tách loại interactive/automatic, và content workflows dùng model fixture.
- PASS: Toàn bộ `tests/test_postgres_database_integration.py` — 7 passed, 3 skipped trên PostgreSQL 18.3 disposable mới tạo, pgvector và migration head `0026`; test xác nhận settlement interactive không đổi bộ đếm automatic. Ba test Redis bị skip vì các URL Redis được đặt trống có chủ đích.
- DONE: Dừng đúng cluster disposable cổng `15557` sau kiểm thử; không chạm PostgreSQL/Redis preview.
- PASS: Ruff, Python `py_compile`, OpenAPI `--check` và `git diff --check`.
- NOT_RUN: Không gọi DeepSeek/Gemini/Qwen live, không kiểm tra UI/API hiển thị chi phí, không chạy Redis/Celery cho các job AI.
- PARTIAL: Gemini/Qwen chưa được nối worker; chưa có tổng hợp interactive trên trang Ngân sách. DeepSeek report tự động và interactive planning/content hiện mới được ledger; chưa khẳng định mọi agent/callsite đều được tính.
- DONE: Dừng PostgreSQL và hai Redis test riêng; preview và Redis dùng chung không bị thay đổi.

### 2026-09-30 19:08 Asia/Ho_Chi_Minh — Chốt bảo vệ dữ liệu tại lớp lưu evidence Facebook

- DONE: Thêm lớp bảo vệ ngay trong `_persist_evidence`; collector Facebook nào gọi tới cũng bị lọc lại email/số điện thoại/địa chỉ theo redactor hiện có trước khi tạo hash, phiên bản evidence và bài Page.
- DONE: Bình luận truyền nhầm vào persistence bị loại bỏ và chỉ giữ số lượng nội dung đã giữ ở trạng thái `privacy_hold`; raw payload Facebook bị loại trước khi storage adapter được gọi.
- DONE: Giữ provenance cho lần lọc bổ sung và title riêng; metadata tiếp tục ghi rõ `names_not_detected`, `not_anonymization` và cần rà soát thủ công. Đây là defense-in-depth, không phải xác nhận căn cứ xử lý hoặc ẩn danh.
- PASS: `tests/test_research_privacy.py tests/test_market_research_api.py` — 33 passed; test mới gọi trực tiếp persistence để xác nhận title/body đã lọc, comment text không vào DB và raw response không vào storage.
- PASS: Ruff trên 4 file Python thay đổi, `py_compile` với cache ở `/private/tmp`, và `git diff --check`.
- NOT_RUN: Chưa chạy PostgreSQL/Redis/Celery hoặc Meta/provider live cho lát cắt này; không thay preview.
- PARTIAL: Redactor vẫn không nhận diện tên người tự do và không bảo đảm đã loại hết dữ liệu cá nhân. Bình luận/media vẫn `privacy_hold`; retention nội dung chuẩn hóa chưa được thực thi.

### 2026-09-30 19:16 Asia/Ho_Chi_Minh — Xác minh chốt privacy trên PostgreSQL thật

- PASS: Khởi tạo cụm PostgreSQL 18.3 disposable mới trên cổng `15558`, tạo `vector` extension, chạy migration fresh tới `0026_research_source_erasure`.
- PASS: `test_postgres_facebook_evidence_persistence_enforces_privacy_boundary` — 1 passed; test gọi `_persist_evidence` trên PostgreSQL thật và đọc lại title/body đã lọc, comment/raw bị giữ, metrics privacy còn lưu.
- DONE: Dừng đúng cụm disposable `page-workspace-privacy-pg-20260930`; không chạm database/Redis preview.
- NOT_RUN: Redis/Celery, object storage thật, Browser UI, Meta và các provider AI.

### 2026-09-30 — Allowlist metadata Facebook tại persistence

- DONE: `_persist_evidence` giờ chỉ lưu metric số được allowlist, provenance counter đã kiểm tra, loại/URL attachment an toàn và metadata redaction đã chuẩn hóa; field tùy ý như `authors`, `comment_text`, `raw_response`, tiêu đề media và query token bị loại.
- DONE: URL hiển thị bỏ query/fragment; bare counter dài có thể giống số điện thoại không được giữ dưới dạng chuỗi raw. Số chuẩn hóa vẫn có thể được lưu khi đến từ metric đã được kiểm tra.
- PASS: Toàn bộ backend fixture suite trên working tree dựa trên SHA `1c54ee1296d1055c1525e95f1383eba65a738748` đạt **301 passed, 18 skipped, 1 deselected**.
- PASS: PostgreSQL 18.3 disposable, migration fresh đến `0026`, `test_postgres_facebook_evidence_persistence_enforces_privacy_boundary` đạt **1 passed** với metric metadata cố tình chứa trường PII/field lạ. Cụm test đã dừng.
- PASS: Ruff `--no-cache`, `py_compile`, `git diff --check`.
- LIMITATION: Đây là defense-in-depth, không phải ẩn danh hoặc xác nhận căn cứ xử lý. Comments/media vẫn `privacy_hold`; expiry/deletion tự động chưa được bật.

### 2026-09-30 — Regression backend sau persistence privacy guard

- PASS: Trên commit `158e44e9dbc22395a87d26090092f28090214095`, `PYTHONPATH=/private/tmp/page-workspace-python-deps python -m pytest -p no:cacheprovider tests --ignore=tests/test_ingestion_parsers.py -k 'not test_parser_returns_locators_and_rejects_scan_pdf' -q` — **300 passed, 18 skipped, 1 deselected**.
- PASS: Bộ tập trung `tests/test_research_privacy.py tests/test_market_research_api.py tests/test_ai_budget.py` — **47 passed**.
- LIMITATION: Các lượt này dùng fixture; không phải kiểm thử PostgreSQL/Redis/browser/Meta/provider live. Một số test parser và integration được bỏ/skip do runtime hoặc service test không cấu hình.
- IN_PROGRESS: Chưa mở Qwen/Gemini cho comments/media. Tiếp tục giữ dữ liệu ở `privacy_hold` cho tới khi có điều kiện xử lý, retention và quyền xóa được xác định đủ rõ.

### 2026-09-30 19:53 Asia/Ho_Chi_Minh — Kiểm chứng ngân sách chung ba provider trên PostgreSQL

- DONE: Bổ sung integration test chứng minh DeepSeek, Gemini và Qwen dự trữ từ cùng hạn mức `ai_usage_budget_days` theo workspace/ngày. Test dùng company và nội dung tổng hợp, không gọi provider.
- PASS: PostgreSQL 18.3 disposable, migration fresh tới `0026`; `test_automatic_ai_budget_is_shared_across_deepseek_gemini_and_qwen` — `1 passed`. DeepSeek và Gemini đặt trước được ghi thành hai ledger rows; reservation Qwen tiếp theo trả `deferred_budget` khi tổng sẽ vượt cap. Kiểm tra tổng reserved vẫn không vượt limit.
- PASS: `tests/test_ai_budget.py` — `14 passed`; Ruff, `py_compile` dùng cache ở `/private/tmp`, `git diff --check`.
- LIMITATION: Đây chỉ chứng minh reservation/ledger dùng chung khi caller cung cấp model, region và token bounds đã kiểm tra. Worker chưa gọi Gemini/Qwen; comment/media tiếp tục `privacy_hold`; không có provider live request.
- PASS: Sau khi sandbox chặn loopback ở lượt đầu, chạy lại toàn `tests/test_postgres_database_integration.py` khi được cấp quyền tới đúng cụm disposable — `9 passed, 3 skipped` (`POSTGRES_TEST_URL` thật; các test Redis bị skip vì Redis test URLs không cấu hình). Cụm PostgreSQL 18.3 port `15559` đã dừng sau test.

### 2026-09-30 20:05 Asia/Ho_Chi_Minh — PostgreSQL API kiểm tra Page không tự cấp membership

- DONE: Mở rộng API integration smoke với tài khoản thứ hai: đăng ký không tạo workspace; dù gửi lại đúng Page ID và Page Access Token đã gắn, tài khoản không phải thành viên vẫn nhận `409 page_already_connected` và danh sách workspace rỗng.
- PASS: `tests/test_postgres_application_modules.py -k test_postgres_api_persists_existing_product_modules` — `1 passed` trên PostgreSQL 18.3 disposable, toàn bộ API call qua `TestClient`, Meta được thay bằng fixture; không có Meta live request.
- PASS: Ruff, `py_compile`, `git diff --check`; PostgreSQL cổng `15559` đã dừng.
- LIMITATION: Đây xác nhận không tự cấp membership qua token trên một request nối tiếp; chưa phải stress test race đồng thời hai request `from-page`.

### 2026-09-30 20:13 Asia/Ho_Chi_Minh — Sửa race kích hoạt cùng Page

- FIXED: Kiểm thử đồng thời phát hiện nhánh `IntegrityError` đọc `user.id` sau rollback; SQLAlchemy có thể làm hết hạn ORM object và gây `MissingGreenlet` thay vì trả conflict có kiểm soát. Endpoint giờ chụp user ID trước giao dịch và dùng scalar ổn định sau rollback.
- PASS: PostgreSQL 18.3 disposable: `test_postgres_concurrent_page_activation_creates_one_workspace` — `1 passed`; hai request được đồng bộ sau cùng truy vấn “Page đã tồn tại” để buộc tranh chấp unique constraint. Kết quả một `201`, một `409 page_already_connected`, một Company/Page và đúng một Owner membership.
- PASS: Chạy chung `test_postgres_api_persists_existing_product_modules` và race test — `2 passed`; regression SQLite Page-owner và reconnect — `2 passed`; Ruff, `py_compile`, `git diff --check`.
- DONE: Cụm PostgreSQL test riêng port `15559` đã dừng. Không có Meta live request hoặc dịch vụ preview bị thay đổi.

### 2026-09-30 20:19 Asia/Ho_Chi_Minh — Kiểm chứng Page gate tại worker claim trên PostgreSQL

- DONE: Thêm regression test chạy `research_tasks._claim` trên PostgreSQL thật cho cả `connection_required` và `needs_reconnect`.
- PASS: Khi Page chưa được kết nối hoặc cần kết nối lại, claim trả `False`; durable job thành `failed` với mã lỗi tương ứng, không tăng attempts, không đặt claim/lease hoặc started_at; ResearchCycle, bước thu thập và JobEvent phản ánh lỗi.
- PASS: Toàn `tests/test_postgres_database_integration.py` — `11 passed, 3 skipped` trên PostgreSQL 18.3 disposable; ba Redis integration bị skip vì không cấu hình URL Redis test.
- PASS: Ruff, `py_compile` và `git diff --check`.
- DONE: PostgreSQL disposable cổng `15559` đã dừng. Không gọi crawler, Meta, DeepSeek, Gemini hoặc Qwen; không tác động preview.
- LIMITATION: Đây kiểm tra worker claim của market research và helper Page gate, không thay thế test Redis/Celery hoặc xác minh riêng mọi loại job, scheduler, browser UI và provider live.

### 2026-09-30 20:23 Asia/Ho_Chi_Minh — Kiểm chứng scheduler không tạo lượt nghiên cứu khi Page cần reconnect

- DONE: Thêm PostgreSQL integration cho due research source khi workspace `needs_reconnect`, có group/source/member đã đến hạn.
- PASS: Scheduler không tạo Job hoặc ResearchCycle, trả số job `0`, tắt due time tổng hợp ở group nhưng giữ due time/lịch riêng của source để có thể khôi phục sau reconnect.
- PASS: Toàn `tests/test_postgres_database_integration.py` — `12 passed, 3 skipped` trên PostgreSQL 18.3 disposable; Redis-specific tests vẫn skip vì URL test chưa cấu hình.
- PASS: Ruff, `py_compile`, `git diff --check`.
- DONE: Cụm test cổng `15559` đã dừng. Không gọi mạng ngoài, Meta, AI hoặc preview.
- LIMITATION: Đây là scheduler function trực tiếp trên PostgreSQL, chưa chạy Celery Beat/Redis hoặc UI để quan sát reconnect → lịch được phục hồi.

### 2026-09-30 21:14 Asia/Ho_Chi_Minh — Tự nối lô Page công ty và phục hồi broker

- FIXED: Backfill trước đây lưu cursor rồi chờ lịch 12 giờ cho lô kế tiếp. Worker mới requeue cùng job/cycle ngay sau commit; lô tiếp đọc cursor, không đọc lại trang mới nhất. Báo cáo chỉ được finalize sau khi không còn lô tiếp.
- DONE: Thời điểm quan sát giữ nguyên; `items_saved` đếm observation duy nhất trong PostgreSQL. Lô thành công không tiêu hao retry attempts; timeout 5 phút có số lần thử giới hạn, giữ dữ liệu đã lưu. Một bài cũ xen bài mới không kết thúc cửa sổ; cursor lặp dừng với `pagination_stalled`.
- PASS: `tests/test_postgres_database_integration.py` — **17 passed**, không skip, trên PostgreSQL 18.3 / Redis 8.6.3 disposable. Test Celery mới đọc sáu trang phản hồi Meta fixture qua năm lô, lưu sáu observation cùng timestamp, tạo đúng một report, replay không tạo report thứ hai; lịch vẫn tắt.
- PASS: Fault test tạo Redis riêng trên cổng tạm, xác minh PID sở hữu, dừng đúng process đó sau khi checkpoint commit, rồi xác nhận queued job/checkpoint còn nguyên. Khởi động lại broker và gửi được đúng job qua production dispatcher. Đây chưa phải thử Celery Beat tự phục hồi theo lịch.
- PASS: `tests/test_market_research_api.py tests/test_meta_client.py tests/test_research_privacy.py` — **76 passed**; trong đó năm case mới kiểm tra bài cũ xen bài mới, cursor lặp, dispatch lỗi và giới hạn retry. API tests dùng SQLite fixture; bằng chứng pipeline thật nằm ở suite PostgreSQL/Redis riêng.
- PASS: Ruff, `git diff --check`; không thay HTTP schema, không có migration mới hoặc thay đổi frontend.
- DONE: Các dịch vụ test cổng `15559`, `16481`, `16482` đã dừng; fault Redis riêng kết thúc theo handle của test. API/frontend/workers preview không bị restart.
- NOT_RUN: Meta live, bình luận/replies, media, Gemini/Qwen routing, UI-to-worker và rollout worker mới. Các phần này vẫn còn trong phạm vi nhiệm vụ; không đánh dấu pilot hoàn tất.
- FIXED: Hủy research job giờ khóa bản ghi job, kết thúc research cycle trong cùng transaction và giữ cursor/bằng chứng. Viewer không được hủy; Owner/Editor dùng quyền `market:manage`. Hai case queued/running qua API fixture xác nhận có thể gửi Crawl mới sau khi hủy thay vì bị trả về job cũ.
- PASS: Regression cuối có thêm `tests/test_campaign_workflows.py` đạt **89 passed**; luồng hủy reservation của content generation vẫn đạt sau khi thêm khóa job.

### 2026-09-30 21:43 Asia/Ho_Chi_Minh — Cấu hình Gemini/Qwen qua restart

- DONE: Launcher đọc `secrets/research-ai.env` tùy chọn từ runtime root, chỉ nhận allowlist Gemini/Qwen và yêu cầu quyền owner-only `0600`. API/worker nhận cấu hình; ingestion/Beat/dispatch/probe DeepSeek không nhận các key mới. File mới không ghi đè auth/database/DeepSeek.
- PASS: `tests/test_local_preview_runtime.py` — **8 passed**; test rewrite/reload file loại bỏ key cũ, kiểm tra mọi process mode và file sai quyền. Ruff đạt. Không gọi provider hoặc restart preview.
- BLOCKED_CONFIG: Kiểm tra chỉ có/thiếu cho thấy runtime chưa có key/model Gemini hoặc key/model/region/endpoint Qwen. Không in hoặc sao chép secret; đã yêu cầu model IDs/region, key cần điền trực tiếp trong secret store local.
- IN_PROGRESS: Owned Page comments/replies và media worker chưa nối; privacy hold giữ nguyên. Đây chưa phải nghiệm thu ba provider.
