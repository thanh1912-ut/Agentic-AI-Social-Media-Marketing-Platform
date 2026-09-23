/**
 * Cấu hình tầng API.
 *
 * Base URL được đọc LÚC CHẠY trong trình duyệt (không phải lúc build) để MỘT
 * image dùng được cho nhiều môi trường mà không cần build lại.
 *
 * Thứ tự ưu tiên:
 *   1. `window.__AGENTIC_RUNTIME_CONFIG__.apiBaseUrl`  — server nhúng vào HTML
 *   2. `process.env.NEXT_PUBLIC_API_BASE_URL`          — lúc build (dev local)
 *   3. Mặc định `http://127.0.0.1:8000`
 *
 * ⚠️ TÊN BIẾN: chỉ dùng `NEXT_PUBLIC_API_BASE_URL`. Khi viết compose/Dockerfile,
 * M2 cần truyền ĐÚNG tên này (repo tham chiếu từng bị lệch tên
 * `WEB_PUBLIC_API_BASE_URL` khiến app âm thầm rơi về mặc định).
 */

export interface RuntimeConfig {
  apiBaseUrl?: string;
  /** Bật mock trong trình duyệt. Chỉ dùng cho demo/pilot chưa có backend. */
  useMocks?: boolean;
  /** Nhãn môi trường hiển thị trên UI, vd "Bản demo". */
  environmentLabel?: string;
}

declare global {
  interface Window {
    __AGENTIC_RUNTIME_CONFIG__?: RuntimeConfig;
  }
}

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

function trimTrailingSlashes(value: string): string {
  return value.replace(/\/+$/, '');
}

function validateApiOrigin(value: string): string {
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error('NEXT_PUBLIC_API_BASE_URL phải là origin đầy đủ, ví dụ https://api.example.com.');
  }
  if (
    (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') ||
    parsed.username !== '' ||
    parsed.password !== '' ||
    parsed.pathname !== '/' ||
    parsed.search !== '' ||
    parsed.hash !== ''
  ) {
    throw new Error('NEXT_PUBLIC_API_BASE_URL chỉ nhận API origin, không thêm /api/v1 hoặc path khác.');
  }
  return trimTrailingSlashes(parsed.origin);
}

function readRuntimeConfig(): RuntimeConfig {
  if (typeof window === 'undefined') return {};
  return window.__AGENTIC_RUNTIME_CONFIG__ ?? {};
}

/** Base URL của API, chưa gồm `/api/v1`. */
export function apiBaseUrl(): string {
  const runtime = readRuntimeConfig().apiBaseUrl;
  if (runtime && runtime.trim() !== '') return validateApiOrigin(runtime.trim());

  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (fromEnv && fromEnv.trim() !== '') return validateApiOrigin(fromEnv.trim());

  return validateApiOrigin(DEFAULT_API_BASE_URL);
}

/** Tiền tố phiên bản API. Mọi endpoint đều nằm dưới đây. */
export const API_PREFIX = '/api/v1';

/** Có đang chạy bằng mock hay không. */
export function useMocks(): boolean {
  const runtime = readRuntimeConfig().useMocks;
  if (typeof runtime === 'boolean') return runtime;
  return process.env.NEXT_PUBLIC_USE_MOCKS === '1';
}

export function environmentLabel(): string {
  return readRuntimeConfig().environmentLabel ?? '';
}

/**
 * Tên cookie CSRF do backend đặt. Client đọc cookie này và gửi lại qua header
 * cho mọi request ghi — backend vẫn là nơi kiểm tra cuối cùng.
 */
export const CSRF_COOKIE_NAME = 'agentic_csrf';
export const CSRF_HEADER_NAME = 'X-CSRF-Token';

/** Header mang khoá chống gửi trùng cho các thao tác không idempotent. */
export const IDEMPOTENCY_HEADER_NAME = 'Idempotency-Key';
