/**
 * Định dạng hiển thị theo chuẩn tiếng Việt.
 * Mọi màn hình dùng chung các hàm này để ngày giờ và số không bị mỗi chỗ một kiểu.
 */

const LOCALE = 'vi-VN';

/** `15/03/2026` */
export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return '—';
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(date);
}

/** `15/03/2026 14:30` */
export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return '—';
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(LOCALE, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** `15/03` — dùng cho trục thời gian của biểu đồ. */
export function formatDayMonth(value: string | Date): string {
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: '2-digit' }).format(date);
}

/** `1.234` */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat(LOCALE).format(value);
}

/** Số gọn cho thẻ số liệu: `1,2 N` (nghìn), `3,4 Tr` (triệu). */
export function formatCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 }).format(value / 1_000_000)} Tr`;
  if (abs >= 1_000) return `${new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 }).format(value / 1_000)} N`;
  return formatNumber(value);
}

/** `12,5%` */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `${new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)}%`;
}

/**
 * Khoảng thời gian tương đối: "vừa xong", "5 phút trước", "2 giờ trước".
 * Dùng cho "lần đồng bộ gần nhất" và tuổi của job.
 */
export function formatRelative(value: string | Date | null | undefined): string {
  if (!value) return 'chưa có';
  const date = typeof value === 'string' ? new Date(value) : value;
  if (Number.isNaN(date.getTime())) return 'chưa có';

  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 0) return 'vừa xong';
  if (seconds < 60) return 'vừa xong';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} phút trước`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} ngày trước`;

  return formatDate(date);
}

/** `1,4 MB` */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 }).format(value)} ${units[unitIndex]}`;
}

/** Cửa sổ đo: `01/03/2026 – 31/03/2026`. */
export function formatWindow(start: string, end: string): string {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

/**
 * Đếm ngày còn lại tới hạn. Dùng cho lời mời và token kết nối.
 */
export function formatDeadline(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const days = Math.ceil((date.getTime() - Date.now()) / 86_400_000);
  if (days < 0) return 'đã hết hạn';
  if (days === 0) return 'hết hạn hôm nay';
  if (days === 1) return 'còn 1 ngày';
  return `còn ${days} ngày`;
}
