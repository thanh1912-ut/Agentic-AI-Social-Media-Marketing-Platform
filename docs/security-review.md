# Security review — core pilot

Cập nhật: 2026-09-24. Branch: `codex/product-v1-completion`; fixes at `d9cb6a8`, `1e1589f` and rate-limit implementation `004020e` are pushed, base `origin/main` at `07938bd`.

## Tóm tắt

Đã xác nhận lỗi path traversal qua tên file upload và thiếu CSRF ở refresh/logout dùng cookie. Hai lỗi đã được sửa trong hai commit riêng, có regression tests. Review này giới hạn ở app/API hiện có; không thay cho penetration test hoặc xác minh cấu hình production/edge.

## Finding

### SEC-FILE-001 — Đã khắc phục: upload filename cho phép path traversal

- **Severity:** High.
- **Location:** `services/api/documents.py:123` chuẩn hóa tên hiển thị; `services/api/documents.py:168` sinh key bằng UUID; `services/api/storage.py:12-40` kiểm segment và containment trước khi local ghi/đọc; `services/api/storage.py:73-79` kiểm key S3.
- **Evidence trước khi sửa:** upload tạo key `company_id/source_hash/filename`; `LocalObjectStorage.put` ghép `root / key` mà không gọi kiểm tra containment. Tái hiện trong thư mục tạm bằng `put('../outside.txt', ...)`: tệp được tạo ở sibling của storage root.
- **Impact:** người dùng đã đăng nhập có thể điều khiển tên file để ghi tệp ra ngoài thư mục object storage, trong giới hạn quyền filesystem của tiến trình API/worker.
- **Fix:** client filename không còn tham gia storage key; metadata chỉ lưu basename. Adapter từ chối key rỗng, tuyệt đối, có NUL, backslash, segment trống, `.` hoặc `..`; local storage resolve path và buộc nằm dưới root.
- **Verification:** `tests/test_storage_security.py` và `test_upload_filename_is_not_used_as_storage_path`; security-focused suite **18 passed**, toàn bộ Python suite **92 passed, 1 skipped** on `1e1589f`.
- **Mitigation:** triển khai commit có sửa lỗi trước khi nhận upload tenant; nếu phát hiện record cũ có key bất thường, key đó sẽ bị từ chối và cần upload lại tài liệu gốc.
- **False-positive notes:** không phải false positive; traversal được tái hiện bằng write ra ngoài temp storage root trước sửa.

### SEC-CSRF-001 — Đã khắc phục: refresh/logout cookie session thiếu CSRF validation

- **Severity:** Medium.
- **Location:** `services/api/auth.py:133-153` bảo vệ refresh/logout; `services/api/dependencies.py:87-99` yêu cầu token nếu access hoặc refresh cookie có mặt; `apps/web/src/lib/api/client.ts:92-104` gửi token khi refresh.
- **Evidence trước khi sửa:** hai auth route thay đổi session bằng `agentic_refresh` nhưng không gọi `require_csrf`; dependency CSRF trước đó chỉ xét access cookie và bỏ qua mọi request có Authorization header. Refresh handler vẫn dùng refresh cookie kể cả khi có header này.
- **Impact:** browser request mang refresh cookie có thể renew/revoke session mà không chứng minh intent của app. Cách khai thác thực tế còn phụ thuộc cookie SameSite, site/origin và proxy configuration.
- **Fix:** route refresh và logout dùng `require_csrf`; access hoặc refresh cookie đều kích hoạt kiểm tra, và Authorization chỉ bỏ qua CSRF khi không có cookie session. Client gửi `X-CSRF-Token` trên refresh.
- **Verification:** `test_refresh_and_logout_require_csrf_for_cookie_sessions` xác nhận access-cookie-expired/refresh-only vẫn đòi token, bogus bearer không bypass, token đúng refresh thành công, logout revoke session. `apps/web/src/lib/api/client.test.ts` xác nhận client gửi token. Focused API tests **4 passed**, frontend test **1 passed**.
- **Mitigation:** giữ secure, SameSite cookie flags và CORS origin allowlist; rà soát toàn bộ state-changing auth routes trước pilot public.
- **False-positive notes:** route handlers đọc refresh cookie trực tiếp; bearer auth không thay thế cookie này nên cần CSRF validation.

### SEC-RATE-001 — Đã thêm Redis rate limit cho route nhạy cảm

