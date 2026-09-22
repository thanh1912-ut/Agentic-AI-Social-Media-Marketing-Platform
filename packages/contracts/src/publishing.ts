/**
 * DRAFT — Publishing: kết nối Facebook, chọn Page, xuất bản, fallback thủ công.
 * Endpoints đề xuất: `/api/v1/workspaces/{id}/connections`, `/publications`
 */

import type { Capability, Id, Timestamp } from './common';
import type {
  ConnectionStatus,
  PublicationSource,
  PublicationStatus,
} from './enums';

// ---------------------------------------------------------------------------
// Kết nối
// ---------------------------------------------------------------------------

export interface SocialConnection {
  id: Id;
  workspace_id: Id;
  provider: 'facebook';
  status: ConnectionStatus;
  /** Tên tài khoản người dùng Facebook đã uỷ quyền. */
  connected_by_name?: string;
  /** Danh sách quyền Meta đã cấp. */
  scopes: string[];
  /** Quyền còn thiếu để publish được. */
  missing_scopes?: string[];
  /** Page đã chọn để đăng. */
  selected_page_id?: Id;
  connected_at: Timestamp;
  /** Token hết hạn lúc nào — UI cảnh báo trước. Token KHÔNG bao giờ trả về browser. */
  expires_at?: Timestamp;
  last_checked_at?: Timestamp;
  /** Vì sao cần kết nối lại. */
  status_reason?: string;
  /** Năng lực của kết nối này — UI hiển thị lý do khi bị khoá. */
  capabilities: Capability[];
}

/** `GET /connections/{id}/pages` */
export interface FacebookPage {
  id: Id;
  name: string;
  /** Ảnh Page, hiển thị khi chọn. */
  picture_url?: string;
  category?: string;
  followers_count?: number;
  /** Người dùng có quyền đăng lên Page này không. */
  can_publish: boolean;
  /** Lý do không đăng được, vd thiếu quyền `pages_manage_posts`. */
  cannot_publish_reason?: string;
  /** Page này đã được workspace khác dùng chưa. */
  already_selected?: boolean;
}

export interface SelectPageRequest {
  page_id: Id;
}

// ---------------------------------------------------------------------------
// Xuất bản
// ---------------------------------------------------------------------------

/**
 * Một lần xuất bản.
 *
 * CẢNH BÁO cho UI:
 * - `outcome_unknown`: đã gửi nhưng không rõ kết quả. KHÔNG hiện nút "Thử lại"
 *   thông thường — phải hướng người dùng sang đối soát thủ công.
 * - `needs_reconnect`: token hỏng, cần kết nối lại rồi mới gửi tiếp.
 * - `manual_recorded`: người dùng tự đăng rồi nhập lại URL/thời gian.
 */
export interface Publication {
  id: Id;
  post_id: Id;
  /** Version của bài được đăng — để biết chính xác nội dung nào đã lên. */
  post_version: number;
  channel: 'facebook_page';
  page_id?: Id;
  page_name?: string;
  status: PublicationStatus;
  source: PublicationSource;
  /** Link bài đã đăng. Chỉ có khi `published` hoặc `manual_recorded`. */
  permalink?: string;
  /** Thời điểm bài thực sự lên mạng. */
  published_at?: Timestamp;
  /** Thời điểm hệ thống gửi yêu cầu đi. */
  sent_at?: Timestamp;
  external_post_id?: string;
  error?: {
    code: string;
    message: string;
    /** Việc người dùng nên làm. */
    hint?: string;
  };
  /** Số lần đã thử gửi. */
  attempt_count: number;
  /**
   * UI có được phép hiện nút "Thử lại" không. Backend quyết định — với
   * `outcome_unknown` luôn là `false`.
   */
  retry_allowed: boolean;
  /** Bắt buộc đối soát thủ công trước khi làm gì tiếp. */
  requires_manual_reconciliation: boolean;
  created_at: Timestamp;
  updated_at: Timestamp;
}

/** Một mốc trong dòng thời gian của lần xuất bản, hiển thị cho người dùng đối soát. */
export interface PublicationEvent {
  at: Timestamp;
  type: 'queued' | 'sending' | 'response' | 'error' | 'manual_note';
  message: string;
}

export interface PublishRequest {
  post_id: Id;
  /** Version phải khớp version đã duyệt. */
  version: number;
  mode: 'now' | 'scheduled';
  scheduled_at?: Timestamp;
}

/**
 * Ghi nhận việc đăng thủ công.
 * Dùng khi: API chưa khả dụng, hoặc lần gửi trước `outcome_unknown` và người
 * dùng đã tự kiểm tra trên Facebook.
 */
export interface ManualPublicationRequest {
  post_id: Id;
  version: number;
  /** Người dùng xác nhận bài đã lên hay chưa lên. */
  outcome: 'published' | 'not_published';
  permalink?: string;
  published_at?: Timestamp;
  note?: string;
}

// ---------------------------------------------------------------------------
// Trạng thái hiển thị
// ---------------------------------------------------------------------------

/**
 * Nhãn tiếng Việt + hướng dẫn cho từng trạng thái xuất bản.
 * Frontend dùng bảng này để render nhất quán ở mọi màn hình.
 *
 * `tone` dùng cho màu badge, `guidance` là câu giải thích cho người dùng.
 */
export const PUBLICATION_STATUS_META: Record<
  PublicationStatus,
  {
    label: string;
    tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger';
    guidance: string;
    /** Có được hiện nút thử lại không (backend vẫn là nơi quyết định cuối). */
    allowRetry: boolean;
  }
> = {
  pending: {
    label: 'Chờ gửi',
    tone: 'neutral',
    guidance: 'Bài đang chờ đến lượt gửi.',
    allowRetry: false,
  },
  sending: {
    label: 'Đang gửi',
    tone: 'info',
    guidance: 'Hệ thống đang gửi bài lên Facebook.',
    allowRetry: false,
  },
  published: {
    label: 'Đã đăng',
    tone: 'success',
    guidance: 'Bài đã lên Facebook.',
    allowRetry: false,
  },
  failed: {
    label: 'Gửi lỗi',
    tone: 'danger',
    guidance: 'Gửi bài thất bại. Có thể thử lại an toàn.',
    allowRetry: true,
  },
  outcome_unknown: {
    label: 'Chưa rõ kết quả',
    tone: 'warning',
    guidance:
      'Đã gửi nhưng chưa xác định được bài có lên Facebook hay không. Hãy mở Facebook Page kiểm tra trước khi làm gì tiếp — thử lại ngay có thể làm bài bị đăng trùng.',
    allowRetry: false,
  },
  needs_reconnect: {
    label: 'Cần kết nối lại',
    tone: 'warning',
    guidance:
      'Kết nối Facebook đã hết hiệu lực. Kết nối lại rồi gửi tiếp.',
    allowRetry: false,
  },
  manual_recorded: {
    label: 'Đã đăng thủ công',
    tone: 'success',
    guidance: 'Bài do người dùng tự đăng và đã được ghi nhận vào hệ thống.',
    allowRetry: false,
  },
};
