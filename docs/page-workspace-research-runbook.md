# Runbook Page workspace và Nghiên cứu

## Onboarding doanh nghiệp

1. Đăng ký/đăng nhập bằng tài khoản Agentic Marketing. Đăng ký tạo tài khoản và phiên, chưa tạo doanh nghiệp.
2. Ở màn hình chọn doanh nghiệp, Owner nhập Page ID và Page Access Token thuộc đúng Page.
3. Backend đọc Page identity và thử đọc một trang bài công khai; không đăng bài thử. Khi thành công, workspace lấy tên Page, lưu avatar an toàn nếu URL ảnh phù hợp, mã hóa token và tạo Owner/Brand trống.
4. Brand Profile vẫn do Owner tự viết. Page name/avatar chỉ là nhận diện workspace.
5. Thành viên khác tham gia bằng lời mời. Có token không tự cấp quyền thành viên.

API dùng trong vận hành:

- `POST /api/v1/auth/register` — tài khoản/session, không tạo workspace.
- `POST /api/v1/workspaces/from-page` — xác minh Page và tạo workspace.
- `PATCH /api/v1/workspaces/{workspace_id}/page-connection` — Owner thay token cho cùng Page ID; đổi Page cần workspace khác.
- `GET /api/v1/workspaces` — danh sách workspace đã được cấp membership.

Không đưa token vào tài liệu, ticket, browser storage, query string hoặc log. Chỉ nhập trên giao diện kết nối hoặc gửi request qua kênh bảo mật.

## Secrets

- Không dán API key, Page Access Token hoặc cookie vào chat, frontend bundle, Git hay log.
- DeepSeek/Gemini/Qwen chỉ được nạp từ backend secret store/runtime environment.
- Page Access Token phải được mã hóa server-side bằng `META_TOKEN_ENCRYPTION_KEY`.
- Mẫu biến cấu hình sẽ dùng placeholder; file này không chứa giá trị bí mật.

`META_TOKEN_ENCRYPTION_KEY` phải được cấu hình ở backend trước khi Owner kết nối Page. Thiếu khóa trả `token_encryption_unavailable`; không tắt mã hóa để vượt lỗi.

## Kết nối lại Page

- Khi token hết hạn/thu hồi, workspace chuyển `needs_reconnect`; dữ liệu lịch sử vẫn đọc được, tác vụ mới bị chặn. Thời điểm chạy bị xóa nhưng `schedule_enabled` giữ nguyên ý định của Owner.
- Owner mở Cài đặt doanh nghiệp, nhập token mới và giữ nguyên Page ID. Backend xác minh lại trước khi thay token mã hóa.
- Nếu một nguồn đang chạy khi mất kết nối, kết quả dở dang không được coi là hoàn thành. Sau khi Owner xác minh lại đúng Page, lịch nguồn đang bật được đặt đến hạn để scheduler phục hồi; idempotency ngăn chạy trùng. Lịch đã tắt không tự bật.
- Lịch đăng đã quá hạn tuân thủ trạng thái missed hiện có; không gửi bù hàng loạt.
- Publication ở `outcome_unknown` cần Page hoạt động để đối soát; trong lúc token mất hiệu lực, chỉ xem trạng thái hoặc hủy lịch chưa bắt đầu, không xác nhận thủ công khi chưa thể kiểm tra Facebook.
- Khi Page cần kết nối lại, Owner vẫn có thể hủy lịch chưa bắt đầu. Lệnh hủy chỉ yêu cầu membership Owner và CSRF; tạo lịch/đăng mới tiếp tục bị chặn cho tới khi Page active.
- Lịch đồng bộ metrics Meta cũng có thể được Owner tắt khi Page cần kết nối lại. API cho phép đọc trạng thái lịch trong thời gian này; chỉ bật lại sau khi xác minh đúng Page và token.
- Xác minh Page bằng metadata và đọc bài chỉ xác nhận danh tính/quyền đọc bài. API trả `publish_capability=not_tested` cho tới khi có lần xuất bản thành công gắn với token hiện tại; chưa thử đăng không đồng nghĩa chắc chắn Meta sẽ từ chối. Giao diện vẫn cần Owner xác nhận bài đã duyệt, còn Meta quyết định tại lần gửi.
- `can_sync_metrics` trong API cho biết ứng dụng có thể gửi yêu cầu đồng bộ; đây không phải cam kết mọi permission/metric đều có sẵn. UI gọi đây là khả năng “yêu cầu đồng bộ”; trạng thái dữ liệu và metric thiếu vẫn lấy từ kết quả sync thực tế.

