'use client';

/**
 * Thư viện UI dùng chung.
 *
 * Mọi màn hình lấy component từ đây để trạng thái loading / empty / error /
 * thiếu quyền / dữ liệu demo trông giống nhau ở mọi chỗ.
 *
 * Quy tắc đã cài sẵn trong component, không được phá:
 * - Nút bị khoá PHẢI kèm lý do (`disabledReason`).
 * - Lỗi hiển thị `role="alert"`, có mã lỗi + mã yêu cầu, và chỉ hiện nút "Thử lại"
 *   khi lỗi thật sự thử lại được.
 * - Dữ liệu demo PHẢI mang nhãn nhìn thấy được.
 */

import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Sắc thái màu — khai báo một chỗ
// ---------------------------------------------------------------------------

export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export const TONE_CLASS: Record<Tone, string> = {
  neutral: 'bg-slate-100 text-slate-700 border-slate-200',
  info: 'bg-sky-50 text-sky-800 border-sky-200',
  success: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  warning: 'bg-amber-50 text-amber-900 border-amber-200',
  danger: 'bg-rose-50 text-rose-800 border-rose-200',
};

export const TONE_DOT_CLASS: Record<Tone, string> = {
  neutral: 'bg-slate-400',
  info: 'bg-sky-500',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  danger: 'bg-rose-500',
};

// ---------------------------------------------------------------------------
// Badge & trạng thái
// ---------------------------------------------------------------------------

