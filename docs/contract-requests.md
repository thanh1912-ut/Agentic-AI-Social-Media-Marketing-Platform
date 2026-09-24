# HTTP contract mapping — M1 ↔ M2/M3

> Cập nhật: 2026-09-23. Phạm vi đợt này: login/workspace → upload/job → Brand
> Profile. Source of truth cho browser là `packages/contracts/openapi.json`,
> generate bằng `cd apps/web && npm run gen:api -- --from ../../packages/contracts/openapi.json`.
> `packages/contracts/models.py` là contract nội bộ M2↔M3, không dùng để suy ra
> request/response HTTP.

## Trạng thái kiểm tra

- OpenAPI hiện có auth, workspace/member, documents, jobs và Brand Profile;
  `apps/web/src/lib/api/schema.d.ts` được generate từ `packages/contracts/openapi.json`.
  Các HTTP DTO Brand Profile được alias trong `apps/web/src/lib/api/types.ts`;
  không dùng Pydantic contract nội bộ M2↔M3 làm kiểu HTTP.
- `GET /api/v1/me` trả `SessionResponse`; login/refresh/invitation-accept trả
  `LoginResponse`. Backend set cookie phiên HTTP-only; browser không lưu
  `access_token`. Client dùng `credentials: include`, gửi `X-CSRF-Token` khi có
  cookie `agentic_csrf`, và refresh một lần khi endpoint không-auth trả 401.
- Envelope lỗi `{ "error": { code, message, field_errors, request_id,
  retryable, details? } }` và các response 401/403/404/409/422/500 của Brand
  Profile hiện đã có schema trong OpenAPI. Các lỗi upload 400/413/415 và lỗi
  nghiệp vụ job vẫn cần đối chiếu/công bố đầy đủ nếu backend hỗ trợ các status đó.
- API local chưa chạy khi kiểm tra nên chưa xác minh được response runtime/cookie,
  evidence do worker tạo hoặc persist sau reload. Tạo OpenAPI trực tiếp từ Python
  app trong môi trường hiện tại bị chặn bởi thiếu dependency `pgvector`; M1 đã
  dùng artifact OpenAPI do M2 cập nhật và chạy `gen:api` từ artifact này.
- `WorkspaceOut.permissions` là quyền backend cấp; UI chỉ dùng để ẩn/giải thích
  thao tác. Backend vẫn kiểm quyền. `MemberOut.user` nullable/optional khi lời
  mời chưa được nhận; UI xử lý trường hợp đó.

## Endpoint đã map theo OpenAPI

