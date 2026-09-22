# Yêu cầu hợp đồng gửi M2 & M3

> Trạng thái: **DRAFT — cần review.**
> Người đề xuất: M1 (Frontend/Product/UX). Ngày: 2026-03-15.
> Nguồn: `packages/contracts/src/**` + tài liệu này.
>
> Mình **không sửa phần của M2/M3**. Tài liệu này liệt kê những gì frontend đang
> giả định, để hai bạn xác nhận hoặc sửa. Khi backend có OpenAPI thật, chạy
> `npm run gen:api` và thay type trong `apps/web/src/lib/api/types.ts`; chữ ký
> trong `endpoints.ts` giữ nguyên nên tầng UI không phải sửa.

---

## 1. Quyết định đã chốt theo repo tham chiếu

Mình đối chiếu repo `agenticAI_VNS_mkt` và **theo đúng** các quy ước sau, để hai
bạn không phải nhớ hai kiểu:

| Hạng mục | Giá trị |
| --- | --- |
| Base path | `/api/v1` |
| Envelope lỗi | **phẳng**: `{ code, message, request_id, retryable, details? }` |
| `message` | câu **tiếng Việt**, hiển thị thẳng cho người dùng |
| `retryable` | do **backend** quyết định, frontend không tự suy từ HTTP status |
| Request dài | trả `202 { job_id, job }`, UI theo dõi `GET /jobs/{job_id}` |
| Enum | `snake_case` chữ thường |
| Nhãn tiếng Việt | tách riêng khỏi enum, không nhúng vào giá trị enum |
| Thời gian | ISO-8601 UTC có offset (`Z`) |

Frontend **đã chịu được** cả envelope phẳng lẫn envelope lồng `{error:{...}}`
(xem `parseErrorBody`), nên nếu M2 chọn kiểu lồng thì UI vẫn chạy.

---

## 2. Cần M2 xác nhận — hợp đồng

### 2.1 Vai trò & quyền

Mình đề xuất 3 vai trò theo brief: `owner` / `editor` / `viewer`.

- `GET /me` trả `workspaces[]`, mỗi phần tử có `role` **và** `permissions[]`
  (danh sách quyền backend thực sự cấp). Frontend dùng `permissions[]` để ẩn/hiện
  nút — **không** tự suy quyền từ `role`.
- Ma trận mặc định ở `packages/contracts/src/enums.ts` → `ROLE_PERMISSIONS`.
  **Cần M2 xác nhận hoặc sửa.**

**Quy tắc 404 vs 403 mình đề xuất** (theo thông lệ của repo tham chiếu): tài
nguyên **không thuộc workspace của người dùng → 404**, không phải 403. Trả 403
sẽ để lộ sự tồn tại của tài nguyên. `details.required_role` kèm theo khi 403.

### 2.2 Job — quan trọng

```jsonc
// GET /api/v1/jobs/{job_id}
{
  "id": "...", "kind": "document_ingest", "status": "running",
  "title": "Đang đọc tài liệu và trích xuất hồ sơ thương hiệu",  // tiếng Việt
  "progress": 60,          // 0..100
  "steps": [
    { "key": "extract", "label": "Đọc nội dung tệp", "status": "succeeded",
      "progress": 100, "message": null, "started_at": "...", "finished_at": "...",
      "error": null }
  ],
  "result": { "document_ids": ["..."] },
  "error": { "code": "pdf_no_text_layer", "message": "...", "hint": "...", "retryable": false },
  "created_at": "...", "started_at": "...", "finished_at": null,
  "cancellable": true
}
```

**Cần chốt:**

1. `title` và `steps[].label` do **backend** trả tiếng Việt hay frontend tự map từ
   `kind`/`step.key`? Mình đang giả định **backend trả**, vì chỉ backend biết job
   thật sự đang làm gì. Nếu backend chỉ trả `key`, mình cần danh sách `key` cố định.