- **Severity:** Medium.
- **Location:** `services/api/rate_limits.py`; cấu hình Redis ở `services/api/main.py`; route declarations trong `services/api/auth.py`, `services/api/documents.py` và `services/api/campaign_workflows.py`.
- **Finding:** trước thay đổi, các route login, đăng ký/reset mật khẩu, accept invitation và upload không có application-level rate limit; host/edge limit chưa có bằng chứng.
- **Fix:** atomic Redis Lua fixed-window counter theo scope và địa chỉ `request.client.host` đã hash. Hạn mức hiện tại: đăng ký 5/giờ, login 15/15 phút, quên mật khẩu 5/giờ, reset 10/giờ, accept invitation 10/15 phút, upload 30/giờ, sinh nội dung 20/giờ. Development mặc định tắt; production mặc định bật và từ chối khởi động nếu bị tắt. Redis lỗi làm route giới hạn trả `503` trong production; development ghi cảnh báo và fail-open.
- **Verification:** `tests/test_rate_limits.py` kiểm tra disabled mode, ngưỡng `429`, key không chứa IP thô, production fail-closed và development fail-open; `tests/test_production_security_config.py` kiểm tra production cấm tắt limiter. Toàn bộ Python suite trên `004020e`: **96 passed, 1 skipped**; skip là live DeepSeek smoke.
- **Limitations:** rate limit chưa được kiểm tra trên Redis/Compose production. Key dựa trên địa chỉ mà ASGI server cung cấp; nếu đặt sau reverse proxy, cần cấu hình trusted proxy/forwarded headers đúng tại server để phân biệt client. Không tin `X-Forwarded-For` từ nguồn không được tin cậy. Fixed window cho phép burst ở ranh giới hai cửa sổ. Edge/WAF limit và account-aware login throttling vẫn cần quyết định/kiểm tra.

## Kiểm tra khác trong phạm vi

- **Tenant authorization:** protected workspace routes kiểm tra active membership; tenant-cross-read được kiểm bằng API integration tests. Chưa chạy test trên PostgreSQL/production policy.
- **Cookie/CSRF:** access/refresh cookie HttpOnly; mọi non-public mutation có dependency CSRF, refresh và logout kiểm tra double-submit token; production yêu cầu Secure cookie. Static route inventory còn 5 public auth writes (`register`, `login`, `forgot-password`, `reset-password`, invitation `accept`) không có CSRF dependency vì chúng không dựa trên cookie session; cần tiếp tục xác minh origin/body controls trên deployment.
- **CORS:** origins lấy từ allowlist cấu hình; methods và headers API dùng allowlist tường minh. Preflight cho header cần thiết pass, header lạ bị từ chối. Cần xác nhận origin allowlist theo deployment tại edge trước pilot public.
- **JWT/docs:** access token kiểm tra chữ ký bằng algorithm đã cấu hình và `exp`; docs/OpenAPI bị tắt trong production; test cấu hình JWT yếu pass.
- **Rate limits:** Redis application-level fixed-window limits đã được thêm cho auth, upload và content generation; production fail-closed khi Redis không dùng được. Cấu hình host/proxy, edge limits, Redis runtime và account-aware login throttling chưa được kiểm chứng. Giữ `SEC-001` IN_PROGRESS.
- **Upload/size:** API giới hạn từng file và số file mỗi request; chưa có bằng chứng request-body aggregate limit ở reverse proxy.
- **Frontend sinks:** inline bootstrap script trong `apps/web/src/app/layout.tsx` dùng `dangerouslySetInnerHTML` cho runtime config từ deployment environment; serializer tại `apps/web/src/lib/runtime-config-script.ts` escape `<` và test xác nhận `</script>` không thể đóng script. Content Security Policy vẫn cần chốt khi triển khai.
- **Dependency/infrastructure:** npm audit lần kiểm gần nhất không báo vulnerability; PostgreSQL, MinIO, Compose, reverse-proxy headers, TLS, backup/restore và production logs chưa được kiểm chứng trong runtime.

## Việc còn lại

1. Xác minh ASGI client IP qua trusted proxy, edge limits và CORS origin allowlist theo deployment; đánh giá account-aware login throttling.
2. Hoàn tất CSRF/authorization matrix cho mọi auth/write route, request-size limit toàn request và log redaction trên deployment test.
3. Chạy PostgreSQL/MinIO/Compose hardening cùng backup/restore trên môi trường cô lập trước pilot.
