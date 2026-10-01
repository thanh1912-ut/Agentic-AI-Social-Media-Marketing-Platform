# Bình luận Fanpage công ty — bằng chứng kiểm thử

Thời điểm: 2026-10-01 17:27 Asia/Ho_Chi_Minh. Code kiểm thử: `e27f9f996856ffc391fdca3a645eff946c1d3f8d`; schema giữ `0029_comment_suppression`.
Nhánh: `codex/page-workspaces-research`. Không thêm migration, không đổi provider/Tier.

| Phạm vi | Kết quả | Bằng chứng và giới hạn |
|---|---|---|
| Owned Page API/UI | PASS code + fixtures | GET posts/candidates dùng chung endpoint với public Page. Owner xem bản còn hạn; current Page/token/policy/decision được kiểm tra. Public collector không được mở rộng sang Meta vì source stale. |
| Manual comments job | PASS API/PostgreSQL | POST source comments/crawl commit trước dispatch; bấm lặp trả job hiện có. Decision đã đổi không diễn giải lại job cũ. Queue lỗi lưu queue_unavailable; CSRF và quyền Owner giữ nguyên. |
| Phiên bản/pagination | PASS API/PostgreSQL | Latest version được chọn trước availability; phiên mới expired/suppressed không làm lộ bản cũ. Cursor đã đổi phiên trả409. Replies tham chiếu version UUID của cha, không trả external/author IDs. |
| Chỉ số | PASS | NULL khác0; Meta like_count không biến thành reactions. Tổng comments+replies tách khỏi số root comments/provider root-edge count. history_complete luôn false. |
| Backend checks | PASS | 93 tests trong các module owned API, public comments, quarantine, suppression, market API; gồm14 case owned API trên PostgreSQL thật và14 tương ứng SQLite cho regression. Ruff task paths và OpenAPI check đạt. Không coi SQLite là nghiệm thu pipeline. |
| Redis/Celery/durability | PASS test infrastructure | 6 tests PostgreSQL/Redis riêng: cạnh tranh/replay, tenant/24h constraints, stale lease, dispatch lỗi/phục hồi, actual Celery root/reply và suppression/restore; schema fresh/upgrade0029 đối chiếu lại. |
| Frontend | PASS | lint/typecheck;60 tests/6files; build production riêng cho API18011 và8001, mocks0. TypeScript sinh từ OpenAPI bằng script repository. |
| Browser → worker → PG → reload | PASS synthetic Meta | Job `c9998b30-9b28-4696-888c-950b2cb2d409`; workspace `9d09381d-1b1e-4279-bc7b-b3b94652a0b2`; source `e13356e9-e597-422f-8b23-06ea95984ab8`. Bấm nút mới tạo job; Redis/Celery nhận thật, job succeeded/dispatch1/attempt1;3 comment versions,2 root/reply edges,2 receipts. Reload giữ2root+1reply. Like0/4/NULL giữ đúng. |
| Live Meta/public Facebook | NOT_RUN trong slice này | Bài nguồn được seed; phản hồi Meta tổng hợp, không dùng token thật. Không chứng minh90 ngày, bình luận Page thật hoặc đọc hết Tier0. Không fallback Meta để chứng minh public collector. |
| Provider/media/analysis | NOT_RUN / INCOMPLETE |0 provider calls, không tải/phân tích media. Candidate còn privacy_hold, tối đa24h; chưa có release/screening cho Gemini hoặc pin comment/media analysis vào hướng viết. |

Lệnh thực thi, sau khi bật hạ tầng disposable của nhiệm vụ:

```bash
# Không đặt secret thật trong các biến môi trường test.
POSTGRES_OWNED_COMMENT_TEST_URL=postgresql+asyncpg://postgres@127.0.0.1:15559/page_comment_suppression_fresh_final_20261001 \
DEEPSEEK_API_KEY='' GEMINI_API_KEY='' python -m pytest \
  tests/test_owned_comment_api.py tests/test_public_facebook_comments.py \
  tests/test_research_comment_quarantine.py tests/test_comment_suppression.py \
  tests/test_market_research_api.py -q

# DATABASE_URL phải cùng POSTGRES_TEST_URL; REDIS_URL cùng REDIS_QUEUE_TEST_URL.
# Fresh/upgrade databases và Redis test riêng, không dùng database preview.
python -m pytest tests/test_postgres_comment_quarantine.py tests/test_postgres_comment_suppression.py -q
npm run lint --workspace apps/web
npm run typecheck --workspace apps/web
npm run test --workspace apps/web
python scripts/export_openapi.py --check
npm run gen:api
NEXT_PUBLIC_USE_MOCKS=0 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 npm run build --workspace apps/web
```

Browser test: `tests/e2e/owned-page-comments.real.spec.ts`. Cần tenant riêng có Page active,
post frontier/policy/decision fixture và Meta adapter tổng hợp tại worker; API18011/web13108,
queue16481/cache16482, không dùng tenant/token của người dùng. Credential file private0600,
không in password. Đặt `E2E_REAL_EXTERNAL_SERVER=1`, `E2E_REAL_PORT=13108`,
`E2E_REAL_API_BASE_URL=http://127.0.0.1:18011` và `E2E_OWNED_COMMENT_CREDENTIAL_FILE`
rồi chạy `npm run test:e2e:real --workspace apps/web -- owned-page-comments.real.spec.ts`.
Result/screenshot tổng hợp giữ tại `/private/tmp/owned-comment-browser-20261001/`, không đưa vào Git.

Một request control inspect ngay sau restart không nhận đủ hai worker; đây chưa phải bằng chứng
worker đã dừng. Readiness được đọc lại có giới hạn, không tự restart thêm. Kết quả rollout/cleanup PASS được ghi trong verification chính: release `codex-page-workspaces-research-e27f9f996856-20261001T102353Z`,API8001
ready/new route present,2worker đúng queue,Page active/lịchowned tắt,key/model vẫn nạp.
Browser signed-out login/register0script errors,origin8001,không cófixture18011.
Smoke harness sửa selector accessible ban đầu và đọc asset trước navigation; không thay code auth.
Fixtureprocess/database/credentials/test-env và PG/Redis test đã dừng/xóa; preview vẫn chạy.

Toàn bộ mục tiêu Page workspace/Nghiên cứu vẫn còn active. Media, comment release/AI,
retention/xóa lan truyền/provider và full hướng viết cần công đoạn tiếp theo. Không cam kết
Tier1 hoặc Tier0 lấy hết Facebook và không gọi pseudonymization là chứng nhận tuân thủ pháp luật.
