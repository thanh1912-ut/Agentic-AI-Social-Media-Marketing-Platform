'use client';

/**
 * Tiến độ một tác vụ nền.
 *
 * Màn hình này là nơi DUY NHẤT được nói về phần trăm của tác vụ, và chỉ khi máy
 * chủ thật sự gửi con số. Không có số thì thanh tiến độ chạy dạng không xác định.
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import {
  JOB_STATUS_LABELS,
  JOB_STATUSES,
  type Job,
  type JobStep,
  type JobStepStatus,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import { formatDateTime, formatNumber, formatRelative } from '@/lib/format';
import { useCancelJob, useJob, useRetryJob } from '@/lib/hooks';
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
 * KHOẢNG TRỐNG HỢP ĐỒNG: `JobStep.status` (pending/running/succeeded/failed/skipped)
 * chưa có bảng nhãn trong `labels.ts` — khác với `JOB_STATUS_LABELS` dành cho
 * trạng thái job. Khai báo tạm một chỗ ở đây thay vì rải chuỗi khắp nơi.
 */
const JOB_STEP_STATUS_LABELS: Record<JobStepStatus, { label: string; tone: Tone }> = {
  pending: { label: 'Chưa bắt đầu', tone: 'neutral' },
  running: { label: 'Đang chạy', tone: 'info' },
  succeeded: { label: 'Xong', tone: 'success' },
  failed: { label: 'Lỗi', tone: 'danger' },
  skipped: { label: 'Bỏ qua', tone: 'neutral' },
};

/**
 * Nhãn cho các khoá thường gặp trong `Job.result`. Khoá lạ vẫn được hiển thị
 * nguyên văn (định danh kỹ thuật) kèm ghi chú, không tự đoán ý nghĩa.
 */
const JOB_RESULT_KEY_LABELS: Record<string, string> = {
  document_id: 'Mã tài liệu',
  document_ids: 'Danh sách mã tài liệu',
  campaign_id: 'Mã chiến dịch',
  post_id: 'Mã bài viết',
  post_ids: 'Danh sách mã bài viết',
  export_id: 'Mã tệp xuất',
  publication_id: 'Mã lần đăng',
  count: 'Số lượng',
  total: 'Tổng số',
  imported: 'Số dòng đã nhập',
  skipped: 'Số dòng bỏ qua',
  url: 'Đường dẫn',
};

/**
 * Phần trăm của tác vụ — CHỈ lấy từ số máy chủ gửi.
 *
 * Hợp đồng khai báo `progress: number`, nhưng thực tế backend có thể bỏ trống,
 * hoặc chỉ gửi `progress_current`/`progress_total`. Thiếu `total` (hoặc total = 0)
 * nghĩa là KHÔNG có phần trăm thật → trả `null` để thanh tiến độ hiển thị dạng
 * không xác định. TUYỆT ĐỐI không lấy số bước đã xong chia cho tổng số bước để tự
 * chế ra một phần trăm.
 */
function reportedProgress(job: Job): number | null {
  const raw = job as Job & { progress_current?: unknown; progress_total?: unknown };
  const current = raw.progress_current;
  const total = raw.progress_total;

  if (typeof current === 'number' && typeof total === 'number' && total > 0) {
    return (current / total) * 100;
  }

  if (typeof job.progress === 'number' && Number.isFinite(job.progress)) {
    return job.progress;
  }

  return null;
}

function resultValueText(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value.trim() === '' ? '—' : value;
  if (typeof value === 'number') return formatNumber(value);
  if (typeof value === 'boolean') return value ? 'Có' : 'Không';
  if (Array.isArray(value)) {
    if (value.length === 0) return '—';
    return value.map((item) => resultValueText(item)).join(', ');
  }
  return JSON.stringify(value);
}

/** Đường dẫn đi tiếp sau khi tác vụ xong — chỉ trỏ tới màn hình đã có trong bản này. */
function resultHref(workspaceId: string, result: Record<string, unknown>): {
  href: string;
  label: string;
} {
  const documentId = result.document_id;
  const documentIds = result.document_ids;
  if (
    (typeof documentId === 'string' && documentId !== '') ||
    (Array.isArray(documentIds) && documentIds.length > 0)
  ) {
    return { href: `/w/${workspaceId}/documents`, label: 'Mở danh sách tài liệu' };
  }
  return { href: `/w/${workspaceId}`, label: 'Về trang Tổng quan' };
}

