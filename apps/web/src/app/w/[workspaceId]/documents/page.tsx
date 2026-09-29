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
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import { useMocks } from '@/lib/api/config';
import type { ApiDocument as DocumentUpload, ApiUploadLimits as UploadLimits } from '@/lib/api/types';
import { formatBytes, formatDateTime, formatNumber, formatRelative } from '@/lib/format';
import {
  extractionStatusMeta,
  knowledgeStatusMeta,
  retrievalModeMeta,
} from '@/lib/processing-status';
import {
  useDeleteDocument,
  useDocuments,
  newDocumentUploadKey,
  useReprocessDocument,
  useExtractedContent,
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
  PageHeader,
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
};

const MIME_KIND: Record<string, DocumentKind> = {
  'application/pdf': DOCUMENT_KINDS.PDF,
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': DOCUMENT_KINDS.DOCX,
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': DOCUMENT_KINDS.XLSX,
  'text/csv': DOCUMENT_KINDS.CSV,
  'text/plain': DOCUMENT_KINDS.TXT,
};

const SUPPORTED_UPLOAD_MIME_TYPES = new Set(Object.keys(MIME_KIND));
const SUPPORTED_DOCUMENT_KINDS = new Set<string>(Object.values(EXTENSION_KIND));

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
  return limits.accepted_kinds
    .filter((kind) => SUPPORTED_DOCUMENT_KINDS.has(kind))
    .map((kind) => Object.entries(DOCUMENT_KIND_LABELS).find(([value]) => value === kind)?.[1] ?? kind)
    .join(', ');
}

