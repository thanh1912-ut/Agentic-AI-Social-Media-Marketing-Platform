# Quy tắc làm việc trong repo này

> ⚠️ **Nhiều agent đang chạy trên CÙNG một máy và CÙNG thư mục này.**
> Chung một working tree, chung một git index. Đọc kỹ trước khi chạy lệnh git.

---

## 1. Lệnh bị CẤM trong thư mục này

| Lệnh | Vì sao nguy hiểm |
| --- | --- |
| `git add -A` / `git add .` | Sẽ commit luôn phần đang làm dở của agent khác vào commit của bạn. |
| `git reset --hard` | **Xoá vĩnh viễn** thay đổi chưa commit của agent khác. |
| `git clean -fd` | Xoá file mới chưa commit của agent khác. |
| `git checkout <branch>` / `git switch` | Đổi nhánh cho **cả hai** agent vì dùng chung working tree. |
| `git stash` | Cất luôn thay đổi của agent kia. |
| `rm -rf node_modules` | Phá build của agent frontend. |

**Luôn dùng `git add <đường-dẫn-cụ-thể>`.** Commit thường xuyên để không có gì
quan trọng nằm ở trạng thái chưa commit.

---

## 2. Phân vùng sở hữu

Mỗi người chỉ sửa phần của mình. Cần thay đổi phần người khác → báo, không tự sửa.

| Đường dẫn | Chủ sở hữu | Nội dung |
| --- | --- | --- |
| `apps/web/**` | **M1** | Next.js frontend |
| `packages/contracts/src/**` (TypeScript) | **M1** | Hợp đồng HTTP API cho frontend |
| `packages/contracts/package.json`, `tsconfig.json` | **M1** | Cấu hình gói contract TS |
| `tests/e2e/**` | **M1** | Playwright |
| `docs/ux-onboarding.md`, `docs/contract-requests.md` | **M1** | Tài liệu UX |
| `services/api/**`, `database/**`, `infra/**` | **M2** | Backend, DB, hạ tầng |
| `services/ingestion/**`, `services/worker/**` | **M2** | Xử lý tài liệu, job nền |
| `packages/contracts/*.py` (Python) | **M2** | Hợp đồng nội bộ M2↔M3 (Pydantic) |
| `services/agents/**` | **M3** | Agentic AI / LangGraph |
| `packages/prompts/**` | **M3** | Prompt template |
| `tests/*.py`, `tests/conftest.py` | **M2 / M3** | Test Python |
| `pyproject.toml` | **M2** | Cấu hình Python |
| `docs/architecture.md`, `docs/api-contracts.md`, `docs/workflows.md` | **cả ba** | Sửa thì báo nhau |

**Vùng chạm nhau:** `packages/contracts/` và `tests/`. Trong `packages/contracts/`:
file `.py` là của M2, thư mục `src/` là của M1. Không xoá file của nhau.

---

## 3. ⚠️ Hai bộ contract đang tồn tại song song — cần chốt

Hiện có **hai** định nghĩa contract trong cùng `packages/contracts/`:

| | `packages/contracts/models.py` (M2) | `packages/contracts/src/*.ts` (M1) |
| --- | --- | --- |
| Ngôn ngữ | Python / Pydantic | TypeScript |
| Tầng | Nội bộ **M2 ↔ M3** | **HTTP API ↔ trình duyệt** |
| Ví dụ | `NormalizedDocument`, `GeneratedPost`, `ContentReview` | `DocumentUpload`, `Job`, `Publication`, `MetricCell` |
| Trạng thái | M2 đang xây | **DRAFT**, chờ review |

**Trùng tên đáng lo:** `BrandProfile`, `CampaignBrief`, `Recommendation`,
`MetricObservation` — cả hai bên đều định nghĩa. Nếu không chốt, backend và
frontend sẽ lệch nhau.

**Đề xuất của M1:** hợp đồng nội bộ M2↔M3 **không** nhất thiết phải trùng hợp đồng
HTTP. Nguồn sự thật cho frontend là **OpenAPI của backend**:

```
models.py (Pydantic, M2)  →  OpenAPI /api/openapi.json  →  npm run gen:api
                                                         →  src/lib/api/schema.d.ts
```

Nghĩa là `packages/contracts/src/*.ts` hiện tại chỉ là **bản tạm** cho tới khi có
OpenAPI, sau đó type sẽ được sinh tự động. Enum và nhãn tiếng Việt trong
`src/enums.ts` + `src/labels.ts` vẫn giữ làm từ vựng chung.

**Cần M2 xác nhận:** OpenAPI sẽ phơi ra đúng những trường mà frontend cần
(xem `docs/contract-requests.md` — 8 điểm), hay frontend phải tự suy từ
`models.py`?

---

## 4. Trước khi push

```bash
git fetch origin
git log --oneline origin/main..HEAD    # xem mình sắp đẩy gì
git push origin main
```

Nếu bị từ chối vì remote có commit mới: **rebase**, đừng force push.

---

## 5. Biến môi trường

Tên phải đúng chính xác — sai thì app vẫn chạy nhưng âm thầm gọi nhầm API:

- `NEXT_PUBLIC_API_BASE_URL` — gốc API, **không** gồm `/api/v1`
- `NEXT_PUBLIC_USE_MOCKS` — `1` = dùng dữ liệu demo
