# Phân tích bình luận đã kiểm tra — bằng chứng nghiệm thu

Code kiểm thử: `752af5d8345e8110f24593e2e984113ac4251476`. Ghi nhận: 2026-10-01 18:27 Asia/Ho_Chi_Minh.
Lát cắt này bổ sung phân tích Gemini sau khi Owner chọn/rà soát các đoạn bình luận;
không thay phạm vi thu thập Tier0 và chưa nối kết quả vào report/hướng viết.

## Hành vi và phạm vi dữ liệu

- Owner mở bình luận của bài, chọn/sửa đoạn, ghi tham chiếu đánh giá xử lý/gửi dữ liệu,
  rồi bấm phân tích. Mở màn hình/poll/reload không tự gửi job AI.
- Tham chiếu là hồ sơ quyết định của người vận hành, không phải sự đồng ý của người
  bình luận hoặc chứng nhận pháp lý của nền tảng. Regex vẫn có thể bỏ sót tên người;
  người vận hành phải kiểm tra nội dung được gửi và điều kiện chuyển dữ liệu.
- Một lô tối đa50 bình luận,1500 ký tự/đoạn và12000 ký tự tổng. Không cắt ngầm.
  Chỉ gửi `evidence_ref` và văn bản đã chọn, không gửi alias/author ID/avatar/profile.
- Snapshot lựa chọn bất biến, gắn đúng source/version/observation. Bản kiểm tra được
  mã hóa; job và ledger chỉ giữ ID. Request UUID cùng nội dung dùng lại job; đổi nội
  dung với UUID cũ trả409. Nguồn/decision/policy/Owner thay đổi thì worker từ chối.
- Gemini cố định `gemini-3.8-flash`, không fallback. Dùng ngân sách tự động chung
  2USD/workspace/ngày theo giờ Việt Nam; deferred giữ checkpoint. Timeout không rõ
  chi phí giữ reservation, replay không tự gọi lại.
- Candidate local vẫn tối đa24h. Bản kiểm tra và kết quả tối đa90 ngày; expiry24h
  của quarantine không xóa các phân tích90 ngày còn hợp lệ. Xóa bình luận chỉ vô
  hiệu lô đã dùng bình luận đó; lô khác giữ nguyên. Xóa nguồn/TTL90 ngày xóa bản kiểm
  tra và kết quả liên quan. Phân tích liên kết vào report/campaign chưa triển khai.

## Migration và contract

Head mới `0030_screened_comment_analysis` sau0029; không sửa migration cũ.
Hai bảng mới `research_comment_analysis_batches`, `research_screened_comments`;
composite tenant/source FKs và unique chống replay. Thêm unique tenant/source/id
cho `research_comment_versions`. Migration dùng DDL cố định, forward-only.
Fresh và upgrade so sánh columns/types/defaults/checks/unique/index/FK của ba bảng.
API dưới prefix market-research: POST/GET source/comment-analyses, GET batch riêng.
Đọc/ghi chỉ Owner, CSRF/rate limit, response private/no-store. OpenAPI/TS sinh từ
script repo; không chỉnh generated types bằng tay.

## Ma trận kiểm thử lần này

| Phạm vi | Kết quả | Bằng chứng |
| --- | --- | --- |
| Backend liên quan | PASS | Sáu module:100 passed,6 skipped; sáu case PG-only skip tại biến thể SQLite, cùng case đã chạy trên PostgreSQL |
| PostgreSQL fresh/upgrade | PASS | PostgreSQL18.3 riêng15559; DB fresh và copy0029 upgrade đến0030; schema comparison thật |
| Tenant/roles/replay | PASS | API và SQL cross-tenant; Editor/Viewer không phân tích; duplicate/version/UUID conflict |
| Worker/budget/fence | PASS PostgreSQL | Replay một provider call; reservation uncertain không resubmit; lease lost không ghi; deferred không mất dữ liệu |
| Xóa/retention | PASS | Chỉ lô chứa version bị xóa vô hiệu; lô không liên quan còn nguyên; TTL90 ngày erases output/excerpts |
| Frontend | PASS | Lint, typecheck,11 test ở hai component liên quan; production build real API8001 đạt |
| Contract | PASS | Ruff, staged whitespace, secret pattern scan và OpenAPI --check |
| Browser→Redis/Celery→PG→reload | PASS adapter tổng hợp | Một E2E13.4s trên API18011/web13108, PostgreSQL thật/Redis thật/inline_jobs=0 |
| Gemini native serialization | PASS fixture | Native SDK + httpx.MockTransport;1 call,1 đoạn,0 identity fields/đoạn ngoài lựa chọn |
| Gemini live | NOT_RUN lần này |0 request live; lỗi503 của smoke lịch sử không được thay bằng fixture PASS |
| Facebook live comments | NOT_RUN lần này | Meta tổng hợp; không coi owned adapter fixture là public Tier0 live |
| Report/hướng viết và media | IN_PROGRESS | Chưa nối pinned comment analysis vào report/campaign; media privacy/download/analysis còn thiếu |