2. `progress` — với job nhiều bước, backend tính hay frontend tự tính từ `steps`?
3. Nếu **không xác định được tổng khối lượng**, backend trả `progress: null`
   (không phải `0`, không phải ước lượng). UI sẽ hiện thanh tiến độ không xác định.
   **Đây là yêu cầu bắt buộc**: mình không bịa phần trăm.
4. `error.hint` — câu hướng dẫn người dùng nên làm gì. Cần có với mọi lỗi người
   dùng tự xử lý được (PDF scan, tệp quá lớn, tệp có mật khẩu).

### 2.3 Xung đột phiên bản

Mình giả định mọi thực thể sửa được đều có trường `version: number`, và client
**gửi kèm version đang giữ** khi PATCH. Lệch → `409 version_conflict`:

```jsonc
{ "code": "version_conflict",
  "message": "Hồ sơ thương hiệu vừa được người khác cập nhật. Bạn đang sửa một bản cũ.",
  "request_id": "...", "retryable": false,
  "details": { "current_version": 7, "your_version": 5 } }
```

**Cần chốt:** M2 dùng `version` số nguyên, `updated_at`, hay `ETag`/`If-Match`?
Repo tham chiếu dùng **số revision tăng dần + `is_current`** và **không có ETag**.
Mình đang theo hướng số nguyên. Quan trọng hơn: **cần `current_version` trong
`details`** để UI nói được "bản mới nhất là bản 7".

### 2.4 Tài liệu & upload

- `GET /workspaces/{id}/documents/limits` → hạn mức để UI báo **trước** khi người
  dùng chọn tệp. Cần: `max_file_size_bytes`, `max_files_per_request`,
  `accepted_kinds[]`, `accepted_mime_types[]`.
- `POST /workspaces/{id}/documents` (multipart, nhiều tệp, header `Idempotency-Key`)
  → `202 { job_id, job }`.
- `DocumentUpload.error` cần `code` + `message` + `hint`. Frontend đã có nhãn tiếng
  Việt cho các mã ở `labels.ts` → `DOCUMENT_ERROR_LABELS`.
  **Cần M2 dùng đúng bộ mã này**, hoặc gửi danh sách mã thật để mình bổ sung.

### 2.5 Provenance — bắt buộc cho Brand Profile

Brief yêu cầu "Xem nguồn tài liệu cho thông tin AI trích xuất". Mình cần backend trả
`provenance[]` cho từng trường:

```jsonc
{ "document_id": "...", "document_name": "brand-book.docx",
  "page": 5, "sheet": null, "row": null,
  "quote": "Giọng điệu: gần gũi, như người nhà nói chuyện.",
  "char_start": 120, "char_end": 168 }
```

`quote` là **đoạn nguyên văn** — UI hiển thị để người dùng tự kiểm chứng.
`char_start/char_end` (tuỳ chọn) để highlight trong tài liệu.

Với trường `state: "conflict"`, cần `alternatives[]`, mỗi phương án có
`value` + `provenance[]` riêng.

### 2.6 Xuất bản — vài ràng buộc bắt buộc

- `POST /workspaces/{id}/publications` — **cần `version`** trong body: chỉ đăng
  đúng version đã được duyệt.
- `Publication.retry_allowed` do **backend** quyết định. Với
  `status: "outcome_unknown"` **luôn là `false`**.
- `requires_manual_reconciliation: true` khi cần người dùng tự kiểm tra trên Facebook.
- `POST /publications/{id}/retry` trả `409 state_conflict` nếu bài đang
  `outcome_unknown`. **Đây là lớp bảo vệ cuối** chống đăng trùng — frontend cũng
  ẩn nút, nhưng backend phải chặn.
- `POST /workspaces/{id}/publications/manual` để ghi nhận đăng thủ công
  (`outcome: published | not_published`).
- **Export trả tệp**, không bao giờ được đặt trạng thái `published`. Mình dùng
  `ExportJob.status ∈ {queued, running, ready, failed}` — tách hẳn khỏi
  `PublicationStatus`.

