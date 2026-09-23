# Quyết định kỹ thuật

Ngày tạo: 2026-09-23. Trạng thái dưới đây được ghi từ audit đầu; cần cập nhật nếu test/implementation buộc đổi.

## DEC-001 — Modular monolith

- Vấn đề: cần nhiều worker/agent nhưng một sản phẩm v1 nhỏ, tenant/auth/approval phải nhất quán.
- Quyết định: giữ Next.js + FastAPI modular monolith; worker và scheduler chạy process riêng, không tạo HTTP service riêng cho agent.
- Lý do: giữ transaction/job/permission rõ, giảm chi phí vận hành.
- Không chọn: microservices/Kubernetes.
- Ảnh hưởng: API/schema/data lưu PostgreSQL; Redis chỉ queue/cache; file ở local/S3-compatible storage; vận hành mục tiêu 2–5 triệu đồng/tháng chưa được đo.
- Trạng thái: PROVISIONAL, phù hợp Compose/code hiện tại.

## DEC-002 — LangGraph cho workflow bền và có kiểm soát

- Vấn đề: ingest→retrieve→profile cần state, error handling và human confirmation; tương lai content có review/approval.
- Quyết định: giữ LangGraph cho control-flow; agent không được có node/API publish.
- Lý do: cần resume/branch/state có kiểm soát hơn một tool loop đơn giản. Đây là lựa chọn khớp skill `ecosystem-primer`/`langgraph-fundamentals`.
- Không chọn: Deep Agents managed runtime cho core API vì hệ thống cần auth/tenant và custom routes; single agent loop cũng không đủ cho workflow.
- Ảnh hưởng: cần persistence/checkpoint nơi phù hợp; nghiệp vụ và job ledger vẫn lưu trong DB.
- Trạng thái: PROVISIONAL tới khi integration/recovery tests pass.

## DEC-003 — DeepSeek làm provider LLM duy nhất

