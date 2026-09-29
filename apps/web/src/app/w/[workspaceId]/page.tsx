'use client';

/**
 * Tổng quan doanh nghiệp.
 *
 * Ba nguồn dữ liệu độc lập (tiến độ nhập liệu, hồ sơ thương hiệu, tài liệu) —
 * mỗi nguồn có khối loading / lỗi / rỗng riêng để một nguồn hỏng không làm trắng
 * cả trang.
 */

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import {
  DOCUMENT_ERROR_LABELS,
  DOCUMENT_STATUS_LABELS,
  DOCUMENT_STATUSES,
  type OnboardingState,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import { useMocks } from '@/lib/api/config';
import type { ApiDocument as DocumentUpload } from '@/lib/api/types';
import { formatNumber, formatRelative } from '@/lib/format';
import { useBrandProfile, useDocuments, useOnboarding } from '@/lib/hooks';
import {
  Button,
  Card,
  DemoNotice,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  PermissionNotice,
  ProgressBar,
  StatCard,
  StatusBadge,
  UnavailableNotice,
  type Tone,
} from '@/components/ui';

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
  const meta =
    Object.entries(DOCUMENT_ERROR_LABELS).find(([code]) => code === error.code)?.[1] ?? {
      label: 'Không đọc được tài liệu',
      hint: 'Kiểm tra tệp rồi thử tải lên lại. Nếu lỗi tiếp tục, liên hệ hỗ trợ và gửi mã yêu cầu.',
    };
  const message = (error.message ?? '').trim();
  const hint = (error.hint ?? '').trim();
  return {
    message: message !== '' ? message : meta.label,
    hint: hint !== '' ? hint : meta.hint,
  };
}

function documentStatusMeta(status: string) {
  return Object.entries(DOCUMENT_STATUS_LABELS).find(([value]) => value === status)?.[1] ?? {
    label: status || 'Chưa rõ',
    tone: 'neutral' as const,
  };
}

/**
 * Màn hình đã có trong bản dựng này, tính theo đoạn đường dẫn sau `/w/{id}`.
 * `OnboardingState.steps[].href` do máy chủ trả về có thể trỏ tới màn hình của
 * lát cắt sau (vd `/campaigns`); khi đó hiện ghi chú thay vì một liên kết chết.
 */
const AVAILABLE_SCREEN_SEGMENTS: readonly string[] = [
  '',
  'brand',
  'documents',
  'campaigns',
  'analytics',
  'settings',
];

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
    return (
      <PermissionNotice
        message={apiError.message}
        requiredPermission={apiError.requiredPermission ?? undefined}
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
  const mocksEnabled = useMocks();

  const onboarding = useOnboarding(activeId);
  const brand = useBrandProfile(activeId);
  const documents = useDocuments(activeId);

  // Nhãn dữ liệu demo: `useMocks()` chỉ đọc được trong trình duyệt nên phải chờ
  // mount, nếu không bản render ở server và ở client sẽ lệch nhau.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

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

  if (!mocksEnabled) {
    return (
      <div className="space-y-5">
        <header>
          <h1 className="text-lg font-semibold text-slate-900">Bắt đầu với {workspace.name}</h1>
          <p className="mt-1 text-sm text-slate-600">
            Tiến độ onboarding chưa có trong HTTP OpenAPI hiện hành. Các màn hình này không dùng dữ liệu demo khi kết nối API thật.
          </p>
        </header>
        <UnavailableNotice
          title="Chưa có endpoint onboarding trong API"
          reason="OpenAPI hiện hành chưa khai báo endpoint đọc tiến độ onboarding, nên không thể hiển thị trạng thái tổng quan có nguồn từ máy chủ."
          remedy="Bạn vẫn có thể tiếp tục ở luồng đã có contract: tải tài liệu lên và theo dõi tác vụ xử lý."
          action={
            <Link
              className="text-sm font-medium text-slate-900 underline"
              href={`/w/${workspaceId}/documents`}
            >
              Mở tài liệu
            </Link>
          }
        />
      </div>
    );
  }

  const profileApplied = brand.data?.profile_mode === 'manual_text_v1' && Boolean(brand.data.profile_text?.trim());

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

      {mounted && mocksEnabled ? <DemoNotice /> : null}

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
                Mở danh sách đã tải lên
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
                const blockedReason = (step.blocked_reason ?? '').trim();
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
                      {/*
                        Máy chủ có thể gửi `blocked_reason` cho bước đang bị chặn, và cả
                        cho bước đang làm dở (lý do chưa xong). Có lý do thì phải hiện —
                        giấu đi là bắt người dùng đoán.
                      */}
                      {step.status === 'blocked' || blockedReason !== '' ? (
                        <p className="mt-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                          <strong className="font-semibold">
                            {step.status === 'blocked'
                              ? 'Vì sao chưa làm được: '
                              : 'Lưu ý từ hệ thống: '}
                          </strong>
                          {blockedReason !== ''
                            ? blockedReason
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
            Xem chi tiết hồ sơ
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
        ) : !brand.data ? (
          <EmptyState
            title="Chưa đọc được hồ sơ thương hiệu"
            description="Hệ thống không trả về dữ liệu hồ sơ cho doanh nghiệp này. Hãy thử tải lại trang."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Hồ sơ thương hiệu cho AI"
              value={profileApplied ? 'Đã áp dụng' : 'Cần Owner nhập'}
              hint={profileApplied ? 'Content Agent dùng nguyên văn hồ sơ do Owner viết.' : 'Hồ sơ cũ chỉ để tham khảo; Owner cần tự viết và lưu.'}
              tone={profileApplied ? 'success' : 'warning'}
            />
            <StatCard
              label="Phiên bản hồ sơ"
              value={formatNumber(brand.data.version)}
              hint={brand.data.applied_at ? `Áp dụng ${formatRelative(brand.data.applied_at)}.` : 'Chưa có phiên bản do Owner áp dụng.'}
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
            <StatCard
              label="Tài liệu cần xử lý lại"
              value={docs === null ? '—' : formatNumber(failedDocs.length)}
              hint={docs === null ? 'Chưa tải được danh sách tài liệu.' : 'Lỗi đọc tài liệu được báo riêng với lỗi AI.'}
              tone={failedDocs.length > 0 ? 'warning' : 'neutral'}
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
            Xem danh sách đã tải lên
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
                Mở trang tải lên
              </Link>
            }
          />
        ) : (
          <div className="space-y-4">
            <ul className="flex flex-wrap gap-3">
              {[...new Set(docs.map((doc) => doc.status))].map((status) => {
                const count = docs.filter((doc) => doc.status === status).length;
                if (count === 0) return null;
                const meta = documentStatusMeta(status);
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
                    Xem và đọc lại tệp lỗi
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
