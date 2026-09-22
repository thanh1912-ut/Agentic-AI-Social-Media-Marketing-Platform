'use client';

/**
 * Tổng quan doanh nghiệp.
 *
 * Ba nguồn dữ liệu độc lập (tiến độ nhập liệu, hồ sơ thương hiệu, tài liệu) —
 * mỗi nguồn có khối loading / lỗi / rỗng riêng để một nguồn hỏng không làm trắng
 * cả trang.
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import {
  BRAND_FIELD_KEYS,
  DOCUMENT_ERROR_LABELS,
  DOCUMENT_STATUS_LABELS,
  DOCUMENT_STATUSES,
  FIELD_REVIEW_STATES,
  type BrandFieldKey,
  type BrandProfile,
  type DocumentStatus,
  type DocumentUpload,
  type OnboardingState,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import { formatNumber, formatPercent, formatRelative } from '@/lib/format';
import { useBrandProfile, useDocuments, useOnboarding } from '@/lib/hooks';
import {
  Button,
  Card,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  PermissionNotice,
  ProgressBar,
  StatCard,
  StatusBadge,
  type Tone,
} from '@/components/ui';

/**
 * Thứ tự hiển thị trường hồ sơ thương hiệu. Danh sách khoá lấy từ hợp đồng,
 * không viết lại chuỗi ở đây.
 */
const BRAND_FIELD_ORDER: BrandFieldKey[] = [
  BRAND_FIELD_KEYS.BUSINESS_NAME,
  BRAND_FIELD_KEYS.INDUSTRY,
  BRAND_FIELD_KEYS.DESCRIPTION,
  BRAND_FIELD_KEYS.PRODUCTS,
  BRAND_FIELD_KEYS.TARGET_AUDIENCE,
  BRAND_FIELD_KEYS.BRAND_VOICE,
  BRAND_FIELD_KEYS.TONE_KEYWORDS,
  BRAND_FIELD_KEYS.DO_NOT_USE,
  BRAND_FIELD_KEYS.COMPETITORS,
  BRAND_FIELD_KEYS.CONTACT,
];

const DOCUMENT_STATUS_ORDER: DocumentStatus[] = [
  DOCUMENT_STATUSES.PENDING,
  DOCUMENT_STATUSES.UPLOADING,
  DOCUMENT_STATUSES.PROCESSING,
  DOCUMENT_STATUSES.READY,
  DOCUMENT_STATUSES.FAILED,
  DOCUMENT_STATUSES.UNSUPPORTED,
];

/**
 * KHOẢNG TRỐNG HỢP ĐỒNG: `OnboardingState.steps[].status` chưa có bảng nhãn
 * trong `@agentic/contracts/labels.ts` (khác với trạng thái job/tài liệu). Khai
 * báo tạm ở đây, một chỗ duy nhất, để không rải chuỗi tiếng Việt khắp màn hình.
 */
const ONBOARDING_STEP_STATUS: Record<
  OnboardingState['steps'][number]['status'],
  { label: string; tone: Tone }
> = {
  todo: { label: 'Chưa làm', tone: 'neutral' },
  in_progress: { label: 'Đang làm', tone: 'info' },
  done: { label: 'Đã xong', tone: 'success' },
  blocked: { label: 'Đang bị chặn', tone: 'warning' },
};

const STEP_CIRCLE_CLASS: Record<OnboardingState['steps'][number]['status'], string> = {
  todo: 'border-slate-200 bg-slate-100 text-slate-700',
  in_progress: 'border-sky-200 bg-sky-50 text-sky-800',
  done: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  blocked: 'border-amber-200 bg-amber-50 text-amber-900',
};

/** Lỗi tài liệu: luôn có câu tiếng Việt, ưu tiên câu backend gửi kèm. */
function documentError(error: NonNullable<DocumentUpload['error']>): {
  message: string;
  hint: string;
} {
  const meta = DOCUMENT_ERROR_LABELS[error.code];
  const message = (error.message ?? '').trim();
  const hint = (error.hint ?? '').trim();
  return {
    message: message !== '' ? message : meta.label,
    hint: hint !== '' ? hint : meta.hint,
  };
}

/**
 * Màn hình đã có trong bản dựng này, tính theo đoạn đường dẫn sau `/w/{id}`.
 * `OnboardingState.steps[].href` do máy chủ trả về có thể trỏ tới màn hình của
 * lát cắt sau (vd `/campaigns`); khi đó hiện ghi chú thay vì một liên kết chết.
 */
