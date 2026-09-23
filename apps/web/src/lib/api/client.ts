/**
 * HTTP client — NƠI DUY NHẤT trong ứng dụng được phép gọi `fetch`.
 *
 * Quy tắc bắt buộc của dự án:
 * - KHÔNG gọi Meta API từ trình duyệt.
 * - KHÔNG gọi LLM API từ trình duyệt.
 * - KHÔNG giữ Meta access token ở frontend.
 * Mọi thứ đó đi qua backend. Client này chỉ nói chuyện với `/api/v1` của mình.
 */

import {
  API_PREFIX,
  CSRF_COOKIE_NAME,
  CSRF_HEADER_NAME,
  IDEMPOTENCY_HEADER_NAME,
  apiBaseUrl,
} from './config';
import { ApiError, networkError, parseErrorBody } from './errors';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface RequestOptions {
  method?: HttpMethod;
  /** Query string; `undefined`, `null` và `''` bị bỏ qua. */
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Body JSON. */
  body?: unknown;
  /** Upload tệp — không tự đặt `Content-Type` để trình duyệt thêm boundary. */
  formData?: FormData;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

const MUTATING_METHODS: readonly HttpMethod[] = ['POST', 'PUT', 'PATCH', 'DELETE'];
let refreshInFlight: Promise<void> | null = null;

function buildQuery(
  query: RequestOptions['query'],
): string {
  if (!query) return '';
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, String(value));
  }
  const serialized = params.toString();
  return serialized === '' ? '' : `?${serialized}`;
}

/** Ghép base URL + tiền tố phiên bản + đường dẫn. */
export function apiUrl(pathname: string, query?: RequestOptions['query']): string {
  const path = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `${apiBaseUrl()}${API_PREFIX}${path}${buildQuery(query)}`;
}

/** URL đầy đủ không kèm tiền tố (dùng cho endpoint ngoài `/api/v1`). */
export function rawUrl(pathname: string): string {
  const path = pathname.startsWith('/') ? pathname : `/${pathname}`;
  return `${apiBaseUrl()}${path}`;
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

/**
 * Khoá chống gửi trùng. Dùng cho upload và mọi thao tác tạo job: nếu người dùng
 * bấm hai lần hoặc mạng chập chờn, backend nhận ra cùng một khoá và không tạo
 * hai job.
 */
export function newIdempotencyKey(prefix = 'req'): string {
  const random =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `${prefix}_${random}`;
}

async function readBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (text.trim() === '') return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function refreshSessionRequest(): Promise<void> {
  let response: Response;
  try {
    response = await fetch(apiUrl('/auth/refresh'), {
      method: 'POST',
      headers: { Accept: 'application/json' },
      credentials: 'include',
      cache: 'no-store',
    });
  } catch (cause) {
    throw networkError(cause);
  }

  if (!response.ok) {
    throw parseErrorBody(await readBody(response), response.status);
  }
}

/** Refresh once for concurrent 401 responses; the server rotates the cookie. */
async function refreshSession(): Promise<void> {
  if (!refreshInFlight) refreshInFlight = refreshSessionRequest();
  const inFlight = refreshInFlight;
  try {
    await inFlight;
  } finally {
    if (refreshInFlight === inFlight) refreshInFlight = null;
  }
}

/**
 * Gọi API và trả dữ liệu đã parse.
 *
 * @throws {ApiError} mọi trường hợp không thành công — kể cả lỗi mạng, để tầng
 * trên chỉ cần xử lý một loại lỗi duy nhất.
 */
export async function apiRequest<T>(
  pathname: string,
  options: RequestOptions = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers };

  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  const send = async (): Promise<Response> => {
    const requestHeaders = { ...headers };
    if (MUTATING_METHODS.includes(method)) {
      const token = readCookie(CSRF_COOKIE_NAME);
      if (token) requestHeaders[CSRF_HEADER_NAME] = token;
      else delete requestHeaders[CSRF_HEADER_NAME];
    }
    try {
      return await fetch(apiUrl(pathname, options.query), {
        method,
        headers: requestHeaders,
        body,
        // Phiên nằm trong cookie HttpOnly do backend đặt — không lưu token ở JS.
        credentials: 'include',
        cache: 'no-store',
        signal: options.signal,
      });
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
      throw networkError(cause);
    }
  };

  let response = await send();
  const isAuthEndpoint = pathname.startsWith('/auth/');
  if (response.status === 401 && !isAuthEndpoint) {
    await refreshSession();
    response = await send();
  }

  const parsed = await readBody(response);

  if (!response.ok) {
    throw parseErrorBody(parsed, response.status);
  }

  return parsed as T;
}

/** Tải tệp (export CSV/XLSX, báo cáo) kèm cookie phiên. */
export async function apiDownload(
  pathname: string,
  query?: RequestOptions['query'],
): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(apiUrl(pathname, query), {
      method: 'GET',
      headers: { Accept: '*/*' },
      credentials: 'include',
      cache: 'no-store',
    });
  } catch (cause) {
    throw networkError(cause);
  }

  if (!response.ok) {
    throw parseErrorBody(await readBody(response), response.status);
  }

  return response.blob();
}

/** Upload một tệp kèm khoá chống trùng. */
export async function apiUpload<T>(
  pathname: string,
  formData: FormData,
  options: { idempotencyKey?: string; signal?: AbortSignal } = {},
): Promise<T> {
  return apiRequest<T>(pathname, {
    method: 'POST',
    formData,
    headers: {
      [IDEMPOTENCY_HEADER_NAME]: options.idempotencyKey ?? newIdempotencyKey('upload'),
    },
    signal: options.signal,
  });
}

/** Kích hoạt tải xuống từ Blob ở trình duyệt. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export { ApiError };
