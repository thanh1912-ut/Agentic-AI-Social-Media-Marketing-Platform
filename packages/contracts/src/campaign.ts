/**
 * DRAFT — Campaign, brief, content calendar, post, version, approval, export.
 * Endpoints đề xuất: `/api/v1/workspaces/{id}/campaigns`, `/posts`, `/approvals`, `/exports`
 */

import type {
  DateString,
  Id,
  Timestamp,
} from './common';
import type {
  ApprovalDecision,
  CampaignObjective,
  CampaignStatus,
  Channel,
  ContentPillar,
  ExportFormat,
  PostFormat,
  PostStatus,
  VersionSource,
} from './enums';

// ---------------------------------------------------------------------------
// Campaign
// ---------------------------------------------------------------------------

/** Brief — đầu vào cho AI sinh nội dung. */
export interface CampaignBrief {
  /** Mục tiêu chiến dịch. */
  objective: CampaignObjective;
  /** Mô tả mục tiêu bằng lời người dùng, hiển thị lại cho họ đọc. */
  objective_note?: string | null;
  /** Chân dung khán giả. */
  audience: string[];
  /** Sản phẩm/dịch vụ được quảng bá. */
  product_ids: Id[];
  /** Thông điệp chính. */
  key_message: string;
  /** Điều bắt buộc phải có / phải tránh. */
  must_include?: string[];
  must_avoid?: string[];
  start_date: DateString;
  end_date: DateString;
}

export interface CampaignContentSlot {
  id: Id;
  scheduled_date: DateString;
  pillar: ContentPillar;
  format: PostFormat;
  topic: string;
  /** ID bài được sinh từ slot; chỉ backend tạo. */
  generated_post_id?: Id | null;
  /** ID job đang giữ slot; chỉ backend tạo. */
  generation_job_id?: Id | null;
}

export interface CampaignContentPlan {
  strategy_summary: string;
  slots: CampaignContentSlot[];
}

export interface Campaign {
  id: Id;
  workspace_id: Id;
  /** Nhóm thị trường dùng để giới hạn Fanpage đích, nếu chiến dịch đã chọn nhóm. */
  group_id?: Id | null;
  name: string;
  status: CampaignStatus;
  brief: CampaignBrief;
  content_plan: CampaignContentPlan;
  /** Trụ nội dung chiến dịch dùng. */
  pillars: ContentPillar[];
  /** Kênh phân phối. */
  channels: Channel[];
  version: number;
  post_count: number;
  approved_count: number;
  published_count: number;
  created_by: Id;
  created_at: Timestamp;
  updated_at: Timestamp;
}

/** Bản nháp điều chỉnh brief do "Apply recommendation" tạo ra, chờ người dùng xem lại. */
export interface BriefRevisionDraft {
  id: Id;
  campaign_id: Id;
  /** Brief gốc tại thời điểm tạo đề xuất. */
  base_version: number;
  /** Các thay đổi đề xuất, từng trường một để UI diff được. */
  changes: Array<{
    field: string;
    label: string;
    before: unknown;
    after: unknown;
    rationale: string;
  }>;
  /** Recommendation sinh ra bản nháp này. */
  source_recommendation_id?: Id;
  status: 'pending_review' | 'accepted' | 'discarded';
  created_at: Timestamp;
}

// ---------------------------------------------------------------------------
// Post & version
// ---------------------------------------------------------------------------

export interface PostMedia {
  id: Id;
  url: string;
  /** Mô tả ảnh cho trợ năng (alt text). */
  alt: string;
  width?: number;
  height?: number;
  mime_type?: string;
  /** Ảnh do AI gợi ý hay người dùng tải lên. */
  source: 'ai_suggested' | 'uploaded' | 'external_url';
  asset_id?: Id;
  filename?: string;
  size_bytes?: number;
  sha256?: string;
}

/** Một phiên bản nội dung. Mọi sửa đổi tạo version mới, không ghi đè. */
export interface MediaAsset {
  id: Id;
  filename: string;
  mime_type: 'image/jpeg' | 'image/png' | 'image/webp';
  size_bytes: number;
  content_sha256: string;
  width: number;
  height: number;
  alt_text: string;
  /** API route path, fetched with the authenticated API client. */
  content_path: string;
}

export interface PostVersion {
  version: number;
  caption: string;
  hashtags: string[];
  media: PostMedia[];
  source: VersionSource;
  /** Ai tạo. Với AI, `created_by` là người yêu cầu. */
  created_by: Id;
  created_by_name: string;
  created_at: Timestamp;
  /** Ghi chú khi sửa, vd prompt người dùng nhập cho "yêu cầu AI sửa". */
  note?: string;
  /** Feedback của AI review cho version này. */
  review?: AiReview;
  /** Version này đã được duyệt. */
  approved_at?: Timestamp;
  approved_by?: Id;
}