const AVAILABLE_SCREEN_SEGMENTS: readonly string[] = ['', 'brand', 'documents', 'settings'];

/**
 * Chuẩn hoá `href` của bước nhập liệu. Máy chủ có thể trả đường dẫn tương đối
 * (`/brand`) hoặc đã kèm doanh nghiệp (`/w/{id}/brand`) — cả hai đều phải ra đúng
 * địa chỉ trong ứng dụng.
 */
function resolveStepTarget(
  workspaceId: string,
  href: string,
): { href: string } | { unavailable: string } | null {
  const trimmed = href.trim();
  if (trimmed === '') return null;
  if (/^https?:\/\//i.test(trimmed)) return { href: trimmed };

  const withoutLeadingSlash = trimmed.replace(/^\/+/, '');
  const workspacePrefix = `w/${workspaceId}/`;
  const segment = withoutLeadingSlash.startsWith(workspacePrefix)
    ? withoutLeadingSlash.slice(workspacePrefix.length)
    : withoutLeadingSlash;
  const head = segment.split('/')[0] ?? '';

  if (!AVAILABLE_SCREEN_SEGMENTS.includes(head)) return { unavailable: segment };
  return { href: `/w/${workspaceId}${segment === '' ? '' : `/${segment}`}` };
}

function countBrandFields(profile: BrandProfile) {
  let awaiting = 0;
  let missing = 0;
  let confirmed = 0;
  for (const key of BRAND_FIELD_ORDER) {
    const state = profile[key].state;
    if (state === FIELD_REVIEW_STATES.SUGGESTED || state === FIELD_REVIEW_STATES.CONFLICT) {
      awaiting += 1;
    } else if (state === FIELD_REVIEW_STATES.MISSING) {
      missing += 1;
    } else if (state === FIELD_REVIEW_STATES.CONFIRMED) {
      confirmed += 1;
    }
  }
  return { awaiting, missing, confirmed, total: BRAND_FIELD_ORDER.length };
}

/**
 * Khối lỗi dùng chung trong trang: lỗi thiếu quyền hiển thị bằng `PermissionNotice`
 * (kèm quyền còn thiếu), các lỗi khác dùng `ErrorPanel` và chỉ hiện "Thử lại" khi
 * backend nói lỗi đó thử lại được.
 */
function SectionError({
  title,
  error,
  onRetry,
}: {
  title: string;
  error: unknown;
  onRetry: () => void;
}) {
  const apiError = error instanceof ApiError ? error : null;

  if (apiError?.isForbidden) {
    const permission = apiError.details.permission;
    return (
      <PermissionNotice
        message={apiError.message}
        requiredPermission={typeof permission === 'string' ? permission : undefined}
      />
    );
  }

  return (
    <ErrorPanel
      title={title}
      message={apiError?.message ?? 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'}
      code={apiError?.code}
      requestId={apiError?.requestId}
      retryable={apiError?.retryable ?? true}
      onRetry={onRetry}
    />
  );
}

export default function TrangTongQuan() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  // Không phải thành viên thì không gọi API của doanh nghiệp đó.
  const activeId = workspace ? workspaceId : '';

  const onboarding = useOnboarding(activeId);
  const brand = useBrandProfile(activeId);
  const documents = useDocuments(activeId);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold text-slate-900">Không mở được doanh nghiệp này</h1>
        <PermissionNotice message="Bạn không thuộc doanh nghiệp này, nên không xem được số liệu tổng quan của doanh nghiệp." />
        <Button variant="secondary" onClick={() => router.push('/')}>
          Về trang chủ
        </Button>
      </div>
    );
  }

  const brandCounts = brand.data ? countBrandFields(brand.data) : null;
  const completeness =
    brand.data && typeof brand.data.completeness === 'number' && Number.isFinite(brand.data.completeness)
      ? brand.data.completeness
      : null;

  const docs = documents.data ?? null;
  const readyDocs = docs?.filter((doc) => doc.status === DOCUMENT_STATUSES.READY) ?? [];
  const failedDocs = docs?.filter((doc) => doc.status === DOCUMENT_STATUSES.FAILED) ?? [];

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">Tổng quan — {workspace.name}</h1>
        <p className="mt-1 text-sm text-slate-600">
          Tiến độ nhập thông tin doanh nghiệp và những việc đang chờ bạn xử lý.
        </p>
      </header>

      {/* ---------------------------------------------------------------- */}
      {/* Tiến độ nhập liệu                                                */}
      {/* ---------------------------------------------------------------- */}
      <Card
        title="Tiến độ nhập thông tin doanh nghiệp"
        description="Làm lần lượt từng bước. Bước bị chặn luôn nêu rõ lý do."
      >
        {onboarding.isPending ? (
          <LoadingBlock label="Đang tải tiến độ nhập thông tin…" />
        ) : onboarding.isError ? (
          <SectionError
            title="Không tải được tiến độ nhập thông tin"
            error={onboarding.error}
            onRetry={() => void onboarding.refetch()}
          />
        ) : onboarding.data.steps.length === 0 ? (
          <EmptyState
            title="Chưa có bước nào để hiển thị"
            description="Hệ thống chưa trả về bước nhập thông tin nào cho doanh nghiệp này. Hãy tải tài liệu lên trước, hoặc liên hệ đội kỹ thuật nếu tình trạng này vẫn tiếp diễn."
            action={
              <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}/documents`}>
                Mở trang Tài liệu
              </Link>
            }
          />
        ) : (
          <div className="space-y-5">
            <ProgressBar
              value={
                onboarding.data.total_count > 0
                  ? (onboarding.data.completed_count / onboarding.data.total_count) * 100
                  : null
              }
              label={`Đã hoàn thành ${formatNumber(onboarding.data.completed_count)}/${formatNumber(
                onboarding.data.total_count,
              )} bước`}
              tone="success"
            />
            <ol className="space-y-3">
              {onboarding.data.steps.map((step, index) => {
                const meta = ONBOARDING_STEP_STATUS[step.status];
                const target = resolveStepTarget(workspaceId, step.href);
                return (
                  <li key={step.key} className="flex gap-3">
                    <span
                      aria-hidden="true"
                      className={`mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-semibold ${
                        STEP_CIRCLE_CLASS[step.status]
                      }`}
                    >
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium text-slate-900">{step.label}</p>
                        <StatusBadge label={meta.label} tone={meta.tone} />
                      </div>
                      {step.status === 'blocked' ? (
                        <p className="mt-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                          <strong className="font-semibold">Vì sao chưa làm được: </strong>
                          {step.blocked_reason && step.blocked_reason.trim() !== ''
                            ? step.blocked_reason
                            : 'Hệ thống chưa nêu lý do cụ thể cho bước này. Hãy thử tải lại trang hoặc liên hệ đội kỹ thuật.'}
                        </p>
                      ) : null}
                      {target && 'href' in target ? (
                        <p className="mt-1 text-sm">
                          <Link className="font-medium text-slate-900 underline" href={target.href}>
                            {step.status === 'done' ? 'Xem lại bước này' : 'Làm bước này'}
                          </Link>
                        </p>
                      ) : null}
                      {target && 'unavailable' in target ? (
                        <p className="mt-1 text-xs text-slate-500">
                          Bước này thuộc màn hình{' '}
                          <code className="font-mono">{target.unavailable}</code> — màn hình đó chưa
                          có trong bản dựng này nên chưa mở được.
                        </p>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        )}
      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* Hồ sơ thương hiệu                                                */}
      {/* ---------------------------------------------------------------- */}
      <section aria-labelledby="tq-ho-so" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 id="tq-ho-so" className="text-base font-semibold text-slate-900">
            Hồ sơ thương hiệu
          </h2>
          <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}/brand`}>
            Mở hồ sơ thương hiệu
          </Link>
        </div>

        {brand.isPending ? (
          <LoadingBlock label="Đang tải hồ sơ thương hiệu…" />
        ) : brand.isError ? (
          <SectionError
            title="Không tải được hồ sơ thương hiệu"
            error={brand.error}
            onRetry={() => void brand.refetch()}
          />
        ) : brandCounts === null ? (
          <EmptyState
            title="Chưa đọc được hồ sơ thương hiệu"
            description="Hệ thống không trả về dữ liệu hồ sơ cho doanh nghiệp này. Hãy thử tải lại trang."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Độ hoàn thiện hồ sơ"
              value={completeness === null ? '—' : formatPercent(completeness * 100, 0)}
              hint={
                completeness === null
                  ? 'Máy chủ chưa trả về độ hoàn thiện nên chưa hiển thị được con số.'
                  : `${formatNumber(brandCounts.confirmed)}/${formatNumber(brandCounts.total)} trường đã được xác nhận.`
              }
              tone={completeness !== null && completeness < 1 ? 'warning' : 'neutral'}
            />
            <StatCard
              label="Trường đang chờ xác nhận"
              value={formatNumber(brandCounts.awaiting)}
              hint="Gồm trường AI gợi ý và trường tài liệu mâu thuẫn — bạn cần chọn hoặc xác nhận."
              tone={brandCounts.awaiting > 0 ? 'warning' : 'neutral'}
            />
            <StatCard
              label="Trường còn thiếu"
              value={formatNumber(brandCounts.missing)}
              hint="Chưa tìm thấy thông tin trong tài liệu đã tải lên và chưa được nhập tay."
              tone={brandCounts.missing > 0 ? 'warning' : 'neutral'}
            />
            <StatCard
              label="Tài liệu đã xử lý xong"
              value={docs === null ? '—' : formatNumber(readyDocs.length)}
              hint={
                docs === null
                  ? 'Chưa tải được danh sách tài liệu nên chưa đếm được.'
                  : `Trên tổng số ${formatNumber(docs.length)} tài liệu đã tải lên.`
              }
            />
          </div>
        )}
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Tài liệu                                                         */}
      {/* ---------------------------------------------------------------- */}
      <Card
        title="Tài liệu đã tải lên"
        description="Tình trạng xử lý từng tài liệu và các tài liệu cần bạn xử lý lại."
        actions={
          <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}/documents`}>
            Quản lý tài liệu
          </Link>
        }
      >
        {documents.isPending ? (
          <LoadingBlock label="Đang tải danh sách tài liệu…" />
        ) : documents.isError ? (
          <SectionError
            title="Không tải được danh sách tài liệu"
            error={documents.error}
            onRetry={() => void documents.refetch()}
          />
        ) : docs === null || docs.length === 0 ? (
          <EmptyState
            title="Chưa có tài liệu nào"
            description="Doanh nghiệp chưa tải lên tài liệu nào. Hãy tải hồ sơ năng lực, bảng giá hoặc mô tả sản phẩm để hệ thống đọc và gợi ý thông tin thương hiệu."
            action={
              <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}/documents`}>
                Tải tài liệu lên
              </Link>
            }
          />
        ) : (
          <div className="space-y-4">
            <ul className="flex flex-wrap gap-3">
              {DOCUMENT_STATUS_ORDER.map((status) => {
                const count = docs.filter((doc) => doc.status === status).length;
                if (count === 0) return null;
                const meta = DOCUMENT_STATUS_LABELS[status];
                return (
                  <li key={status} className="flex items-center gap-2">
                    <StatusBadge label={meta.label} tone={meta.tone} />
                    <span className="text-sm font-medium tabular-nums text-slate-900">
                      {formatNumber(count)}
                    </span>
                  </li>
                );
              })}
              <li className="flex items-center gap-2">
                <span className="text-sm text-slate-600">Tổng cộng</span>
                <span className="text-sm font-medium tabular-nums text-slate-900">
                  {formatNumber(docs.length)}
                </span>
              </li>
            </ul>

            {failedDocs.length > 0 ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3">
                <h3 className="text-sm font-semibold text-rose-900">
                  {formatNumber(failedDocs.length)} tài liệu xử lý lỗi — cần bạn xử lý
                </h3>
                <ul className="mt-2 space-y-2">
                  {failedDocs.map((doc) => {
                    const detail = doc.error ? documentError(doc.error) : null;
                    return (
                      <li key={doc.id} className="text-sm text-rose-900">
                        <p className="font-medium">{doc.filename}</p>
                        <p className="mt-0.5">
                          {detail
                            ? detail.message
                            : 'Tài liệu bị lỗi nhưng máy chủ chưa gửi kèm mô tả lỗi. Hãy mở trang Tài liệu để đọc lại tài liệu.'}
                        </p>
                        {detail ? <p className="mt-0.5 text-rose-800">Việc cần làm: {detail.hint}</p> : null}
                        <p className="mt-0.5 text-xs text-rose-700/80">
                          Nộp lúc {formatRelative(doc.uploaded_at)}
                        </p>
                      </li>
                    );
                  })}
                </ul>
                <div className="mt-3">
                  <Link className="text-sm font-medium text-rose-900 underline" href={`/w/${workspaceId}/documents`}>
                    Mở trang Tài liệu để đọc lại
                  </Link>
                </div>
              </div>
            ) : null}
          </div>
        )}
      </Card>
    </div>
  );
}
