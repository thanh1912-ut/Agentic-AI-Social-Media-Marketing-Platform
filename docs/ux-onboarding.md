# UX & hướng dẫn nhập doanh nghiệp (onboarding)

> Người viết: M1 (Frontend/Product/UX). Đối tượng: chủ quán F&B và cửa hàng bán lẻ
> — người dùng **không rành kỹ thuật**, thường dùng điện thoại, có rất ít thời gian.

---

## 1. Nguyên tắc thiết kế

| # | Nguyên tắc | Vì sao |
| --- | --- | --- |
| 1 | **Không bao giờ khoá một nút mà không nói lý do** | Người dùng bấm không được sẽ nghĩ app hỏng rồi bỏ. Luôn kèm câu giải thích và việc cần làm. |
| 2 | **Không hiển thị `0` khi thật ra là "chưa có dữ liệu"** | `0` là một sự thật ("tuần này không ai tương tác"); thiếu dữ liệu là chuyện khác. Lẫn hai thứ này làm người dùng ra quyết định sai. |
| 3 | **Không bịa phần trăm tiến độ** | Thanh chạy 60% trông rất thuyết phục. Nếu con số đó không thật, người dùng sẽ chờ vô ích hoặc tưởng máy treo. |
| 4 | **Dữ liệu demo phải mang nhãn nhìn thấy được** | Không được để chủ quán tưởng số liệu mẫu là số của quán mình. |
| 5 | **Lỗi phải nói việc cần làm**, không chỉ nói "đã xảy ra lỗi" | "PDF này là ảnh scan" kèm "hãy xuất lại từ Word" giúp tự xử lý được. |
| 6 | **Sửa bài đã duyệt thì phải duyệt lại** | Nếu không, người duyệt đã duyệt một nội dung khác với nội dung được đăng. |
| 7 | **Không đăng trùng** | Với trường hợp "chưa rõ kết quả", thà bắt người dùng mở Facebook kiểm tra còn hơn tự động thử lại và đăng hai lần. |

---

## 2. Luồng nhập doanh nghiệp (tuần đầu của khách pilot)

```
Đăng nhập
   ↓
Chọn / tạo doanh nghiệp
   ↓
① Nhập thông tin cơ bản          ← form ngắn, không bắt buộc hết
   ↓
② Tải tài liệu lên              ← thực đơn, brand book, khảo sát khách
   ↓
③ Xem tiến độ xử lý             ← từng bước, có lý do khi lỗi
   ↓
④ Xác nhận hồ sơ thương hiệu    ← đây là bước quan trọng nhất
   ↓
⑤ Tạo chiến dịch đầu tiên
```

### Vì sao bước ④ quan trọng nhất

AI đọc tài liệu và **đoán** thông tin thương hiệu. Nếu chủ quán không kiểm tra,
AI sẽ viết nội dung dựa trên thông tin sai — và tệ hơn, chủ quán không biết vì sao
nội dung lại sai.

Nên màn hình Hồ sơ thương hiệu được thiết kế để **buộc nhìn thấy nguồn**:

- Mỗi thông tin đều có nút **"Xem nguồn"** → mở ra tài liệu nào, trang nào, và
  **đoạn văn nguyên văn** đã sinh ra thông tin đó.
- Thông tin AI vừa gợi ý hiện nhãn **"AI gợi ý — cần xác nhận"** kèm độ tin cậy.
- Khi hai tài liệu nói khác nhau, hiện nhãn **"Tài liệu mâu thuẫn — cần chọn"** và
  cho chọn giữa các phương án, **mỗi phương án kèm nguồn riêng của nó**.
  Hệ thống **không tự chọn** thay người dùng.

---

## 3. Câu chữ đã chuẩn hoá

Dùng đúng những câu này ở mọi màn hình. Nếu mỗi màn hình nói một kiểu, người dùng
phải học lại từ đầu mỗi lần.

### Trạng thái tài liệu

| Trạng thái | Câu hiển thị |
| --- | --- |
| Chờ tải lên | Chờ tải lên |
| Đang tải lên | Đang tải lên |
| Đang đọc nội dung | Đang đọc nội dung |
| Đã xử lý | Đã xử lý |
| Xử lý lỗi | Xử lý lỗi |
| Không hỗ trợ | Không hỗ trợ |

### Lỗi tài liệu — luôn kèm việc cần làm

