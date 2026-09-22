/**
 * DRAFT — Kiểu dùng chung: định danh, thời gian, phân trang, job, capability, nguồn.
 */

import type {
  CapabilityKey,
  DataOrigin,
  JobKind,
  JobStatus,
  JobStepStatus,
} from './enums';

/** Định danh. Backend trả UUIDv7 dạng chuỗi. */
export type Id = string;

/** ISO-8601 UTC, vd `2026-01-15T08:30:00Z`. Mọi mốc thời gian dùng định dạng này. */
export type Timestamp = string;

/** Ngày dạng `YYYY-MM-DD` (dùng cho lịch nội dung, cửa sổ đo). */
export type DateString = string;

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/** Tham số phân trang chuẩn. */
export interface PageParams {
  page?: number;
  page_size?: number;
}

// ---------------------------------------------------------------------------
// Job
// ---------------------------------------------------------------------------

/** Một bước trong job — UI hiển thị tiến độ theo bước, không chỉ thanh %. */
export interface JobStep {
  key: string;
  /** Nhãn tiếng Việt do backend trả về, UI hiển thị thẳng. */
  label: string;
  status: JobStepStatus;
  /** 0..100, chỉ có khi bước đang chạy. */
  progress?: number;
  message?: string;
  started_at?: Timestamp;
  finished_at?: Timestamp;
  error?: {
    code: string;
    message: string;
  };
}

export interface JobError {
  code: string;
  message: string;
  /** Gợi ý cho người dùng, vd "Tệp PDF này là bản scan, cần bật OCR." */
  hint?: string;
  retryable: boolean;
}

/**
 * `GET /api/v1/jobs/{job_id}` — và cũng là `job` nhúng trong response 202.
 */
export interface Job {
  id: Id;
  kind: JobKind;
  status: JobStatus;
  /** Nhãn tiếng Việt, vd "Đang xử lý tài liệu". */
  title: string;
  /** 0..100. Với job nhiều bước, backend tính từ các bước. */
  progress: number;
  steps: JobStep[];
  /** Id của thực thể mà job tạo ra, vd `document_id` hoặc `post_ids`. */
  result?: Record<string, unknown>;
  error?: JobError;
  created_at: Timestamp;
  started_at?: Timestamp;
  finished_at?: Timestamp;
  /** Cho phép huỷ hay không. */
  cancellable: boolean;
  /** Sau khi xong, thời điểm backend xoá job khỏi lịch sử. */
  expires_at?: Timestamp;
}

/** Response 202 khi một request dài được nhận. */
export interface AcceptedResponse {
  job_id: Id;
  job: Job;
}

/** Một sự kiện trong dòng sự kiện của job (dùng cho SSE hoặc polling delta). */
export interface JobEvent {
  id: Id;
  job_id: Id;
  at: Timestamp;
  type: 'status' | 'step' | 'log' | 'error';
  message: string;
  /** Chỉ số tiến độ tại thời điểm sự kiện. */
  progress?: number;
}

// ---------------------------------------------------------------------------
// Capability — "vì sao tính năng chưa khả dụng"
// ---------------------------------------------------------------------------

/**
 * Trạng thái một năng lực. UI BẮT BUỘC hiển thị `reason` khi `available = false`,
 * không được chỉ khoá nút mà không nói lý do.
 */
export interface Capability {
  key: CapabilityKey;
  available: boolean;
  /** Lý do tiếng Việt, hiển thị thẳng cho người dùng. */
  reason?: string;
  /** Việc người dùng cần làm để mở khoá, vd "Kết nối lại Facebook Page". */
  remedy?: string;
}

// ---------------------------------------------------------------------------
// Nguồn dữ liệu & độ mới
// ---------------------------------------------------------------------------

/**
 * Nhãn nguồn. `demo` phải được hiển thị rõ trên UI — không giả thành dữ liệu thật.
 */
export interface DataOriginMeta {
  origin: DataOrigin;
  /** Nhãn tiếng Việt hiển thị, vd "Dữ liệu demo" hoặc "Dữ liệu thật". */
  label: string;
}

/** Cửa sổ đo mà một số liệu được tổng hợp. */
export interface MeasurementWindow {
  start: DateString;
  end: DateString;
  /** Múi giờ dùng để cắt ngày. */
  timezone: string;
}

/** Thông tin "số liệu này mới đến đâu". */
export interface Freshness {
  last_synced_at?: Timestamp;
  /** Số giây kể từ lần đồng bộ gần nhất, backend tính sẵn. */
  age_seconds?: number;
  /** Backend đánh giá dữ liệu đã cũ. */
  is_stale: boolean;
  /** Nhãn tiếng Việt, vd "Đồng bộ 2 giờ trước". */
  label: string;
}