function JobSteps({ steps }: { steps: JobStep[] }) {
  return (
    <ol className="space-y-3">
      {steps.map((step) => {
        const meta = JOB_STEP_STATUS_LABELS[step.status];
        return (
          <li key={step.key} className="border-b border-slate-100 pb-3 last:border-b-0 last:pb-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium text-slate-900">{step.label}</p>
              <StatusBadge label={meta.label} tone={meta.tone} />
            </div>
            {step.message ? <p className="mt-1 text-sm text-slate-600">{step.message}</p> : null}
            {typeof step.progress === 'number' && Number.isFinite(step.progress) ? (
              <div className="mt-2 max-w-sm">
                <ProgressBar value={step.progress} label={`Tiến độ bước “${step.label}”`} />
              </div>
            ) : null}
            {step.error ? (
              <p className="mt-1 text-sm text-rose-800">
                {step.error.message}
                {step.error.code ? (
                  <span className="text-xs text-rose-700/80">
                    {' '}
                    (mã: <code className="font-mono">{step.error.code}</code>)
                  </span>
                ) : null}
              </p>
            ) : null}
            <p className="mt-1 text-xs text-slate-500">
              {step.started_at ? `Bắt đầu ${formatDateTime(step.started_at)}` : 'Chưa bắt đầu'}
              {step.finished_at ? ` · Kết thúc ${formatDateTime(step.finished_at)}` : ''}
            </p>
          </li>
        );
      })}
    </ol>
  );
}