function acceptedMimeTypes(limits: UploadLimits): string[] {
  return limits.accepted_mime_types.filter((mimeType) => SUPPORTED_UPLOAD_MIME_TYPES.has(mimeType));
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

function ExtractedContentPreview({ workspaceId, documentId }: { workspaceId: string; documentId: string }) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [pageIndex, setPageIndex] = useState(0);
  const page = useExtractedContent(workspaceId, documentId, cursors[pageIndex] ?? null);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Nội dung đã đọc</h3>
          {page.data ? <p className="mt-0.5 text-xs text-slate-600">{formatNumber(page.data.total_text_blocks)} đoạn chữ · {formatNumber(page.data.total_tables)} bảng · {formatNumber(page.data.total_rows)} dòng</p> : null}
        </div>
        <div className="flex gap-2">
          {pageIndex > 0 ? <Button variant="secondary" size="sm" onClick={() => setPageIndex((index) => index - 1)}>Phần trước</Button> : null}
          {page.data?.has_more && page.data.next_cursor ? (
            <Button variant="secondary" size="sm" loading={page.isFetching} onClick={() => {
              setCursors((items) => [...items.slice(0, pageIndex + 1), page.data!.next_cursor!]);
              setPageIndex((index) => index + 1);
            }}>Tải phần tiếp theo</Button>
          ) : null}
        </div>
      </div>
      {page.isPending ? <p className="mt-3 text-sm text-slate-600">Đang tải nội dung đã trích xuất…</p> : null}
      {page.isError ? <p role="alert" className="mt-3 text-sm text-rose-800">Không tải được nội dung. Làm mới trang tài liệu rồi thử lại.</p> : null}
      {page.data?.warnings?.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-900">{page.data.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul> : null}
      <div className="mt-3 max-h-[32rem] space-y-3 overflow-auto">
        {page.data?.items.map((item, index) => (
          <article key={`${item.locator}-${index}`} className="rounded border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-medium text-slate-500">{item.kind === 'table_row' ? 'Dòng bảng' : 'Văn bản'} · {item.locator}</p>
            {item.text !== undefined && item.text !== null ? <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-sm text-slate-800">{item.text}</pre> : null}
            {item.cells ? <dl className="mt-2 grid gap-1 sm:grid-cols-2">{item.cells.map((cell, cellIndex) => <div key={cellIndex} className="min-w-0 text-sm text-slate-800"><dt className="font-medium text-slate-600">{item.headers?.[cellIndex] ?? `Cột ${cellIndex + 1}`}</dt><dd className="break-words">{cell || '—'}</dd></div>)}</dl> : null}
          </article>
        ))}
      </div>
    </div>
  );
}

export default function TrangTaiLieu() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();
  const mocksEnabled = useMocks();

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const activeId = workspace ? workspaceId : '';

  const limitsQuery = useUploadLimits(activeId);
  const documentsQuery = useDocuments(activeId);
  const upload = useUploadDocuments(activeId);
  const reprocess = useReprocessDocument(activeId);
  const remove = useDeleteDocument(activeId);

  const [isDragging, setIsDragging] = useState(false);
  const [rejected, setRejected] = useState<RejectedFile[]>([]);
  const [lastBatch, setLastBatch] = useState<{ files: File[]; idempotencyKey: string } | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [lastReprocessId, setLastReprocessId] = useState<string | null>(null);
  const [expandedDocumentId, setExpandedDocumentId] = useState<string | null>(null);

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

    const request = { files: result.accepted, idempotencyKey: newDocumentUploadKey() };
    setLastBatch(request);
    upload.mutate(request, {
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
      <PageHeader
        eyebrow="Nguồn tham khảo"
        title="Tài liệu"
        description="Lưu bảng giá, thông tin sản phẩm và dữ liệu tham khảo. Bạn chọn tài liệu cần dùng khi yêu cầu AI viết bài."
        actions={<Link href={`/w/${workspaceId}/campaigns`} className="inline-flex items-center rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-teal-800 hover:bg-teal-50">Tạo bài viết</Link>}
      />

      {/* ---------------------------------------------------------------- */}
      {/* Hạn mức + vùng tải lên                                            */}
      {/* ---------------------------------------------------------------- */}
      <Card
        title="Tải tài liệu lên"
        description="Đọc chữ và bảng, lưu làm kiến thức. Hồ sơ thương hiệu bạn tự viết được giữ nguyên."
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
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-600">
              <span className="font-semibold text-slate-800">PDF, Word (DOCX), Excel (XLSX), CSV, Văn bản (TXT)</span>
              <span>Tối đa {formatBytes(limits.max_file_size_bytes)}/tệp</span>
              <span>{formatNumber(limits.max_files_per_request)} tệp mỗi lần</span>
            </div>

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
                  ? 'border-teal-500 bg-teal-50'
                  : 'border-teal-200 bg-teal-50/40'
              } ${canPickFiles ? '' : 'opacity-70'}`}
            >
              <p className="text-base font-semibold text-slate-900">Thêm nguồn cho bài viết tiếp theo</p>
              <p id="upload-help" className="mt-1 text-sm text-slate-600">
                Kéo thả tệp vào đây hoặc chọn từ máy. Tệp chưa hợp lệ sẽ có lý do cụ thể.
              </p>
              <div className="mt-3">
                <input
                  id="document-files"
                  name="files"
                  type="file"
                  multiple
                  accept={acceptedMimeTypes(limits).join(',')}
                  className="peer sr-only"
                  onChange={handleInputChange}
                  disabled={!canPickFiles || upload.isPending}
                  aria-describedby="upload-help"
                />
                <label
                  htmlFor="document-files"
                  className={`inline-flex items-center rounded-lg px-4 py-2 text-sm font-medium peer-focus-visible:ring-2 peer-focus-visible:ring-slate-900 peer-focus-visible:ring-offset-2 ${
                    canPickFiles
                      ? 'cursor-pointer bg-teal-800 text-white hover:bg-teal-900'
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

            <div className="flex flex-wrap items-start justify-between gap-3 text-xs text-slate-600">
              <p>Không hỗ trợ ảnh và PDF scan không có lớp chữ. OCR đang tắt.</p>
              <details className="max-w-xl">
                <summary className="cursor-pointer font-medium text-teal-800">Xem giới hạn xử lý</summary>
                <dl className="mt-2 grid gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 sm:grid-cols-2">
                  <div><dt className="font-medium">Số dòng bảng</dt><dd>{formatNumber(limits.max_table_rows ?? 100_000)} dòng/tệp</dd></div>
                  <div><dt className="font-medium">Số cột mỗi bảng</dt><dd>{formatNumber(limits.max_table_columns ?? 256)} cột</dd></div>
                  <div><dt className="font-medium">Tổng số ô</dt><dd>{formatNumber(limits.max_table_cells ?? 1_000_000)} ô/tệp</dd></div>
                  <div><dt className="font-medium">Dung lượng tối đa mỗi tệp</dt><dd>{formatBytes(limits.max_file_size_bytes)}</dd></div>
                </dl>
              </details>
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
                  lastBatch && canPickFiles ? () => upload.mutate(lastBatch) : () => undefined
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
        description={documents?.length ? `${formatNumber(documents.length)} tài liệu trong workspace · mở nội dung để kiểm tra trước khi dùng.` : 'Nguồn đã lưu sẽ xuất hiện tại đây, sẵn sàng để bạn chọn khi tạo bài.'}
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
                    ? () => reprocess.mutate(reprocess.variables ?? { documentId: lastReprocessId, mode: 'document' })
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
                    const statusMeta = documentStatusMeta(doc.status);
                    const isBusy =
                      doc.status === DOCUMENT_STATUSES.PROCESSING ||
                      doc.status === DOCUMENT_STATUSES.UPLOADING ||
                      doc.status === DOCUMENT_STATUSES.PENDING;
                    const extracted = extractedText(doc);
                    const errorDetail = doc.error ? documentError(doc.error) : null;
                    const isPendingDelete = pendingDeleteId === doc.id;
                    const extractionMeta = extractionStatusMeta(doc.extraction_status);
                    const knowledgeMeta = knowledgeStatusMeta(doc.knowledge_status);
                    const retrievalMeta = retrievalModeMeta(doc.retrieval_mode);

                    return (
                      <Fragment key={doc.id}>
                        <tr className="border-b border-slate-100 align-top">
                          <td className="max-w-xs px-3 py-3 font-semibold text-slate-900"><span className="break-words">{doc.filename}</span>{extracted ? <p className="mt-1 text-xs font-normal text-slate-500">{extracted}</p> : null}</td>
                          <td className="px-3 py-3 text-slate-700">
                            {Object.entries(DOCUMENT_KIND_LABELS).find(([kind]) => kind === doc.kind)?.[1] ?? doc.kind}
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
                                  loading={reprocess.isPending && reprocess.variables?.documentId === doc.id}
                                  disabled={!canUpload}
                                  disabledReason={uploadDeniedReason}
                                  onClick={() => {
                                    setLastReprocessId(doc.id);
                                    reprocess.mutate({ documentId: doc.id, mode: 'document' }, {
                                      onSuccess: (response) =>
                                        router.push(`/w/${workspaceId}/jobs/${response.job_id}`),
                                    });
                                  }}
                                >
                                  Đọc lại tài liệu
                                </Button>
                              ) : null}
                              {doc.extraction_status === 'extracted' || doc.extraction_status === 'partial' ? (
                                <Button variant="ghost" size="sm" aria-expanded={expandedDocumentId === doc.id} onClick={() => setExpandedDocumentId((current) => current === doc.id ? null : doc.id)}>{expandedDocumentId === doc.id ? 'Ẩn nội dung' : 'Xem nội dung đã đọc'}</Button>
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
                              ) : mocksEnabled ? (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  disabled={!canUpload}
                                  disabledReason={uploadDeniedReason}
                                  onClick={() => setPendingDeleteId(doc.id)}
                                >
                                  Xoá tài liệu
                                </Button>
                              ) : null}
                            </div>
                          </td>
                        </tr>

                        <tr className="border-b border-slate-100 bg-slate-50">
                          <td colSpan={6} className="px-3 py-3">
                            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
                              {[
                                { label: '1. Đọc tài liệu', meta: extractionMeta },
                                { label: '2. Lưu kiến thức', meta: knowledgeMeta },
                              ].map(({ label, meta }) => (
                                <div key={label} className="flex flex-wrap items-center gap-2" title={meta.description}>
                                  <span className="text-xs font-medium text-slate-600">{label}</span>
                                  <StatusBadge label={meta.label} tone={meta.tone} />
                                </div>
                              ))}
                              <details className="min-w-0 text-xs text-slate-500">
                                <summary className="cursor-pointer font-medium text-teal-800">Chi tiết xử lý</summary>
                                <div className="mt-2 max-w-xl space-y-2 rounded-lg border border-slate-200 bg-white p-3">
                                  <p><strong>Đọc tài liệu:</strong> {extractionMeta.description}</p>
                                  <p><strong>Lưu kiến thức:</strong> {knowledgeMeta.description}</p>
                                  <p><strong>{retrievalMeta.label}:</strong> {retrievalMeta.description}</p>
                                  {doc.processed_at ? <p>Xử lý xong lúc {formatDateTime(doc.processed_at)}</p> : null}
                                </div>
                              </details>
                            </div>
                          </td>
                        </tr>

                        {errorDetail || isBusy || doc.extraction_status === 'partial' ? (
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

                              {doc.extraction_status === 'partial' ? <p className="mt-2 text-sm text-amber-900">Đã lưu nội dung một phần. Kiểm tra cảnh báo trích xuất trước khi dùng làm nguồn.</p> : null}
                            </td>
                          </tr>
                        ) : null}
                        {expandedDocumentId === doc.id ? (
                          <tr className="border-b border-slate-100 bg-slate-50"><td colSpan={6} className="px-3 py-3"><ExtractedContentPreview key={doc.id} workspaceId={workspaceId} documentId={doc.id} /></td></tr>
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
