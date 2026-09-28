'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useSession } from '@/components/session-gate';
import { Badge, Button, Card, EmptyState, ErrorPanel, LoadingBlock, PermissionNotice, StatusBadge } from '@/components/ui';
import { ApiError, marketResearchApi, marketResearchKeys, useMocks } from '@/lib/api';
import type { ResearchSourceType } from '@/lib/api/market-research';
import { useJob } from '@/lib/hooks';
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
  not_started: { label: 'Chưa kiểm tra', tone: 'neutral' },
  queued: { label: 'Đang chờ worker', tone: 'info' },
  collected: { label: 'Đã thu thập', tone: 'success' },
  completed: { label: 'Đã thu thập', tone: 'success' },
  partial: { label: 'Thu thập một phần', tone: 'warning' },
  blocked_robots: { label: 'Lượt collector cũ bị robots chặn', tone: 'danger' },
  platform_permission_required: { label: 'Lượt collector cũ cần quyền Meta', tone: 'warning' },
  access_denied: { label: 'Facebook từ chối truy cập', tone: 'danger' },
  challenge: { label: 'Facebook yêu cầu xác minh', tone: 'warning' },
  login_required: { label: 'Facebook yêu cầu đăng nhập', tone: 'warning' },
  challenge_required: { label: 'Facebook yêu cầu xác minh', tone: 'warning' },
  page_public_content_access_not_configured: { label: 'Meta API chưa được cấu hình', tone: 'warning' },
  page_public_access_denied: { label: 'Meta không cấp quyền đọc', tone: 'danger' },
  no_posts_returned: { label: 'Page đọc được, chưa trả bài viết', tone: 'warning' },
  engine_unavailable: { label: 'facebook-cli runner chưa sẵn sàng', tone: 'danger' },
  rate_limited: { label: 'Facebook đang giới hạn yêu cầu', tone: 'warning' },
  network_error: { label: 'Lỗi kết nối Facebook', tone: 'danger' },
  parser_error: { label: 'Không đọc được dữ liệu Facebook', tone: 'danger' },
  page_identity_unverified: { label: 'Chưa xác minh được Fanpage', tone: 'warning' },
  request_budget_reached: { label: 'Đã hết ngân sách lượt crawl', tone: 'warning' },
  collector_coordination_lost: { label: 'Lượt dừng do worker mất quyền xử lý', tone: 'danger' },
  source_processing_failed: { label: 'Lỗi xử lý nguồn', tone: 'danger' },
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
  const mocksOn = useMocks();
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
  const [lastSourceCrawl, setLastSourceCrawl] = useState<{ jobId: string; sourceId: string } | null>(null);
  const [expandedCompetitorId, setExpandedCompetitorId] = useState('');
  const [draftCampaign, setDraftCampaign] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [webKind, setWebKind] = useState('product');

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
  const webItemsQuery = useQuery({
    queryKey: marketResearchKeys.webItems(workspaceId, activeGroupId, webKind),
    queryFn: () => marketResearchApi.webItems(workspaceId, activeGroupId, webKind),
    enabled: workspaceId !== '' && activeGroupId !== '',
  });
  const expandedCompetitor = sourcesQuery.data?.find(
    (source) => source.id === expandedCompetitorId && source.source_type === 'competitor_facebook_page',
  );
  const competitorPostsQuery = useInfiniteQuery({
    queryKey: marketResearchKeys.competitorPosts(workspaceId, expandedCompetitorId),
    queryFn: ({ pageParam }) => marketResearchApi.competitorPosts(workspaceId, expandedCompetitorId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: workspaceId !== '' && expandedCompetitor !== undefined,
    refetchInterval: (query) => query.state.fetchStatus === 'fetching' ? false : 15_000,
  });
  const competitorRunsQuery = useQuery({
    queryKey: marketResearchKeys.competitorRuns(workspaceId, expandedCompetitorId),
    queryFn: () => marketResearchApi.competitorCollectionRuns(workspaceId, expandedCompetitorId),
    enabled: workspaceId !== '' && expandedCompetitor !== undefined,
    refetchInterval: (query) => query.state.fetchStatus === 'fetching' ? false : 15_000,
  });
  const pages = pagesQuery.data ?? [];
  const sources = sourcesQuery.data ?? [];
  const reports = reportsQuery.data ?? [];
  const competitorPosts = competitorPostsQuery.data?.pages.flatMap((page) => page.posts) ?? [];
  const competitorAudience = competitorPostsQuery.data?.pages[0];
  const groupJobQuery = useJob(lastCrawlJob?.jobId);
  const sourceJobQuery = useJob(lastSourceCrawl?.jobId);

  const refreshGroupData = useCallback(async (groupId = activeGroupId) => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.groups(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.pages(workspaceId, groupId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.sources(workspaceId, groupId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.reports(workspaceId, groupId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.webItems(workspaceId, groupId, 'product') }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.webItems(workspaceId, groupId, 'article') }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.webItems(workspaceId, groupId, 'business_info') }),
    ]);
  }, [activeGroupId, queryClient, workspaceId]);

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
  const updateCrawlSettings = useMutation({
    mutationFn: ({ sourceId, settings }: { sourceId: string; settings: {
      crawl_mode: 'legacy' | 'site_catalog'; crawl_page_limit: number; render_mode: 'http_only' | 'javascript';
      resource_hosts: string[]; schedule_enabled: boolean;
    } }) => marketResearchApi.updateCrawlSettings(workspaceId, sourceId, settings),
    onSuccess: async () => refreshGroupData(),
  });
  const updateCollectionSettings = useMutation({
    mutationFn: ({ sourceId, settings }: { sourceId: string; settings: {
      collector: 'public_web' | 'meta_api' | 'manual'; schedule_enabled: boolean; post_limit: number;
    } }) => marketResearchApi.updateCollectionSettings(workspaceId, sourceId, settings),
    onSuccess: async (_source, variables) => {
      await refreshGroupData();
      await queryClient.invalidateQueries({ queryKey: marketResearchKeys.competitorRuns(workspaceId, variables.sourceId) });
    },
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
  const crawlCompetitorNow = useMutation({
    mutationFn: (sourceId: string) => marketResearchApi.crawlSource(workspaceId, sourceId),
    onSuccess: async (accepted, sourceId) => {
      setLastSourceCrawl({ jobId: accepted.job_id, sourceId });
      setExpandedCompetitorId(sourceId);
      await refreshGroupData();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: marketResearchKeys.competitorPosts(workspaceId, sourceId) }),
        queryClient.invalidateQueries({ queryKey: marketResearchKeys.competitorRuns(workspaceId, sourceId) }),
      ]);
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

  useEffect(() => {
    if (groupJobQuery.data && ['succeeded', 'failed', 'cancelled'].includes(groupJobQuery.data.status)) {
      void refreshGroupData(lastCrawlJob?.groupId ?? activeGroupId);
    }
  }, [activeGroupId, groupJobQuery.data, lastCrawlJob?.groupId, refreshGroupData]);

  useEffect(() => {
    if (!sourceJobQuery.data || !lastSourceCrawl?.sourceId
        || !['succeeded', 'failed', 'cancelled'].includes(sourceJobQuery.data.status)) return;
    void refreshGroupData();
    void queryClient.invalidateQueries({
      queryKey: marketResearchKeys.competitorPosts(workspaceId, lastSourceCrawl.sourceId),
    });
    void queryClient.invalidateQueries({
      queryKey: marketResearchKeys.competitorRuns(workspaceId, lastSourceCrawl.sourceId),
    });
  }, [queryClient, refreshGroupData, sourceJobQuery.data, lastSourceCrawl?.sourceId, workspaceId]);

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
          {mocksOn ? 'Bản demo chỉ mô phỏng job, chưa crawl website thật. ' : 'Đã đưa yêu cầu crawl vào hàng đợi. '}
          <Link className="font-medium underline" href={'/w/' + workspaceId + '/jobs/' + lastCrawlJob.jobId}>Theo dõi tiến độ</Link>.
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
            description="Lưu link Fanpage đối thủ một lần, rồi crawl ngay hoặc bật lịch 12 giờ. Chế độ facebook-cli Tier 0 không dùng tài khoản đăng nhập và có thể chỉ nhận được một phần dữ liệu Facebook công khai."
          >
            {canManageMarket ? (
              <form className="grid gap-3 sm:grid-cols-2" onSubmit={submitSource}>
                <label className="text-sm text-slate-700">Loại nguồn<select value={sourceType} onChange={(event) => setSourceType(event.currentTarget.value as ResearchSourceType)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2">{Object.entries(SOURCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label className="text-sm text-slate-700">Tên nguồn<input name="name" required maxLength={200} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="Tên website/Page/nhóm" /></label>
                <label className="text-sm text-slate-700 sm:col-span-2">Link website hoặc Facebook<input name="url" required type="url" maxLength={2048} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="https://…" /></label>
                {sourceType === 'competitor_facebook_page' ? <p className="text-xs text-slate-500 sm:col-span-2">Nguồn mới dùng facebook-cli Tier 0, không cần Page Access Token và không đăng nhập Facebook. Facebook có thể trả ít bài, yêu cầu đăng nhập hoặc từ chối truy cập; giao diện sẽ giữ đúng trạng thái đó.</p> : null}
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
                const isCompetitor = source.source_type === 'competitor_facebook_page';
                const statusKey = isCompetitor ? (source.collection_status || source.status) : source.status;
                const status = SOURCE_STATUS[statusKey] ?? SOURCE_STATUS[source.status] ?? { label: statusKey, tone: 'neutral' as const };
                const schedulePaused = ['login_required', 'access_denied', 'challenge', 'challenge_required'].includes(source.collection_status ?? '');
                return (
                  <div key={source.id} className="rounded-lg border border-slate-200 px-3 py-3">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2"><p className="font-medium text-slate-900">{source.name}</p><StatusBadge label={status.label} tone={status.tone} /></div>
                        <p className="mt-1 break-all text-xs text-slate-600">{source.url}</p>
                        <p className="mt-1 text-xs text-slate-500">{SOURCE_LABELS[source.source_type]}{source.last_crawled_at ? ' · lần đọc gần nhất ' + formatDateTime(source.last_crawled_at) : ''}</p>
                        {isCompetitor ? <p className="mt-1 text-xs text-slate-500">Engine: {source.collection_mode === 'public_web' ? 'facebook-cli · Tier 0' : source.collection_mode ?? 'chưa chọn'} · Lần thử: {source.last_collection_attempt_at ? formatDateTime(source.last_collection_attempt_at) : 'chưa có'} · Lần có dữ liệu: {source.last_collection_success_at ? formatDateTime(source.last_collection_success_at) : 'chưa có'} · Lịch: {source.schedule_enabled ? schedulePaused ? 'đang tạm dừng sau khi Facebook từ chối/yêu cầu đăng nhập' : '12 giờ' : 'đã tắt'}</p> : null}
                        {source.error?.message ? <p className="mt-1 text-xs text-rose-800">{source.error.message}</p> : null}
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {isCompetitor && canManageMarket ? (
                          <>
                            <label className="sr-only" htmlFor={'collector-' + source.id}>Phương thức thu thập</label>
                            <select id={'collector-' + source.id} aria-label="Phương thức thu thập" value={source.collection_mode ?? 'manual'} disabled={updateCollectionSettings.isPending} onChange={(event) => updateCollectionSettings.mutate({ sourceId: source.id, settings: { collector: event.currentTarget.value as 'public_web' | 'meta_api' | 'manual', schedule_enabled: source.schedule_enabled ?? true, post_limit: source.collection_post_limit ?? 50 } })} className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-xs">
                              <option value="public_web">Tự thu thập công khai · facebook-cli (Tier 0)</option>
                              <option value="meta_api">Meta API đã được duyệt</option>
                              <option value="manual">Nhập thủ công</option>
                            </select>
                            <Button size="sm" variant="secondary" loading={crawlCompetitorNow.isPending && crawlCompetitorNow.variables === source.id} disabled={source.collection_mode === 'manual'} disabledReason="Chọn một phương thức thu thập tự động trước." onClick={() => crawlCompetitorNow.mutate(source.id)}>Crawl ngay</Button>
                            <Button size="sm" variant="secondary" loading={updateCollectionSettings.isPending} onClick={() => updateCollectionSettings.mutate({ sourceId: source.id, settings: { collector: source.collection_mode === 'meta_api' ? 'meta_api' : 'public_web', schedule_enabled: !(source.schedule_enabled ?? true), post_limit: source.collection_post_limit ?? 50 } })}>{source.schedule_enabled === false ? 'Bật lịch 12 giờ' : 'Tắt lịch'}</Button>
                            <Button size="sm" variant="secondary" onClick={() => setExpandedCompetitorId(expandedCompetitorId === source.id ? '' : source.id)}>{expandedCompetitorId === source.id ? 'Ẩn bài viết' : 'Bài viết & lịch sử'}</Button>
                          </>
                        ) : null}
                        {source.source_type === 'website' && canManageMarket && (source.crawl_mode ?? 'legacy') === 'legacy' ? <Button size="sm" variant="secondary" loading={updateCrawlSettings.isPending} onClick={() => updateCrawlSettings.mutate({ sourceId: source.id, settings: { crawl_mode: 'site_catalog', crawl_page_limit: 1000, render_mode: 'http_only', resource_hosts: [], schedule_enabled: true } })}>Bật sản phẩm & bài viết</Button> : null}
                        {source.source_type === 'website' && canManageMarket && source.crawl_mode === 'site_catalog' ? <Button size="sm" variant="secondary" loading={updateCrawlSettings.isPending} onClick={() => updateCrawlSettings.mutate({ sourceId: source.id, settings: { crawl_mode: 'site_catalog', crawl_page_limit: source.crawl_page_limit ?? 1000, render_mode: 'http_only', resource_hosts: source.resource_hosts ?? [], schedule_enabled: !(source.schedule_enabled ?? true) } })}>{source.schedule_enabled === false ? 'Bật lịch' : 'Tắt lịch'}</Button> : null}
                        {source.source_type !== 'website' && canManageMarket ? <Button size="sm" variant="ghost" onClick={() => { setManualSourceId(source.id); setManualResult(null); }}>Nhập dữ liệu</Button> : null}
                        {canManageMarket ? <Button size="sm" variant="ghost" loading={deleteSource.isPending} onClick={() => deleteSource.mutate(source.id)}>Xoá link</Button> : null}
                      </div>
                    </div>
                    {isCompetitor && lastSourceCrawl?.sourceId === source.id ? (
                      <p role="status" className="mt-3 rounded-md bg-sky-50 px-3 py-2 text-xs text-sky-900">
                        Job {sourceJobQuery.data?.status ?? 'queued'} · <Link className="font-medium underline" href={'/w/' + workspaceId + '/jobs/' + lastSourceCrawl.jobId}>Theo dõi tiến độ</Link>
                        {sourceJobQuery.data?.result?.analysis_status === 'not_run_no_new_evidence' ? ' · không có bằng chứng mới nên AI chưa chạy' : ''}
                      </p>
                    ) : null}
                    {isCompetitor && crawlCompetitorNow.error ? <p role="alert" className="mt-2 text-xs text-rose-800">{readableError(crawlCompetitorNow.error, 'Không tạo được lượt crawl.')}</p> : null}
                    {isCompetitor && updateCollectionSettings.error ? <p role="alert" className="mt-2 text-xs text-rose-800">{readableError(updateCollectionSettings.error, 'Không cập nhật được cấu hình thu thập.')}</p> : null}
                    {isCompetitor && expandedCompetitorId === source.id ? (
                      <div className="mt-4 space-y-4 border-t border-slate-200 pt-4">
                        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
                          <Badge>{source.collection_mode === 'public_web' ? 'facebook-cli · Tier 0' : 'Collector: ' + (source.collection_mode ?? 'legacy')}</Badge>
                          <Badge>Giới hạn: {source.collection_post_limit ?? 50} bài/lượt</Badge>
                          <Badge>Người theo dõi: {competitorAudience?.followers == null ? 'chưa công bố' : new Intl.NumberFormat('vi-VN').format(competitorAudience.followers)}</Badge>
                          {competitorAudience?.followers_observed_at ? <span>Quan sát {formatDateTime(competitorAudience.followers_observed_at)}</span> : null}
                        </div>
                        {competitorPostsQuery.isLoading ? <LoadingBlock label="Đang tải bài viết đã lưu…" /> : null}
                        {competitorPostsQuery.error ? <ErrorPanel message={readableError(competitorPostsQuery.error, 'Không tải được bài viết đối thủ.')} retryable onRetry={() => void competitorPostsQuery.refetch()} /> : null}
                        {competitorPosts.length ? (
                          <div className="space-y-3">
                            {competitorPosts.map((post) => (
                              <article key={post.id} className="rounded-lg bg-slate-50 p-3">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <a href={post.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-sky-800 underline">{post.title || 'Bài viết Fanpage'}</a>
                                  <span className="text-xs text-slate-500">{post.published_at ? formatDateTime(post.published_at) : 'Ngày đăng chưa công bố'}</span>
                                </div>
                                <p className="mt-2 whitespace-pre-line text-sm text-slate-700">{post.text}{post.content_truncated ? ' … [nội dung đã cắt ở giới hạn lưu]' : ''}</p>
                                <p className="mt-2 text-xs text-slate-500">{formatMetrics(post.metrics) || 'Chưa công bố chỉ số tương tác'}{post.observed_at ? ' · đọc lúc ' + formatDateTime(post.observed_at) : ''}</p>
                                {Object.entries(post.metric_provenance).some(([, value]) => value.raw) ? <p className="mt-1 text-xs text-slate-500">Giá trị hiển thị gốc: {Object.entries(post.metric_provenance).filter(([, value]) => value.raw).map(([key, value]) => (MARKET_METRIC_LABELS[key] ?? key) + ': ' + value.raw).join(' · ')}</p> : null}
                              </article>
                            ))}
                            {competitorPostsQuery.hasNextPage ? <Button size="sm" variant="secondary" loading={competitorPostsQuery.isFetchingNextPage} onClick={() => void competitorPostsQuery.fetchNextPage()}>Tải thêm bài viết</Button> : null}
                          </div>
                        ) : null}
                        {!competitorPostsQuery.isLoading && !competitorPostsQuery.error && competitorPosts.length === 0 ? <p className="text-sm text-slate-600">Chưa có bài viết lưu được. facebook-cli chạy Tier 0, không đăng nhập; kết quả có thể chỉ gồm một phần bài viết công khai mà Facebook trả về.</p> : null}
                        <div>
                          <h4 className="text-sm font-medium text-slate-800">Lịch sử crawl</h4>
                          {competitorRunsQuery.isLoading ? <p className="mt-2 text-xs text-slate-500">Đang tải lịch sử…</p> : null}
                          {competitorRunsQuery.data?.length ? <ul className="mt-2 space-y-2">{competitorRunsQuery.data.map((run) => <li key={run.id} className="rounded-md bg-slate-50 p-2 text-xs text-slate-600"><div className="flex flex-wrap items-center gap-2"><StatusBadge label={SOURCE_STATUS[run.status]?.label ?? run.status} tone={SOURCE_STATUS[run.status]?.tone ?? 'neutral'} />{run.collector}{run.engine ? ' · ' + run.engine : ''}{run.engine_version ? ' ' + run.engine_version : ''}{run.access_tier === 0 ? ' · Tier 0, không đăng nhập' : ''} · {formatDateTime(run.created_at)} · {String(run.counters.items_saved ?? 0)} bài lưu</div>{run.blocked_reason ? <p className="mt-1">Lý do: {run.blocked_reason}</p> : null}{typeof run.coverage.coverage_reason === 'string' ? <p className="mt-1">Độ phủ: {run.coverage.coverage_reason}</p> : null}{Array.isArray(run.coverage.missing_fields) && run.coverage.missing_fields.length ? <p className="mt-1">Chưa có trường: {(run.coverage.missing_fields as string[]).join(', ')}</p> : null}{run.coverage.metrics_unavailable ? <p className="mt-1">Thiếu chỉ số: {String((run.coverage.metrics_unavailable as string[]).join(', '))}</p> : null}</li>)}</ul> : null}
                          {!competitorRunsQuery.isLoading && !competitorRunsQuery.data?.length ? <p className="mt-2 text-xs text-slate-500">Chưa có lượt crawl nào.</p> : null}
                        </div>
                      </div>
                    ) : null}
                  </div>
                );
              })}
              {sources.length === 0 ? <EmptyState title="Chưa lưu link nào" description="Thêm website, Fanpage của bạn hoặc link đối thủ/nhóm Facebook để bắt đầu." /> : null}
              {updateCrawlSettings.error ? <p role="alert" className="text-sm text-rose-800">{readableError(updateCrawlSettings.error, 'Không cập nhật được cấu hình website.')}</p> : null}
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

          <Card title="Dữ liệu website đã trích xuất" description="Giá, gói bán và số liệu chỉ hiện khi website công khai dữ liệu có bằng chứng. Giá không rõ được để trống; số tự công bố không được coi là số liệu đã kiểm toán.">
            <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Loại dữ liệu website">
              {([['product', 'Sản phẩm & giá'], ['article', 'Bài viết'], ['business_info', 'Thông tin website']] as const).map(([value, label]) => (
                <Button key={value} size="sm" variant={webKind === value ? 'primary' : 'secondary'} onClick={() => setWebKind(value)}>{label}</Button>
              ))}
            </div>
            {webItemsQuery.isLoading ? <LoadingBlock label="Đang tải dữ liệu website…" /> : null}
            {webItemsQuery.error ? <ErrorPanel message={readableError(webItemsQuery.error, 'Không tải được dữ liệu website.')} retryable onRetry={() => void webItemsQuery.refetch()} /> : null}
            {webItemsQuery.data?.items.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[720px] border-collapse text-left text-sm">
                  <thead><tr className="border-b border-slate-200 text-xs text-slate-500"><th className="py-2 pr-4">Tên</th><th className="py-2 pr-4">Giá / nội dung</th><th className="py-2 pr-4">Số liệu công khai</th><th className="py-2">Quan sát</th></tr></thead>
                  <tbody>{webItemsQuery.data.items.map((item) => {
                    const data = item.data ?? {};
                    const sold = typeof data.sold_count_raw === 'string' ? data.sold_count_raw : (typeof data.sold_count === 'number' ? String(data.sold_count) : null);
                    const summary = typeof data.description === 'string' ? data.description : (typeof data.content === 'string' ? data.content : '');
                    return <tr key={item.id} className="border-b border-slate-100 align-top last:border-0">
                      <td className="py-3 pr-4"><a className="font-medium text-sky-800 underline" href={item.url} target="_blank" rel="noopener noreferrer">{item.title || item.url}</a><p className="mt-1 text-xs text-slate-500">{item.kind === 'product' ? 'Sản phẩm / gói dịch vụ' : item.kind === 'article' ? 'Bài viết' : 'Thông tin doanh nghiệp'}</p></td>
                      <td className="max-w-md py-3 pr-4 text-slate-700">
                        {item.offers.length ? <ul className="space-y-1">{item.offers.map((offer) => <li key={offer.id}>{offer.price_kind === 'contact' ? 'Liên hệ báo giá' : offer.price ? `${offer.price} ${offer.currency ?? ''}`.trim() : offer.low_price || offer.high_price ? `${offer.low_price ?? '…'}–${offer.high_price ?? '…'} ${offer.currency ?? ''}`.trim() : 'Chưa công bố giá'}{offer.original_price ? ` · Giá gốc ${offer.original_price} ${offer.currency ?? ''}` : ''}{offer.billing_unit ? ` · ${offer.billing_unit}` : ''}{offer.availability ? ` · ${offer.availability.split('/').pop()}` : ''}</li>)}</ul> : <p className="line-clamp-3 text-xs">{summary || 'Không có nội dung tóm tắt.'}</p>}
                      </td>
                      <td className="py-3 pr-4 text-slate-700">{sold ? `Đã bán: ${sold}` : 'Chưa công bố số đã bán'}{typeof data.review_count_raw === 'string' ? <p className="mt-1 text-xs text-slate-500">Đánh giá: {data.review_count_raw}</p> : null}</td>
                      <td className="whitespace-nowrap py-3 text-xs text-slate-500">{item.observed_at ? formatDateTime(item.observed_at) : '—'}</td>
                    </tr>;
                  })}</tbody>
                </table>
                <p className="mt-3 text-xs text-slate-500">Đang hiển thị tối đa 100 mục theo lần quét mới nhất. Để xem bằng chứng, mở liên kết nguồn ở cột Tên.</p>
              </div>
            ) : null}
            {!webItemsQuery.isLoading && !webItemsQuery.error && !webItemsQuery.data?.items.length ? <EmptyState title="Chưa có dữ liệu website" description="Thêm website vào nhóm, chuyển nguồn sang chế độ sản phẩm & nội dung rồi bấm Crawl ngay. Nguồn cũ giữ chế độ legacy cho đến khi được chuyển rõ ràng." /> : null}
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
                  <div className="mt-4"><h4 className="text-sm font-semibold text-slate-900">Xu hướng ghi nhận</h4><ul className="mt-2 space-y-2">{report.report.trends?.map((trend, index) => <li key={trend.title + index} className="rounded-lg bg-slate-50 p-3"><p className="text-sm font-medium text-slate-900">{trend.title} <span className="text-xs font-normal text-slate-500">· độ tin cậy {Math.round(trend.confidence * 100)}%</span></p><p className="mt-1 text-sm text-slate-700">{trend.explanation}</p><p className="mt-1 text-xs text-slate-500">{trend.evidence_ids.length} nguồn văn bản · {trend.web_snapshot_ids?.length ?? 0} snapshot sản phẩm/bài viết</p></li>)}</ul></div>
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
