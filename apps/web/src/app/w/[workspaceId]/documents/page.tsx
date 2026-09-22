'use client';

/**
 * Tài liệu: hạn mức, tải lên, tình trạng xử lý.
 *
 * Quy tắc của màn hình:
 * - Đọc hạn mức TRƯỚC khi người dùng chọn tệp, để họ biết ngay tệp nào hợp lệ.
 * - Tệp bị từ chối phải nêu lý do cụ thể — không âm thầm bỏ qua.
 * - Kiểm tra ở trình duyệt chỉ là tiện ích; máy chủ vẫn kiểm tra lại.
 */

import { Fragment, useState, type ChangeEvent, type DragEvent } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import {
  DOCUMENT_ERROR_LABELS,
  DOCUMENT_KIND_LABELS,
  DOCUMENT_KINDS,
  DOCUMENT_STATUS_LABELS,
  DOCUMENT_STATUSES,
  type DocumentKind,
  type DocumentUpload,
  type UploadLimits,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import { formatBytes, formatDateTime, formatNumber, formatRelative } from '@/lib/format';
import {
  useDeleteDocument,
  useDocuments,
  useReprocessDocument,
  useUploadDocuments,
  useUploadLimits,
} from '@/lib/hooks';
import { ACTION_REQUIREMENTS, hasPermission, permissionDeniedReason } from '@/lib/permissions';
import {
  Button,
  Card,
  DisabledReason,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  PermissionNotice,
  ProgressBar,
  StatusBadge,
} from '@/components/ui';

/**
 * Nhận dạng loại tài liệu ở trình duyệt.
 *
 * KHOẢNG TRỐNG: hợp đồng chỉ trả `accepted_kinds` (enum) và `accepted_mime_types`,
 * không có bảng ánh xạ đuôi tệp → loại. Bảng dưới đây phải cập nhật khi backend
 * thêm định dạng mới. Đây chỉ là kiểm tra sớm cho người dùng; máy chủ vẫn là nơi
 * quyết định cuối cùng.
 */
const EXTENSION_KIND: Record<string, DocumentKind> = {
  pdf: DOCUMENT_KINDS.PDF,
  docx: DOCUMENT_KINDS.DOCX,
  xlsx: DOCUMENT_KINDS.XLSX,
  csv: DOCUMENT_KINDS.CSV,
  txt: DOCUMENT_KINDS.TXT,
  png: DOCUMENT_KINDS.IMAGE,
  jpg: DOCUMENT_KINDS.IMAGE,
  jpeg: DOCUMENT_KINDS.IMAGE,
  webp: DOCUMENT_KINDS.IMAGE,
  gif: DOCUMENT_KINDS.IMAGE,
  heic: DOCUMENT_KINDS.IMAGE,
};

const MIME_KIND: Record<string, DocumentKind> = {
  'application/pdf': DOCUMENT_KINDS.PDF,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': DOCUMENT_KINDS.DOCX,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': DOCUMENT_KINDS.XLSX,
  'text/csv': DOCUMENT_KINDS.CSV,
  'text/plain': DOCUMENT_KINDS.TXT,
  'image/png': DOCUMENT_KINDS.IMAGE,
  'image/jpeg': DOCUMENT_KINDS.IMAGE,
  'image/webp': DOCUMENT_KINDS.IMAGE,
  'image/gif': DOCUMENT_KINDS.IMAGE,
  'image/heic': DOCUMENT_KINDS.IMAGE,
};

interface RejectedFile {
  name: string;
  reason: string;
}

function detectKind(file: File): DocumentKind | null {
  const name = file.name;
  const extension = name.includes('.') ? (name.split('.').pop() ?? '').toLowerCase() : '';
  const byExtension = EXTENSION_KIND[extension];
  if (byExtension) return byExtension;
  const byMime = MIME_KIND[file.type];
  return byMime ?? null;
}

function acceptedKindText(limits: UploadLimits): string {
  return limits.accepted_kinds.map((kind) => DOCUMENT_KIND_LABELS[kind]).join(', ');
}

/** Kiểm tra sớm ở trình duyệt. Trả về cả tệp nhận và tệp bị từ chối kèm lý do. */
function validateFiles(
  files: File[],
  limits: UploadLimits,
): { accepted: File[]; rejected: RejectedFile[] } {
  const accepted: File[] = [];
  const rejected: RejectedFile[] = [];
  const kindsText = acceptedKindText(limits);
  const maxFiles =
    typeof limits.max_files_per_request === 'number' && limits.max_files_per_request > 0
      ? limits.max_files_per_request
      : null;

  for (const file of files) {
    const kind = detectKind(file);

    if (kind === null || !limits.accepted_kinds.includes(kind)) {
      rejected.push({
        name: file.name,
        reason: `Định dạng tệp chưa được hỗ trợ. Hệ thống chỉ nhận: ${kindsText}.`,
      });
      continue;
    }

    if (
      limits.accepted_mime_types.length > 0 &&
      file.type !== '' &&
      !limits.accepted_mime_types.includes(file.type)
    ) {
      rejected.push({
        name: file.name,
        reason: `Kiểu tệp "${file.type}" không nằm trong danh sách hệ thống nhận. Hãy đổi sang: ${kindsText}.`,
      });
      continue;
    }

    if (file.size > limits.max_file_size_bytes) {
      rejected.push({
        name: file.name,
        reason: `Tệp nặng ${formatBytes(file.size)}, vượt mức tối đa ${formatBytes(
          limits.max_file_size_bytes,
        )} cho mỗi tệp. Hãy nén tệp hoặc chia nhỏ rồi tải lên.`,
      });
      continue;
    }

    accepted.push(file);
  }

  if (maxFiles !== null && accepted.length > maxFiles) {
    const overflow = accepted.splice(maxFiles);
    for (const file of overflow) {
      rejected.push({
        name: file.name,
        reason: `Mỗi lần chỉ tải lên tối đa ${formatNumber(
          maxFiles,
        )} tệp. Hãy gửi tệp này ở lần tải kế tiếp.`,
      });
    }
  }

  return { accepted, rejected };
}

function documentError(error: NonNullable<DocumentUpload['error']>): { message: string; hint: string } {
  const meta = DOCUMENT_ERROR_LABELS[error.code];
  const message = (error.message ?? '').trim();
  const hint = (error.hint ?? '').trim();
  return {
    message: message !== '' ? message : meta.label,
    hint: hint !== '' ? hint : meta.hint,
  };
}

function extractedText(doc: DocumentUpload): string | null {
  const extracted = doc.extracted;
  if (!extracted) return null;
  const parts: string[] = [];
  if (typeof extracted.pages === 'number') parts.push(`${formatNumber(extracted.pages)} trang`);
  if (typeof extracted.rows === 'number') parts.push(`${formatNumber(extracted.rows)} dòng`);
  if (typeof extracted.images === 'number') parts.push(`${formatNumber(extracted.images)} ảnh`);
  if (typeof extracted.characters === 'number') {
    parts.push(`${formatNumber(extracted.characters)} ký tự`);
  }
  return parts.length > 0 ? parts.join(' · ') : null;
}

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

export default function TrangTaiLieu() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const activeId = workspace ? workspaceId : '';

  const limitsQuery = useUploadLimits(activeId);
  const documentsQuery = useDocuments(activeId);
  const upload = useUploadDocuments(activeId);
  const reprocess = useReprocessDocument(activeId);
  const remove = useDeleteDocument(activeId);

  const [isDragging, setIsDragging] = useState(false);
  const [rejected, setRejected] = useState<RejectedFile[]>([]);
  const [lastBatch, setLastBatch] = useState<File[]>([]);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [lastReprocessId, setLastReprocessId] = useState<string | null>(null);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold text-slate-900">Không mở được tài liệu</h1>
        <PermissionNotice message="Bạn không thuộc doanh nghiệp này, nên không xem được tài liệu của doanh nghiệp." />
        <Button variant="secondary" onClick={() => router.push('/')}>
          Về trang chủ
        </Button>
      </div>
    );
  }

  const limits = limitsQuery.data ?? null;
  const canUpload = hasPermission(workspace, ACTION_REQUIREMENTS.uploadDocument);
  const uploadDeniedReason = permissionDeniedReason(workspace, ACTION_REQUIREMENTS.uploadDocument);
  const uploadDisabledReason = !canUpload
    ? uploadDeniedReason
    : limits === null
      ? 'Chưa đọc được hạn mức tải lên nên chưa kiểm tra được tệp trước khi gửi. Hãy thử lại phần hạn mức ở trên.'
      : undefined;
  const canPickFiles = uploadDisabledReason === undefined;

  const documents = documentsQuery.data ?? null;

  function handleFiles(fileList: FileList | File[] | null) {
    if (!fileList) return;
    const files = Array.from(fileList);
    if (files.length === 0) return;

    if (!canPickFiles || limits === null) {
      setRejected(
        files.map((file) => ({
          name: file.name,
          reason:
            uploadDisabledReason ??
            'Chưa kiểm tra được tệp vì thiếu hạn mức tải lên từ máy chủ.',
        })),
      );
      return;
    }

    const result = validateFiles(files, limits);
    setRejected(result.rejected);

    if (result.accepted.length === 0) return;

    setLastBatch(result.accepted);
    upload.mutate(result.accepted, {
      onSuccess: (response) => {
        // Có job_id thì đưa người dùng sang màn hình theo dõi tiến độ.
        router.push(`/w/${workspaceId}/jobs/${response.job_id}`);
      },
    });
  }

  function handleInputChange(event: ChangeEvent<HTMLInputElement>) {
    handleFiles(event.target.files);
    // Cho phép chọn lại đúng tệp vừa bị từ chối.
    event.target.value = '';
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    handleFiles(event.dataTransfer.files);
  }

  const uploadError = upload.error;
  const deleteError = remove.error;
  const reprocessError = reprocess.error;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">Tài liệu</h1>
        <p className="mt-1 text-sm text-slate-600">
          Tải hồ sơ doanh nghiệp lên để hệ thống đọc và gợi ý thông tin thương hiệu. Mỗi tệp được
          xử lý riêng, tệp lỗi có thể đọc lại.
        </p>
      </header>

      {/* ---------------------------------------------------------------- */}
      {/* Hạn mức + vùng tải lên                                            */}
      {/* ---------------------------------------------------------------- */}
      <Card
        title="Tải tài liệu lên"
        description="Hạn mức dưới đây do máy chủ công bố. Hệ thống kiểm tra tệp ngay tại trình duyệt và kiểm tra lại ở máy chủ."
      >
        {limitsQuery.isPending ? (
          <LoadingBlock label="Đang đọc hạn mức tải lên…" />
        ) : limitsQuery.isError ? (
          <SectionError
            title="Không đọc được hạn mức tải lên"
            error={limitsQuery.error}
            onRetry={() => void limitsQuery.refetch()}
          />
        ) : limits === null ? (
          <EmptyState
            title="Máy chủ chưa công bố hạn mức tải lên"
            description="Chưa có thông tin định dạng và dung lượng cho phép nên hệ thống chưa thể kiểm tra tệp trước khi gửi. Hãy thử tải lại trang."
          />
        ) : (
          <div className="space-y-4">
            <dl className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <dt className="text-xs font-medium text-slate-600">Định dạng nhận</dt>
                <dd className="mt-0.5 text-sm text-slate-900">{acceptedKindText(limits)}</dd>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <dt className="text-xs font-medium text-slate-600">Dung lượng tối đa mỗi tệp</dt>
                <dd className="mt-0.5 text-sm text-slate-900">
                  {formatBytes(limits.max_file_size_bytes)}
                </dd>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                <dt className="text-xs font-medium text-slate-600">Số tệp mỗi lần gửi</dt>
                <dd className="mt-0.5 text-sm text-slate-900">
                  tối đa {formatNumber(limits.max_files_per_request)} tệp
                </dd>
              </div>
            </dl>

            <div
              onDragOver={(event) => {
                event.preventDefault();
                if (canPickFiles) setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              aria-disabled={!canPickFiles}
              className={`rounded-xl border-2 border-dashed px-4 py-6 text-center ${
                isDragging && canPickFiles
                  ? 'border-sky-400 bg-sky-50'
                  : 'border-slate-300 bg-slate-50'
              } ${canPickFiles ? '' : 'opacity-70'}`}
            >
              <p id="upload-help" className="text-sm text-slate-700">
                Kéo thả tệp vào ô này, hoặc chọn tệp từ máy. Tệp sai định dạng hoặc quá nặng sẽ được
                liệt kê kèm lý do, không bị bỏ qua im lặng.
              </p>
              <div className="mt-3">
                <input
                  id="document-files"
                  name="files"
                  type="file"
                  multiple
                  accept={limits.accepted_mime_types.join(',')}
                  className="peer sr-only"
                  onChange={handleInputChange}
                  disabled={!canPickFiles || upload.isPending}
                  aria-describedby="upload-help"
                />
                <label
                  htmlFor="document-files"
                  className={`inline-flex items-center rounded-lg px-4 py-2 text-sm font-medium peer-focus-visible:ring-2 peer-focus-visible:ring-slate-900 peer-focus-visible:ring-offset-2 ${
                    canPickFiles
                      ? 'cursor-pointer bg-slate-900 text-white hover:bg-slate-800'
                      : 'cursor-not-allowed bg-slate-400 text-white'
                  }`}
                >
                  {upload.isPending ? 'Đang tải lên…' : 'Chọn tệp từ máy'}
                </label>
              </div>
              {uploadDisabledReason ? (
                <DisabledReason>
                  {uploadDisabledReason}
                  {!canUpload
                    ? ' Vì vậy vùng tải lên, nút “Đọc lại tài liệu” và nút “Xoá tài liệu” đều bị khoá.'
                    : ''}
                </DisabledReason>
              ) : null}
            </div>

            {rejected.length > 0 ? (
              <div role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <h3 className="text-sm font-semibold text-amber-900">
                  {formatNumber(rejected.length)} tệp không được gửi lên
                </h3>
                <ul className="mt-2 space-y-1">
                  {rejected.map((item) => (
                    <li key={item.name} className="text-sm text-amber-900">
                      <span className="font-medium">{item.name}</span> — {item.reason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {upload.error ? (
              <SectionError
                title="Không tải lên được tài liệu"
                error={uploadError}
                onRetry={
                  lastBatch.length > 0 && canPickFiles ? () => upload.mutate(lastBatch) : () => undefined
                }
              />
            ) : null}
          </div>
        )}
      </Card>

      {/* ---------------------------------------------------------------- */}
      {/* Danh sách tài liệu                                                */}
      {/* ---------------------------------------------------------------- */}
      <Card
        title="Tài liệu đã tải lên"
        description="Tình trạng đọc nội dung của từng tệp."
        actions={
          <Button variant="secondary" size="sm" onClick={() => void documentsQuery.refetch()}>
            Làm mới danh sách
          </Button>
        }
      >
        {documentsQuery.isPending ? (
          <LoadingBlock label="Đang tải danh sách tài liệu…" />
        ) : documentsQuery.isError ? (
          <SectionError
            title="Không tải được danh sách tài liệu"
            error={documentsQuery.error}
            onRetry={() => void documentsQuery.refetch()}
          />
        ) : documents === null || documents.length === 0 ? (
          <EmptyState
            title="Chưa có tài liệu nào"
            description="Doanh nghiệp chưa tải lên tài liệu nào. Hãy dùng ô tải lên ở trên để gửi hồ sơ năng lực, bảng giá hoặc mô tả sản phẩm."
          />
        ) : (
          <div className="space-y-3">
            {deleteError ? (
              <SectionError
                title="Không xoá được tài liệu"
                error={deleteError}
                onRetry={
                  pendingDeleteId
                    ? () => remove.mutate(pendingDeleteId)
                    : () => undefined
                }
              />
            ) : null}

            {reprocessError ? (
              <SectionError
                title="Không đọc lại được tài liệu"
                error={reprocessError}
                onRetry={
                  lastReprocessId && canUpload
                    ? () => reprocess.mutate(lastReprocessId)
                    : () => undefined
                }
              />
            ) : null}

            <div className="table-scroll">
              <table className="w-full min-w-[640px] border-collapse text-left text-sm">
                <caption className="sr-only">Danh sách tài liệu đã tải lên và tình trạng xử lý</caption>
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                    <th scope="col" className="px-3 py-2 font-medium">
                      Tên tệp
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Loại
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Dung lượng
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Trạng thái
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Tải lên
                    </th>
                    <th scope="col" className="px-3 py-2 font-medium">
                      Thao tác
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => {
                    const statusMeta = DOCUMENT_STATUS_LABELS[doc.status];
                    const isBusy =
                      doc.status === DOCUMENT_STATUSES.PROCESSING ||
                      doc.status === DOCUMENT_STATUSES.UPLOADING;
                    const extracted = extractedText(doc);
                    const errorDetail = doc.error ? documentError(doc.error) : null;
                    const isPendingDelete = pendingDeleteId === doc.id;

                    return (
                      <Fragment key={doc.id}>
                        <tr className="border-b border-slate-100 align-top">
                          <td className="px-3 py-3 text-slate-900">{doc.filename}</td>
                          <td className="px-3 py-3 text-slate-700">
                            {DOCUMENT_KIND_LABELS[doc.kind]}
                          </td>
                          <td className="px-3 py-3 tabular-nums text-slate-700">
                            {formatBytes(doc.size)}
                          </td>
                          <td className="px-3 py-3">
                            <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
                          </td>
                          <td className="px-3 py-3 text-slate-700" title={formatDateTime(doc.uploaded_at)}>
                            {formatRelative(doc.uploaded_at)}
                          </td>
                          <td className="px-3 py-3">
                            <div className="flex flex-wrap gap-2">
                              {doc.job_id ? (
                                <Link
                                  className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50"
                                  href={`/w/${workspaceId}/jobs/${doc.job_id}`}
                                >
                                  Xem tiến độ
                                </Link>
                              ) : null}

                              {doc.status === DOCUMENT_STATUSES.FAILED ? (
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  loading={reprocess.isPending && reprocess.variables === doc.id}
                                  disabled={!canUpload}
                                  disabledReason={uploadDeniedReason}
                                  onClick={() => {
                                    setLastReprocessId(doc.id);
                                    reprocess.mutate(doc.id, {
                                      onSuccess: (response) =>
                                        router.push(`/w/${workspaceId}/jobs/${response.job_id}`),
                                    });
                                  }}
                                >
                                  Đọc lại tài liệu
                                </Button>
                              ) : null}

                              {isPendingDelete ? (
                                <>
                                  <Button
                                    variant="danger"
                                    size="sm"
                                    loading={remove.isPending}
                                    onClick={() =>
                                      remove.mutate(doc.id, {
                                        onSuccess: () => setPendingDeleteId(null),
                                      })
                                    }
                                  >
                                    Xác nhận xoá
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setPendingDeleteId(null)}
                                  >
                                    Huỷ
                                  </Button>
                                </>
                              ) : (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={!canUpload}
                                  disabledReason={uploadDeniedReason}
                                  onClick={() => setPendingDeleteId(doc.id)}
                                >
                                  Xoá tài liệu
                                </Button>
                              )}
                            </div>
                          </td>
                        </tr>

                        {errorDetail || extracted || isBusy ? (
                          <tr className="border-b border-slate-100 bg-slate-50">
                            <td colSpan={6} className="px-3 py-3">
                              {errorDetail ? (
                                <div className="text-sm">
                                  <p className="font-medium text-rose-900">{errorDetail.message}</p>
                                  <p className="mt-0.5 text-rose-800">
                                    Việc cần làm: {errorDetail.hint}
                                  </p>
                                  <p className="mt-0.5 text-xs text-rose-700/80">
                                    Mã lỗi: <code className="font-mono">{doc.error?.code}</code>
                                  </p>
                                </div>
                              ) : null}

                              {isBusy ? (
                                <div className="max-w-sm">
                                  <ProgressBar
                                    value={
                                      typeof doc.progress === 'number' && Number.isFinite(doc.progress)
                                        ? doc.progress
                                        : null
                                    }
                                    label="Tiến độ xử lý tệp"
                                  />
                                </div>
                              ) : null}

                              {doc.status === DOCUMENT_STATUSES.READY ? (
                                <p className="text-sm text-slate-700">
                                  {extracted
                                    ? `Đã đọc được: ${extracted}.`
                                    : 'Máy chủ báo tài liệu đã xử lý xong nhưng chưa gửi số liệu trích xuất (trang/dòng/ảnh) nên chưa hiển thị được con số nào.'}
                                  {doc.processed_at ? (
                                    <span className="text-slate-500">
                                      {' '}
                                      · Xử lý xong lúc {formatDateTime(doc.processed_at)}
                                    </span>
                                  ) : null}
                                </p>
                              ) : null}
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {!canUpload ? (
              <p className="text-xs text-slate-500">
                Lý do khoá nút: {uploadDeniedReason} (đã nêu ở phần “Tải tài liệu lên” phía trên).
              </p>
            ) : null}

            <p className="text-xs text-slate-500">
              Cần xem lại tiến độ một tác vụ?{' '}
              <Link className="underline" href={`/w/${workspaceId}`}>
                Về màn hình chính
              </Link>
              .
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}
