'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import { DOCUMENT_STATUS_LABELS, DOCUMENT_STATUSES } from '@agentic/contracts';
import { useSession } from '@/components/session-gate';
import { Icon } from '@/components/icon';
import { ApiError, useMocks } from '@/lib/api';
import { formatNumber, formatRelative } from '@/lib/format';
import { useBrandProfile, useDocuments } from '@/lib/hooks';
import { Button, Card, DemoNotice, EmptyState, ErrorPanel, LoadingBlock, PageHeader, PermissionNotice, StatusBadge } from '@/components/ui';

function documentStatusMeta(status: string) {
  return Object.entries(DOCUMENT_STATUS_LABELS).find(([value]) => value === status)?.[1] ?? {
    label: status || 'Chưa rõ',
    tone: 'neutral' as const,
  };
}

function SectionError({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  const apiError = error instanceof ApiError ? error : null;
  if (apiError?.isForbidden) {
    return <PermissionNotice message={apiError.message} requiredPermission={apiError.requiredPermission ?? undefined} />;
  }
  return <ErrorPanel title={title} message={apiError?.message ?? 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'} code={apiError?.code} requestId={apiError?.requestId} retryable={apiError?.retryable ?? true} onRetry={onRetry} />;
}

export default function WorkspaceOverviewPage() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const activeId = workspace ? workspaceId : '';
  const brand = useBrandProfile(activeId);
  const documents = useDocuments(activeId);
  const mocksEnabled = useMocks();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  if (!workspace) {
    return <div className="space-y-4">
      <h1 className="text-lg font-semibold text-slate-900">Không mở được doanh nghiệp này</h1>
      <PermissionNotice message="Bạn không thuộc doanh nghiệp này, nên không xem được số liệu tổng quan của doanh nghiệp." />
      <Button variant="secondary" onClick={() => router.push('/')}>Về trang chủ</Button>
    </div>;
  }

  const documentItems = documents.data ?? null;
  const failedDocuments = documentItems?.filter((doc) => doc.status === DOCUMENT_STATUSES.FAILED) ?? [];
  const readyCount = documentItems?.filter((doc) => doc.status === DOCUMENT_STATUSES.READY).length ?? 0;
  const recentDocuments = documentItems
    ? [...documentItems].sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at)).slice(0, 5)
    : [];
  const manualProfile = brand.data?.profile_mode === 'manual_text_v1' && Boolean(brand.data.profile_text?.trim());
  const brandUnknown = brand.isPending || brand.isError;
  const nextTitle = brandUnknown
    ? brand.isPending ? 'Đang kiểm tra hồ sơ thương hiệu' : 'Chưa tải được trạng thái hồ sơ'
    : !manualProfile ? 'Viết hồ sơ thương hiệu'
      : failedDocuments.length ? 'Kiểm tra tài liệu chưa xử lý'
        : 'Bắt đầu một nội dung mới';
  const nextDescription = brandUnknown
    ? brand.isPending ? 'Đang đọc trạng thái từ workspace.' : 'Hãy thử tải lại trước khi thay đổi hồ sơ.'
    : !manualProfile ? 'Giới thiệu thương hiệu bằng lời của bạn để Content Agent hiểu sản phẩm và cách bạn muốn viết.'
      : failedDocuments.length ? `${formatNumber(failedDocuments.length)} tài liệu cần được xem lại trước khi dùng làm nguồn cho nội dung.`
        : 'Nhập yêu cầu viết, chọn tài liệu nếu cần, rồi kiểm tra bản nháp trước khi duyệt.';
  const nextHref = brandUnknown ? null
    : !manualProfile ? `/w/${workspaceId}/brand`
      : failedDocuments.length ? `/w/${workspaceId}/documents`
        : `/w/${workspaceId}/campaigns`;
  const nextLabel = brandUnknown ? 'Thử tải lại'
    : !manualProfile ? 'Mở hồ sơ thương hiệu'
      : failedDocuments.length ? 'Mở tài liệu cần xem'
        : 'Mở chiến dịch';

  return <div className="space-y-8">
    <PageHeader title={`Tổng quan — ${workspace.name}`} description="Thương hiệu, tài liệu tham khảo và nội dung của bạn ở cùng một nơi." />
    {mounted && mocksEnabled ? <DemoNotice /> : null}

    <section className="overview-workspace" aria-labelledby="overview-next-title">
      <div className="overview-next-step">
        <p className="text-sm font-medium text-teal-800">Việc nên làm tiếp</p>
        <h2 id="overview-next-title">{nextTitle}</h2>
        <p>{nextDescription}</p>
        {nextHref
          ? <Link className="overview-primary-action" href={nextHref}>{nextLabel}</Link>
          : <Button onClick={() => { void brand.refetch(); void documents.refetch(); }}>{nextLabel}</Button>}
      </div>
      <div className="overview-work-list" aria-label="Các khu vực làm việc">
        <Link href={`/w/${workspaceId}/brand`} className="overview-work-row">
          <span><strong>Hồ sơ thương hiệu</strong><small>{brand.isPending ? 'Đang tải trạng thái' : brand.isError ? 'Không tải được trạng thái' : manualProfile ? 'Đã áp dụng' : 'Chưa có hồ sơ do bạn viết'}</small></span>
          {brand.isError ? <span className="text-sm font-medium text-rose-700">Thử lại</span> : <StatusBadge label={brand.isPending ? 'Đang tải' : manualProfile ? 'Sẵn sàng' : 'Cần nhập'} tone={brand.isPending ? 'neutral' : manualProfile ? 'success' : 'warning'} />}
        </Link>
        <Link href={`/w/${workspaceId}/documents`} className="overview-work-row">
          <span><strong>Tài liệu tham khảo</strong><small>{documents.isPending ? 'Đang tải danh sách' : documents.isError ? 'Không tải được danh sách' : documentItems?.length ? `${formatNumber(readyCount)} sẵn sàng · ${formatNumber(failedDocuments.length)} cần xem lại` : 'Chọn tài liệu theo từng yêu cầu viết'}</small></span>
          <span className={`text-sm font-medium ${documents.isError ? 'text-rose-700' : 'text-teal-800'}`}>{documentItems ? formatNumber(documentItems.length) : documents.isError ? 'Thử lại' : 'Mở'}</span>
        </Link>
        <Link href={`/w/${workspaceId}/campaigns`} className="overview-work-row">
          <span><strong>Chiến dịch</strong><small>Tạo brief, bản nháp và lịch nội dung</small></span>
          <span className="text-sm font-medium text-teal-800">Mở</span>
        </Link>
      </div>
    </section>

    <Card title="Tài liệu mới thêm" description="Trạng thái đọc và lưu kiến thức được lấy trực tiếp từ workspace." actions={<Link href={`/w/${workspaceId}/documents`} className="text-sm font-semibold text-teal-800">Xem tất cả</Link>}>
      {documents.isPending ? <LoadingBlock label="Đang tải tài liệu…" />
        : documents.isError ? <SectionError title="Không tải được tài liệu" error={documents.error} onRetry={() => void documents.refetch()} />
          : recentDocuments.length ? <ul className="divide-y divide-slate-100">{recentDocuments.map((doc) => {
            const meta = documentStatusMeta(doc.status);
            return <li key={doc.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"><span className="min-w-0 break-words text-sm font-medium text-slate-800">{doc.filename}</span><span className="flex items-center gap-3"><span className="text-xs text-slate-500">{formatRelative(doc.uploaded_at)}</span><StatusBadge label={meta.label} tone={meta.tone} /></span></li>;
          })}</ul>
            : <EmptyState title="Chưa có tài liệu" description="Thêm tài liệu tham khảo khi bạn muốn Content Agent sử dụng số liệu hoặc thông tin cụ thể." action={<Link href={`/w/${workspaceId}/documents`} className="font-semibold text-teal-800">Tải tài liệu lên</Link>} />}
    </Card>

    <nav aria-label="Lối tắt" className="flex flex-wrap gap-x-6 gap-y-3 border-t border-slate-200 pt-5">
      <Link href={`/w/${workspaceId}/publishing`} className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-teal-800"><Icon name="publish" size={17} /> Xuất bản</Link>
      <Link href={`/w/${workspaceId}/fanpages`} className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-teal-800"><Icon name="globe" size={17} /> Fanpage & thị trường</Link>
      <Link href={`/w/${workspaceId}/analytics`} className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 hover:text-teal-800"><Icon name="chart" size={17} /> Hiệu quả</Link>
    </nav>
  </div>;
}
