/**
 * DRAFT — Brand knowledge: tài liệu, trích xuất, Brand Profile và nguồn.
 * Endpoints đề xuất: `/api/v1/workspaces/{id}/documents`, `/brand-profile`
 */

import type { Id, Timestamp } from './common';
import type {
  BrandFieldKey,
  DocumentErrorCode,
  DocumentKind,
  DocumentStatus,
  FieldReviewState,
} from './enums';

// ---------------------------------------------------------------------------
// Tài liệu
// ---------------------------------------------------------------------------

export interface DocumentUpload {
  id: Id;
  workspace_id: Id;
  filename: string;
  kind: DocumentKind;
  mime_type: string;
  /** Kích thước byte. */
  size: number;
  status: DocumentStatus;
  /** 0..100. */
  progress: number;
  /** Job xử lý tài liệu (trích xuất text / OCR). */
  job_id?: Id;
  error?: {
    code: DocumentErrorCode;
    /** Thông điệp tiếng Việt hiển thị thẳng. */
    message: string;
    /** Việc người dùng nên làm tiếp. */
    hint?: string;
  };
  /** Số trang / số dòng / số ảnh trích xuất được, tuỳ loại. */
  extracted?: {
    pages?: number;
    rows?: number;
    images?: number;
    characters?: number;
  };
  uploaded_by: Id;
  uploaded_at: Timestamp;
  processed_at?: Timestamp;
}

/**
 * Hạn mức upload do backend công bố — UI đọc để hiển thị trước khi người dùng
 * chọn tệp, thay vì để họ upload rồi mới báo lỗi.
 */
export interface UploadLimits {
  max_file_size_bytes: number;
  max_files_per_request: number;
  accepted_kinds: DocumentKind[];
  accepted_mime_types: string[];
}

/** Một đoạn trích dẫn chứng minh cho giá trị AI trích xuất. */
export interface ProvenanceRef {
  document_id: Id;
  document_name: string;
  /** Trang (PDF/DOCX) hoặc sheet + dòng (XLSX/CSV). */
  page?: number;
  sheet?: string;
  row?: number;
  /** Đoạn text nguyên văn chứa thông tin. */
  quote: string;
  /** Vị trí ký tự trong text đã trích xuất, để UI highlight. */
  char_start?: number;
  char_end?: number;
}

// ---------------------------------------------------------------------------
// Brand Profile
// ---------------------------------------------------------------------------

/**
 * Một trường của Brand Profile.
 *
 * `state` cho biết giá trị đến từ đâu và đã được người dùng xác nhận chưa:
 * - `suggested`: AI gợi ý, chưa xác nhận → UI phải đánh dấu "cần xác nhận"
 * - `confirmed`: người dùng đã xác nhận
 * - `edited`   : người dùng sửa tay
 * - `missing`  : thiếu, cần bổ sung
 * - `conflict` : nhiều tài liệu mâu thuẫn → UI phải cho chọn
 */
export interface BrandProfileField<T = unknown> {
  key: BrandFieldKey;
  /** Nhãn tiếng Việt hiển thị. */
  label: string;
  value: T | null;
  state: FieldReviewState;
  /** 0..1. Chỉ có khi `state = suggested`. */
  confidence?: number;
  /** Bằng chứng cho giá trị này — UI cho phép xem nguồn. */
  provenance: ProvenanceRef[];
  /** Khi `state = conflict`: các giá trị mâu thuẫn để người dùng chọn. */
  alternatives?: Array<{
    value: T;
    provenance: ProvenanceRef[];
  }>;
  updated_at?: Timestamp;
  updated_by?: Id;
}

export interface BrandProduct {
  id: Id;
  name: string;
  description?: string;
  price_range?: string;
  usp?: string[];
  image_url?: string;
}

export interface BrandProfile {
  id: Id;
  workspace_id: Id;
  /** Version để phát hiện xung đột khi lưu. */
  version: number;
  business_name: BrandProfileField<string>;
  industry: BrandProfileField<string>;
  description: BrandProfileField<string>;
  products: BrandProfileField<BrandProduct[]>;
  target_audience: BrandProfileField<string[]>;
  brand_voice: BrandProfileField<string>;
  tone_keywords: BrandProfileField<string[]>;
  do_not_use: BrandProfileField<string[]>;
  competitors: BrandProfileField<string[]>;
  contact: BrandProfileField<Record<string, string>>;
  /** Đã xác nhận toàn bộ profile chưa — điều kiện để tạo campaign. */
  confirmed_at?: Timestamp;
  confirmed_by?: Id;
  /** Tỉ lệ trường đã xác nhận, 0..1, backend tính sẵn. */
  completeness: number;
  updated_at: Timestamp;
}

/**
 * `PATCH /brand-profile` — gửi kèm `version` đang giữ.
 * Nếu lệch, backend trả 409 `version_conflict`; UI yêu cầu tải bản mới.
 */
export interface UpdateBrandProfileRequest {
  version: number;
  fields: Array<{
    key: BrandFieldKey;
    value: unknown;
  }>;
  /** Xác nhận luôn sau khi lưu. */
  confirm?: boolean;
}

/** Yêu cầu AI trích xuất lại một trường từ tài liệu. */
export interface ReextractFieldRequest {
  key: BrandFieldKey;
  /** Chỉ định tài liệu cụ thể, bỏ trống = toàn bộ. */
  document_ids?: Id[];
}

// ---------------------------------------------------------------------------
// Onboarding
// ---------------------------------------------------------------------------

/**
 * `GET /workspaces/{id}/onboarding` — tiến độ nhập doanh nghiệp.
 * UI dùng để hiển thị checklist và biết bước nào còn thiếu.
 */
export interface OnboardingState {
  steps: Array<{
    key: 'business_info' | 'upload_documents' | 'confirm_brand' | 'create_campaign';
    label: string;
    status: 'todo' | 'in_progress' | 'done' | 'blocked';
    /** Vì sao bước này chưa làm được. */
    blocked_reason?: string;
    href: string;
  }>;
  completed_count: number;
  total_count: number;
}
