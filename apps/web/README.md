# apps/web — Frontend (M1)

Next.js 15 (App Router) + React 19 + TypeScript + Tailwind CSS v4 + ECharts.
Toàn bộ giao diện tiếng Việt; định danh trong mã nguồn dùng tiếng Anh.

---

## 1. Lệnh chạy (dành cho M2 viết Dockerfile)

Chạy từ **gốc repo** (npm workspaces):

| Việc | Lệnh |
| --- | --- |
| Cài phụ thuộc | `npm ci` |
| Dev | `npm run dev` |
| **Build** | `npm run build` |
| **Start** | `npm run start` |
| Lint | `npm run lint` |
| Typecheck | `npm run typecheck` |
| Unit test | `npm test` |
| E2E | `npm run test:e2e` |
| Sinh type từ OpenAPI | `npm run gen:api` |

Chạy trực tiếp trong `apps/web`: `npm run build`, `npm start`, `npx tsc --noEmit`.

### Thông số để đóng gói image

| Mục | Giá trị |
| --- | --- |
| Node | `>=22` (đã kiểm với Node 26) |
| Output mode | **`standalone`** (`next.config.ts`) |
| `outputFileTracingRoot` | **gốc repo** — bắt buộc, vì `@agentic/contracts` nằm ngoài `apps/web` |
| Port | **3000** (`next start --port 3000`, `ENV PORT=3000`, `EXPOSE 3000`) |
| Thư mục sau build | `.next/standalone` |
| Start trong container | `node apps/web/server.js` (nếu standalone giữ cấu trúc workspace) hoặc `node server.js` |

### Health path

**Chưa có endpoint health riêng.** Dùng `GET /` và coi `status < 500` là sống:

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000/').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"
```

> Nếu M2 cần một health path rẻ và ổn định hơn `/`, mình sẽ thêm `src/app/api/health/route.ts`
> trả `{"status":"ok"}` — nói một tiếng là mình làm.

### Biến môi trường

Đọc **lúc chạy** (không nhúng vào bundle) nên **một image dùng được cho nhiều môi trường**:

| Biến | Ý nghĩa |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Gốc API, **không** gồm `/api/v1`. Ví dụ `http://api:8000` |
| `NEXT_PUBLIC_USE_MOCKS` | `1` = chạy bằng dữ liệu demo, không gọi backend |
| `NEXT_PUBLIC_ENVIRONMENT_LABEL` | Nhãn hiện trên thanh trên cùng, ví dụ `Bản pilot` |

⚠️ **Tên biến phải đúng chính xác.** Repo tham chiếu từng bị lệch tên
(`WEB_PUBLIC_API_BASE_URL` trong compose nhưng mã nguồn đọc
`NEXT_PUBLIC_API_BASE_URL`), khiến app **âm thầm** rơi về `http://127.0.0.1:8000`
mà không báo lỗi. Nếu tên sai, frontend vẫn chạy nhưng gọi nhầm địa chỉ.

### Bản đồ file để M2 viết Dockerfile

```
apps/web/
├── package.json          # next build / next start
├── next.config.ts        # output: 'standalone', outputFileTracingRoot
├── public/               # COPY vào image (có mockServiceWorker.js)
└── src/app/layout.tsx    # nhúng runtime config vào HTML
```

---

## 2. Quy tắc kiến trúc

1. **Mọi HTTP đi qua `src/lib/api/client.ts`** — đây là nơi duy nhất gọi `fetch`.
   Có test tự động chặn vi phạm (`src/lib/copy-contract.test.ts`).
2. **Không gọi Meta API, không gọi LLM API từ trình duyệt.** Không giữ Meta access
   token ở frontend. Tất cả đi qua backend.
3. **Không tự tính số liệu.** `null` nghĩa là "chưa có dữ liệu" — hiển thị `—` kèm
   lý do, **không** hiển thị `0`.
4. **Không bịa phần trăm tiến độ.** Chỉ hiện % khi backend thật sự báo tổng khối
   lượng; còn lại dùng thanh tiến độ không xác định.
5. **Không bịa tính năng.** Nút nào bị khoá đều phải kèm lý do.
6. **Dữ liệu demo phải mang nhãn** nhìn thấy được.
7. **Xung đột phiên bản (409) không bao giờ tự ghi đè** — chỉ có lối đi "tải bản mới".

## 3. Cấu trúc

```
src/
├── app/                        # App Router, mọi page đều 'use client'
│   ├── layout.tsx              # runtime config + providers + SessionGate
│   ├── login/, forgot-password/
│   └── w/[workspaceId]/        # khu vực làm việc của một doanh nghiệp
├── components/
│   ├── ui.tsx                  # bộ UI dùng chung (badge, tiến độ, lỗi, rỗng…)
│   ├── providers.tsx           # TanStack Query + chính sách retry
│   ├── session-gate.tsx        # cổng phiên + useSession()
│   ├── app-shell.tsx           # điều hướng + nhãn vai trò
│   └── mocking-provider.tsx    # bật MSW trước request đầu tiên
└── lib/
    ├── api/                    # config, client, errors, endpoints
    ├── hooks.ts                # toàn bộ hook dữ liệu
    ├── mocks/                  # seed + handlers MSW (dữ liệu demo)
    ├── permissions.ts          # ẩn/hiện nút + lý do khoá
    ├── format.ts               # định dạng vi-VN
    └── copy-contract.test.ts   # cổng chặn câu chữ sai
```

## 4. Chạy bằng dữ liệu demo

```bash
cp .env.example .env.local
# đặt NEXT_PUBLIC_USE_MOCKS=1
npm run dev
```

Tài khoản demo (mật khẩu `demo1234`):

| Email | Vai trò |
| --- | --- |
| `chu.quan@phobac.vn` | Chủ sở hữu |
| `bientap@phobac.vn` | Biên tập viên |
| `xem@phobac.vn` | Người xem |

Đăng nhập bằng tài khoản khác nhau để kiểm tra giao diện theo vai trò.
