# Runbook: hồ sơ thương hiệu tự nhập và tài liệu tham khảo

## Cách dùng

1. Mở **Hồ sơ thương hiệu** trong workspace và tự viết nội dung bằng ngôn ngữ tự nhiên. Nêu những điều bạn biết chắc như sản phẩm, khách hàng, giọng viết và điều cần tránh.
2. Owner bấm **Lưu và áp dụng**. Nội dung được giữ nguyên, tạo revision bất biến và dùng cho các yêu cầu viết sau đó. Thao tác này không gọi DeepSeek.
3. Tải PDF có lớp chữ, DOCX, XLSX, CSV hoặc TXT ở mục **Tài liệu**. Hệ thống đọc bằng Docling và lưu knowledge; bước này không tạo hoặc cập nhật hồ sơ.
4. Trong trang campaign, chọn các tài liệu cần dùng cho lần tạo bài và ghi chú cách dùng nếu cần. Không chọn tài liệu nghĩa là agent chỉ dùng hồ sơ, brief và yêu cầu viết.
5. Khi sửa bài, kiểm tra lại danh sách tài liệu đã lưu từ lần tạo trước. Có thể đổi hoặc bỏ hết tài liệu; yêu cầu sửa vẫn cần review và duyệt như trước.

## Hành vi API

- `PATCH /api/v1/workspaces/{workspace_id}/brand-profile` nhận `version` và `profile_text`. Văn bản chỉ được chuẩn hóa ký tự xuống dòng; nội dung rỗng bị từ chối, tối đa 20.000 ký tự.
- Chỉ Owner có thể lưu và áp dụng. Xung đột version trả `409`; nạp lại revision trước khi lưu tiếp.
- Ghi profile theo các trường cấu trúc cũ trả `410 legacy_brand_profile_write_removed`.
- Upload/reprocess tài liệu chỉ thực hiện extraction, chuẩn hóa, chunk và index. `mode=profile_only` cũ trả `410 brand_profile_generation_removed`.
- Generate: `document_ids` vắng mặt hoặc `[]` nghĩa là không dùng tài liệu. Tối đa 20 ID, trong cùng workspace và đã sẵn sàng.
- Revise: API/UI gửi danh sách được giữ từ phiên bản trước; danh sách `[]` bỏ toàn bộ tài liệu. Lựa chọn và ghi chú được lưu trong nội dung phiên bản.

## Lỗi thường gặp

- `brand_profile_manual_required`: Owner cần tự viết và áp dụng hồ sơ hiện tại trước khi lập campaign hoặc sinh bài.
- `selected_document_unavailable`: một nguồn đã xóa, bị tắt, chưa đọc xong hoặc chưa sẵn sàng cho knowledge; tải lại danh sách và chọn nguồn khác.
- `no_relevant_selected_context`: tài liệu đã chọn không có đoạn phù hợp. Agent không tự mở rộng tìm kiếm sang kho tài liệu khác.
- Lỗi DeepSeek không làm mất nội dung Docling đã đọc hoặc knowledge đã lưu.
- Hồ sơ AI cũ chỉ để tham khảo. Tự chép nội dung mong muốn vào ô văn bản rồi bấm **Lưu và áp dụng**.

## Vận hành và rollback

Không cần migration schema mới cho hồ sơ; prose được lưu trong JSON hiện tại và revision hiện có. Triển khai API/worker/web cùng một release để worker mới không chạy contract cũ. Không xóa revisions, jobs, documents, posts hoặc approvals cũ. Rollback code về release trước vẫn giữ JSON lịch sử, nhưng bản cũ không hiểu `profile_text` hoặc selection metadata mới; giữ nguyên dữ liệu và không chạy job cũ với worker cũ trước khi xác định khả năng tương thích.

Môi trường chạy local dùng cấu hình PostgreSQL/Redis/storage của dự án. Không đặt `DEEPSEEK_API_KEY`, token Meta hoặc thông tin database trong frontend hay tài liệu này.