| Mã | Câu hiển thị | Việc cần làm |
| --- | --- | --- |
| `pdf_no_text_layer` | PDF này là ảnh scan, không có lớp văn bản để đọc. | Hãy tải lên bản PDF có thể chọn/copy chữ, hoặc xuất lại từ Word. |
| `file_too_large` | Tệp vượt quá dung lượng cho phép. | Hãy nén tệp hoặc chia nhỏ rồi tải lên từng phần. |
| `unsupported_type` | Định dạng tệp chưa được hỗ trợ. | Hãy chuyển sang PDF, DOCX, XLSX, CSV, TXT hoặc ảnh. |
| `encrypted` | Tệp có mật khẩu bảo vệ. | Hãy bỏ mật khẩu của tệp rồi tải lên lại. |
| `ocr_failed` | Không đọc được chữ trong ảnh. | Hãy dùng ảnh rõ hơn, hoặc nhập tay thông tin cần thiết. |

### Trạng thái xuất bản

| Trạng thái | Câu hiển thị | Có nút thử lại? |
| --- | --- | --- |
| `pending` | Chờ gửi | Không |
| `sending` | Đang gửi | Không |
| `published` | Đã đăng | Không |
| `failed` | Gửi lỗi | **Có** |
| `outcome_unknown` | **Chưa rõ kết quả** | **KHÔNG** |
| `needs_reconnect` | Cần kết nối lại | Không |
| `manual_recorded` | Đã đăng thủ công | Không |

> **`outcome_unknown` là trường hợp nguy hiểm nhất.** Câu hướng dẫn bắt buộc:
> *"Đã gửi nhưng chưa xác định được bài có lên Facebook hay không. Hãy mở Facebook
> Page kiểm tra trước khi làm gì tiếp — thử lại ngay có thể làm bài bị đăng trùng."*

---

## 4. Trạng thái màn hình bắt buộc

Mọi màn hình phải xử lý đủ 5 trạng thái. Có **test tự động** chặn nếu thiếu
(`apps/web/src/lib/copy-contract.test.ts`).

| Trạng thái | Hiển thị |
| --- | --- |
| Đang tải | Khối "Đang tải …" có `role="status"` |
| Rỗng | Câu giải thích + việc cần làm đầu tiên, **không** để trắng |
| Lỗi | `role="alert"`, có mã lỗi + mã yêu cầu, nút "Thử lại" **chỉ khi lỗi thử lại được** |
| Thiếu quyền | Nói rõ vai trò hiện tại không làm được gì và nhờ ai |
| Dữ liệu demo | Nhãn "Dữ liệu demo" nhìn thấy được |

---

## 5. Trên điện thoại

Khách pilot dùng điện thoại là chính.

- Bảng rộng **cuộn ngang**, không bóp chữ lại (`.table-scroll`, `min-w-[640px]`).
- Chỉ dùng hai mốc `sm:` và `lg:` — giao diện giữ nhất quán.
- Nút hành động chính đủ lớn để bấm bằng ngón tay.
- Không có cử chỉ chỉ dùng được bằng chuột.

---

## 6. Việc còn phải kiểm chứng với khách thật

Mình **chưa** chạy thử với người dùng thật. Cần kiểm trong tuần 11–12:

1. Chủ quán có tự hiểu nút "Xem nguồn" để làm gì không?
2. Khi gặp trường "mâu thuẫn", họ có biết phải chọn không, hay tưởng là lỗi?
3. Câu "Chưa rõ kết quả" có đủ rõ để họ không bấm thử lại không?
4. Họ có nhận ra nhãn "Dữ liệu demo" không, hay vẫn tưởng là số thật?

Đây là giả định, chưa phải kết luận.

---

## 7. Trạng thái nối API (2026-09-23)

Real mode dùng API origin từ `NEXT_PUBLIC_API_BASE_URL` (không thêm `/api/v1`)
và `NEXT_PUBLIC_USE_MOCKS=0`. Auth/session, workspace, upload, document list và
job dùng DTO generate từ OpenAPI. Trình duyệt gửi cookie credentials + CSRF header;
không lưu access token vào local storage/session storage.

- Login xong, người thuộc nhiều doanh nghiệp chọn workspace; một workspace được
  mở thẳng. URL chứa workspace hiện tại để F5 vẫn trở lại đúng khu vực đó.