export default function TrangTienDoTacVu() {
  const params = useParams<{ workspaceId?: string; jobId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const jobId = params?.jobId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;

  const jobQuery = useJob(jobId);
  const cancel = useCancelJob(jobId);
  const retry = useRetryJob(jobId);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold text-slate-900">Không mở được tác vụ</h1>
        <PermissionNotice message="Bạn không thuộc doanh nghiệp này, nên không xem được tác vụ của doanh nghiệp." />
        <Button variant="secondary" onClick={() => router.push('/')}>
          Về trang chủ
        </Button>
      </div>
    );
  }

  if (jobId === '') {
    return (
      <EmptyState
        tone="warning"
        title="Thiếu mã tác vụ"
        description="Đường dẫn không kèm mã tác vụ nên không có gì để theo dõi. Hãy mở lại tác vụ từ danh sách tài liệu."
        action={
          <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}/documents`}>
            Mở danh sách tài liệu
          </Link>
        }
      />
    );
  }

  if (jobQuery.isPending) {
    return <LoadingBlock label="Đang tải tiến độ tác vụ…" />;
  }

  const apiError = jobQuery.error instanceof ApiError ? jobQuery.error : null;

  if (jobQuery.isError) {
    if (apiError?.isNotFound) {
      return (
        <div className="space-y-4">
          <EmptyState
            tone="neutral"
            title="Không tìm thấy tác vụ này"
            description="Tác vụ không tồn tại, đã bị xoá khỏi lịch sử hoặc không thuộc doanh nghiệp bạn đang mở. Lịch sử tác vụ chỉ được lưu một thời gian ngắn sau khi kết thúc."
            action={
              <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}/documents`}>
                Mở danh sách tài liệu
              </Link>
            }
          />
          <p className="text-xs text-slate-500">
            Mã tác vụ đã mở: <code className="font-mono">{jobId}</code>
          </p>
        </div>
      );
    }

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
        title="Không tải được tiến độ tác vụ"
        message={apiError?.message ?? 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'}
        code={apiError?.code}
        requestId={apiError?.requestId}
        retryable={apiError?.retryable ?? true}
        onRetry={() => void jobQuery.refetch()}
      />
    );
  }

  const job = jobQuery.data;
  const statusMeta = JOB_STATUS_LABELS[job.status];
  const progress = reportedProgress(job);
  const isActive = job.status === JOB_STATUSES.QUEUED || job.status === JOB_STATUSES.RUNNING;
  const result = job.result ?? null;
  const resultEntries = result ? Object.entries(result).slice(0, 20) : [];
  const hasResult = resultEntries.length > 0;
  const onward = result ? resultHref(workspaceId, result) : null;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-slate-900">{job.title}</h1>
          <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
        </div>
        <p className="text-sm text-slate-600">
          Tạo lúc {formatDateTime(job.created_at)} ({formatRelative(job.created_at)})
          {job.started_at ? ` · Bắt đầu ${formatDateTime(job.started_at)}` : ''}
          {job.finished_at ? ` · Kết thúc ${formatDateTime(job.finished_at)}` : ''}
        </p>
        {isActive ? (
          <p role="status" className="text-sm text-sky-800">
            Đang theo dõi tiến độ — màn hình tự cập nhật cho tới khi tác vụ kết thúc.
          </p>
        ) : null}
        {job.expires_at ? (
          <p className="text-xs text-slate-500">
            Tác vụ sẽ bị xoá khỏi lịch sử sau {formatDateTime(job.expires_at)}.
          </p>
        ) : null}
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          label="Trạng thái"
          value={statusMeta.label}
          hint={
            isActive
              ? 'Tác vụ đang chạy nền, bạn có thể rời trang và quay lại sau.'
              : 'Tác vụ đã kết thúc.'
          }
        />
        <StatCard
          label="Số bước"
          value={formatNumber(job.steps.length)}
          hint="Số bước máy chủ báo về cho tác vụ này."
        />
        <StatCard
          label="Có thể huỷ"
          value={job.cancellable ? 'Có' : 'Không'}
          hint={
            job.cancellable
              ? 'Bạn có thể huỷ tác vụ này giữa chừng.'
              : 'Máy chủ báo tác vụ này không huỷ được ở trạng thái hiện tại.'
          }
        />
      </div>

      <Card title="Tiến độ" description="Thanh tiến độ chỉ hiện số khi máy chủ gửi kèm số liệu.">
        {progress === null ? (
          <div className="space-y-2">
            <ProgressBar value={null} label="Tiến độ tác vụ" tone={isActive ? 'info' : 'neutral'} />
            <p className="text-sm text-slate-600">
              Máy chủ chưa gửi tổng khối lượng công việc nên chưa thể hiện phần trăm. Hãy xem tiến
              độ theo từng bước ở dưới.
            </p>
          </div>
        ) : (
          <ProgressBar value={progress} label="Tiến độ tác vụ" tone="info" />
        )}
      </Card>

      <Card
        title="Các bước xử lý"
        description="Nhãn từng bước do máy chủ gửi, giữ nguyên tiếng Việt."
      >
        {job.steps.length === 0 ? (
          <EmptyState
            title="Tác vụ chưa có bước nào"
            description={
              isActive
                ? 'Tác vụ đang chờ hoặc vừa bắt đầu nên máy chủ chưa gửi bước xử lý nào. Màn hình sẽ tự cập nhật.'
                : 'Máy chủ không gửi bước xử lý nào cho tác vụ này, nên chỉ có thể xem trạng thái tổng.'
            }
          />
        ) : (
          <JobSteps steps={job.steps} />
        )}
      </Card>

      {job.status === JOB_STATUSES.SUCCEEDED ? (
        <Card title="Kết quả" description="Dữ liệu máy chủ trả về sau khi tác vụ hoàn tất.">
          {hasResult && result ? (
            <div className="space-y-4">
              <dl className="space-y-2">
                {resultEntries.map(([key, value]) => (
                  <div key={key} className="grid gap-1 sm:grid-cols-[240px_1fr] sm:gap-4">
                    <dt className="text-sm font-medium text-slate-600">
                      {JOB_RESULT_KEY_LABELS[key] ?? (
                        <code className="font-mono text-xs">{key}</code>
                      )}
                    </dt>
                    <dd className="text-sm text-slate-900">{resultValueText(value)}</dd>
                  </div>
                ))}
              </dl>
              {Object.keys(result).length > resultEntries.length ? (
                <p className="text-xs text-slate-500">
                  Chỉ hiển thị {formatNumber(resultEntries.length)} mục đầu tiên.
                </p>
              ) : null}
              {onward ? (
                <Link className="text-sm font-medium text-slate-900 underline" href={onward.href}>
                  {onward.label}
                </Link>
              ) : null}
            </div>
          ) : (
            <EmptyState
              title="Tác vụ xong nhưng không có kết quả kèm theo"
              description="Máy chủ báo tác vụ đã hoàn tất nhưng không gửi dữ liệu kết quả. Hãy kiểm tra lại danh sách tài liệu hoặc hồ sơ thương hiệu để xem thay đổi."
              action={
                <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}`}>
                  Về trang Tổng quan
                </Link>
              }
            />
          )}
        </Card>
      ) : null}

      {job.status === JOB_STATUSES.FAILED ? (
        <Card title="Tác vụ thất bại">
          <div className="space-y-3">
            <div>
              <p className="text-sm font-semibold text-rose-900">
                {job.error?.message ?? 'Máy chủ báo tác vụ thất bại nhưng không gửi kèm mô tả lỗi.'}
              </p>
              {job.error?.hint ? (
                <p className="mt-1 text-sm text-rose-800">Việc cần làm: {job.error.hint}</p>
              ) : null}
              {job.error?.code ? (
                <p className="mt-1 text-xs text-rose-700/80">
                  Mã lỗi: <code className="font-mono">{job.error.code}</code>
                </p>
              ) : null}
            </div>

            {job.error?.retryable ? (
              <div>
                <Button
                  loading={retry.isPending}
                  onClick={() =>
                    retry.mutate(undefined, {
                      onSuccess: (response) =>
                        router.push(`/w/${workspaceId}/jobs/${response.job_id}`),
                    })
                  }
                >
                  Thử lại
                </Button>
                <p className="mt-1 text-xs text-slate-500">
                  Hệ thống sẽ tạo một tác vụ mới và mở trang theo dõi tác vụ đó.
                </p>
              </div>
            ) : (
              <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
                Lỗi này không thử lại được: bấm lại sẽ cho kết quả y hệt. Hãy xử lý theo hướng dẫn ở
                trên rồi tải lại tài liệu.
              </p>
            )}

            {retry.error ? (
              <ErrorPanel
                title="Không thử lại được tác vụ"
                message={
                  retry.error instanceof ApiError
                    ? retry.error.message
                    : 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'
                }
                code={retry.error instanceof ApiError ? retry.error.code : null}
                requestId={retry.error instanceof ApiError ? retry.error.requestId : null}
                retryable={
                  retry.error instanceof ApiError ? retry.error.retryable : false
                }
                onRetry={() => retry.mutate()}
              />
            ) : null}
          </div>
        </Card>
      ) : null}

      {job.status === JOB_STATUSES.CANCELLED ? (
        <Card title="Tác vụ đã bị huỷ">
          <p className="text-sm text-slate-700">
            Tác vụ đã dừng theo yêu cầu. Kết quả dở dang không được dùng; hãy tạo lại tác vụ nếu vẫn
            cần xử lý.
          </p>
        </Card>
      ) : null}

      {isActive ? (
        <Card title="Dừng tác vụ">
          {job.cancellable ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-600">
                Huỷ tác vụ sẽ dừng phần việc còn lại. Phần đã xử lý xong có thể vẫn được giữ lại.
              </p>
              <div>
                <Button
                  variant="danger"
                  loading={cancel.isPending}
                  onClick={() => cancel.mutate()}
                >
                  Huỷ tác vụ
                </Button>
              </div>
              {cancel.error ? (
                <ErrorPanel
                  title="Không huỷ được tác vụ"
                  message={
                    cancel.error instanceof ApiError
                      ? cancel.error.message
                      : 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'
                  }
                  code={cancel.error instanceof ApiError ? cancel.error.code : null}
                  requestId={cancel.error instanceof ApiError ? cancel.error.requestId : null}
                  retryable={cancel.error instanceof ApiError ? cancel.error.retryable : false}
                  onRetry={() => cancel.mutate()}
                />
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-slate-700">
              Tác vụ này không huỷ được: máy chủ báo <code className="font-mono">cancellable = false</code>{' '}
              ở trạng thái hiện tại. Hãy chờ tác vụ chạy xong; nếu tác vụ lỗi, màn hình sẽ hiện nút
              “Thử lại” khi lỗi đó thử lại được.
            </p>
          )}
        </Card>
      ) : null}
    </div>
  );
}