export function Badge({
  children,
  tone = 'neutral',
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap ${TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

/** Badge có chấm màu — dùng cho trạng thái để không chỉ dựa vào màu chữ. */
export function StatusBadge({
  label,
  tone = 'neutral',
  title,
}: {
  label: string;
  tone?: Tone;
  title?: string;
}) {
  return (
    <Badge tone={tone} title={title}>
      <span aria-hidden="true" className={`size-1.5 rounded-full ${TONE_DOT_CLASS[tone]}`} />
      {label}
    </Badge>
  );
}

/**
 * Nhãn dữ liệu demo. BẮT BUỘC dùng ở mọi màn hình đang hiển thị dữ liệu mẫu.
 */
export function DemoBadge({ label = 'Dữ liệu demo' }: { label?: string }) {
  return (
    <Badge tone="warning" title="Số liệu mẫu để xem thử luồng làm việc, không phải dữ liệu thật của doanh nghiệp bạn.">
      {label}
    </Badge>
  );
}

/** Dải cảnh báo đặt đầu màn hình khi nội dung là dữ liệu demo. */
export function DemoNotice({ children }: { children?: ReactNode }) {
  return (
    <div
      role="note"
      className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
    >
      <strong className="font-semibold">Dữ liệu demo. </strong>
      {children ??
        'Màn hình này đang hiển thị dữ liệu mẫu để bạn xem thử luồng làm việc. Số liệu không phải của doanh nghiệp bạn.'}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tải & tiến độ
// ---------------------------------------------------------------------------

export function Spinner({ label = 'Đang tải' }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-slate-600">
      <span
        aria-hidden="true"
        className="size-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600"
      />
      {label}
    </span>
  );
}

export function LoadingBlock({ label = 'Đang tải dữ liệu…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-10">
      <Spinner label={label} />
    </div>
  );
}

export function SkeletonLines({ count = 3 }: { count?: number }) {
  return (
    <div role="status" aria-label="Đang tải" className="space-y-2">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="h-4 animate-pulse rounded bg-slate-200" />
      ))}
    </div>
  );
}

/**
 * Thanh tiến độ.
 *
 * `value = null` nghĩa là CHƯA XÁC ĐỊNH ĐƯỢC tổng khối lượng → thanh chạy ở
 * dạng không xác định. TUYỆT ĐỐI không bịa ra một phần trăm nào trong trường hợp
 * này: backend chỉ gửi `progress_current`/`progress_total`, và nếu thiếu `total`
 * thì không có phần trăm thật để hiển thị.
 */
export function ProgressBar({
  value,
  label,
  tone = 'info',
}: {
  value: number | null;
  label: string;
  tone?: Tone;
}) {
  if (value === null) {
    return (
      <div className="space-y-1">
        <div
          role="progressbar"
          aria-label={`${label} — chưa xác định được tổng khối lượng`}
          className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
        >
          <div className={`h-full w-1/3 animate-pulse rounded-full ${TONE_DOT_CLASS[tone]}`} />
        </div>
        <p className="text-xs text-slate-500">
          {label} — chưa xác định được tổng khối lượng
        </p>
      </div>
    );
  }

  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="space-y-1">
      <div
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
      >
        <div
          className={`h-full rounded-full transition-[width] duration-300 ${TONE_DOT_CLASS[tone]}`}
          style={{ width: `${clamped}%` }}
        />
      </div>
      <p className="text-xs text-slate-500">
        {label} — {clamped}%
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trạng thái rỗng & lỗi
// ---------------------------------------------------------------------------

export function EmptyState({
  title,
  description,
  action,
  tone = 'neutral',
}: {
  title: string;
  description: string;
  action?: ReactNode;
  tone?: Tone;
}) {
  return (
    <div
      className={`rounded-lg border border-dashed px-6 py-10 text-center ${TONE_CLASS[tone]}`}
    >
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mx-auto mt-1 max-w-prose text-sm opacity-90">{description}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

/**
 * Khối lỗi.
 *
 * Hiển thị mã lỗi + mã yêu cầu để người dùng gửi cho hỗ trợ, nhưng KHÔNG bao giờ
 * hiện stack trace hay thông báo kỹ thuật của proxy.
 */
export function ErrorPanel({
  title = 'Không tải được dữ liệu',
  message,
  code,
  requestId,
  retryable = false,
  onRetry,
  retryLabel = 'Thử lại',
  children,
}: {
  title?: string;
  message: string;
  code?: string | null;
  requestId?: string | null;
  retryable?: boolean;
  onRetry?: () => void;
  retryLabel?: string;
  children?: ReactNode;
}) {
  return (
    <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-4">
      <h3 className="text-sm font-semibold text-rose-900">{title}</h3>
      <p className="mt-1 text-sm text-rose-800">{message}</p>
      {children}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        {retryable && onRetry ? (
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {retryLabel}
          </Button>
        ) : null}
        {code || requestId ? (
          <p className="text-xs text-rose-700/80">
            {code ? <>Mã lỗi: <code className="font-mono">{code}</code></> : null}
            {code && requestId ? ' · ' : null}
            {requestId ? <>Mã yêu cầu: <code className="font-mono">{requestId}</code></> : null}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Xung đột phiên bản (409).
 *
 * KHÔNG có nút "Thử lại" — bấm lại sẽ ghi đè mất thay đổi của người khác.
 * Chỉ có một lối đi: tải bản mới.
 */
export function VersionConflictNotice({
  currentVersion,
  onReload,
}: {
  currentVersion?: number | null;
  onReload: () => void;
}) {
  return (
    <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-4">
      <h3 className="text-sm font-semibold text-amber-900">
        Nội dung này vừa được người khác cập nhật
      </h3>
      <p className="mt-1 text-sm text-amber-900">
        Bạn đang sửa một bản cũ
        {currentVersion ? <> (bản mới nhất là bản {currentVersion})</> : null}. Để tránh ghi đè
        mất thay đổi của đồng nghiệp, hệ thống không lưu tự động. Hãy chép lại phần bạn vừa sửa
        rồi tải bản mới nhất.
      </p>
      <div className="mt-3">
        <Button variant="secondary" size="sm" onClick={onReload}>
          Tải bản mới nhất
        </Button>
      </div>
    </div>
  );
}

/**
 * Thiếu quyền.
 *
 * Nói rõ thiếu quyền gì và ai làm được — không chỉ báo "bạn không có quyền".
 */
export function PermissionNotice({
  message,
  requiredPermission,
}: {
  message: string;
  requiredPermission?: string;
}) {
  return (
    <div role="note" className="rounded-lg border border-slate-300 bg-slate-50 px-4 py-3">
      <h3 className="text-sm font-semibold text-slate-800">Bạn không thực hiện được việc này</h3>
      <p className="mt-1 text-sm text-slate-700">{message}</p>
      {requiredPermission ? (
        <p className="mt-1 text-xs text-slate-500">
          Quyền cần có: <code className="font-mono">{requiredPermission}</code>
        </p>
      ) : null}
    </div>
  );
}

/**
 * Tính năng chưa khả dụng.
 *
 * BẮT BUỘC kèm `reason`. Nếu có `remedy` thì hiện thêm việc người dùng cần làm.
 */
export function UnavailableNotice({
  title,
  reason,
  remedy,
  action,
}: {
  title: string;
  reason: string;
  remedy?: string;
  action?: ReactNode;
}) {
  return (
    <div role="note" className="rounded-lg border border-slate-300 bg-slate-50 px-4 py-3">
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      <p className="mt-1 text-sm text-slate-700">{reason}</p>
      {remedy ? <p className="mt-1 text-sm text-slate-600">Việc cần làm: {remedy}</p> : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Khung & số liệu
// ---------------------------------------------------------------------------

export function Card({
  title,
  description,
  actions,
  children,
  footer,
}: {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {title || actions ? (
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
          <div>
            {title ? <h2 className="text-base font-semibold text-slate-900">{title}</h2> : null}
            {description ? (
              <p className="mt-0.5 text-sm text-slate-600">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
        </header>
      ) : null}
      <div className="px-5 py-4">{children}</div>
      {footer ? (
        <footer className="border-t border-slate-200 px-5 py-3 text-sm text-slate-600">
          {footer}
        </footer>
      ) : null}
    </section>
  );
}

/**
 * Thẻ số liệu.
 *
 * `value` là chuỗi đã định dạng sẵn — component này KHÔNG tự đổi `null` thành 0.
 * Việc phân biệt số 0 thật với "chưa có dữ liệu" do tầng gọi quyết định.
 */
export function StatCard({
  label,
  value,
  hint,
  tone = 'neutral',
  badge,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: Tone;
  badge?: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-slate-600">{label}</p>
        {badge}
      </div>
      <p
        className={`mt-1 text-2xl font-semibold tabular-nums ${
          tone === 'warning' ? 'text-amber-700' : 'text-slate-900'
        }`}
      >
        {value}
      </p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}

/** Một dòng nhãn–giá trị, dùng trong trang chi tiết. */
export function FieldRow({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div className="grid gap-1 border-b border-slate-100 py-3 last:border-b-0 sm:grid-cols-[200px_1fr] sm:gap-4">
      <dt className="text-sm font-medium text-slate-600">{label}</dt>
      <dd className="text-sm text-slate-900">
        {children}
        {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
      </dd>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Nút
// ---------------------------------------------------------------------------

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';

const BUTTON_VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary: 'bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-400',
  secondary:
    'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 disabled:text-slate-400',
  danger: 'bg-rose-600 text-white hover:bg-rose-700 disabled:bg-rose-300',
  ghost: 'text-slate-700 hover:bg-slate-100 disabled:text-slate-400',
};

/**
 * Nút có lý do khoá.
 *
 * Nếu `disabled` mà không truyền `disabledReason`, nút vẫn bị khoá nhưng KHÔNG
 * giải thích — đây là lỗi UX. Luôn truyền `disabledReason`.
 */
export function Button({
  children,
  onClick,
  type = 'button',
  variant = 'primary',
  size = 'md',
  disabled = false,
  disabledReason,
  loading = false,
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  type?: 'button' | 'submit';
  variant?: ButtonVariant;
  size?: 'sm' | 'md';
  disabled?: boolean;
  disabledReason?: string;
  loading?: boolean;
  title?: string;
}) {
  const isDisabled = disabled || loading;
  const tooltip = title ?? (isDisabled ? disabledReason : undefined);
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={isDisabled}
      title={tooltip}
      aria-disabled={isDisabled}
      aria-describedby={isDisabled && disabledReason ? 'btn-disabled-reason' : undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors ${
        size === 'sm' ? 'px-3 py-1.5 text-sm' : 'px-4 py-2 text-sm'
      } ${BUTTON_VARIANT_CLASS[variant]} disabled:cursor-not-allowed`}
    >
      {loading ? (
        <span
          aria-hidden="true"
          className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      ) : null}
      {children}
    </button>
  );
}

/** Dòng giải thích đặt ngay dưới một nút vừa bị khoá. */
export function DisabledReason({ children }: { children: ReactNode }) {
  return (
    <p id="btn-disabled-reason" className="text-xs text-slate-500">
      {children}
    </p>
  );
}
