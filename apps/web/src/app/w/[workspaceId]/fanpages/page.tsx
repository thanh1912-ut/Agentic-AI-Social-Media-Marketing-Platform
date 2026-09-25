'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useSession } from '@/components/session-gate';
import { Badge, Button, Card, EmptyState, ErrorPanel, LoadingBlock, PermissionNotice, StatusBadge } from '@/components/ui';
import { ApiError, marketResearchApi, marketResearchKeys } from '@/lib/api';
import type { ResearchSourceType } from '@/lib/api/market-research';
import { formatDateTime } from '@/lib/format';

const SOURCE_LABELS: Record<ResearchSourceType, string> = {
  website: 'Website công khai',
  owned_facebook_page: 'Fanpage của workspace',
  competitor_facebook_page: 'Fanpage đối thủ',
  facebook_group: 'Nhóm Facebook',
};

const MARKET_METRIC_LABELS: Record<string, string> = {
  reactions: 'Cảm xúc',
  comments: 'Bình luận',
  shares: 'Chia sẻ',
  interactions: 'Tương tác',
  views: 'Lượt xem',
  followers: 'Người theo dõi Page',
};

function formatMetrics(metrics: Record<string, number | null> | undefined): string {
  if (!metrics) return '';
  return Object.entries(metrics)
    .filter(([key, value]) => key in MARKET_METRIC_LABELS && typeof value === 'number' && Number.isFinite(value))
    .map(([key, value]) => `${MARKET_METRIC_LABELS[key]}: ${new Intl.NumberFormat('vi-VN').format(value as number)}`)
    .join(' · ');
}

function formatMetricChanges(metrics: Record<string, number | null> | undefined): string {
  if (!metrics) return '';
  return Object.entries(metrics)
    .filter(([key, value]) => key in MARKET_METRIC_LABELS && typeof value === 'number' && Number.isFinite(value))
    .map(([key, value]) => {
      const amount = new Intl.NumberFormat('vi-VN').format(Math.abs(value as number));
      const direction = (value as number) > 0 ? '+' : (value as number) < 0 ? '−' : '';
      return `${MARKET_METRIC_LABELS[key]}: ${direction}${amount}`;
    })
    .join(' · ');
}

const SOURCE_STATUS: Record<string, { label: string; tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' }> = {
  active: { label: 'Tự động thu thập', tone: 'success' },
  manual_import_only: { label: 'Cần nhập dữ liệu thủ công', tone: 'info' },
  needs_access: { label: 'Cần kết nối lại / thiếu quyền', tone: 'warning' },
  error: { label: 'Lỗi khi thu thập', tone: 'danger' },
  disabled: { label: 'Đã tắt', tone: 'neutral' },
};

function readableError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