Lệnh backend: `python -m pytest -q -p no:cacheprovider tests/test_owned_comment_api.py tests/test_screened_comment_analysis.py tests/test_comment_suppression.py tests/test_research_comment_quarantine.py tests/test_gemini_text_provider.py tests/test_ai_budget.py`.
Đặt `POSTGRES_OWNED_COMMENT_TEST_URL`, `POSTGRES_SCREENED_FRESH_URL`,
`POSTGRES_SCREENED_UPGRADE_URL` trỏ database test riêng; không dùng preview.
Frontend: `npm run lint --workspace=@agentic/web`, `npm run typecheck --workspace=@agentic/web`,
`npm run test --workspace=@agentic/web -- src/components/ScreenedCommentAnalysis.test.tsx src/components/PublicPageComments.test.tsx`,
`npm run build --workspace=@agentic/web` (real API8001, mocks0).
E2E opt-in dùng `E2E_REAL_EXTERNAL_SERVER=1`, `E2E_REAL_PORT=13108`,
`E2E_REAL_API_BASE_URL=http://127.0.0.1:18011`, credential file test riêng và
`npm run test:e2e:real --workspace=@agentic/web -- screened-comment-analysis.real.spec.ts`.

## Evidence pipeline tổng hợp

- Workspace `eb35fca0-281a-4454-b771-0f01e01b5632`, source `a0f70b6a-65b3-4b3a-a810-4b8e2a1c6db2`.
- Crawl job `d1824c0c-beec-488b-84dc-044b174b126c`; analysis job `384e2563-c705-4545-9ad8-cc5bdf7d156d`.
- Batch `e6947ffd-4a01-4cc0-9f63-8278d8d1f272`; pinned version `427a1898-8d77-4484-90fc-30b53f85fa1b`.
-1 dispatch/attempt;1 selected excerpt mã hóa; citation giữ sau reload; lifetime90 ngày.
- Ledger53microUSD từ usage tổng hợp, không phải chi phí thanh toán thật.
- Kết quả/check ảnh local đã làm sạch; credentials/env test không đưa Git.

## Còn lại trong mục tiêu đầy đủ

Nối các analysis IDs bất biến vào research report/hướng viết, erasure/tombstone
lan tới các report/campaign phụ thuộc; hoàn thiện media/download/privacy/TTL và
phân tích theo hash; nghiệm thu provider và Facebook live đúng mức truy cập;
kiểm tra rollout toàn luồng. Không tuyên bố Page-workspace Research hoàn tất.

## Rollout — 2026-10-01 18:28 Asia/Ho_Chi_Minh

PASS: backend schema0029→0030, backup `page-screened-comment-maintenance-20261001T112525Z`;
65 bảng lịch sử giữ đúng số bản ghi, hai bảng mới rỗng. Không tạo live assessment/job.
API8001 ready, hai worker đúng queue và có task registry mới, Page active/owned
schedule off,0queued/running. Hash secret files giữ nguyên. Frontend real release
`codex-page-workspaces-research-752af5d8345e-20261001T112751Z` tại13104, API8001/mocks0.
Release trước còn để rollback.0provider calls trong rollout.

PASS: browser release13104 login/register200,0script errors, không chứa fixture
origin18011. FixtureAPI/worker/web đã dừng theo PID/cwd/port xác minh; credentials
và runtime test-env đã xóa. TestPG/Redis riêng giữ tạm cho chặng report tiếp theo,
không chứa dữ liệu người dùng/secret provider.