/** Kết quả AI review nội dung — hiển thị cạnh version để người dùng quyết định. */
export interface AiReview {
  score?: number;
  /** Nhận xét tổng quát. */
  summary: string;
  checks: Array<{
    key: string;
    label: string;
    status: 'pass' | 'warn' | 'fail';
    message: string;
    /** Vị trí trong caption cần chú ý, để UI highlight. */
    char_start?: number;
    char_end?: number;
  }>;
}

export interface Post {
  id: Id;
  campaign_id: Id;
  workspace_id: Id;
  channel: Channel;
  pillar: ContentPillar;
  format: PostFormat;
  status: PostStatus;
  /** Version hiện tại — client phải gửi kèm khi sửa để phát hiện xung đột. */
  version: number;
  current: PostVersion;
  /** Lịch đăng dự kiến. */
  scheduled_at?: Timestamp;
  /** Đăng ngay hay hẹn giờ. */
  publish_mode?: 'now' | 'scheduled' | 'manual';
  /** Bài đã duyệt nhưng bị sửa → cần duyệt lại. Backend đặt cờ này. */
  requires_reapproval: boolean;
  rejection_reason?: string;
  created_at: Timestamp;
  updated_at: Timestamp;
}

/** `GET /posts/{id}/versions` — lịch sử phiên bản để so sánh. */
export interface PostVersionList {
  post_id: Id;
  versions: PostVersion[];
  current_version: number;
  /** Version đang được duyệt (nếu có) — dùng để duyệt ĐÚNG version. */
  pending_approval_version?: number;
}

export interface PostMediaAttachment {
  asset_id: Id;
  alt_text: string;
}

export interface UpdatePostRequest {
  /** Version client đang giữ. Lệch → 409 version_conflict. */
  version: number;
  caption?: string;
  hashtags?: string[];
  media?: PostMediaAttachment[];
  scheduled_at?: Timestamp;
  note?: string;
}

/** "Yêu cầu AI sửa" — sinh version mới, không ghi đè version hiện tại. */
export interface ReviseWithAiRequest {
  version: number;
  /** Chỉ dẫn cho AI, vd "ngắn hơn và thêm CTA". */
  instruction: string;
  /** Phạm vi sửa. */
  scope?: 'caption' | 'hashtags' | 'media' | 'all';
}

/** Yêu cầu sinh nội dung hàng loạt. Tối đa 10 bài mỗi lần. */
export interface GenerateContentRequest {
  campaign_id: Id;
  /** Số bài muốn sinh — backend từ chối nếu > 10. */
  count: number;
  /** Sinh đúng một bản nháp theo slot đã lưu trong campaign. */
  slot_id?: Id;
  pillars?: ContentPillar[];
  formats?: PostFormat[];
  /** Khoảng ngày muốn rải bài. */
  start_date?: DateString;
  end_date?: DateString;
  /** Chỉ dẫn thêm cho AI. */
  instruction?: string;
}

export interface GenerateContentResponse {
  job_id: Id;
  /** Số bài tối đa backend cho phép mỗi lần. UI hiển thị ở ô nhập số lượng. */
  max_count: number;
}

/** Tạo bản nháp thủ công khi AI provider chưa được bật cho workspace. */
export interface CreateManualPostRequest {
  pillar: ContentPillar;
  format: PostFormat;
  caption: string;
  hashtags?: string[];
}

// ---------------------------------------------------------------------------
// Approval
// ---------------------------------------------------------------------------

/**
 * Quyết định duyệt. `version` BẮT BUỘC: người duyệt phải duyệt đúng version
 * họ đã đọc, tránh trường hợp nội dung đổi giữa lúc xem và lúc bấm.
 */
export interface ApprovalRequest {
  version: number;
  decision: ApprovalDecision;
  reason?: string;
}

export interface ApprovalRecord {
  id: Id;
  post_id: Id;
  version: number;
  decision: ApprovalDecision;
  reason?: string;
  decided_by: Id;
  decided_by_name: string;
  decided_at: Timestamp;
  content_sha256?: string;
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

/**
 * Yêu cầu export. Export trả về TỆP — đây không phải hành vi "đăng bài".
 * UI không được hiển thị export là đã published.
 */
export interface CreateExportRequest {
  campaign_id: Id;
  format: ExportFormat;
  /** Bài nào được đưa vào tệp. */
  post_ids?: Id[];
  /** Các cột muốn xuất. */
  columns?: string[];
}

export interface ExportJob {
  id: Id;
  campaign_id: Id;
  format: ExportFormat;
  status: 'queued' | 'running' | 'ready' | 'failed';
  job_id?: Id;
  /** Chỉ có khi `status = ready`. */
  download_url?: string;
  filename?: string;
  size?: number;
  error?: { code: string; message: string };
  created_at: Timestamp;
  ready_at?: Timestamp;
}