- Upload chỉ được mở khi tải được upload limits. File unsupported/quá giới hạn
  bị nêu tên và lý do trước khi gửi; lỗi API hiển thị lỗi thật, không thay bằng
  tài liệu demo. Mỗi lần upload retry giữ nguyên `Idempotency-Key`.
- Job lấy status/progress từ API. Chỉ hiển thị phần trăm backend gửi; polling dừng
  khi job kết thúc, request lỗi hoặc quá 10 phút.
- Danh sách tài liệu hiển thị riêng trạng thái đọc/trích xuất, knowledge,
  `retrieval_mode` và Brand Profile từ `DocumentOut`. `retrieval_mode` phân biệt
  `lexical`, `semantic_vector` và `not_available`; đây là mode chứ không phải
  health check riêng của embedding provider. `extraction_status=extracted`
  không được diễn giải là profile đã tạo; `profile_status=ready` vẫn không có
  nghĩa người dùng đã xác nhận profile. `not_available` và trạng thái chưa biết
  được giữ riêng, không tự quy nguyên nhân embedding/provider nếu API chưa gửi.
- Job lỗi provider được dịch sang nội dung provider-neutral theo `JobErrorOut`
  (`provider_not_configured`, `provider_model_not_found`, timeout,
  `generation_failed` và alias worker cũ).
  Nút thử lại chỉ xuất hiện theo cờ `retryable` từ API. Frontend không tích hợp
  SDK/key của provider và không đưa lộ trình cấu hình OpenAI vào nội dung UI.
- Lời mời chưa được nhận có `user=null`; giao diện hiển thị email lời mời và
  trạng thái chờ, không giả lập hồ sơ người dùng.
- Trang Brand Profile dùng GET/PATCH/POST confirm trong OpenAPI: hiển thị trạng
  thái gợi ý/thiếu/mâu thuẫn, nguồn và locator; lưu kèm `version`, không tự retry
  409. Sửa + xác nhận dùng PATCH nguyên tử; xác nhận revision không chỉnh sửa
  dùng POST confirm. Real mode tải lại profile từ API, không lấy fixture.
- Luồng end-to-end “upload → AI profile → source → confirm → reload” mới có
  frontend và E2E real được chuẩn bị. Chưa xác nhận hoàn tất cho tới khi API và
  worker chạy trong môi trường tích hợp, trả evidence từ tài liệu và E2E chạy với
  account pilot thật.
- OpenAPI dùng field lỗi `code` dạng string cùng `message`, `hint`, `retryable`
  (chưa có enum mã lỗi); worker chuyển mã provider-neutral của M3 và frontend
  quyết định thử lại chỉ theo `retryable`. `retrieval_mode` cho biết lexical,
  semantic/vector hoặc chưa khả dụng, nhưng không khẳng định sức khoẻ provider.
- Dashboard onboarding, campaign, publishing, analytics và recommendation vẫn
  là mock-only; real mode chặn các trang chưa được nối contract.
- OpenAPI hiện không khai báo scanner state; không được hứa người dùng rằng file
  đã quét an toàn. M2 cần cung cấp state/error/quarantine rõ ràng trước pilot.

### Chạy kiểm tra

Mock E2E hiện tại (dữ liệu demo có nhãn):

```sh
cd apps/web
npm run test:e2e
```

Real E2E dùng config riêng, đặt `NEXT_PUBLIC_USE_MOCKS=0` và không cài MSW. Cần
API test environment, account/workspace đã provision và origin browser truy cập được.
API upload/job phải tạo profile có ít nhất một provenance reference; E2E dùng AI
fixture phía server nếu đã cấu hình, còn nghiệm thu chung cần một lượt LLM thật:

```sh
cd apps/web
E2E_REAL_API_BASE_URL=https://api.example.vn \
E2E_REAL_EMAIL='pilot-owner@example.vn' \
E2E_REAL_PASSWORD='...' \
E2E_REAL_WORKSPACE_ID='...' \
npm run test:e2e:real
```

Không ghi credentials thật vào repo/log. Bộ real E2E kiểm login, upload TXT/PDF
có text, job, reload danh sách tài liệu, Brand Profile source/confirm, 409 không
retry, reload dữ liệu đã lưu, logout/session mất cookie, API error không rơi về
fixture và request đi đúng API origin. Chưa chạy được E2E real nếu API origin hoặc
account chưa được provision; kết quả mock không được tính là nghiệm thu backend/AI.
