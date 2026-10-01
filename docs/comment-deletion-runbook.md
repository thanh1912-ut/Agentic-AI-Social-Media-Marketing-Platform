# Xóa bình luận trong Nghiên cứu

## Phạm vi

Owner mở bài → Xem bình luận và tương tác → Loại bình luận khỏi nghiên cứu → chọn lý do → Xóa và ngăn nhập lại. Đây là xóa dữ liệu của ứng dụng, không gửi yêu cầu xóa bình luận lên Facebook.

Một thao tác xóa ciphertext, metadata trích xuất, số tương tác và thời gian đăng của tất cả phiên bản cùng bình luận và replies đã biết trong cùng post/source/workspace. Replies chưa từng được collector cung cấp không được tuyên bố đã tìm thấy/xóa. Collector Meta dừng frontier replies đã bị loại; Tier0 không có khả năng paginate mọi replies.

Ledger giữ restricted source comment ID, hash permalink, tenant/source, actor và lý do. Không giữ body/name/avatar trong ledger. Đây vẫn là dữ liệu vận hành hạn chế, không phải bằng chứng vô danh. Alias không dùng để theo dõi một người xuyên Page/workspace.

Collector kiểm tra ledger lại trong transaction ghi; cache bình luận cùng source bị làm mới sau xóa. Lượt crawl mới hoặc sửa body nguồn không làm mất suppression. Aggregate receipt cũ giữ lịch sử số lượng đã nhận, không được trình bày thành số bình luận hiện còn lưu. Source purge giữ ledger; xóa hẳn tenant/source có thể cascade ledger, không bảo đảm suppression xuyên nguồn mới tạo hoặc workspace khác.

API Owner-only/CSRF:
`POST /api/v1/workspaces/{workspace_id}/market-research/sources/{source_id}/comments/{version_id}/suppress`, body reason là `subject_request`, `out_of_scope` hoặc `privacy_risk`. Erasure vẫn được phép khi Page needs_reconnect. Không phát sinh Meta/provider call.

## Migration và rollback

Thêm migration0029 sau0028. Fresh và upgrade đã so sánh schema trên PostgreSQL thật; giữ mọi dữ liệu cũ. Canonicalize các enum check không đổi tập giá trị để pg_dump/restore và fresh có cùng định nghĩa; không tự xóa dữ liệu sai.

Drain worker trước migration; backup database/storage và giữ secrets riêng. Chạy `python -m alembic upgrade head` bằng runtime migration được cấu hình. API/worker/Beat dùng cùng schema, queue, encryption key. Chỉ restart các label preview đã xác định; không purge queue hoặc reset tài khoản.

Downgrade0029 bị chặn có chủ ý. Có thể rollback frontend hoặc tắt UI/collector mới; giữ worker/check tại persistence hiểu suppression ledger. Không rollback code cũ bỏ qua ledger, không restore backup cũ trực tiếp ra môi trường phục vụ.

## Ledger sau backup/restore

Bản backup trước thời điểm xóa có thể chứa ciphertext cũ. Trước khi restore phục vụ, lấy **ledger mới nhất**, restore vào database riêng, nâng schema, áp ledger, kiểm tra rồi mới mở API/workers. Ledger nằm ngoài Git và tách khỏi backup cũ. Tài khoản/tenant/source mapping thiếu làm apply fail toàn transaction; cần xử lý mapping trước khi phục vụ.

Ví dụ với `DATABASE_URL` đã nạp từ secret/runtime (không in DSN):

```sh
python scripts/research_comment_deletion_ledger.py export /absolute/private/path/latest-deletion-ledger.ndjson
python scripts/research_comment_deletion_ledger.py apply /absolute/private/path/latest-deletion-ledger.ndjson
```

Export tạo file mới0600, không ghi đè. Apply bị giới hạn64MiB/100.000 records, replay idempotent; output chỉ counts. Giữ file hạn chế, không gửi qua chat hoặc commit. Dùng đường dẫn ledger mới cho mỗi export rồi quản lý latest bằng công cụ vận hành có quyền phù hợp; không xóa bản mới nhất trước khi xác minh backup khác.

Đã diễn tập `pg_dump/pg_restore` trước/sau xóa trên PostgreSQL disposable và kiểm tra re-crawl không nhập lại. **Chưa nối auto export ledger vào lịch backup**; người vận hành phải xuất/giữ ledger mới nhất trước restore. Không tuyên bố erasure toàn provider/media/report khi các pipeline đó chưa tồn tại.

## Kiểm thử

Dùng PostgreSQL/Redis disposable, provider keys rỗng, `INLINE_JOBS=0`/`AUTO_CREATE_SCHEMA=0`:

```sh
python -m pytest tests/test_comment_suppression.py -q
python -m pytest tests/test_postgres_public_facebook_comments.py tests/test_postgres_comment_quarantine.py tests/test_postgres_comment_checkpoints.py tests/test_postgres_comment_suppression.py -q
```

`POSTGRES_TEST_URL` và `POSTGRES_FRESH_TEST_URL` trỏ database riêng đã migrate head; không dùng database UI fixture cho test TTL purge toàn hệ thống. Các API tests unit dùng fixture; bằng chứng PG/Redis và Playwright được ghi riêng.

Browser test `tests/e2e/public-page-comments.real.spec.ts` dùng server/collector/credentials tổng hợp của test; không thao tác phiên đang đăng nhập của người dùng. Không gọi đó là bình luận Facebook thật.

## Giới hạn còn lại

Comment candidates vẫn privacy_hold, encrypted, tối đa24giờ và Owner-only. Suppression không cấp quyền gửi AI. Chưa có released comment90ngày, media/Gemini worker, auto provider deletion hoặc erasure lan tới report có comment/media. Không tuyên bố tuân thủ đầy đủ luật hoặc lấy hết lịch sử. Thêm Tier1 không bảo đảm đầy đủ và chưa nằm trong chế độ được chọn.
