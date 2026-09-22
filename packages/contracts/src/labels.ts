/**
 * DRAFT — Nhãn tiếng Việt cho mọi enum.
 *
 * Mục đích: mọi màn hình dùng CHUNG một cách gọi tên. Nếu để mỗi component tự
 * viết nhãn, cùng một trạng thái sẽ hiện 3 kiểu chữ khác nhau.
 *
 * Quy ước viết:
 * - Câu ngắn, không viết hoa đầu từ giữa câu.
 * - Nói thẳng trạng thái, không dùng từ kỹ thuật (không "timeout", không "500").
 * - Với trạng thái lỗi, luôn kèm `guidance` nói người dùng nên làm gì.
 */

import type {
  DocumentKind,
  DocumentStatus,
  JobStatus,
  MetricSource,
  MetricState,
  PostStatus,
  PublicationSource,
  WorkspaceRole,
  CampaignStatus,
  FieldReviewState,
  EvidenceStrength,
  RecommendationStatus,
  DataOrigin,
  ContentPillar,
  PostFormat,
  CampaignObjective,
  DocumentErrorCode,
} from './enums';

/** Nhãn + sắc thái cho badge. `tone` ánh xạ sang class Tailwind ở tầng UI. */
export interface LabelMeta {
  label: string;
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
}

export const ROLE_LABELS: Record<WorkspaceRole, string> = {
  owner: 'Chủ sở hữu',
  editor: 'Biên tập viên',
  viewer: 'Người xem',
};

export const ROLE_DESCRIPTIONS: Record<WorkspaceRole, string> = {
  owner: 'Toàn quyền: quản lý thành viên, kết nối kênh, duyệt và đăng bài.',
  editor: 'Tạo và sửa nội dung, tải tài liệu, xuất tệp. Không duyệt, không đăng.',
  viewer: 'Chỉ xem nội dung và số liệu. Không sửa được gì.',
};

export const JOB_STATUS_LABELS: Record<JobStatus, LabelMeta> = {
  queued: { label: 'Đang chờ', tone: 'neutral' },
  running: { label: 'Đang xử lý', tone: 'info' },
  succeeded: { label: 'Hoàn tất', tone: 'success' },
  failed: { label: 'Thất bại', tone: 'danger' },
  cancelled: { label: 'Đã huỷ', tone: 'neutral' },
};

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, LabelMeta> = {
  pending: { label: 'Chờ tải lên', tone: 'neutral' },
  uploading: { label: 'Đang tải lên', tone: 'info' },
  processing: { label: 'Đang đọc nội dung', tone: 'info' },
  ready: { label: 'Đã xử lý', tone: 'success' },
  failed: { label: 'Xử lý lỗi', tone: 'danger' },
  unsupported: { label: 'Không hỗ trợ', tone: 'warning' },
};

export const DOCUMENT_KIND_LABELS: Record<DocumentKind, string> = {
  pdf: 'PDF',
  docx: 'Word (DOCX)',
  xlsx: 'Excel (XLSX)',
  csv: 'CSV',
  txt: 'Văn bản (TXT)',
  image: 'Hình ảnh',
};

/**
 * Giải thích lỗi xử lý tài liệu. `hint` là việc người dùng nên làm —
 * bắt buộc có, không được chỉ báo "lỗi".
 */
export const DOCUMENT_ERROR_LABELS: Record<
  DocumentErrorCode,
  { label: string; hint: string }
> = {
  pdf_no_text_layer: {
    label: 'PDF này là ảnh scan, không có lớp văn bản để đọc.',
    hint: 'Hãy tải lên bản PDF có thể chọn/copy chữ, hoặc xuất lại từ Word.',
  },
  file_too_large: {
    label: 'Tệp vượt quá dung lượng cho phép.',
    hint: 'Hãy nén tệp hoặc chia nhỏ rồi tải lên từng phần.',
  },
  unsupported_type: {
    label: 'Định dạng tệp chưa được hỗ trợ.',
    hint: 'Hãy chuyển sang PDF, DOCX, XLSX, CSV, TXT hoặc ảnh.',
  },
  corrupted: {
    label: 'Tệp bị hỏng, không mở được.',
    hint: 'Hãy mở lại tệp trên máy để kiểm tra rồi tải lên bản khác.',
  },
  encrypted: {
    label: 'Tệp có mật khẩu bảo vệ.',
    hint: 'Hãy bỏ mật khẩu của tệp rồi tải lên lại.',
  },
  ocr_failed: {
    label: 'Không đọc được chữ trong ảnh.',
    hint: 'Hãy dùng ảnh rõ hơn, hoặc nhập tay thông tin cần thiết.',
  },
  empty_content: {
    label: 'Tệp không có nội dung đọc được.',
    hint: 'Hãy kiểm tra lại tệp — có thể tệp chỉ có trang trắng.',
  },
};

export const FIELD_REVIEW_STATE_LABELS: Record<FieldReviewState, LabelMeta> = {
  suggested: { label: 'AI gợi ý — cần xác nhận', tone: 'warning' },
  confirmed: { label: 'Đã xác nhận', tone: 'success' },
  edited: { label: 'Bạn đã sửa', tone: 'info' },
  missing: { label: 'Còn thiếu', tone: 'danger' },
  conflict: { label: 'Tài liệu mâu thuẫn — cần chọn', tone: 'warning' },
};