export default function FanpagesMarketResearchPage() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const queryClient = useQueryClient();
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const canManageMarket = Boolean(workspace?.permissions.includes('market:manage'));
  const canConnectPage = Boolean(workspace?.permissions.includes('connection:manage'));

  const [selectedGroupId, setSelectedGroupId] = useState('');
  const [groupFormOpen, setGroupFormOpen] = useState(false);
  const [pageId, setPageId] = useState('');
  const [pageToken, setPageToken] = useState('');
  const [pageError, setPageError] = useState<string | null>(null);
  const [pageSaved, setPageSaved] = useState<string | null>(null);
  const [pageBusy, setPageBusy] = useState(false);
  const [sourceType, setSourceType] = useState<ResearchSourceType>('website');
  const [manualSourceId, setManualSourceId] = useState('');
  const [manualPostUrl, setManualPostUrl] = useState('');
  const [manualTitle, setManualTitle] = useState('');
  const [manualText, setManualText] = useState('');
  const [manualReactions, setManualReactions] = useState('');
  const [manualCommentsCount, setManualCommentsCount] = useState('');
  const [manualShares, setManualShares] = useState('');
  const [manualViews, setManualViews] = useState('');
  const [manualFollowers, setManualFollowers] = useState('');
  const [manualCommentText, setManualCommentText] = useState('');
  const [manualResult, setManualResult] = useState<string | null>(null);
  const [pageNotice, setPageNotice] = useState<string | null>(null);
  const [lastCrawlJob, setLastCrawlJob] = useState<{ jobId: string; groupId: string } | null>(null);
  const [draftCampaign, setDraftCampaign] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);

  const groupsQuery = useQuery({
    queryKey: marketResearchKeys.groups(workspaceId),
    queryFn: () => marketResearchApi.groups(workspaceId),
    enabled: workspaceId !== '',
  });
  const groups = groupsQuery.data ?? [];
  const selectedGroup = groups.find((group) => group.id === selectedGroupId) ?? groups[0] ?? null;
  const activeGroupId = selectedGroup?.id ?? '';
  useEffect(() => {
    if (activeGroupId && selectedGroupId !== activeGroupId) setSelectedGroupId(activeGroupId);
  }, [activeGroupId, selectedGroupId]);

  const pagesQuery = useQuery({
    queryKey: marketResearchKeys.pages(workspaceId, activeGroupId),
    queryFn: () => marketResearchApi.pages(workspaceId, activeGroupId),
    enabled: workspaceId !== '' && activeGroupId !== '',
  });
  const sourcesQuery = useQuery({
    queryKey: marketResearchKeys.sources(workspaceId, activeGroupId),
    queryFn: () => marketResearchApi.sources(workspaceId, activeGroupId),
    enabled: workspaceId !== '' && activeGroupId !== '',
  });
  const reportsQuery = useQuery({
    queryKey: marketResearchKeys.reports(workspaceId, activeGroupId),
    queryFn: () => marketResearchApi.reports(workspaceId, activeGroupId),
    enabled: workspaceId !== '' && activeGroupId !== '',
    refetchInterval: (query) => query.state.fetchStatus === 'fetching' ? false : 15_000,
  });
  const pages = pagesQuery.data ?? [];
  const sources = sourcesQuery.data ?? [];
  const reports = reportsQuery.data ?? [];

  const refreshGroupData = async (groupId = activeGroupId) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.groups(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.pages(workspaceId, groupId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.sources(workspaceId, groupId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.reports(workspaceId, groupId) }),
    ]);
  };

  const createGroup = useMutation({
    mutationFn: (form: FormData) => marketResearchApi.createGroup(workspaceId, {
      name: String(form.get('name') ?? ''),
      industry: String(form.get('industry') ?? ''),
      region: String(form.get('region') ?? ''),
      locale: String(form.get('locale') ?? 'vi-VN'),
      keywords: String(form.get('keywords') ?? '').split(',').map((item) => item.trim()).filter(Boolean).slice(0, 30),
    }),
    onSuccess: async (group) => {
      setSelectedGroupId(group.id);
      setGroupFormOpen(false);
      await refreshGroupData();
    },
  });
  const createSource = useMutation({
    mutationFn: (form: FormData) => marketResearchApi.createSource(workspaceId, {
      group_id: activeGroupId,
      source_type: sourceType,
      name: String(form.get('name') ?? ''),
      url: String(form.get('url') ?? ''),
      competitor_name: String(form.get('competitor_name') ?? '') || undefined,
      connection_id: sourceType === 'owned_facebook_page' ? String(form.get('connection_id') ?? '') : undefined,
    }),
    onSuccess: async () => {
      await refreshGroupData();
    },
  });
  const deleteSource = useMutation({
    mutationFn: (sourceId: string) => marketResearchApi.deleteSource(workspaceId, sourceId),
    onSuccess: () => refreshGroupData(),
  });
  const disconnectPage = useMutation({
    mutationFn: (connectionId: string) => marketResearchApi.disconnectPage(workspaceId, connectionId),
    onSuccess: async () => {
      setPageNotice('Đã ngắt kết nối Fanpage. Token đã bị xoá khỏi cấu hình đang hoạt động.');
      await refreshGroupData();
    },
  });
  const crawlNow = useMutation({
    mutationFn: (groupId: string) => marketResearchApi.crawlNow(workspaceId, groupId),
    onMutate: () => setLastCrawlJob(null),
    onSuccess: (accepted, groupId) => {
      setLastCrawlJob({ jobId: accepted.job_id, groupId });
      void refreshGroupData(groupId);
    },
  });
  const importManual = useMutation({
    mutationFn: () => {
      const metric = (value: string) => value.trim() === '' ? null : Number(value);
      const comments = manualCommentText.split('\n').map((value) => value.trim()).filter(Boolean);
      return marketResearchApi.importObservations(workspaceId, manualSourceId, [{
        url: manualPostUrl,
        title: manualTitle,
        text: manualText,
        metrics: {
          reactions: metric(manualReactions),
          comments: metric(manualCommentsCount),
          shares: metric(manualShares),
          views: metric(manualViews),
          followers: metric(manualFollowers),
        },
        comments,
      }]);
    },
    onSuccess: async (result) => {
      setManualResult('Đã nhập ' + result.imported + ' bài. Nội dung bình luận đã được ẩn email và số điện thoại.');
      setManualPostUrl('');
      setManualTitle('');
      setManualText('');
      setManualCommentText('');
      setManualReactions('');
      setManualCommentsCount('');
      setManualShares('');
      setManualViews('');
      setManualFollowers('');
      await refreshGroupData();
    },
  });
  const createDraft = useMutation({
    mutationFn: ({ reportId, suggestionIndex }: { reportId: string; suggestionIndex: number }) =>
      marketResearchApi.createDraft(workspaceId, reportId, suggestionIndex),
    onSuccess: (result) => {
      setDraftCampaign(result.campaign_id);
      setDraftError(null);
    },
    onError: (error) => setDraftError(readableError(error, 'Không tạo được chiến dịch nháp.')),
  });

  async function submitPageConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPageError(null);
    setPageSaved(null);
    setPageBusy(true);
    const submittedToken = pageToken;
    setPageToken('');
    try {
      const page = await marketResearchApi.connectPage(workspaceId, activeGroupId, {
        page_id: pageId.trim(),
        page_access_token: submittedToken,
      });
      setPageId('');
      setPageSaved('Đã xác minh ' + (page.page_name || 'Fanpage') + ' (' + page.page_id + '). Token được mã hoá trong backend.');
      await refreshGroupData();
    } catch (error) {
      setPageError(readableError(error, 'Không xác minh hoặc lưu được Fanpage.'));
    } finally {
      setPageToken('');
      setPageBusy(false);
    }
  }

  function submitGroup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    createGroup.mutate(form);
    event.currentTarget.reset();
  }

  function submitSource(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createSource.mutate(new FormData(event.currentTarget));
    event.currentTarget.reset();
  }

  if (!workspace) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold text-slate-900">Không mở được Fanpage và thị trường</h1>
        <PermissionNotice message="Bạn không thuộc doanh nghiệp này, nên không xem được Page và dữ liệu nghiên cứu." />
        <Button variant="secondary" onClick={() => router.push('/')}>Về trang chủ</Button>
      </div>
    );
  }

  if (groupsQuery.isLoading) return <LoadingBlock label="Đang tải nhóm Fanpage và nguồn nghiên cứu…" />;
  if (groupsQuery.isError) {
    return <ErrorPanel message={readableError(groupsQuery.error, 'Không tải được cấu hình thị trường.')} code={groupsQuery.error instanceof ApiError ? groupsQuery.error.code : undefined} retryable onRetry={() => void groupsQuery.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">Fanpage và nghiên cứu thị trường</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            Kết nối tối đa 5 Fanpage và lưu 20 link nguồn cho mỗi workspace; hệ thống tổng hợp thị trường mỗi 12 giờ.
            Báo cáo chỉ gợi ý; người trong workspace xem lại trước khi tạo nội dung.
          </p>
        </div>
        {activeGroupId && canManageMarket ? (
          <Button loading={crawlNow.isPending} onClick={() => crawlNow.mutate(activeGroupId)}>
            Crawl ngay
          </Button>
        ) : null}
      </header>

      {pageNotice ? <p role="status" className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">{pageNotice}</p> : null}
      {lastCrawlJob?.groupId === activeGroupId ? (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          Đã đưa yêu cầu crawl vào hàng đợi. <Link className="font-medium underline" href={'/w/' + workspaceId + '/jobs/' + lastCrawlJob.jobId}>Theo dõi tiến độ</Link>.
        </p>
      ) : null}
      {crawlNow.error ? <ErrorPanel title="Không xếp được lượt thu thập" message={readableError(crawlNow.error, 'Hãy kiểm tra worker và nguồn đã lưu.')} code={crawlNow.error instanceof ApiError ? crawlNow.error.code : undefined} /> : null}
      {draftError ? <ErrorPanel title="Chưa tạo được chiến dịch nháp" message={draftError} /> : null}
      {draftCampaign ? (
        <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          Đã tạo chiến dịch nháp. <Link className="font-medium underline" href={'/w/' + workspaceId + '/campaigns/' + draftCampaign}>Mở chiến dịch để xem lại và yêu cầu AI sinh bài</Link>.
        </div>
      ) : null}

      <Card
        title="Nhóm Fanpage và thị trường"
        description="Mỗi nhóm có một hồ sơ ngành/khu vực riêng. Hồ sơ thương hiệu vẫn dùng chung trong workspace."
        actions={canManageMarket ? <Button variant="secondary" onClick={() => setGroupFormOpen((value) => !value)}>{groupFormOpen ? 'Đóng' : 'Tạo nhóm'}</Button> : null}
      >
        {groups.length === 0 ? (
          <EmptyState title="Chưa có nhóm" description="Tạo nhóm để kết nối Fanpage và lưu vùng thị trường cần theo dõi." />
        ) : (
          <div className="space-y-3">
            <label className="block max-w-xl text-sm font-medium text-slate-700">
              Nhóm đang xem
              <select className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2" value={activeGroupId} onChange={(event) => setSelectedGroupId(event.currentTarget.value)}>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name} · {group.industry} · {group.region}</option>)}
              </select>
            </label>
            {selectedGroup ? (
              <div className="flex flex-wrap gap-2 text-sm text-slate-600">
                <Badge>{selectedGroup.page_count} Fanpage trong nhóm</Badge>
                <Badge>{selectedGroup.source_count} nguồn trong nhóm</Badge>
                <span>Ngôn ngữ: {selectedGroup.locale}</span>
                <span>Lượt gần nhất: {selectedGroup.last_cycle_at ? formatDateTime(selectedGroup.last_cycle_at) : 'chưa có'}</span>
                <span>Lượt kế tiếp: {selectedGroup.next_due_at ? formatDateTime(selectedGroup.next_due_at) : 'chưa lên lịch'}</span>
              </div>
            ) : null}
          </div>
        )}
        {groupFormOpen && canManageMarket ? (
          <form className="mt-5 grid gap-3 border-t border-slate-200 pt-4 sm:grid-cols-2" onSubmit={submitGroup}>
            <label className="text-sm text-slate-700">Tên nhóm<input name="name" required maxLength={160} placeholder="Ví dụ: Mỹ phẩm miền Nam" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
            <label className="text-sm text-slate-700">Ngành<input name="industry" required maxLength={160} placeholder="Mỹ phẩm, F&B…" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
            <label className="text-sm text-slate-700">Khu vực<input name="region" required maxLength={160} placeholder="TP. Hồ Chí Minh, Việt Nam…" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
            <label className="text-sm text-slate-700">Mã ngôn ngữ<input name="locale" defaultValue="vi-VN" required maxLength={24} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
            <label className="text-sm text-slate-700 sm:col-span-2">Từ khoá thị trường, phân cách bằng dấu phẩy<input name="keywords" maxLength={1000} placeholder="kem chống nắng, chăm sóc da, mùa hè" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label>
            <div className="sm:col-span-2"><Button type="submit" loading={createGroup.isPending}>Lưu nhóm</Button></div>
            {createGroup.error ? <p role="alert" className="text-sm text-rose-800 sm:col-span-2">{readableError(createGroup.error, 'Không tạo được nhóm.')}</p> : null}
          </form>
        ) : null}
      </Card>

      {activeGroupId ? (
        <>
          <Card
            title="Kết nối Fanpage của bạn"
            description="Nhập Page ID và Page Access Token trong ứng dụng. Token được gửi tới backend, mã hoá trước khi lưu và không xuất hiện lại trên màn hình."
          >
            {!canConnectPage ? <PermissionNotice message="Chỉ chủ workspace được thêm hoặc ngắt kết nối Fanpage." requiredPermission="connection:manage" /> : null}
            {canConnectPage ? (
              <form className="grid gap-3 sm:grid-cols-2" onSubmit={(event) => void submitPageConnection(event)}>
                <label className="text-sm text-slate-700">Page ID<input value={pageId} onChange={(event) => setPageId(event.currentTarget.value)} required inputMode="numeric" pattern="[0-9]{1,32}" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="ID số của Fanpage" /></label>
                <label className="text-sm text-slate-700">Page Access Token<input type="password" value={pageToken} onChange={(event) => setPageToken(event.currentTarget.value)} required minLength={20} maxLength={4096} autoComplete="off" spellCheck={false} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="Dán token vào đây, không gửi trong chat" /></label>
                <p className="text-xs text-slate-500 sm:col-span-2">Backend xác minh ID/token bằng Meta Graph API trước khi lưu. Token cần quyền đọc bài của Page. Việc đăng bài vẫn cần duyệt nội dung theo luồng hiện có.</p>
                <div className="sm:col-span-2"><Button type="submit" loading={pageBusy} disabled={!pageId || !pageToken} disabledReason="Nhập Page ID và Page Access Token trước khi kết nối.">Xác minh và lưu Fanpage</Button></div>
                {pageError ? <p role="alert" className="text-sm text-rose-800 sm:col-span-2">{pageError}</p> : null}
                {pageSaved ? <p role="status" className="text-sm text-emerald-800 sm:col-span-2">{pageSaved}</p> : null}
              </form>
            ) : null}
            <div className="mt-4 space-y-2">
              {pagesQuery.isLoading ? <p className="text-sm text-slate-500">Đang tải Fanpage…</p> : null}
              {pages.map((page) => (
                <div key={page.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-3">
                  <div>
                    <p className="font-medium text-slate-900">{page.page_name || 'Fanpage'} <span className="font-normal text-slate-500">· {page.page_id}</span></p>
                    <p className="text-xs text-slate-500">{page.verified_at ? 'Xác minh ' + formatDateTime(page.verified_at) : 'Chưa xác minh'}{page.last_error_code ? ' · ' + page.last_error_code : ''}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge label={page.status === 'verified' ? 'Đã xác minh' : 'Cần kết nối lại'} tone={page.status === 'verified' ? 'success' : 'warning'} />
                    {canConnectPage ? <Button size="sm" variant="danger" loading={disconnectPage.isPending} onClick={() => disconnectPage.mutate(page.id)}>Ngắt</Button> : null}
                  </div>
                </div>
              ))}
              {!pagesQuery.isLoading && pages.length === 0 ? <p className="text-sm text-slate-500">Chưa kết nối Fanpage nào trong nhóm này.</p> : null}
            </div>
          </Card>

          <Card
            title="Nguồn thu thập"
            description="Website, Page của workspace và Fanpage đối thủ có quyền Meta phù hợp được đọc mỗi 12 giờ. Nhóm Facebook hiện lưu link và nhập dữ liệu thủ công; số liệu thiếu quyền sẽ để trống."
          >
            {canManageMarket ? (
              <form className="grid gap-3 sm:grid-cols-2" onSubmit={submitSource}>
                <label className="text-sm text-slate-700">Loại nguồn<select value={sourceType} onChange={(event) => setSourceType(event.currentTarget.value as ResearchSourceType)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2">{Object.entries(SOURCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label className="text-sm text-slate-700">Tên nguồn<input name="name" required maxLength={200} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="Tên website/Page/nhóm" /></label>
                <label className="text-sm text-slate-700 sm:col-span-2">Link website hoặc Facebook<input name="url" required type="url" maxLength={2048} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="https://…" /></label>
                {sourceType === 'competitor_facebook_page' ? <p className="text-xs text-slate-500 sm:col-span-2">Tự thu thập Page đối thủ cần backend cấu hình access token của Meta App đã được duyệt quyền Page Public Content Access. Nếu chưa có quyền, link vẫn được lưu và có thể nhập số liệu thủ công.</p> : null}
                {sourceType === 'facebook_group' ? <p className="text-xs text-slate-500 sm:col-span-2">Link nhóm được lưu để tái sử dụng. Meta đã gỡ Groups API nên hệ thống không tự đọc bài trong nhóm; hãy nhập nội dung và số liệu mà bạn được phép sử dụng.</p> : null}
                {sourceType === 'owned_facebook_page' ? (
                  <label className="text-sm text-slate-700 sm:col-span-2">Fanpage đã kết nối<select name="connection_id" required className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2"><option value="">Chọn Fanpage</option>{pages.filter((page) => page.status === 'verified').map((page) => <option key={page.id} value={page.id}>{page.page_name} · {page.page_id}</option>)}</select></label>
                ) : null}
                {sourceType === 'competitor_facebook_page' ? <label className="text-sm text-slate-700 sm:col-span-2">Tên đối thủ<input name="competitor_name" maxLength={200} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label> : null}
                <div className="sm:col-span-2"><Button type="submit" loading={createSource.isPending} disabled={!canManageMarket} disabledReason="Vai trò của bạn chưa có quyền quản lý nguồn nghiên cứu.">Lưu link nguồn</Button></div>
                {createSource.error ? <p role="alert" className="text-sm text-rose-800 sm:col-span-2">{readableError(createSource.error, 'Không lưu được nguồn.')}</p> : null}
              </form>
            ) : <PermissionNotice message="Bạn có thể xem báo cáo, nhưng cần quyền market:manage để thêm hoặc xoá nguồn." requiredPermission="market:manage" />}
            <div className="mt-5 space-y-2">
              {sources.map((source) => {
                const status = SOURCE_STATUS[source.status] ?? { label: source.status, tone: 'neutral' as const };
                return (
                  <div key={source.id} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-slate-200 px-3 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2"><p className="font-medium text-slate-900">{source.name}</p><StatusBadge label={status.label} tone={status.tone} /></div>
                      <p className="mt-1 break-all text-xs text-slate-600">{source.url}</p>
                      <p className="mt-1 text-xs text-slate-500">{SOURCE_LABELS[source.source_type]}{source.last_crawled_at ? ' · lần đọc gần nhất ' + formatDateTime(source.last_crawled_at) : ''}</p>
                      {source.error?.message ? <p className="mt-1 text-xs text-rose-800">{source.error.message}</p> : null}
                    </div>
                    <div className="flex gap-2">
                      {source.source_type !== 'website' && canManageMarket ? <Button size="sm" variant="secondary" onClick={() => { setManualSourceId(source.id); setManualResult(null); }}>Nhập dữ liệu</Button> : null}
                      {canManageMarket ? <Button size="sm" variant="ghost" loading={deleteSource.isPending} onClick={() => deleteSource.mutate(source.id)}>Xoá link</Button> : null}
                    </div>
                  </div>
                );
              })}
              {sources.length === 0 ? <EmptyState title="Chưa lưu link nào" description="Thêm website, Fanpage của bạn hoặc link đối thủ/nhóm Facebook để bắt đầu." /> : null}
            </div>
            {manualSourceId ? (
              <form className="mt-5 grid gap-3 rounded-lg border border-sky-200 bg-sky-50 p-4 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); importManual.mutate(); }}>
                <div className="sm:col-span-2"><h3 className="font-medium text-slate-900">Nhập dữ liệu bài viết</h3><p className="mt-1 text-xs text-slate-600">Chỉ nhập số liệu bạn được phép sử dụng. Tên người bình luận không có trường riêng; email và số điện thoại trong bình luận sẽ được ẩn trước khi lưu.</p></div>
                <label className="text-sm text-slate-700 sm:col-span-2">Link bài viết<input type="url" required value={manualPostUrl} onChange={(event) => setManualPostUrl(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700 sm:col-span-2">Tiêu đề<input value={manualTitle} onChange={(event) => setManualTitle(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700 sm:col-span-2">Nội dung bài viết<textarea required maxLength={12000} rows={4} value={manualText} onChange={(event) => setManualText(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700">Lượt thích / cảm xúc<input inputMode="numeric" type="number" min="0" value={manualReactions} onChange={(event) => setManualReactions(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700">Số bình luận<input inputMode="numeric" type="number" min="0" value={manualCommentsCount} onChange={(event) => setManualCommentsCount(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700">Lượt chia sẻ<input inputMode="numeric" type="number" min="0" value={manualShares} onChange={(event) => setManualShares(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700">Lượt xem<input inputMode="numeric" type="number" min="0" value={manualViews} onChange={(event) => setManualViews(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700">Người theo dõi Page<input inputMode="numeric" type="number" min="0" value={manualFollowers} onChange={(event) => setManualFollowers(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <label className="text-sm text-slate-700 sm:col-span-2">Nội dung bình luận (mỗi dòng một bình luận)<textarea rows={3} value={manualCommentText} onChange={(event) => setManualCommentText(event.currentTarget.value)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                <div className="flex gap-2 sm:col-span-2"><Button type="submit" loading={importManual.isPending} disabled={!manualText || !manualPostUrl} disabledReason="Nhập link và nội dung bài viết.">Lưu dữ liệu</Button><Button variant="secondary" onClick={() => setManualSourceId('')}>Đóng</Button></div>
                {manualResult ? <p role="status" className="text-sm text-emerald-800 sm:col-span-2">{manualResult}</p> : null}
                {importManual.error ? <p role="alert" className="text-sm text-rose-800 sm:col-span-2">{readableError(importManual.error, 'Không nhập được dữ liệu.')}</p> : null}
              </form>
            ) : null}
          </Card>

          <Card title="Báo cáo xu hướng và gợi ý" description="DeepSeek phân tích nội dung, tương tác, views, follower count và thay đổi giữa các lần crawl khi nguồn trả dữ liệu. Giá trị thiếu được để trống; kết luận có nguồn đối chiếu.">
            {reportsQuery.isLoading ? <LoadingBlock label="Đang tải báo cáo…" /> : null}
            {reportsQuery.error ? <ErrorPanel message={readableError(reportsQuery.error, 'Không tải được báo cáo.')} retryable onRetry={() => void reportsQuery.refetch()} /> : null}
            {reports.map((report) => (
              <article key={report.id} className="mb-4 rounded-xl border border-slate-200 p-4 last:mb-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><h3 className="font-semibold text-slate-900">{report.report.headline || 'Báo cáo thị trường'}</h3><p className="mt-1 text-xs text-slate-500">Tạo {formatDateTime(report.created_at)}{report.model_name ? ' · ' + report.model_name : ''}</p></div>
                  <StatusBadge label={report.coverage.ai_status === 'completed' ? 'Đã phân tích' : 'Phân tích chưa hoàn tất'} tone={report.coverage.ai_status === 'completed' ? 'success' : 'warning'} />
                </div>
                <p className="mt-3 whitespace-pre-line text-sm text-slate-700">{report.report.summary}</p>
                {(report.report.trends ?? []).length > 0 ? (
                  <div className="mt-4"><h4 className="text-sm font-semibold text-slate-900">Xu hướng ghi nhận</h4><ul className="mt-2 space-y-2">{report.report.trends?.map((trend, index) => <li key={trend.title + index} className="rounded-lg bg-slate-50 p-3"><p className="text-sm font-medium text-slate-900">{trend.title} <span className="text-xs font-normal text-slate-500">· độ tin cậy {Math.round(trend.confidence * 100)}%</span></p><p className="mt-1 text-sm text-slate-700">{trend.explanation}</p><p className="mt-1 text-xs text-slate-500">{trend.evidence_ids.length} nguồn đối chiếu</p></li>)}</ul></div>
                ) : null}
                {(report.report.suggestions ?? []).length > 0 ? (
                  <div className="mt-4"><h4 className="text-sm font-semibold text-slate-900">Gợi ý nội dung</h4><div className="mt-2 grid gap-3 lg:grid-cols-2">{report.report.suggestions?.map((suggestion, index) => <div key={suggestion.title + index} className="rounded-lg border border-slate-200 p-3"><p className="font-medium text-slate-900">{suggestion.title}</p><p className="mt-1 text-sm text-slate-700">{suggestion.angle}</p><p className="mt-2 text-sm text-slate-600">Mở bài: “{suggestion.hook}” · {suggestion.format}</p><p className="mt-1 text-xs text-slate-500">{suggestion.evidence_ids.length} nguồn liên quan</p><div className="mt-3"><Button size="sm" variant="secondary" loading={createDraft.isPending && createDraft.variables?.reportId === report.id && createDraft.variables?.suggestionIndex === index} onClick={() => createDraft.mutate({ reportId: report.id, suggestionIndex: index })}>Tạo chiến dịch nháp</Button></div></div>)}</div></div>
                ) : null}
                {(report.report.evidence_refs ?? []).length > 0 ? (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-sm font-medium text-slate-700">Nguồn dữ liệu ({report.report.evidence_refs?.length})</summary>
                    <ul className="mt-2 space-y-1 text-xs text-slate-600">
                      {report.report.evidence_refs?.map((reference) => (
                        <li key={reference.id}>
                          <a href={reference.url} target="_blank" rel="noopener noreferrer" className="underline">
                            {reference.title || reference.url}
                          </a>
                          {reference.published_at ? ' · ' + formatDateTime(reference.published_at) : ''}
                          {formatMetrics(reference.metrics) ? <p className="mt-1 text-xs text-slate-600">{formatMetrics(reference.metrics)}</p> : null}
                          {formatMetricChanges(reference.metric_delta) ? <p className="mt-1 text-xs text-slate-600">Thay đổi giữa hai lần crawl: {formatMetricChanges(reference.metric_delta)}</p> : null}
                          {reference.comments?.length ? <ul className="mt-1 list-inside list-disc text-xs text-slate-600">{reference.comments.map((comment, index) => <li key={`${reference.id}-comment-${index}`}>{comment}</li>)}</ul> : null}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
                {(report.coverage.sources ?? []).length > 0 ? <details className="mt-4"><summary className="cursor-pointer text-sm font-medium text-slate-700">Chi tiết nguồn và quyền số liệu</summary><ul className="mt-2 space-y-1 text-xs text-slate-600">{report.coverage.sources?.map((source) => <li key={source.source_id}>{source.status} · {source.items_saved ?? 0} mục đã lưu{source.metrics_available?.length ? ' · số liệu có: ' + source.metrics_available.join(', ') : ''}{source.metrics_unavailable?.length ? ' · số liệu thiếu: ' + source.metrics_unavailable.join(', ') : ''}{source.metrics_partial && Object.keys(source.metrics_partial).length ? ' · thiếu một phần: ' + Object.entries(source.metrics_partial).map(([key, value]) => `${key} (${value.observed_posts}/${value.total_posts})`).join(', ') : ''}{source.message ? ' · ' + source.message : ''}</li>)}</ul>{report.coverage.metrics_note ? <p className="mt-2 text-xs text-slate-500">{report.coverage.metrics_note}</p> : null}</details> : null}
              </article>
            ))}
            {!reportsQuery.isLoading && reports.length === 0 ? <EmptyState title="Chưa có báo cáo" description="Sau khi lưu nguồn, bấm Thu thập ngay hoặc chờ lượt tự động đầu tiên. Lịch tiếp theo chạy sau mỗi 12 giờ." /> : null}
          </Card>
        </>
      ) : null}
    </div>
  );
}