| Màn hình | HTTP | Request | Success response | Ghi chú/status cần M2 công bố |
| --- | --- | --- | --- | --- |
| Login | `POST /api/v1/auth/login` | `LoginRequest {email,password}` | `200 LoginResponse` | Backend set session cookies; response có `access_token` nhưng browser không lưu token. |
| Session | `GET /api/v1/me` | Cookie session | `200 SessionResponse` | `401` khi chưa đăng nhập/hết hạn; client thử refresh một lần. |
| Refresh | `POST /api/v1/auth/refresh` | Cookie refresh | `200 LoginResponse` | Chạy qua API origin/cookie; không gọi lặp vô hạn. |
| Logout | `POST /api/v1/auth/logout` | Cookie session | `204` | Gọi qua API client và chỉ chuyển UI sau khi request revoke thành công. |
| Workspace list/select | `GET /api/v1/workspaces`; `PUT /api/v1/me/active-workspace` | Select: `SelectWorkspaceRequest {workspace_id}` | `WorkspaceOut[]`; `SessionResponse` | PUT yêu cầu CSRF. Backend hiện trả active id theo request, nhưng `GET /me` mặc định workspace đầu tiên; cần M2 xác nhận semantics lưu lựa chọn qua lần tải mới. URL `/w/{id}` giữ workspace đang mở. |
| Members | `GET /api/v1/workspaces/{company_id}/members`; `POST` cùng path | Invite: `InviteMemberRequest {email,role}` | `200 MemberOut[]`; `201 InviteMemberResponse` | `MemberOut.user` nullable/optional. |
| Upload limits | `GET /api/v1/workspaces/{company_id}/documents/limits` | Không có body | `200 UploadLimits` | Gồm max bytes/files, `accepted_kinds`, `accepted_mime_types`. |
| Documents | `GET /api/v1/workspaces/{company_id}/documents`; `GET .../{document_id}` | Không có body | `200 DocumentOut[]` / `DocumentOut` | OpenAPI sinh `extraction_status`, `knowledge_status`, `retrieval_mode` (`lexical/semantic_vector/not_available`) và `profile_status`. UI hiển thị riêng việc đọc, knowledge, retrieval mode và tạo profile; `status=ready` không đồng nghĩa profile đã tạo/xác nhận. `status` và `kind` vẫn là string tự do. |
| Upload | `POST /api/v1/workspaces/{company_id}/documents` | Multipart, field `files` lặp lại; header `Idempotency-Key`; CSRF | `202 AcceptedResponse {job_id,job}` | Backend code có thể trả 400/409/413/415/422; OpenAPI chưa mô tả các response lỗi này. |
| Reprocess | `POST /api/v1/workspaces/{company_id}/documents/{document_id}/reprocess` | Không có body; CSRF | `202 AcceptedResponse` | Quyền `document:upload`. |
| Job | `GET /api/v1/jobs/{job_id}` | Không có body | `200 JobOut` | UI poll khi `queued/running`, dừng ở trạng thái cuối/lỗi/10 phút; `JobOut.error` và `JobStepOut.error` đều là `JobErrorOut`; OpenAPI để `status` tự do và `result` là object không schema. |
| Job events/cancel/retry | `GET .../events`; `POST .../cancel`; `POST .../retry` | `after_seq` query; cancel/retry CSRF | `JobEventOut[]`; `JobOut`; `202 AcceptedResponse` | Chỉ retry khi job báo lỗi có thể retry; không áp dụng retry mù cho kết quả không rõ. |
| Brand Profile read | `GET /api/v1/workspaces/{company_id}/brand-profile` | Cookie session | `200 BrandProfileOut` | `401/403/404/422/500`; 10 field có `key`, `label`, `value?`, `state`, `confidence?`, `provenance?`, `alternatives?`; `version`, completeness và confirmation metadata ở profile. |
| Brand Profile edit | `PATCH /api/v1/workspaces/{company_id}/brand-profile` | `UpdateBrandProfileRequest {version, fields?, confirm?}`; CSRF; `fields[]` là `{key,value}` | `200 BrandProfileOut` | `401/403/404/409/422/500`; 409 là `version_conflict`, `details.current_version` và `details.your_version`; PATCH có thể edit+confirm nguyên tử. |
| Brand Profile confirm | `POST /api/v1/workspaces/{company_id}/brand-profile/confirm` | `ConfirmBrandProfileRequest {version}`; CSRF | `200 BrandProfileOut` | `401/403/404/409/422/500`; đúng revision/version hiện hành, nếu xung đột thì phải tải bản mới. |
| Brand Profile history | `GET .../brand-profile/revisions`; `GET .../revisions/{revision_number}` | Không có body | `BrandProfileRevisionOut[]` / `BrandProfileRevisionOut` | Có profile snapshot, version, warnings và snapshot id; hiện UI chưa nối lịch sử revision trong slice này. |

Provenance HTTP DTO trả `document_id`, `document_name`, `quote`, và locator
tuỳ loại nguồn: `page`, `sheet`, `row`, `char_start`, `char_end`. Alternative
có provenance riêng; mọi locator là optional/nullable theo OpenAPI.

### Trạng thái knowledge/provider và lỗi generation

- `JobErrorOut` trong OpenAPI hiện chỉ cam kết `code: string`, `message: string`,
  `hint?` và `retryable`; chưa có enum hay mô tả ngữ nghĩa mã lỗi. Frontend nhận
  mã lỗi từ API, trình bày các mã chung `provider_not_configured`,
  `provider_model_not_found`, `provider_timeout`/`timeout`, `generation_failed`
  và tương thích các mã worker cũ `ai_not_configured` /
  `brand_profile_generation_failed`. Quyền thử lại chỉ dựa trên `retryable` do
  backend trả.
- Worker hiện giữ mã/retryability của `BrandProfileJobError`; lỗi cấu hình cũ
  `ai_not_configured` vẫn được frontend hỗ trợ như alias. OpenAPI `code` vẫn là
  string tự do, nên **M2 + M3** cần duy trì mapping ổn định cho provider config,
  model-not-found, timeout và generation. Frontend loại bỏ hint cũ nếu nó nhắc
  OpenAI, và hiển thị `provider_model_not_found` riêng theo mã chung.
- `knowledge_status` hiện cho biết `pending/ready/not_available/failed`; OpenAPI
  bổ sung `retrieval_mode` với `lexical/semantic_vector/not_available`. UI hiển thị riêng trạng thái knowledge
  và mode truy xuất. `lexical` nói rõ đang không dùng embedding/vector semantic;
  `semantic_vector` nói rõ mode vector đang bật; `not_available` giữ nguyên là
  chưa khả dụng. Các giá trị này không phải health check riêng cho provider
  embedding và UI không suy đoán nguyên nhân ngoài contract. Nếu job có
  `provider_model_not_found`, retry vẫn do `JobErrorOut.retryable` quyết định.

### Những điểm không được giả làm contract

