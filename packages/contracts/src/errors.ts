/**
 * DRAFT — Error envelope dùng chung.
 *
 * Mọi response lỗi của backend PHẢI theo đúng shape này để UI xử lý thống nhất
 * (hiển thị thông điệp, quyết định có cho retry hay không, phát hiện 409).
 *
 * Shape PHẲNG (không lồng trong `error`), khớp với repo tham chiếu
 * `agenticAI_VNS_mkt` để M2 không phải viết hai kiểu:
 * ```json
 * {
 *   "code": "version_conflict",
 *   "message": "Bài viết đã được người khác cập nhật.",
 *   "request_id": "req_01H...",
 *   "retryable": false,
 *   "details": { "current_version": 4, "your_version": 3 }
 * }
 * ```
 *
 * `message` là câu tiếng Việt hiển thị thẳng cho người dùng.
 * `request_id` in ra để người dùng gửi cho hỗ trợ.
 * `retryable` do BACKEND quyết định — frontend không tự đoán.
 */

export const ERROR_CODES = {
  /** 400 — dữ liệu gửi lên sai. `details.fields` liệt kê lỗi từng trường. */
  VALIDATION_ERROR: 'validation_error',
  /** 401 — chưa đăng nhập. */
  UNAUTHENTICATED: 'unauthenticated',
  /** 401 — phiên hết hạn, cần đăng nhập lại (UI hiện thông báo riêng). */
  SESSION_EXPIRED: 'session_expired',
  /** 403 — thiếu quyền. `details.permission` cho biết quyền còn thiếu. */
  FORBIDDEN: 'forbidden',
  /** 404 */
  NOT_FOUND: 'not_found',
  /** 409 — xung đột phiên bản. KHÔNG được ghi đè âm thầm. */
  VERSION_CONFLICT: 'version_conflict',
  /** 409 — vi phạm ràng buộc trạng thái (vd: publish bài chưa duyệt). */
  STATE_CONFLICT: 'state_conflict',
  /** 422 — không xử lý được nội dung (vd: PDF không có lớp text). */
  UNPROCESSABLE: 'unprocessable',
  /** 429 */
  RATE_LIMITED: 'rate_limited',
  /** 500 */
  INTERNAL_ERROR: 'internal_error',
  /** 502/504 — lỗi từ nhà cung cấp bên thứ ba (LLM, Meta...). */
  UPSTREAM_ERROR: 'upstream_error',
  /** Job nền thất bại — dùng trong `Job.error`. */
  JOB_FAILED: 'job_failed',
} as const;
export type ErrorCode = (typeof ERROR_CODES)[keyof typeof ERROR_CODES];

/** Lỗi theo từng trường, dùng cho form validation. */
export interface FieldError {
  /** Đường dẫn trường, vd `brief.objective` hoặc `documents[0].size`. */
  field: string;
  message: string;
  code?: string;
}

export interface ApiErrorBody {
  code: ErrorCode | string;
  /** Câu tiếng Việt hiển thị thẳng cho người dùng. */
  message: string;
  /** Mã tra cứu khi cần hỗ trợ. Backend luôn sinh trường này. */
  request_id?: string;
  /**
   * Backend quyết định lỗi này có thử lại được không.
   * Frontend KHÔNG tự suy ra từ HTTP status.
   */
  retryable?: boolean;
  details?: {
    fields?: FieldError[];
    /** Với `version_conflict`: version hiện tại trên server. */
    current_version?: number;
    /** Với `version_conflict`: version mà client đang giữ. */
    your_version?: number;
    /** Với `forbidden`: quyền còn thiếu. */
    permission?: string;
    /** Với `forbidden`: vai trò tối thiểu cần có. */
    required_role?: string;
    /** Với `rate_limited`: số giây nên chờ. */
    retry_after_seconds?: number;
    [key: string]: unknown;
  };
}

/** Body lỗi chính là `ApiErrorBody` (shape phẳng). */
export type ApiErrorResponse = ApiErrorBody;

/**
 * HTTP status ↔ error code. UI dùng bảng này để quyết định hành vi:
 * có cho retry, có redirect về đăng nhập, hay phải tải lại dữ liệu.
 */
export const ERROR_HTTP_STATUS: Record<string, number> = {
  [ERROR_CODES.VALIDATION_ERROR]: 400,
  [ERROR_CODES.UNAUTHENTICATED]: 401,
  [ERROR_CODES.SESSION_EXPIRED]: 401,
  [ERROR_CODES.FORBIDDEN]: 403,
  [ERROR_CODES.NOT_FOUND]: 404,
  [ERROR_CODES.VERSION_CONFLICT]: 409,
  [ERROR_CODES.STATE_CONFLICT]: 409,
  [ERROR_CODES.UNPROCESSABLE]: 422,
  [ERROR_CODES.RATE_LIMITED]: 429,
  [ERROR_CODES.INTERNAL_ERROR]: 500,
  [ERROR_CODES.UPSTREAM_ERROR]: 502,
};

/**
 * Những lỗi nên hiện nút "Thử lại" với người dùng.
 * `version_conflict` KHÔNG nằm ở đây: retry sẽ ghi đè mất dữ liệu người khác.
 */
export const RETRYABLE_ERROR_CODES: readonly string[] = [
  ERROR_CODES.INTERNAL_ERROR,
  ERROR_CODES.UPSTREAM_ERROR,
  ERROR_CODES.RATE_LIMITED,
];