- Vấn đề: người vận hành dùng DeepSeek API; OpenAI `parse()` không được giả định tương thích chỉ do SDK chung.
- Quyết định: một adapter trong `services/agents/providers/deepseek.py`, worker lấy qua factory; dùng Chat Completions JSON mode + schema/example trong prompt + Pydantic validation, tối đa một repair.
- Lý do: DeepSeek hiện tài liệu hóa `response_format={"type":"json_object"}`; docs hiện liệt kê `deepseek-flash` và `deepseek-v4-pro`. [JSON Output](https://api-docs.deepseek.com/guides/json_mode/), [Models](https://api-docs.deepseek.com/api/list-models/).
- Không chọn: fallback âm thầm sang OpenAI hoặc gọi structured-output helper chưa xác minh.
- Ảnh hưởng: `LLM_PROVIDER`, `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `LLM_DEFAULT_MODEL` cấu hình server-side; lỗi token/model/timeout phải chuẩn hóa; chi phí hiện unavailable khi không có giá/usage được kiểm chứng.
- Trạng thái: adapter IMPLEMENTED; model-account availability và live request NOT_VERIFIED.

## DEC-004 — Embedding độc lập với DeepSeek chat

- Vấn đề: DeepSeek chat docs không chứng minh embedding endpoint tương thích.
- Quyết định: mặc định lexical retrieval (`EMBEDDING_PROVIDER=none`); chỉ bật vector mode với provider riêng, key/model/dimension rõ và reindex migration.
- Lý do: không gửi DeepSeek key sang provider khác và không gắn nhãn lexical là semantic RAG.
- Không chọn: giả định DeepSeek `/embeddings` hoặc service provider không được cấp quyền.
- Ảnh hưởng: hiện semantic RAG chưa bật; vector dimension migration/reindex là điều kiện trước khi bật.
- Trạng thái: lexical path configured; semantic path NOT_CONFIGURED.

## DEC-005 — OpenAPI là contract HTTP cho frontend

- Vấn đề: Python M2↔M3 internal models và TypeScript UI types khác tầng, trùng tên nhưng không nhất thiết cùng nghĩa.
- Quyết định: Pydantic HTTP DTO → FastAPI OpenAPI → generated TS types; internal model map tường minh.
- Lý do: có một nguồn contract HTTP, phát hiện lệch sớm.
- Không chọn: tự suy API type từ internal model hoặc `any`.
- Ảnh hưởng: phải regenerate/check OpenAPI artifacts khi đổi DTO.
- Trạng thái: một phần đã thiết lập cho auth/document/brand; campaign/content contract chưa có backend thật.

## DEC-006 — Manual Meta fallback cho pilot

- Vấn đề: Page permission/App Review/version/token/metrics semantics chưa được kiểm chứng trên app và Page được cấp quyền.
- Quyết định: chưa bật auto publish/sync; export + manual publication/metrics là fallback v1 khi kiểm chứng được.
- Lý do: tránh blind retry POST gây đăng trùng và tránh claim quyền chưa có.
- Không chọn: scraping/browser automation để lách permission.
- Ảnh hưởng: Meta connector trạng thái BLOCKED_EXTERNAL cho tới khi có credentials, quyền và live evidence; user vẫn phân biệt export với publish.
- Trạng thái: cần kiểm tra tài liệu Meta hiện hành và app thực trước khi thiết kế connector.

## DEC-007 — Tạm khóa gửi dữ liệu tenant tới DeepSeek

- Vấn đề: Brand Profile extraction và content generation cần gửi đoạn trích tài liệu/Brand Profile tới nhà cung cấp LLM bên ngoài.
- Quyết định: upload-driven extraction worker fail-closed trước khi tạo provider; generation API trả `503 provider_approval_required`, không tạo job. Không gọi DeepSeek cho tới khi chủ dự án chấp thuận rõ data flow.
- Lý do: auto-review chặn worker định gửi nội dung workspace nhạy cảm tới dịch vụ ngoài và hướng dẫn không tìm đường vòng qua worker hoặc thực thi gián tiếp.
- Ảnh hưởng: local parsing/indexing và fake-agent tests vẫn có thể chạy; live Brand Profile extraction, content generation, latency, token/cost và acceptance flow chưa được nghiệm thu.
- Trạng thái: BLOCKED chờ chấp thuận user; DeepSeek API key cũng chưa được provision trong môi trường test.

## DEC-008 — Cấu hình bảo mật production và PostCSS

- Quyết định: production đòi hỏi JWT secret riêng tối thiểu 32 bytes và `COOKIE_SECURE=1`; API docs/OpenAPI UI tắt trong production. PostCSS được override tối thiểu lên nhánh vá hiện dùng trong lockfile.
- Bằng chứng: production config tests pass; `npm ls postcss --all` cho 8.5.24/8.5.28; npm audit trước đó trả 0 vulnerabilities.
- Trạng thái: IMPLEMENTED; full security review vẫn cần làm.

## DEC-009 — Recommendation là mô tả bằng chứng, không phải nhân quả

- Vấn đề: snapshot quan sát được có thể lệch về pillar, format, tuổi bài hoặc cách thu thập; không đủ để kết luận một thay đổi gây ra hiệu quả.
- Quyết định: tính KPI và nhóm dữ liệu bằng code; chỉ đề xuất thử nghiệm deterministic khi đủ ít nhất 5 bài qua ít nhất 2 pillar, gắn evidence IDs, giới hạn, confidence thấp và bước đo lại. Nếu dữ liệu thiếu thì abstain.
- Không chọn: để LLM tự khẳng định nguyên nhân hoặc tự áp dụng chiến lược/publish.
- Ảnh hưởng: feedback, apply thành revision và theo dõi kết quả thử nghiệm là phần tiếp theo; UI phải giữ rõ đây là đề xuất mô tả.
- Trạng thái: API/UI đề xuất cơ bản IMPLEMENTED; feedback/apply loop INCOMPLETE.
