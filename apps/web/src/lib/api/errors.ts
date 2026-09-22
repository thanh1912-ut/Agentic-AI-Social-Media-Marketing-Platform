/**
 * Lỗi API.
 *
 * Mọi lỗi từ backend đều theo envelope trong `@agentic/contracts`:
 * `{ error: { code, message, details?, request_id? } }`
 *
 * Nguyên tắc: KHÔNG BAO GIỜ hiển thị nguyên văn thông báo kỹ thuật của proxy
 * (HTML, "502 Bad Gateway") cho người dùng. Luôn thay bằng câu tiếng Việt.
 */

import {
  ERROR_CODES,
  RETRYABLE_ERROR_CODES,

  type ErrorCode,
  type FieldError,
} from '@agentic/contracts';

const FALLBACK_MESSAGE = 'Không thực hiện được yêu cầu. Vui lòng thử lại.';

export interface ApiErrorDetails {
  fields?: FieldError[];
  current_version?: number;
  your_version?: number;
  permission?: string;
  retry_after_seconds?: number;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number | null;
  readonly requestId: string | null;
  readonly details: ApiErrorDetails;
  /** Backend nói lỗi này có thử lại được không. */
  readonly retryable: boolean;

  constructor(init: {
    code: string;
    message: string;
    status?: number | null;
    requestId?: string | null;
    details?: ApiErrorDetails;
    retryable?: boolean;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.code = init.code;
    this.status = init.status ?? null;
    this.requestId = init.requestId ?? null;
    this.details = init.details ?? {};
    this.retryable = init.retryable ?? RETRYABLE_ERROR_CODES.includes(init.code);
  }

  /** Chưa đăng nhập → UI đưa về màn hình đăng nhập. */
  get isUnauthenticated(): boolean {
    return (
      this.status === 401 ||
      this.code === ERROR_CODES.UNAUTHENTICATED ||
      this.code === ERROR_CODES.SESSION_EXPIRED
    );
  }

  /** Phiên hết hạn (khác "chưa từng đăng nhập" ở câu chữ hiển thị). */
  get isSessionExpired(): boolean {
    return this.code === ERROR_CODES.SESSION_EXPIRED;
  }

  /** Thiếu quyền → hiện thông báo riêng, không cho retry. */
  get isForbidden(): boolean {
    return this.status === 403 || this.code === ERROR_CODES.FORBIDDEN;
  }

  get isNotFound(): boolean {
    return this.status === 404 || this.code === ERROR_CODES.NOT_FOUND;
  }

  /**
   * Xung đột phiên bản → BẮT BUỘC yêu cầu người dùng tải bản mới.
   * TUYỆT ĐỐI không tự ghi đè, không tự retry.
   */
  get isVersionConflict(): boolean {
    return this.code === ERROR_CODES.VERSION_CONFLICT;
  }

  /** Lỗi mạng (không tới được server) — khác với server trả lỗi. */
  get isNetworkError(): boolean {
    return this.code === 'network_error';
  }

  /** Version hiện tại trên server, dùng để hiển thị "bản mới đã có". */
  get currentVersion(): number | null {
    const value = this.details.current_version;
    return typeof value === 'number' ? value : null;
  }

  /** Chuỗi hiển thị kèm khi cần báo cho người dùng gửi hỗ trợ. */
  get reference(): string | null {
    if (!this.code && !this.requestId) return null;
    return [this.code, this.requestId].filter(Boolean).join(' · ');
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/**
 * Đọc envelope lỗi từ body đã parse. Chấp nhận cả `error` lồng và dạng phẳng
 * (`detail`, `message`) để chịu được backend chưa theo đúng contract.
 */
export function parseErrorBody(body: unknown, status: number | null): ApiError {
  if (!isRecord(body)) {
    return new ApiError({
      code: status && status >= 500 ? ERROR_CODES.INTERNAL_ERROR : 'invalid_response',
      message: FALLBACK_MESSAGE,
      status,
    });
  }

  const nested = isRecord(body.error) ? body.error : null;
  const source: Record<string, unknown> = nested ?? body;

  const rawCode = source.code ?? body.code;
  const code = typeof rawCode === 'string' && rawCode !== '' ? rawCode : 'unknown_error';

  const rawMessage = source.message ?? source.detail ?? body.message;
  const message =
    typeof rawMessage === 'string' && rawMessage.trim() !== '' && looksLikeProse(rawMessage)
      ? rawMessage
      : FALLBACK_MESSAGE;

  const rawRequestId = source.request_id ?? source.requestId ?? body.request_id;
  const requestId = typeof rawRequestId === 'string' ? rawRequestId : null;

  const rawDetails = source.details ?? body.details;
  const details: ApiErrorDetails = isRecord(rawDetails)
    ? (rawDetails as ApiErrorDetails)
    : {};

  const rawRetryable = source.retryable;
  const retryable = typeof rawRetryable === 'boolean' ? rawRetryable : undefined;

  return new ApiError({ code, message, status, requestId, details, retryable });
}

/**
 * Proxy/load-balancer có thể trả HTML hoặc plain text. Những chuỗi đó không
 * phải câu dành cho người dùng cuối.
 */
function looksLikeProse(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed.startsWith('<')) return false;
  if (/^\d{3}\s/.test(trimmed)) return false;
  if (/bad gateway|service unavailable|gateway timeout/i.test(trimmed)) return false;
  return true;
}

export function networkError(cause?: unknown): ApiError {
  return new ApiError({
    code: 'network_error',
    message: 'Không kết nối được tới máy chủ. Kiểm tra kết nối mạng rồi thử lại.',
    retryable: true,
    details: cause instanceof Error ? { cause: cause.message } : {},
  });
}

export type { ErrorCode };