- `POST /auth/forgot-password`, `POST /auth/reset-password` và
  `GET /auth/invitations/{token}` có response schema rỗng trong OpenAPI. M1 để
  kiểu response là `unknown`, không tự khẳng định các field. UI quên mật khẩu
  chỉ hiện câu xác nhận trung tính sau HTTP success.
- Python code hiện có `DELETE /workspaces/{company_id}/documents/{document_id}`,
  nhưng operation này chưa có trong OpenAPI generate đang dùng. UI xoá tài liệu
  chỉ hoạt động trong mock; real mode không phát request đó.
- OpenAPI `DocumentOut.status`, `DocumentOut.kind`, `JobOut.status` và
  `JobStepOut.status` là `string`; không thể coi chuỗi trong TypeScript fixture
  là enum server đã cam kết.

## Việc còn cần phối hợp để nghiệm thu thật

- M1 đã nối GET/PATCH/POST confirm theo schema generate. Cần chạy API thực tế để
  xác minh status, quyền `brand:edit`/`brand:confirm`, CSRF, lỗi 409 và tải profile
  sau refresh. Endpoint revision history đã có schema nhưng ngoài luồng màn hình
  lần này.
- **M2:** cung cấp API origin truy cập được từ browser, cấu hình CORS credential
  cho origin web/E2E và tài khoản workspace pilot có quyền upload/edit/confirm.
  Xác nhận OpenAPI artifact được tạo từ đúng build backend đang chạy. Chốt status
  scanning/quarantine và response 400/413/415 nếu các trạng thái đó được phát ra.
- **M3 + M2:** xác nhận upload job chỉ trả `succeeded` sau khi extraction/agent
  đã lưu xong revision Brand Profile, hoặc công bố cách chờ/đọc lại khi profile
  còn đang xử lý. E2E real cần seed AI fixture server-side để ổn định và tối thiểu
  một vòng nghiệm thu riêng bằng LLM thật.
- **M2 + M3:** cung cấp HTTP error codes provider-neutral và kiểm chứng thực tế
  các nhánh `provider_not_configured`, `provider_model_not_found`, timeout và
  `generation_failed`; không trả hướng dẫn theo một provider cụ thể. `retrieval_mode`
  đã phân biệt lexical, semantic/vector và chưa khả dụng; không đại diện cho
  health check riêng của embedding provider.

## Yêu cầu tích hợp runtime cần M2 xác nhận

- Frontend cần `NEXT_PUBLIC_API_BASE_URL` là origin đầy đủ, ví dụ
  `https://api.example.vn` — **không** gồm `/api/v1`. `NEXT_PUBLIC_USE_MOCKS=0`
  khi nghiệm thu real mode. M2 xác nhận hai giá trị được đưa vào container lúc
  runtime/build phù hợp với cấu hình Next.js và cung cấp origin mà browser truy cập được.
- API phải cho phép CORS credentials từ origin frontend thật. Cookie access,
  refresh và CSRF phải hoạt động với domain/SameSite/Secure phù hợp; nếu khác
  host cần thống nhất `COOKIE_DOMAIN`, HTTPS và cơ chế browser đọc cookie CSRF.
  `CORS_ALLOWED_ORIGINS` mặc định hiện chỉ gồm hai localhost origin cổng 3000,
  chưa đủ cho real E2E cổng riêng hoặc production domain nếu không override env.
- Backend hiện chưa công bố trạng thái virus/file scanning. Xin M2 chốt status,
  error code, hành vi quarantine và message cho file đang scan/bị từ chối. Các lỗi
  parser đã thấy gồm encrypted/corrupt/PDF không có text layer/unsupported; ảnh
  hiện không có OCR.
- Xác nhận active workspace chỉ là response theo request hay phải persist ở server;
  sau reload, GET `/me` hiện tạo session với workspace đầu tiên.

## Yêu cầu M3 cho lát cắt upload → AI Profile

- Nêu job kind/status/result/event thực tế khi M3 agent được worker gọi; upload
  job thành công có bảo đảm profile revision mới chưa, hay profile có thể chưa sẵn.
- Đảm bảo evidence từ retrieval giữ document id, locator và quote ổn định để HTTP
  DTO của M2 trả provenance có thể kiểm chứng. HTTP schema đã có các field locator,
  nhưng dữ liệu nguồn runtime chưa kiểm chứng được khi API/worker chưa chạy.
- E2E server-side AI fixture có thể dùng để ổn định, nhưng cần một lượt nghiệm thu
  riêng với LLM thật trước khi coi kết quả profile pilot đạt.

## Ngoài phạm vi slice hiện tại

Publishing/Facebook, campaign/approval/export, analytics/metric import và
recommendation chưa được nối real API trong đợt này. Mock hiện có chỉ dành cho
phát triển/E2E demo và phải có nhãn; real mode chặn các trang chưa có contract,
không chuyển API error thành fixture.