### 2.7 Số liệu — ba trạng thái phải phân biệt được

Repo tham chiếu cưỡng chế bằng bất biến: **thiếu giá trị thì bắt buộc có lý do**.
Mình theo đúng nguyên tắc đó:

```jsonc
{ "key": "impressions", "label": "Lượt hiển thị", "value": 0,
  "state": "value", "unit": "count", "source": "api",
  "state_reason": null }
```

| `state` | `value` | UI hiển thị |
| --- | --- | --- |
| `value` | `0` | **`0`** — số 0 thật |
| `no_data` | `null` | `—` + "Chưa có dữ liệu cho khoảng thời gian này." |
| `not_permitted` | `null` | `—` + "Bạn không có quyền xem chỉ số này." |
| `not_supported` | `null` | `—` + "Kênh này không cung cấp chỉ số này." |
| `stale` | số | số + cảnh báo dữ liệu cũ |

**Cần M2 xác nhận** dùng `state` tường minh (mình đề xuất) hay chỉ `value: null` +
`unavailable_reason` như repo tham chiếu. Cả hai đều dùng được; mình cần biết để
không hiển thị sai.

Ngoài ra `AnalyticsMeta` cần: `source` (`api` | `manual` | `mixed`),
`source_label` (tiếng Việt), `window`, `freshness.last_synced_at`, `origin`.

**Nhãn nguồn — không được gây hiểu nhầm:** dữ liệu từ tệp phải ghi rõ là tệp nhập,
không được trình bày như kết nối trực tiếp. Mình đang dùng:
`api` → "Đồng bộ từ Facebook", `manual` → "Nhập từ tệp".

### 2.8 Đề xuất & áp dụng

- `Recommendation` cần `evidence[]`, mỗi mảnh có `strength` + `strength_reason`
  (nói thẳng vì sao yếu, ví dụ "chỉ có 6 bài, chưa đủ để kết luận").
- `POST /recommendations/{id}/apply` **không được tự đổi campaign đang chạy**.
  Phải trả về `created_draft` để người dùng xem lại.
  Response cần `notice` (câu tiếng Việt) nếu có điều gì cần lưu ý.

---

## 3. Cần M3 xác nhận — phần AI

1. **Giới hạn 10 bài mỗi lần sinh.** `GenerateContentResponse.max_count` do backend
   trả để UI giới hạn ô nhập số lượng, thay vì để người dùng nhập 50 rồi báo lỗi.
2. **Lịch sử phiên bản.** "Yêu cầu AI sửa" phải sinh **version mới**, không ghi đè
   version cũ. `PostVersion.source ∈ {human, ai_generated, ai_revised, imported}`.
3. **AI review.** `PostVersion.review` cần `checks[]` với `status`
   `pass|warn|fail` + `message` tiếng Việt, và `char_start/char_end` nếu muốn UI
   highlight đúng chỗ.
4. **Trạng thái hết hạn.** Khi AI trích xuất xong, trường nào có bằng chứng yếu thì
   phải để `state: "suggested"` kèm `confidence`, **không** tự đánh dấu đã xác nhận.

---

## 4. Việc mình đang chặn (chưa có backend)

| Màn hình | Đang chờ |
| --- | --- |
| Kết nối Facebook + chọn Page | Endpoint OAuth start/callback + danh sách Page |
| Xuất bản & đối soát | `publications` + `publication events` |
| Nhập số liệu | `metrics/import/preview` + `commit` |
| Đề xuất | `recommendations` + `apply` |

Trong lúc chờ, các màn hình này chạy bằng mock tuân thủ đúng contract ở trên. Khi
backend sẵn sàng, chỉ cần tắt `NEXT_PUBLIC_USE_MOCKS`.

---

## 5. Cách phản hồi

Sửa trực tiếp `packages/contracts/src/**` rồi báo mình, hoặc ghi comment vào tài
liệu này. Mình sẽ cập nhật tầng UI theo. **Mình sẽ không tự đổi contract khi chưa
thống nhất.**
