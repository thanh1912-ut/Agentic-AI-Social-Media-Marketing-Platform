# Gemini Files API cho media Nghiên cứu — checkpoint

Code: `23c8736de8e82885a2ec2fb96b972a1621f3294b`; kiểm tra 2026-10-01 20:18 Asia/Ho_Chi_Minh. Nhánh `codex/page-workspaces-research`.
Đây là adapter Python đã kiểm thử bằng HTTPX MockTransport, không phải nghiệm
thu pipeline media. Preview vẫn chạy release ba23d79/schema0031 và chưa dùng
adapter mới; không khởi động media worker hoặc gọi provider thật lần này.

## Ranh giới đã thực hiện

`GeminiFilesClient` nhận ApprovedMediaInput có bytes/hash/nguồn/điều kiện đã kiểm
tra. Không nhận URL ngoài, cookie hoặc tài khoản Facebook. Ảnh tối đa10MiB;
video tối đa100MiB và cần duration_ms đã đo không quá600000. SDK chưa tự đo độ
dài; worker/probe local sẽ chịu trách nhiệm, không được đoán giá trị đó.

Upload qua fixed Google HTTPS origin, không kế thừa proxy ở client mặc định,
không follow redirect. Session URL chỉ tồn tại trong memory và được kiểm tra
host/port/path/query trước khi gửi bytes; không được trả cho UI/journal/log.
Metadata response tối đa64KiB. Kết quả phải đúng filename, URI, MIME, dung lượng,
hash; file ACTIVE thiếu hash không được phân tích. Display tag được băm từ asset
identity và content hash, không dùng tên người/file gốc.

Callback on_uploaded bắt buộc, gọi khi nhận handle trước khi kiểm tra metadata,
rồi cập nhật trạng thái sau kiểm tra. Caller phải ghi durable journal; adapter
không tự tạo database record. Callback/metadata thất bại cố xóa file. Xóa lỗi
trả ProviderFileCleanupRequired với handle an toàn để worker đối soát. Không
đưa URL upload, credential hoặc chi tiết lỗi DB vào exception an toàn.

Upload timeout/receipt không có handle hợp lệ trả ProviderUploadOutcomeUnknown
và tag để đối soát, không upload lại. find_uploaded chỉ giữ các file khớp tag/hash
của request, phân trang có budget; completion=False không chứng minh file không
tồn tại. Không giữ metadata file khác. DELETE404 là kết quả idempotent đã không
còn file; không tự retry upload/generation. Các thao tác list/get/delete không
gửi lại binary. Worker phải tiếp tục cleanup kể cả khi Page/approval bị thu hồi.

GeminiFileMediaAnalyzer chỉ phân tích file ACTIVE còn hạn, hash và các source/
asset/evidence ID khớp đúng bytes đã được phép dùng. Request gửi fileData URI,
không nhúng lại binary; schema Pydantic và usage/thinking token dùng boundary
Gemini hiện có. Prompt coi chữ/lời thoại trong media là dữ liệu không đáng tin,
không nhận diện danh tính/thuộc tính nhạy cảm. Không retry/repair/fallback.

Giới hạn inline20MiB vẫn là chính sách ứng dụng; thông báo không còn mô tả nó
như giới hạn hiện hành của Google. Files path riêng hỗ trợ video lớn hơn.

## Bằng chứng lần này

| Phạm vi | Kết quả | Bằng chứng / giới hạn |
| --- | --- | --- |
| Provider/Files/budget regression | PASS fixture |64passed,1skipped ở5module; skip là live smoke cần opt-in |
| Upload/parse/generate/delete | PASS HTTPX fixture | Journal trước metadata, fileData đúng URI; usage có thinking tokens; DELETE riêng |
| Video lớn | PASS boundary fixture | Binary lớn hơn10MiB đi upload, không inline; giới hạn100MiB được khai báo. Chưa benchmark video100MiB thật |
| Privacy/hash/duration/expiry | PASS fixture | Privacy hold hoặc hash sai bị chặn trước network; duration không đo/quá10phút bị chặn; file khác source/hết hạn không generate |
| URL/redirect/response limits | PASS native transport fixture | Private host, port, scheme, query lạ, path và redirect không nhận bytes; metadata quá lớn bị từ chối |
| Journal/uncertain/reconcile | PASS fixture | Lỗi DB không lộ detail; delete failure giữ handle; timeout không re-upload; paginated lookup không coi page rỗng là hoàn tất |
| Static/source | PASS | Ruff, whitespace và scan mẫu/giá trị secret của file nhiệm vụ |
| Gemini/Facebook live | NOT_RUN |0provider calls và0Facebook calls |
| Durable media journal/worker | TODO | Chưa có model/transaction/service gọi callbacks; chưa kiểm tra PostgreSQL/Redis riêng cho Files path |
| Download/privacy review/retention/UI/report | TODO | Chưa được nối; không nhận adapter unit PASS là media feature PASS |

Lệnh: `python -m pytest -q -p no:cacheprovider tests/test_gemini_files.py tests/test_gemini_provider.py tests/test_gemini_text_provider.py tests/test_gemini_api_smoke.py tests/test_ai_budget.py`.
Không bật RUN_GEMINI_SMOKE. Ruff chỉ trên các file Python thay đổi. Không đổi
HTTP contract, migration, frontend hoặc secrets; không cần frontend rebuild
cho checkpoint này. ffprobe/ffmpeg hiện có trên máy, chưa dùng để nghiệm thu.

## Công việc tiếp theo thuộc cùng mục tiêu

1. Asset/version/decision/analysis records gắn evidence/observation và tenant;
   URL tải tạm mã hóa, bytes quarantine và journal cleanup phải bền trong PG.
2. Resolver Meta/CLI + downloader có DNS/IP pinning/CDN allowlist, MIME/signature/
   duration/size/timeout, không tải URL tùy ý hoặc signed URL trong log/UI.
3. Worker media concurrency1, checkpoint5asset/batch, download ledger500MiB/ngày,
   budget AI trước call, upload journal trước provider, fencing và erasure jobs.
4. Privacy hold/review đúng hash, TTL24h/30ngày, suppression/deletion xuyên raw/
   provider/cache/analysis/report; không dùng checkbox làm chứng nhận pháp lý.
5. Nối summaries vào report/hướng viết đã ghim và UI; browser/PG/Redis thật,
   media synthetic smoke trước live trong ngân sách; triển khai sau nghiệm thu.

Full goal Page workspace/Nghiên cứu còn IN_PROGRESS. Không thay Tier0/cookies,
không tự đăng bài và không gắn các dữ liệu nghiên cứu thành hồ sơ thương hiệu.

## Tài liệu upstream đã đối chiếu

[Gemini Files API](https://ai.google.dev/gemini-api/docs/files) mô tả upload,
get/list/delete và file expiry; ứng dụng chủ động xóa sau xử lý, không lấy TTL
provider làm cơ chế cleanup duy nhất. [Files reference](https://ai.google.dev/api/files)
cung cấp cấu trúc hash/state/expiration. [Video understanding](https://ai.google.dev/gemini-api/docs/video-understanding)
mô tả file inputs; hạn100MiB/10phút là budget sản phẩm của đợt local.
