# Security review — core pilot and market research feature

Cập nhật: 2026-09-25. Branch hiện tại: `codex/page-groups-market-research`, code commit `67d4b2c`; lượt rà soát mới nhất gồm các commit kế thừa hardening từ `codex/product-v1-completion` và phần backend market research bên dưới. Review giới hạn ở code/config trong repo; không thay cho penetration test hoặc xác minh cấu hình production/edge.

## Tóm tắt

Đã xác nhận lỗi path traversal qua tên file upload và thiếu CSRF ở refresh/logout dùng cookie. Hai lỗi đã được sửa trong hai commit riêng, có regression tests. Hardening bổ sung chặn Host không được duyệt, giới hạn trusted proxy, body size ở ASGI và bắt buộc HTTPS cho DeepSeek khi chạy production.

Rà soát market research chặn DTD/XML entity kể cả feed UTF-16, thêm Redis limits cho crawl thủ công và xác minh Page token, ẩn credentials khỏi `Settings` repr, đồng thời làm production config fail closed nếu thiếu PostgreSQL/CORS HTTPS origin hoặc còn MinIO credentials mặc định. Python full suite: **190 passed, 1 skipped**. Frontend dependency audit hiện tại: **0 vulnerabilities trên 508 dependency nodes** sau nâng Next.js và `@next/eslint-plugin-next` lên 15.5.26. Theo [security update chính thức ngày 22-09](https://nextjs.org/blog/nextjs-security-update-september-22-2026), 15.5.26 bổ sung hardening liên quan; Next 15.x không bị ảnh hưởng bởi RCE trong advisory đó. Next.js thông báo [15.5.27 ngày 30-09](https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026) để xử lý chín vấn đề khác; re-audit sau khi bản đó có sẵn.

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

### SEC-HOST-001 — Host, proxy và model transport được giới hạn ở production

- **Severity:** Medium.
- **Location:** `services/api/config.py`, `services/api/main.py`, `services/api/__main__.py`, root `docker-compose.yml`.
- **Finding:** API trước đây chấp nhận Host tùy ý, chưa cấu hình rõ nguồn forwarded headers, và cho phép đặt URL DeepSeek qua HTTP kể cả trong production.
- **Fix:** production bắt buộc `ALLOWED_HOSTS` tường minh, cấm wildcard toàn cục và wildcard sai dạng; `TrustedHostMiddleware` từ chối Host ngoài allowlist. `FORWARDED_ALLOW_IPS` chỉ nhận IP/CIDR hợp lệ, Uvicorn chỉ tin các proxy được liệt kê. Production yêu cầu `DEEPSEEK_BASE_URL` dùng HTTPS và URL không chứa credentials/query/fragment.
- **Verification:** production TestClient xác nhận Host lạ trả 400; subprocess tests kiểm tra thiếu/wildcard/multiple wildcard, proxy `*`, entrypoint Uvicorn và DeepSeek HTTP bị từ chối.
- **Limitations:** IP/CIDR phải được thay bằng địa chỉ proxy thật tại deployment; Compose, TLS termination và đường mạng production chưa được chạy ở môi trường này.

### SEC-BODY-001 — Giới hạn tổng request body tại ASGI

- **Severity:** Medium.
- **Location:** `services/api/request_limits.py`, `services/api/config.py`, `.env.example`.
- **Fix:** middleware từ chối `Content-Length` vượt `MAX_REQUEST_BODY_BYTES` trước khi FastAPI parse multipart, đồng thời đếm các chunk khi route đọc body. Default là 256 MiB; cấu hình phải cao hơn `MAX_UPLOAD_BYTES` ít nhất 1 MiB để chừa multipart overhead. API trả lỗi `413 request_too_large` có request ID.
- **Verification:** focused tests bao phủ Content-Length, streamed body, đúng ngưỡng, error envelope và request ID; full suite trên code `c5bb13e` **147 passed, 1 skipped**. Skip duy nhất là live DeepSeek smoke vì chưa có key.
- **Limitations:** reverse proxy/ingress vẫn phải giới hạn request trước khi chuyển traffic vào API để bảo vệ băng thông và kết nối. Compose/runtime chưa được xác minh.

### SEC-MARKET-001 — Đã khắc phục: DTD/XML entity guard bỏ sót UTF-16

- **Severity:** Low.
- **Location:** `services/research/web_crawler.py:240-249`; regression ở `tests/test_market_research_sources.py`.
- **Evidence trước khi sửa:** `_feed_items` chỉ tìm byte ASCII `<!DOCTYPE` và `<!ENTITY`; XML UTF-16 chèn byte NUL giữa ký tự nên vượt qua phép tìm kiếm.
- **Impact:** nguồn RSS/XML công khai có thể vượt qua chính sách từ chối DTD và đưa nội dung entity do nguồn kiểm soát vào parser/trích xuất.
- **Fix:** chuẩn hóa chữ hoa rồi loại byte NUL trước khi kiểm tra cả `DOCTYPE` lẫn `ENTITY`; body nguyên bản vẫn bị giới hạn dung lượng trước khi parse.
- **Verification:** `test_feed_extraction_rejects_xml_entities_and_limits_to_safe_host` xác nhận XML UTF-8 và UTF-16 có DTD đều bị từ chối; toàn bộ Python suite pass.
- **Mitigation:** response vẫn bị giới hạn 2 MiB và chỉ nguồn RSS/XML công khai được parse.
- **False-positive notes:** đây là bypass có thể tái hiện trên guard byte cũ; kiểm tra mới không phụ thuộc encoding UTF-8/16/32 có byte NUL.

### SEC-MARKET-002 — Đã khắc phục: crawl và xác minh Page thiếu hạn mức riêng

- **Severity:** Medium.
- **Location:** `services/api/market_research.py:204-208` và `:417-424`; limiter Redis tại `services/api/rate_limits.py`.
- **Evidence trước khi sửa:** endpoint gọi Meta để xác minh Page và endpoint bắt đầu chu kỳ crawl chưa dùng application rate limit, dù có thể gọi dịch vụ ngoài và kích hoạt phân tích tính phí.
- **Impact:** thành viên có quyền quản lý nguồn có thể lặp các yêu cầu crawl/xác minh quá nhanh, tăng chi phí và tải website/Meta.
- **Fix:** xác minh Page giới hạn 10 lần/giờ; crawl thủ công 6 lần/giờ. Dependency được đặt sau xác thực người dùng/quyền workspace. Production fail-closed nếu Redis limiter không khả dụng.
- **Verification:** route-wiring regression xác nhận hai limiter chạy sau `current_user`; generic limiter tests xác nhận vượt ngưỡng trả 429 và production Redis outage trả 503.
- **Mitigation:** cron 12 giờ vẫn độc lập với hạn mức manual; theo dõi Redis usage và điều chỉnh quotas từ workload pilot.
- **False-positive notes:** giới hạn hiện dùng IP do ASGI cung cấp và chia sẻ giữa người dùng cùng IP; account/workspace quota còn cần đo thực tế.

### SEC-PROD-002 — Đã khắc phục: production cho phép thiếu cấu hình hạ tầng bắt buộc

- **Severity:** Medium.
- **Location:** `services/api/config.py:158-193`; tests tại `tests/test_production_security_config.py`.
- **Evidence trước khi sửa:** production đã bắt buộc Host allowlist nhưng vẫn có thể dùng SQLite, thiếu `CORS_ALLOWED_ORIGINS`, hoặc khởi động với `minioadmin` nếu S3 được bật.
- **Impact:** cấu hình triển khai dễ khởi động với database không phù hợp cho pilot nhiều người dùng, CORS sai/không hoạt động hoặc object storage dùng credentials mặc định.
- **Fix:** production giờ yêu cầu PostgreSQL URL, danh sách CORS rõ ràng gồm HTTPS origins không có wildcard/path/credentials/query/fragment, và credentials S3 khác `minioadmin` khi chọn S3.
- **Verification:** subprocess config tests xác nhận production từ chối SQLite, wildcard CORS và S3 defaults; helper test production dùng PostgreSQL + HTTPS CORS hợp lệ.
- **Mitigation:** các giá trị credentials thực tế phải được cấu hình qua secret store; không ghi chúng vào `.env.example` hoặc Git.
- **False-positive notes:** local development vẫn giữ SQLite/local storage và HTTP CORS origins. Local Compose với `APP_ENV=development` không bị ảnh hưởng.

### SEC-SECRETS-002 — Đã khắc phục: settings repr có thể in thông tin xác thực

- **Severity:** Low.
- **Location:** `services/api/config.py:24-70`; regression tại `tests/test_production_security_config.py`.
- **Evidence trước khi sửa:** dataclass tự sinh `repr` cho database/Redis URL, JWT secret, SMTP username, S3 endpoint/access/secret.
- **Impact:** nếu object settings bị in trong log/chẩn đoán, chuỗi kết nối và credentials có thể lộ.
- **Fix:** các trường này dùng `repr=False`; trường API keys/Page tokens vốn đã ẩn tiếp tục được giữ ẩn.
- **Verification:** test tạo `Settings` bằng các sentinel credentials và xác nhận không sentinel nào có trong `repr`.
- **Mitigation:** tiếp tục tránh ghi nguyên environment/settings object vào log.
- **False-positive notes:** chưa thấy call site hiện tại log toàn bộ object; fix loại bỏ nguy cơ rò rỉ ngoài ý muốn trong tương lai.

## Kiểm tra khác trong phạm vi

- **Tenant authorization:** protected workspace routes kiểm tra active membership; tenant-cross-read được kiểm bằng API integration tests. Chưa chạy test trên PostgreSQL/production policy.
- **Cookie/CSRF:** access/refresh cookie HttpOnly; mọi non-public mutation có dependency CSRF, refresh và logout kiểm tra double-submit token; production yêu cầu Secure cookie. Static route inventory còn 5 public auth writes (`register`, `login`, `forgot-password`, `reset-password`, invitation `accept`) không có CSRF dependency vì chúng không dựa trên cookie session; cần tiếp tục xác minh origin/body controls trên deployment.
- **CORS:** origins lấy từ allowlist cấu hình; methods và headers API dùng allowlist tường minh. Preflight cho header cần thiết pass, header lạ bị từ chối. Production hiện bắt buộc danh sách HTTPS origins cụ thể; cần điền origin triển khai thật.
- **JWT/docs:** access token kiểm tra chữ ký bằng algorithm đã cấu hình và `exp`; docs/OpenAPI bị tắt trong production; test cấu hình JWT yếu pass.
- **Rate limits:** Redis application-level fixed-window limits bao gồm auth, upload, content generation, Meta Page verification và manual market crawl; production fail-closed khi Redis không dùng được. Host allowlist và trusted proxy được kiểm tra trong app/tests; edge limits, Redis runtime, proxy IP thực tế và account-aware quotas chưa được kiểm chứng. Giữ `SEC-001` IN_PROGRESS.
- **Upload/size:** API kiểm MIME/extension, từng file, toàn batch trước storage; parser giới hạn text/table/page/archive/image và đọc theo block 64 KiB. ASGI có aggregate body cap; edge/ingress vẫn cần cap riêng và runtime verification.
- **Frontend sinks:** inline bootstrap script trong `apps/web/src/app/layout.tsx` dùng `dangerouslySetInnerHTML` cho runtime config từ deployment environment; serializer tại `apps/web/src/lib/runtime-config-script.ts` escape `<` và test xác nhận `</script>` không thể đóng script. Content Security Policy vẫn cần chốt khi triển khai.
- **Dependency/infrastructure:** manifest và lockfile dùng Next.js/`@next/eslint-plugin-next` 15.5.26; `npm audit --json` ngày 2026-09-25 báo 0 vulnerabilities/508 dependency nodes. Clean `npm ci`, production build và mock E2E pass. Re-audit sau [Next.js 15.5.27 dự kiến 2026-09-30](https://nextjs.org/blog/upcoming-nextjs-security-release-september-2026). Browser security headers ở edge chưa xác minh; PostgreSQL/MinIO/Compose/proxy-TLS production chưa chạy chung; backup/restore/logging còn giới hạn như phần trên. API production yêu cầu HTTPS cho URL DeepSeek.

## Việc còn lại

1. Đặt Host allowlist/trusted proxy/CORS origins theo deployment; xác minh client IP, edge body/rate limits và account-aware quotas.
2. Hoàn tất CSRF/authorization matrix cho mọi auth/write route và log redaction trên deployment test.
3. Recheck Next.js 15.5.27 và chạy `npm audit` sau khi bản dự kiến 2026-09-30 được phát hành; xác minh dependency patch cùng CI lockfile.
4. Chạy PostgreSQL/MinIO/Compose hardening cùng backup/restore trên môi trường cô lập trước pilot.
