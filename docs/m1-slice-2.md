# M1 vertical slice: Campaign → Approval → Export

## Demo flow

1. Đăng nhập bằng tài khoản Owner demo.
2. Mở **Chiến dịch và lịch nội dung**.
3. Mở campaign `cmp_khai_truong` để xem brief và content calendar.
4. Mở bài viết, chỉnh caption, lưu version mới, rồi gửi duyệt.
5. Owner duyệt hoặc reject đúng version; lịch sử version hiển thị source và trạng thái.
6. Tạo export CSV/XLSX. UI chuyển sang job progress và không gọi kết quả export là đã đăng.

## Frontend routes

- `/w/{workspaceId}/campaigns`
- `/w/{workspaceId}/campaigns/{campaignId}`
- `/w/{workspaceId}/campaigns/{campaignId}/posts/{postId}`

## Contract đang dùng

Slice này dùng các contract hiện có trong `packages/contracts` và API base `/api/v1`:

- `GET /workspaces/{workspaceId}/campaigns`
- `GET /workspaces/{workspaceId}/campaigns/{campaignId}`
- `GET /workspaces/{workspaceId}/posts/{postId}`
- `GET /workspaces/{workspaceId}/posts/{postId}/versions`
- `PATCH /workspaces/{workspaceId}/posts/{postId}`
- `POST /workspaces/{workspaceId}/posts/{postId}/submit-approval`
- `POST /workspaces/{workspaceId}/posts/{postId}/approval`
- `POST /workspaces/{workspaceId}/posts/generate`
- `POST /workspaces/{workspaceId}/exports`
- `GET /workspaces/{workspaceId}/jobs/{jobId}`

Khi backend chưa có endpoint tương ứng, MSW mock giữ cùng request/response shape và mô phỏng `version_conflict`, job progress, version mới, approval và export.

## Chạy và kiểm tra

```bash
npm run typecheck
npm run test
npm run build
NODE_PATH=apps/web/node_modules npm run test:e2e -- --project=desktop-chromium tests/e2e/slice2-campaign.spec.ts
```

E2E cần browser binary của Playwright được cài trên máy. Nếu môi trường chưa có, chạy `npx playwright install chromium` một lần.

## Dependency còn thiếu từ backend

- OpenAPI generator và generated client chưa được tích hợp; frontend hiện dùng typed endpoint wrapper trong `apps/web/src/lib/api`.
- Cần chốt response/error schema cho approval, export và job polling trong OpenAPI trước khi tắt mock.
- Cần backend hỗ trợ quyền theo workspace và trả `409 version_conflict` với version hiện tại để UI yêu cầu tải bản mới.