export const CAMPAIGN_STATUS_LABELS: Record<CampaignStatus, LabelMeta> = {
  draft: { label: 'Bản nháp', tone: 'neutral' },
  active: { label: 'Đang chạy', tone: 'info' },
  completed: { label: 'Đã kết thúc', tone: 'success' },
  archived: { label: 'Đã lưu trữ', tone: 'neutral' },
};

export const CAMPAIGN_OBJECTIVE_LABELS: Record<CampaignObjective, string> = {
  awareness: 'Nhận biết thương hiệu',
  engagement: 'Tương tác',
  traffic: 'Kéo truy cập',
  leads: 'Thu khách hàng tiềm năng',
  sales: 'Bán hàng',
  retention: 'Giữ chân khách cũ',
};

export const CONTENT_PILLAR_LABELS: Record<ContentPillar, string> = {
  education: 'Kiến thức',
  entertainment: 'Giải trí',
  inspiration: 'Truyền cảm hứng',
  promotion: 'Khuyến mãi',
  community: 'Cộng đồng',
  behind_the_scenes: 'Hậu trường',
  product: 'Sản phẩm',
  testimonial: 'Khách hàng nói',
};

export const POST_FORMAT_LABELS: Record<PostFormat, string> = {
  text: 'Chỉ chữ',
  image: 'Một ảnh',
  carousel: 'Nhiều ảnh',
  video: 'Video',
  reel: 'Reel',
  story: 'Story',
};

/**
 * Trạng thái bài viết. `guidance` là câu giải thích cho người dùng khi bài
 * đang ở trạng thái đó.
 */
export const POST_STATUS_LABELS: Record<
  PostStatus,
  LabelMeta & { guidance: string }
> = {
  draft: {
    label: 'Bản nháp',
    tone: 'neutral',
    guidance: 'Bài chưa gửi duyệt.',
  },
  needs_review: {
    label: 'Chờ duyệt',
    tone: 'warning',
    guidance: 'Bài đang chờ người có quyền duyệt.',
  },
  approved: {
    label: 'Đã duyệt',
    tone: 'success',
    guidance: 'Bài đã được duyệt và có thể đăng.',
  },
  rejected: {
    label: 'Bị từ chối',
    tone: 'danger',
    guidance: 'Bài bị từ chối. Sửa lại rồi gửi duyệt tiếp.',
  },
  scheduled: {
    label: 'Đã hẹn giờ',
    tone: 'info',
    guidance: 'Bài sẽ tự động đăng vào thời điểm đã hẹn.',
  },
  published: {
    label: 'Đã đăng',
    tone: 'success',
    guidance: 'Bài đã lên Facebook.',
  },
  failed: {
    label: 'Đăng lỗi',
    tone: 'danger',
    guidance: 'Đăng bài thất bại. Xem chi tiết ở mục Xuất bản.',
  },
};

export const PUBLICATION_SOURCE_LABELS: Record<PublicationSource, string> = {
  api: 'Hệ thống đăng',
  manual: 'Người dùng tự đăng',
};

export const METRIC_SOURCE_LABELS: Record<MetricSource, string> = {
  api: 'Đồng bộ từ Facebook',
  manual: 'Nhập từ tệp',
};

/**
 * Cách hiển thị một ô không có số.
 * `text` là thứ hiện trên bảng; `explain` là câu giải thích đầy đủ.
 */
export const METRIC_STATE_DISPLAY: Record<
  MetricState,
  { text: string; explain: string; tone: 'neutral' | 'warning' | 'danger' | 'info' }
> = {
  value: { text: '', explain: '', tone: 'neutral' },
  no_data: {
    text: '—',
    explain: 'Chưa có dữ liệu cho khoảng thời gian này.',
    tone: 'neutral',
  },
  not_permitted: {
    text: '—',
    explain: 'Bạn không có quyền xem chỉ số này.',
    tone: 'warning',
  },
  not_supported: {
    text: '—',
    explain: 'Kênh này không cung cấp chỉ số này.',
    tone: 'neutral',
  },
  stale: {
    text: '',
    explain: 'Số liệu đã cũ, có thể chưa phản ánh đúng hiện tại.',
    tone: 'warning',
  },
};

export const EVIDENCE_STRENGTH_LABELS: Record<EvidenceStrength, LabelMeta> = {
  strong: { label: 'Bằng chứng mạnh', tone: 'success' },
  moderate: { label: 'Bằng chứng vừa', tone: 'info' },
  weak: { label: 'Bằng chứng yếu', tone: 'warning' },
  insufficient: { label: 'Chưa đủ bằng chứng', tone: 'danger' },
};

export const RECOMMENDATION_STATUS_LABELS: Record<RecommendationStatus, LabelMeta> = {
  new: { label: 'Mới', tone: 'info' },
  acknowledged: { label: 'Đã xem', tone: 'neutral' },
  applied: { label: 'Đã áp dụng', tone: 'success' },
  dismissed: { label: 'Đã bỏ qua', tone: 'neutral' },
};

/** Nhãn cho dữ liệu demo — BẮT BUỘC hiển thị ở mọi màn hình có dữ liệu demo. */
export const DATA_ORIGIN_LABELS: Record<DataOrigin, LabelMeta> = {
  live: { label: 'Dữ liệu thật', tone: 'success' },
  demo: { label: 'Dữ liệu demo', tone: 'warning' },
};

/** Câu cảnh báo hiển thị khi màn hình đang dùng dữ liệu demo. */
export const DEMO_DATA_NOTICE =
  'Màn hình này đang hiển thị dữ liệu demo để bạn xem thử luồng làm việc. Số liệu không phải của doanh nghiệp bạn.';
