# Creative Studio UI — rollout và rollback

## Cấu hình frontend

Preview dùng bản real mode:

- Web: `http://127.0.0.1:13104`
- API: `http://127.0.0.1:8001` — `NEXT_PUBLIC_API_BASE_URL` không có `/api/v1`.
- `NEXT_PUBLIC_USE_MOCKS=0`
- Không cần đưa DeepSeek key, Meta token, database URL hoặc cookie vào frontend.

Font Be Vietnam Pro được phục vụ từ `public/fonts/be-vietnam-pro/`; runtime không cần truy cập CDN.

## Build và kiểm tra trước khi kích hoạt

Từ `apps/web` của worktree đã checkout:

```bash
NEXT_PUBLIC_USE_MOCKS=0 \
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8001 \
NEXT_PUBLIC_ENVIRONMENT_LABEL='API thật' \
npm run build
node scripts/prepare-standalone.mjs
python3 scripts/creative-studio-preview.py status
```

`status` chỉ báo API/frontend có sẵn, LaunchAgent có nạp hay không và release hiện hành; không in giá trị bí mật.

## Kích hoạt đúng frontend preview

```bash
python3 scripts/creative-studio-preview.py activate
python3 scripts/creative-studio-preview.py status
```

Script tạo bản standalone bất biến ở `~/.local/share/agentic-marketing/frontend-releases/`, sao lưu plist hiện tại, rồi chỉ thay LaunchAgent `com.agentic-marketing.auth-preview-web`. Nó xác nhận API `/readyz`, trang `/login` và font local trước khi báo thành công. Nếu khởi động lỗi, script tự khôi phục plist cũ.

## Rollback

```bash
python3 scripts/creative-studio-preview.py rollback
python3 scripts/creative-studio-preview.py status
```

Rollback nạp lại plist đã lưu và giữ cả release mới lẫn cũ để có thể kiểm tra. Không xoá thư mục release cũ trong lúc cần rollback.

## Kiểm thử browser

Fixture desktop (mock có nhãn, không phải dữ liệu doanh nghiệp thật):

```bash
CREATIVE_STUDIO_SCREENSHOT_DIR=../../docs/creative-studio-ui/screenshots \
E2E_PORT=13106 npm run test:e2e -- --project=desktop-chromium
```

Chụp riêng trang đăng nhập của preview real mode mà không nhập thông tin tài khoản:

```bash
E2E_REAL_API_BASE_URL=http://127.0.0.1:8001 \
E2E_REAL_PORT=13104 \
E2E_REAL_EXTERNAL_SERVER=1 \
CREATIVE_STUDIO_REAL_SCREENSHOTS=../../docs/creative-studio-ui/screenshots \
npm run test:e2e:real -- --grep='chụp màn hình đăng nhập'
```

Không chạy lệnh installer tổng hợp cho API/worker/Beat khi chỉ triển khai UI. Khi cần kiểm thử thao tác ghi thật, dùng workspace kiểm thử riêng; không reset tài khoản hoặc nội dung của người dùng. Không gọi DeepSeek, crawl live hay đăng Facebook để kiểm thử thiết kế.