## Nghiên cứu

- Mở mục **Nghiên cứu**. Các nhóm database cũ vẫn được giữ; UI/API facade tự đặt nguồn mới vào nhóm nội bộ của workspace.
- Page doanh nghiệp được thêm tự động khi workspace kích hoạt. Các nguồn khác: website công khai, Page Facebook công khai và Group Facebook công khai.
- Bấm Crawl ngay cho nguồn hoặc nhóm nội bộ. Lịch nguồn có thể bật/tắt riêng; mở trang không tự chạy crawl.
- Public Page chạy collector `facebook-cli` Tier 0 hiện có; không đăng nhập. Public Group chỉ có thể trả thông tin nhóm, không có thảo luận Tier 1. Không báo hoàn thành toàn bộ lịch sử.
- Với Group mới, nhập URL trang chủ `https://www.facebook.com/groups/{id-or-slug}`. Bật/tắt lịch trên thẻ nguồn; Crawl ngay chạy dù lịch tắt. Runner chỉ đọc shell metadata công khai qua Tier 0, không gọi feed; run được lưu `partial`, `history_complete=false`, không sinh report từ metadata đơn lẻ. Nếu privacy không xác nhận public, trạng thái là `group_not_public` và lịch không tiếp tục tự thử. Nguồn public Group cần binary tại `FACEBOOK_CLI_RUNNER_PATH` đã build từ bản upstream ghim.
- Bình luận hiện ở trạng thái `privacy_hold`: chỉ số tổng hợp có thể lưu, nhưng text bình luận mới không tải/lưu/gửi cho agent. Endpoint nhập thủ công cũng bỏ qua comment text và trả `comments_withheld_count`. Văn bản bài Facebook và manual import chạy qua `facebook-contact-patterns-v1`, che email, điện thoại và cụm địa chỉ nhà có nhãn rõ; observation ghi số lượng/phiên bản bộ lọc. Bộ lọc không phát hiện tên hoặc mọi kiểu PII, không phải cơ chế ẩn danh. Media chưa có pipeline tải/phân tích.
- Vì vậy, evidence Facebook chưa được gửi dạng tiêu đề/nội dung vào DeepSeek. Report chỉ có Facebook trả `deferred_privacy_review` và không gọi model; report lẫn website chỉ gửi metrics/IDs và nhãn giữ nội dung từ Facebook. Kết quả cache chỉ được phát lại khi fingerprint evidence/version/trạng thái Facebook khớp với lượt hiện tại. Chưa có đường chuyển trạng thái sang `approved_for_provider`.
- Owner có thể xem/ghi nhận cấu hình theo nguồn tại `GET/PUT /api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/privacy-policy`: mục đích, tham chiếu hồ sơ căn cứ, phiên bản chính sách và thời hạn lưu dự kiến (1–365 ngày, mặc định UI 90). Thao tác yêu cầu Owner + CSRF; các revision giữ lịch sử, gửi lại đúng cùng nội dung idempotent.
- Nguồn Facebook mới ở `needs_privacy_policy`; worker và manual import kiểm tra lại mục đích/tham chiếu trước khi xử lý. Khi đủ trường cấu hình, nguồn được mở lại cho collector theo lịch đã chọn. `collection_ready` chỉ có nghĩa là đủ trường; `legal_basis_verified` luôn `false`. Đây không xác minh quyền xử lý, sự đồng ý hay tuân thủ. Nếu tổ chức chưa xác định được căn cứ áp dụng, giữ nguồn tạm dừng thay vì nhập dữ liệu giả để vượt gate.
- Trạng thái response luôn `retention_enforcement_status=not_enforced` và `comments_content_status=privacy_hold`. Thời hạn ở form chỉ là giá trị đã ghi nhận, chưa vận hành xóa nội dung; việc nhập mục đích/căn cứ không chứng minh có quyền xử lý hoặc đồng ý của chủ thể và không mở comment/media sang provider. Audit log không chứa văn bản mục đích/căn cứ.
- Trước khi cho phép xử lý dữ liệu cá nhân, đội vận hành cần tự rà soát văn bản hiện hành và hoàn thành đánh giá pháp lý/tổ chức; ứng dụng không xác minh điều đó. Nguồn tham khảo chính thức: [Luật 91/2025/QH15](https://vanban.chinhphu.vn/?classid=1&docid=214590&pageid=27160&typegroupid=3), hiệu lực 01-01-2026; [Nghị định 356/2025/NĐ-CP](https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-356-2025-nd-cp-468371/61065.htm), hiệu lực 01-01-2026.
- Khi mở một lượt public Facebook mới, worker chụp ID/no/version và thời hạn yêu cầu của policy revision mới nhất vào `WebCrawlRun.config_json`. Đây là provenance bất biến theo lượt; chỉnh policy về sau không sửa lịch sử lượt cũ. Nếu lượt không có policy, API trả trường revision rỗng. Cả hai trường hợp vẫn giữ `privacy_hold`/`not_enforced`.
- Campaign tạo từ hướng viết của báo cáo giữ `report_id`, evidence version, observation, content hash và metrics cụ thể. Worker dùng pin đó; nếu report không có pin hoặc source đã tắt/xóa thì dừng để người dùng chọn lại. Comment text không được đưa vào Content Agent.
- Báo cáo DeepSeek mới dùng hồ sơ `manual_text_v1` của Owner chỉ khi đó là revision hiện hành đã áp dụng; report JSON và coverage giữ `brand_id`, `revision_id` và số revision. Campaign draft lưu provenance này để giữ đúng ngữ cảnh lịch sử. Hồ sơ legacy/AI cũ không được gửi làm hướng dẫn thương hiệu. Nếu chưa có hồ sơ Owner, báo cáo vẫn có thể phân tích nguồn nhưng phải ghi rõ chưa cá nhân hóa.
- Các giá trị nội bộ `Chưa xác định`, `unknown`, `not specified` và `n/a` không được biến thành audience hay market scope. Nếu chưa khai báo ngành/vùng rõ ràng, brief tạo từ report để audience rỗng thay vì bịa chân dung khách hàng.
- Snapshot website được chọn cũng phải thuộc cùng report/tenant và source còn active; worker chuyển phần dữ liệu đã allowlist (không kèm URL ảnh ký tạm) vào Content Agent, rồi xác minh lại các pin trước khi lưu draft.
- Lỗi nguồn mới không được xóa kết quả nguồn thành công trước đó.
- Raw research payload nếu cần quarantine được gắn hạn xóa tối đa 24 giờ; scheduler xóa object đến hạn. Nội dung nghiên cứu chuẩn hóa 90 ngày, media 30 ngày và propagation khi có yêu cầu xóa vẫn chưa được triển khai đầy đủ; không coi raw TTL hoặc trường thời hạn trong policy form là cơ chế xóa dữ liệu cá nhân hoàn chỉnh.

## Adapter Qwen đang ở trạng thái fixture-only

Adapter text yêu cầu `QWEN_API_KEY`, `QWEN_MODEL` và `QWEN_BASE_URL` do quản trị viên cung cấp từ secret store/runtime. `QWEN_BASE_URL` phải là HTTPS endpoint Model Studio đúng region/workspace; không dùng endpoint giả định. Có thể cấu hình `QWEN_MAX_TOKENS`, còn giới hạn input dùng `LLM_MAX_INPUT_CHARS`. Qwen chỉ có method `summarize_screened_comments(PrivacyApprovedCommentBatch)`; đường `generate` tổng quát bị khóa. Batch cần policy decision/version và run-scoped evidence refs, không có trường author/profile; decision ID/version chỉ dùng nội bộ, không gửi model. Adapter kiểm tra mọi citation trả về có trong batch và tắt repair/retry để tránh lời gọi chưa reserve chi phí. Hiện chưa có route gọi adapter từ pipeline bình luận, chưa có Qwen pricing entry trong ledger và chưa có key/region đã nghiệm thu. Không bật bằng cách chỉ đặt ba biến; trước hết cần privacy-approved comment batch và mức giá phù hợp model/region. Xem [endpoint OpenAI-compatible chính thức](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions) và [quy tắc JSON output](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen-structured-output); model/region/pricing phải được xác nhận cho đúng tài khoản.

## Adapter Gemini đang ở trạng thái fixture-only

Media adapter yêu cầu `GEMINI_API_KEY` và `GEMINI_MODEL` tường minh; không có model mặc định hoặc fallback. Chỉ nhận byte ảnh/video đã được service gọi đánh dấu privacy-approved, có SHA-256, source/evidence IDs và MIME allowlist; cờ đó là kiểm tra phòng thủ, không thay thế quyết định pháp lý/căn cứ xử lý của tầng sở hữu dữ liệu. Adapter không nhận URL, không tải asset, không gọi Files API, không tự sửa output và không retry. Asset tối đa mặc định 10 MiB, tổng JSON request không quá 20 MiB; video lớn/dài bị từ chối chờ tích hợp upload/deletion/budget phù hợp. `estimated_cost_usd` chưa có giá trị thực, `cost_estimate_available=false`; không nối vào pipeline tự động trước khi ledger giữ reservation theo model/usage. Tài liệu Google mô tả giới hạn inline và Files API cho asset lớn/tái sử dụng: [video](https://ai.google.dev/gemini-api/docs/video-understanding), [ảnh](https://ai.google.dev/gemini-api/docs/image-understanding), [structured output](https://ai.google.dev/gemini-api/docs/structured-output).

## Trạng thái ban đầu

- Account-only registration, Page-based workspace activation và reconnect được triển khai trong nhánh này; vẫn cần kiểm chứng migration trên PostgreSQL thật.
- UI Nghiên cứu không yêu cầu người dùng chọn nhóm. Cấu trúc lưu trữ legacy vẫn group-scoped.
- Qwen/Gemini adapters có fixture nhưng chưa nối; video/image collection, comment processing/erasure chưa triển khai.

## Thao tác vận hành

Không bật xử lý comment/media từ cờ thủ công. Trước khi mở các chức năng này cần xác định mục đích/căn cứ xử lý, thời hạn, quy trình quyền xóa, vùng provider và kiểm thử deletion end-to-end. Đây là yêu cầu vận hành/pháp lý, không thể thay bằng regex hoặc checkbox.

## Phần chưa sẵn sàng

- Gemini và Qwen chưa có model ID/region/key được xác minh hoặc routing production; DeepSeek hiện là adapter cho báo cáo Nghiên cứu. Không tự fallback giữa provider.
- Ledger hiện áp dụng cho báo cáo Nghiên cứu DeepSeek tự động; chưa bao phủ Gemini/Qwen, media hoặc mọi call AI tự động khác. Trang Nghiên cứu đọc số liệu qua `GET .../market-research/ai-budget`; báo cáo hoãn hiện chỉ được hiển thị, chưa có tác vụ tự lên lịch chạy lại.
- Chưa tải hay gửi ảnh/video đến provider; không tuyên bố media analysis đã chạy.
- Không có full comment pagination/replies hoặc database checkpoint mới. Coverage là `privacy_hold`/Tier 0 partial.
- Không tự nhận hệ thống tuân thủ đầy đủ Luật 91/2025/QH15 hoặc Nghị định 356/2025/NĐ-CP.

## Kiểm thử/deploy

- Backend API: dùng lệnh service/test đã cấu hình của checkout, không bật `AUTO_CREATE_SCHEMA` hay inline jobs để nghiệm thu.
- Migration phải chạy `alembic upgrade head` trên database test riêng trước rollout; không chạy rollback phá lịch sử.
- Đừng thay API/workers đang phục vụ preview. Drain worker cũ trước khi thay backend và giữ snapshot/rollback tương thích Page gate.
- Cấu hình key dạng placeholder trong secret store: `DEEPSEEK_API_KEY=<secret>`, `GEMINI_API_KEY=<secret>`, `QWEN_API_KEY=<secret>`; hiện chỉ adapter DeepSeek đang được dùng.

### Ngân sách AI tự động hiện có

- Mặc định `AUTO_AI_DAILY_BUDGET_MICRO_USD=2000000` (2 USD/workspace/ngày Việt Nam); cấu hình thấp hơn được phép, cao hơn cap sản phẩm bị từ chối khi nạp settings.
- Ledger nằm trong `ai_usage_budget_days` và `ai_usage_ledger`. Mỗi research cycle có idempotency key; worker không gọi lại khi kết quả đã lưu hoặc kết quả provider trước chưa rõ.
- Structured report chỉ được giữ trong ledger như recovery copy cho tới khi `MarketReport` commit; cùng transaction đó xóa bản sao ledger.
- DeepSeek dùng giá peak/cache-miss và upper bound cho đầu vào cùng một lần repair. Bảng đã ghi nhận `deepseek-flash`, `deepseek-v4-pro`, `gemini-3.8-flash` và `qwen3.8-27b`; phiên hiện tại là `provider-public-pricing-2026-09-30-v2`.
- Gemini `gemini-3.8-flash`: $0.75/1M input và $3.75/1M output theo giá Standard introductory, chỉ đến hết 2026-12-31; sau ngày đó helper từ chối giá cũ cho tới khi được rà soát lại. Nguồn: [Google Gemini model update](https://ai.google.dev/gemini-api/docs/latest-model) và [bảng giá Gemini](https://ai.google.dev/gemini-api/docs/pricing).
- Qwen `qwen3.8-27b`: $0.50/1M input và $3/1M output theo deployment International tại Singapore; dùng full list price, không trừ free quota/khuyến mại. `price_for` bắt buộc `region=singapore`; region khác trả `pricing_region_unverified`. Nguồn: [Alibaba Model Studio pricing](https://www.alibabacloud.com/help/en/model-studio/model-pricing) và [trang model Qwen3.8-27B](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/qwen3-8-27b).
- Gemini/Qwen vẫn chưa được gọi từ worker. Reservation của provider ngoài DeepSeek yêu cầu caller truyền giới hạn token tường minh; với media, character count không phải upper bound an toàn. Tích hợp phải tính cả retry/attempt trước khi mở pipeline.
- Đây chưa phải cap chung cho mọi agent: chỉ báo cáo nghiên cứu tự động DeepSeek đã nối vào ledger; Gemini/Qwen, media và các tác vụ tự động khác vẫn chưa được route qua budget.
- DeepSeek rates: [bảng giá DeepSeek chính thức](https://api-docs.deepseek.com/quick_start/pricing/). Giá là snapshot đã ghi nhận; model/rate ngoài bảng fail closed.
- Nếu usage thiếu hoặc không xác định được model trả về, ledger giữ reservation ở `unknown`; không tự nhả ngân sách hay gọi lặp. Đối soát hiện chưa có giao diện.

### PostgreSQL/Redis test cách ly của lần xác minh này

Các lần test integration dùng cluster tạm dưới `/private/tmp/agentic-page-workspaces-it-20260930`, chỉ bind loopback; không dùng database/queue của preview. PostgreSQL nghe cổng `15433`; cluster riêng cho đường upgrade `0021 → 0022` nghe cổng `15543`; Redis queue `26379` và cache `26380`. Redis test không bật persistence và không chạy worker. Các tiến trình này đã được dừng sau kiểm thử.

Khi không còn cần chạy integration trong phiên làm việc, dừng đúng các tiến trình test bằng:

```bash
/opt/homebrew/bin/pg_ctl -D /private/tmp/agentic-page-workspaces-it-20260930/pgdata -m fast -w stop
/opt/homebrew/bin/pg_ctl -D /private/tmp/agentic-page-workspaces-it-20260930/pgdata-budget -m fast -w stop
/opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 26379 shutdown
/opt/homebrew/bin/redis-cli -h 127.0.0.1 -p 26380 shutdown
```

Không dùng các lệnh này nếu đã tái sử dụng các cổng cho tiến trình khác; xác minh tiến trình/cổng trước khi dừng.

### Phục hồi chu kỳ nghiên cứu

- Kết quả từng nguồn trong `research_cycles.source_results_json` được commit sau khi xử lý xong nguồn. Nếu job vẫn ở trạng thái đang chạy khi worker bị gián đoạn, lần nhận lại bỏ qua nguồn đã checkpoint; nguồn đang dở hoặc có kết quả retryable được thử lại.
- Với nguồn `owned_facebook_page`, migration `0025_owned_page_research_backfill` bổ sung cursor và coverage 90 ngày. Mỗi source-run xử lý tối đa 100 bài; trong lúc backfill dùng 50 bài mới nhất và 50 bài theo cursor lịch sử. Khi còn cursor, lượt đến hạn sau 12 giờ tiếp tục từ cursor đó. Sau khi hết lịch sử, lượt sau làm mới 100 bài mới nhất. Page ID được lưu cùng cursor; khi danh tính Page khác đi thì cursor cũ bị reset. Cờ `owned_page_backfill_window_complete` giữ lại kết quả coverage 90 ngày sau các lượt refresh.
- `research_cycles.collection_observed_at` được ghi trước khi worker bắt đầu thu thập và dùng lại khi job cùng cycle được phục hồi, để replay giữ cùng identity cho evidence/observation. Bản ghi cursor chỉ cập nhật sau khi các bài ở batch đã persist.
- Job result ghi `history_complete`, `window_coverage_complete`, `coverage_status`, `oldest_post_at`, `unknown_published_at_count`, `stop_reason` và cờ có checkpoint kế tiếp. `provider_history_exhausted_before_90_days` là kết quả một phần, không được báo đủ 90 ngày; ngày đăng thiếu vẫn được tính riêng.
- Lịch của nguồn Page công ty bật/tắt trong Nghiên cứu qua `collection-settings`; collector bị khóa ở `meta_api`. Crawl ngay vẫn dùng được khi lịch tắt. Bình luận/replies chưa có cursor và vẫn `privacy_hold`; media binary/AI chưa được triển khai.
- Lượt Facebook công khai ghi policy revision được quan sát khi bắt đầu nguồn, cùng `comments_content_status=privacy_hold` và `retention_enforcement_status=not_enforced`. Snapshot là provenance, không phải bằng chứng có căn cứ xử lý hoặc xóa dữ liệu tự động.

### Đồng bộ tên và ảnh Page

- Owner mở Cài đặt doanh nghiệp → Fanpage → **Đồng bộ tên và ảnh từ Fanpage**. API chỉ dùng token đã mã hóa phía server, xác minh lại Page ID và gọi đọc bài ở chế độ chỉ đọc.
- Nếu thành công, tên được cập nhật cho workspace, Meta connection và nguồn Page; ảnh đại diện cập nhật theo metadata Meta. Brand Profile do Owner viết không đổi.
- Nếu Meta báo token hết hạn/thiếu quyền, workspace chuyển sang `needs_reconnect`; tác vụ bị tạm dừng, thời điểm đến hạn được xóa nhưng lịch đã bật của Owner vẫn được giữ để phục hồi sau reconnect. Dữ liệu cũ vẫn đọc được. Owner dùng biểu mẫu **Xác minh lại Fanpage** với token mới của đúng Page.
- API không trả token và không thử đăng bài. Metadata refresh không chứng minh Page có quyền publish.

### Nguồn Nghiên cứu khi Page cần kết nối lại

- Các báo cáo và dữ liệu đã lưu vẫn đọc được; crawl, thêm nguồn, bật lịch và tạo chiến dịch từ báo cáo bị khóa tới khi Owner xác minh lại Page.
- Người có quyền quản lý nguồn có thể tắt lịch đang bật hoặc chọn **Ngừng theo dõi** để soft-disable nguồn. Thao tác này không xóa dữ liệu đã thu thập, evidence hay snapshots; yêu cầu xóa dữ liệu phải đi qua quy trình xóa riêng.
- Khi Page đã kết nối lại, Owner/Editor có thể bật lịch hoặc chạy Crawl ngay theo quyền hiện có. Không có job nào được gửi tự động chỉ vì mở trang.

### Link và attachment metadata của bài Page

- Migration `0024_page_post_media_references` bổ sung `link_url`, `attachments_json` và `attachment_metadata_status` cho bài của Page công ty.
- Metadata gồm loại attachment và link đích đã bỏ query/fragment; không lưu binary media, URL CDN có chữ ký, title hoặc description tự do. Link chỉ được hiển thị cho người dùng mở; ứng dụng không tự fetch link đó.
- `metadata_only_privacy_hold` nghĩa là hình/video chưa được kiểm tra điều kiện riêng tư và chưa tải hoặc gửi sang Gemini. Không coi loại attachment hoặc link là phân tích media hoàn tất.
- Nếu Meta từ chối các trường attachment, collector lấy lại các trường bài/metrics ổn định và lưu `not_returned`; dữ liệu bài đọc được vẫn giữ.
- Có thể kiểm tra API metadata trong Nghiên cứu hoặc Analytics. Dữ liệu cũ chưa được backfill, nên trạng thái lịch sử mặc định là `not_returned`.
