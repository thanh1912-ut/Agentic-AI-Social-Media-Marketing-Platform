'use client';

import Link from 'next/link';
import Image from 'next/image';
import { useParams, usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useSession } from '@/components/session-gate';
import { Icon } from '@/components/icon';
import { Badge, Button, Card, EmptyState, ErrorPanel, LoadingBlock, PageHeader, PermissionNotice, StatusBadge } from '@/components/ui';
import { ApiError, marketResearchApi, marketResearchKeys, useMocks } from '@/lib/api';
import type { ResearchSourceType } from '@/lib/api/market-research';
import { useJob } from '@/lib/hooks';
import { UrlTabs, useUrlTab } from '@/components/url-tabs';
import { formatDateTime } from '@/lib/format';

const MARKET_TABS = ['pages', 'sources', 'reports'] as const;
const MARKET_TAB_LABELS = { pages: 'Doanh nghiệp', sources: 'Thu thập', reports: 'Phân tích & hướng viết' } as const;
const MARKET_HASHES = {
  '#fanpage-connections': 'pages',
  '#market-sources': 'sources',
  '#website-data': 'sources',
  '#market-reports': 'reports',
} as const;

const SOURCE_LABELS: Record<ResearchSourceType, string> = {
  website: 'Website công khai',
  owned_facebook_page: 'Fanpage của workspace',
  competitor_facebook_page: 'Fanpage công khai · đối thủ hoặc tin tức',
  facebook_group: 'Nhóm Facebook công khai · Tier 0 chỉ hỗ trợ thông tin nhóm',
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

function safeExternalHttpUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
    if (['localhost', '127.0.0.1', '::1'].includes(url.hostname.toLowerCase())) return null;
    return url.toString();
  } catch {
    return null;
  }
}

const ATTACHMENT_KIND_LABELS = { image: 'Ảnh', video: 'Video', link: 'Liên kết', other: 'Tệp đính kèm', unknown: 'Media chưa rõ loại' } as const;

function formatUsdMicro(value: number): string {
  return new Intl.NumberFormat('vi-VN', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 4,
  }).format(value / 1_000_000);
}

const SOURCE_STATUS: Record<string, { label: string; tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger' }> = {
  active: { label: 'Tự động thu thập', tone: 'success' },
  manual_import_only: { label: 'Cần nhập dữ liệu thủ công', tone: 'info' },
  unsupported_tier0: { label: 'Tier 0 không đọc nội dung nhóm', tone: 'warning' },
  group_not_public: { label: 'Không xác minh được nhóm công khai', tone: 'warning' },
  needs_access: { label: 'Cần kết nối lại / thiếu quyền', tone: 'warning' },
  needs_privacy_policy: { label: 'Tạm dừng · thiếu ghi nhận phạm vi dữ liệu', tone: 'warning' },
  privacy_policy_required: { label: 'Tạm dừng · cần ghi nhận mục đích xử lý', tone: 'warning' },
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
  const pathname = usePathname();
  const workspaceId = params?.workspaceId ?? '';
  const [marketTab, setMarketTab] = useUrlTab('tab', 'pages', MARKET_TABS, MARKET_HASHES);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { workspaces } = useSession();
  const mocksOn = useMocks();
  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const canManageMarket = Boolean(workspace?.permissions.includes('market:manage'));
  const canManageConnections = Boolean(workspace?.permissions.includes('connection:manage'));
  const [sourceType, setSourceType] = useState<ResearchSourceType>('website');
  const [lastCrawlJob, setLastCrawlJob] = useState<{ jobId: string; groupId: string } | null>(null);
  const [lastSourceCrawl, setLastSourceCrawl] = useState<{ jobId: string; sourceId: string } | null>(null);
  const [expandedCompetitorId, setExpandedCompetitorId] = useState('');
  const [expandedPrivacyPolicyId, setExpandedPrivacyPolicyId] = useState('');
  const [draftCampaign, setDraftCampaign] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [webKind, setWebKind] = useState('product');

  useEffect(() => {
    if (!pathname.endsWith('/fanpages')) return;
    router.replace(`${pathname.slice(0, -'/fanpages'.length)}/research${window.location.search}${window.location.hash}`);
  }, [pathname, router]);

  const groupsQuery = useQuery({
    queryKey: marketResearchKeys.groups(workspaceId),
    queryFn: () => marketResearchApi.groups(workspaceId),
    enabled: workspaceId !== '',
  });
  const groups = groupsQuery.data ?? [];
  const selectedGroup = groups.find((group) => group.name === 'Nghiên cứu') ?? groups[0] ?? null;
  const activeGroupId = selectedGroup?.id ?? '';

  const pagesQuery = useQuery({
    queryKey: marketResearchKeys.pages(workspaceId, 'all'),
    queryFn: () => marketResearchApi.allPages(workspaceId),
    enabled: workspaceId !== '',
  });
  const sourcesQuery = useQuery({
    queryKey: marketResearchKeys.sources(workspaceId),
    queryFn: () => marketResearchApi.sources(workspaceId),
    enabled: workspaceId !== '',
  });
  const reportsQuery = useQuery({
    queryKey: marketResearchKeys.reports(workspaceId, 'all'),
    queryFn: () => marketResearchApi.allReports(workspaceId),
    enabled: workspaceId !== '',
    refetchInterval: (query) => query.state.fetchStatus === 'fetching' ? false : 15_000,
  });
  const aiBudgetQuery = useQuery({
    queryKey: marketResearchKeys.aiBudget(workspaceId),
    queryFn: () => marketResearchApi.aiBudget(workspaceId),
    enabled: workspaceId !== '',
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
  const expandedFacebookSource = sourcesQuery.data?.find(
    (source) => source.id === expandedCompetitorId
      && (source.source_type === 'competitor_facebook_page' || source.source_type === 'facebook_group'),
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
    enabled: workspaceId !== '' && expandedFacebookSource !== undefined,
    refetchInterval: (query) => query.state.fetchStatus === 'fetching' ? false : 15_000,
  });
  const privacyPolicyQuery = useQuery({
    queryKey: marketResearchKeys.privacyPolicy(workspaceId, expandedPrivacyPolicyId),
    queryFn: () => marketResearchApi.privacyPolicy(workspaceId, expandedPrivacyPolicyId),
    enabled: workspaceId !== '' && expandedPrivacyPolicyId !== '',
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
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.pages(workspaceId, 'all') }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.sources(workspaceId) }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.reports(workspaceId, 'all') }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.webItems(workspaceId, groupId, 'product') }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.webItems(workspaceId, groupId, 'article') }),
      queryClient.invalidateQueries({ queryKey: marketResearchKeys.webItems(workspaceId, groupId, 'business_info') }),
    ]);
  }, [activeGroupId, queryClient, workspaceId]);

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
  const savePrivacyPolicy = useMutation({
    mutationFn: ({ sourceId, body }: { sourceId: string; body: {
      purpose: string; processing_basis_reference: string; policy_version: string; requested_retention_days: number;
    } }) => marketResearchApi.savePrivacyPolicy(workspaceId, sourceId, body),
    onSuccess: async (policy, variables) => {
      queryClient.setQueryData(marketResearchKeys.privacyPolicy(workspaceId, variables.sourceId), policy);
      await queryClient.invalidateQueries({ queryKey: marketResearchKeys.privacyPolicy(workspaceId, variables.sourceId) });
    },
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
      await queryClient.invalidateQueries({ queryKey: marketResearchKeys.competitorPosts(workspaceId, sourceId) });
      await queryClient.invalidateQueries({ queryKey: marketResearchKeys.competitorRuns(workspaceId, sourceId) });
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

  if (groupsQuery.isLoading) return <LoadingBlock label="Đang tải dữ liệu nghiên cứu…" />;
  if (groupsQuery.isError) {
    return <ErrorPanel message={readableError(groupsQuery.error, 'Không tải được cấu hình thị trường.')} code={groupsQuery.error instanceof ApiError ? groupsQuery.error.code : undefined} retryable onRetry={() => void groupsQuery.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Doanh nghiệp & thị trường"
        title="Nghiên cứu"
        description="Thu thập nguồn, xem bằng chứng và chọn hướng nội dung cho doanh nghiệp."
        actions={activeGroupId && canManageMarket ? <Button loading={crawlNow.isPending} onClick={() => crawlNow.mutate(activeGroupId)}><Icon name="globe" size={17} /> Crawl ngay</Button> : undefined}
      />

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

      {selectedGroup ? <p className="text-sm text-slate-500">Nguồn nghiên cứu được lưu trong không gian doanh nghiệp. Bạn không cần tạo hay chọn nhóm để thu thập.</p> : <EmptyState title="Chưa có cấu hình nghiên cứu" description="Kết nối Fanpage doanh nghiệp để khởi tạo không gian nghiên cứu." />}

      {activeGroupId ? (
        <>
          <UrlTabs label="Fanpage và thị trường" values={MARKET_TABS} labels={MARKET_TAB_LABELS}
            active={marketTab} onChange={setMarketTab} idPrefix="market" />
          {marketTab === "pages" ? (
        <div id="market-panel" role="tabpanel" aria-labelledby="market-tab-pages" className="route-tab-panel">
          <Card title="Fanpage doanh nghiệp" description="Page đã xác minh là danh tính của không gian làm việc. Quản lý kết nối và thay token trong cài đặt doanh nghiệp.">
            {workspace.page_id ? <div className="flex items-center gap-4">
                  {workspace.page_avatar_url ? <Image src={workspace.page_avatar_url} alt="" width={56} height={56} unoptimized referrerPolicy="no-referrer" className="h-14 w-14 rounded-full object-cover" /> : <span className="grid h-14 w-14 place-items-center rounded-full bg-slate-100 text-xl font-semibold">{workspace.name.slice(0, 1).toUpperCase()}</span>}
              <div><p className="font-semibold text-slate-950">{workspace.name}</p><p className="mt-1 text-sm text-slate-600">Page ID {workspace.page_id} · {workspace.page_connection_state === 'active' ? 'Đã xác minh' : 'Cần kết nối lại'}</p></div>
            </div> : <EmptyState title="Fanpage chưa được xác minh" description="Owner cần kết nối Page trong lúc kích hoạt doanh nghiệp trước khi dùng các tác vụ Agentic." />}
            <div className="mt-4">{pagesQuery.isLoading ? <LoadingBlock label="Đang tải trạng thái kết nối…" /> : pagesQuery.error ? <ErrorPanel message={readableError(pagesQuery.error, 'Không tải được trạng thái Page.')} retryable onRetry={() => void pagesQuery.refetch()} /> : pages.map((page) => <p key={page.id} className="text-sm text-slate-600">Kết nối Meta: {page.status === 'verified' ? 'đã xác minh' : 'cần kết nối lại'} · kiểm tra {page.verified_at ? formatDateTime(page.verified_at) : 'chưa có'}</p>)}</div>
            <Link href={`/w/${workspaceId}/settings`} className="mt-5 inline-flex text-sm font-medium text-pink-800 underline underline-offset-4">Mở cài đặt doanh nghiệp</Link>
          </Card>
        </div>
      ) : null}
          {marketTab === "sources" ? (
        <div id="market-panel" role="tabpanel" aria-labelledby="market-tab-sources" className="route-tab-panel">
<section id="market-sources" className="scroll-mt-24">
          <Card
            title="Nguồn thu thập"
            description="Lưu link một lần, thu thập ngay hoặc cập nhật mỗi 12 giờ. Facebook công khai có thể chỉ trả một phần dữ liệu."
          >
            {canManageMarket ? (
              <form className="grid gap-4 rounded-xl bg-slate-50/70 p-4 sm:grid-cols-2" onSubmit={submitSource}>
                <label className="text-sm text-slate-700">Loại nguồn<select value={sourceType} onChange={(event) => setSourceType(event.currentTarget.value as ResearchSourceType)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2">{Object.entries(SOURCE_LABELS).filter(([value]) => value !== 'owned_facebook_page').map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label className="text-sm text-slate-700">Tên nguồn<input name="name" required maxLength={200} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="Tên website/Page/nhóm" /></label>
                <label className="text-sm text-slate-700 sm:col-span-2">Link website hoặc Facebook<input name="url" required type="url" maxLength={2048} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" placeholder="https://…" /></label>
                {sourceType === 'competitor_facebook_page' ? <p className="text-xs text-slate-500 sm:col-span-2">Nguồn mới dùng facebook-cli Tier 0, không cần Page Access Token và không đăng nhập Facebook. Facebook có thể trả ít bài, yêu cầu đăng nhập hoặc từ chối truy cập; giao diện sẽ giữ đúng trạng thái đó.</p> : null}
                {sourceType === 'facebook_group' ? <p className="text-xs text-amber-800 sm:col-span-2">facebook-cli Tier 0 chỉ đọc metadata nhóm mà Facebook xác nhận công khai. Lượt chạy không gọi feed thảo luận; hệ thống không đăng nhập hoặc tham gia nhóm, và sẽ ghi coverage một phần.</p> : null}
                {sourceType === 'competitor_facebook_page' ? <label className="text-sm text-slate-700 sm:col-span-2">Tên đối thủ<input name="competitor_name" maxLength={200} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2" /></label> : null}
                <div className="sm:col-span-2"><Button type="submit" loading={createSource.isPending} disabled={!canManageMarket} disabledReason="Vai trò của bạn chưa có quyền quản lý nguồn nghiên cứu.">Lưu link nguồn</Button></div>
                {createSource.error ? <p role="alert" className="text-sm text-rose-800 sm:col-span-2">{readableError(createSource.error, 'Không lưu được nguồn.')}</p> : null}
              </form>
            ) : <PermissionNotice message="Bạn có thể xem báo cáo, nhưng cần quyền market:manage để thêm hoặc xoá nguồn." requiredPermission="market:manage" />}
            <div className="mt-5 space-y-2">
              {sources.map((source) => {
                const isCompetitor = source.source_type === 'competitor_facebook_page';
                const isGroup = source.source_type === 'facebook_group';
                const isOwnedPage = source.source_type === 'owned_facebook_page';
                const isPublicFacebook = isCompetitor || isGroup;
                const statusKey = isPublicFacebook || isOwnedPage ? (source.collection_status || source.status) : source.status;
                const status = SOURCE_STATUS[statusKey] ?? SOURCE_STATUS[source.status] ?? { label: statusKey, tone: 'neutral' as const };
                const schedulePaused = source.status === 'needs_privacy_policy' || ['login_required', 'access_denied', 'challenge', 'challenge_required', 'group_not_public', 'page_needs_reconnect', 'page_token_unavailable', 'page_token_expired', 'page_permission_missing', 'privacy_policy_required'].includes(source.collection_status ?? '');
                return (
                  <div key={source.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2"><p className="font-medium text-slate-900">{source.name}</p><StatusBadge label={status.label} tone={status.tone} /></div>
                        <p className="mt-1 break-all text-xs text-slate-600">{source.url}</p>
                        <p className="mt-1 text-xs text-slate-500">{SOURCE_LABELS[source.source_type]}{source.last_crawled_at ? ' · lần đọc gần nhất ' + formatDateTime(source.last_crawled_at) : ''}</p>
                        {isPublicFacebook || isOwnedPage ? <p className="mt-1 text-xs text-slate-500">Engine: {isOwnedPage ? 'Meta API · Page đã kết nối' : source.collection_mode === 'public_web' ? 'facebook-cli · Tier 0' : source.collection_mode ?? 'chưa chọn'} · Lần thử: {source.last_collection_attempt_at ? formatDateTime(source.last_collection_attempt_at) : 'chưa có'} · Lần đọc thành công: {source.last_collection_success_at ? formatDateTime(source.last_collection_success_at) : 'chưa có'} · Lịch: {source.schedule_enabled ? schedulePaused ? source.status === 'needs_privacy_policy' || source.collection_status === 'privacy_policy_required' ? 'đang tạm dừng đến khi ghi nhận phạm vi xử lý' : 'đang tạm dừng sau khi Facebook từ chối/yêu cầu đăng nhập' : '12 giờ' : 'đã tắt'}</p> : null}
                        {source.error?.message ? <p className="mt-1 text-xs text-rose-800">{source.error.message}</p> : null}
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {!isCompetitor && canManageMarket ? <Button size="sm" variant="secondary" loading={crawlCompetitorNow.isPending && crawlCompetitorNow.variables === source.id} onClick={() => crawlCompetitorNow.mutate(source.id)}>Crawl ngay</Button> : null}
                        {isOwnedPage && canManageMarket ? <Button size="sm" variant="secondary" loading={updateCollectionSettings.isPending} onClick={() => updateCollectionSettings.mutate({ sourceId: source.id, settings: { collector: 'meta_api', schedule_enabled: !(source.schedule_enabled ?? false), post_limit: source.collection_post_limit ?? 100 } })}>{source.schedule_enabled ? 'Tắt lịch 12 giờ' : 'Bật lịch 12 giờ'}</Button> : null}
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
                        {isGroup && canManageMarket ? <>
                          <Button size="sm" variant="secondary" loading={updateCollectionSettings.isPending} onClick={() => updateCollectionSettings.mutate({ sourceId: source.id, settings: { collector: 'public_web', schedule_enabled: !(source.schedule_enabled ?? true), post_limit: source.collection_post_limit ?? 50 } })}>{source.schedule_enabled === false ? 'Bật lịch 12 giờ' : 'Tắt lịch'}</Button>
                          <Button size="sm" variant="secondary" onClick={() => setExpandedCompetitorId(expandedCompetitorId === source.id ? '' : source.id)}>{expandedCompetitorId === source.id ? 'Ẩn metadata & lịch sử' : 'Metadata & lịch sử'}</Button>
                        </> : null}
                        {source.source_type === 'website' && canManageMarket && (source.crawl_mode ?? 'legacy') === 'legacy' ? <Button size="sm" variant="secondary" loading={updateCrawlSettings.isPending} onClick={() => updateCrawlSettings.mutate({ sourceId: source.id, settings: { crawl_mode: 'site_catalog', crawl_page_limit: 1000, render_mode: 'http_only', resource_hosts: [], schedule_enabled: true } })}>Bật sản phẩm & bài viết</Button> : null}
                        {source.source_type === 'website' && canManageMarket && source.crawl_mode === 'site_catalog' ? <Button size="sm" variant="secondary" loading={updateCrawlSettings.isPending} onClick={() => updateCrawlSettings.mutate({ sourceId: source.id, settings: { crawl_mode: 'site_catalog', crawl_page_limit: source.crawl_page_limit ?? 1000, render_mode: 'http_only', resource_hosts: source.resource_hosts ?? [], schedule_enabled: !(source.schedule_enabled ?? true) } })}>{source.schedule_enabled === false ? 'Bật lịch' : 'Tắt lịch'}</Button> : null}
                        {canManageConnections ? <Button size="sm" variant="secondary" onClick={() => setExpandedPrivacyPolicyId(expandedPrivacyPolicyId === source.id ? '' : source.id)}>{expandedPrivacyPolicyId === source.id ? 'Ẩn chính sách dữ liệu' : 'Chính sách dữ liệu'}</Button> : null}
                        {canManageMarket ? <Button size="sm" variant="ghost" loading={deleteSource.isPending} onClick={() => deleteSource.mutate(source.id)}>Xoá link</Button> : null}
                      </div>
                    </div>
                    {expandedPrivacyPolicyId === source.id ? (
                      <div className="mt-4 border-t border-slate-200 pt-4">
                        {privacyPolicyQuery.isLoading ? <LoadingBlock label="Đang tải ghi nhận chính sách…" /> : null}
                        {privacyPolicyQuery.error ? <ErrorPanel message={readableError(privacyPolicyQuery.error, 'Không tải được ghi nhận chính sách.')} retryable onRetry={() => void privacyPolicyQuery.refetch()} /> : null}
                        {privacyPolicyQuery.data ? (
                          <form className="grid gap-3 rounded-lg bg-slate-50 p-4" onSubmit={(event) => {
                            event.preventDefault();
                            const values = new FormData(event.currentTarget);
                            savePrivacyPolicy.mutate({
                              sourceId: source.id,
                              body: {
                                purpose: String(values.get('purpose') ?? ''),
                                processing_basis_reference: String(values.get('processing_basis_reference') ?? ''),
                                policy_version: String(values.get('policy_version') ?? ''),
                                requested_retention_days: Number(values.get('requested_retention_days') ?? 90),
                              },
                            });
                          }}>
                            <div>
                              <h3 className="text-sm font-semibold text-slate-950">Ghi nhận phạm vi xử lý cho nguồn</h3>
                              <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-600">Ghi nhận mục đích, tài liệu tham chiếu và thời hạn dự kiến. Nguồn Facebook tạm dừng thu thập đến khi có các thông tin này; hệ thống không xác minh tài liệu và không coi bản ghi là căn cứ pháp lý hoặc sự đồng ý.</p>
                              {privacyPolicyQuery.data.configured ? <p className="mt-1 text-xs text-slate-500">Bản ghi gần nhất: revision {privacyPolicyQuery.data.revision_no} · {privacyPolicyQuery.data.policy_version} · lưu {privacyPolicyQuery.data.configured_at ? formatDateTime(privacyPolicyQuery.data.configured_at) : 'chưa rõ thời điểm'} · {privacyPolicyQuery.data.collection_ready ? 'đủ trường cấu hình để tiếp tục' : 'thiếu trường bắt buộc'} · căn cứ pháp lý đã xác minh: không</p> : <p className="mt-1 text-xs text-slate-500">Chưa có bản ghi cho nguồn này; thu thập Facebook đang tạm dừng.</p>}
                            </div>
                            <label className="grid gap-1 text-sm text-slate-700">Mục đích xử lý<textarea name="purpose" required minLength={10} maxLength={4000} rows={3} defaultValue={privacyPolicyQuery.data.purpose ?? ''} className="rounded-md border border-slate-300 bg-white px-3 py-2" /></label>
                            <label className="grid gap-1 text-sm text-slate-700">Mã/tài liệu tham chiếu căn cứ xử lý<textarea name="processing_basis_reference" required minLength={5} maxLength={4000} rows={2} defaultValue={privacyPolicyQuery.data.processing_basis_reference ?? ''} className="rounded-md border border-slate-300 bg-white px-3 py-2" placeholder="Ghi mã hồ sơ/chính sách nội bộ đã được tổ chức rà soát" /></label>
                            <div className="grid gap-3 sm:grid-cols-2">
                              <label className="grid gap-1 text-sm text-slate-700">Phiên bản chính sách<input name="policy_version" required maxLength={100} defaultValue={privacyPolicyQuery.data.policy_version ?? ''} className="rounded-md border border-slate-300 bg-white px-3 py-2" placeholder="privacy-policy-v1" /></label>
                              <label className="grid gap-1 text-sm text-slate-700">Thời hạn lưu giữ dự kiến (ngày)<input name="requested_retention_days" type="number" required min={1} max={365} defaultValue={privacyPolicyQuery.data.requested_retention_days ?? 90} className="rounded-md border border-slate-300 bg-white px-3 py-2" /></label>
                            </div>
                            <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950">
                              Trạng thái hiện tại: bình luận văn bản vẫn <strong>privacy_hold</strong>; thời hạn lưu giữ ở đây mới được ghi nhận, chưa được áp dụng tự động. Chưa có quy trình xóa lan truyền đầy đủ; không gửi bình luận/media cá nhân sang AI dựa trên biểu mẫu này.
                            </div>
                            {savePrivacyPolicy.error ? <p role="alert" className="text-sm text-rose-800">{readableError(savePrivacyPolicy.error, 'Không lưu được ghi nhận chính sách.')}</p> : null}
                            {savePrivacyPolicy.data?.source_id === source.id ? <p role="status" className="text-sm text-emerald-800">Đã lưu bản ghi revision {savePrivacyPolicy.data.revision_no} cho phiên bản {savePrivacyPolicy.data.policy_version}. Bình luận vẫn được giữ ở trạng thái privacy_hold.</p> : null}
                            <div><Button type="submit" size="sm" loading={savePrivacyPolicy.isPending} disabled={!canManageConnections} disabledReason="Chỉ Owner được ghi nhận chính sách dữ liệu.">Lưu ghi nhận</Button></div>
                          </form>
                        ) : null}
                      </div>
                    ) : null}
                    {lastSourceCrawl?.sourceId === source.id ? (
                      <p role="status" className="mt-3 rounded-md bg-sky-50 px-3 py-2 text-xs text-sky-900">
                        Job {sourceJobQuery.data?.status ?? 'queued'} · <Link className="font-medium underline" href={'/w/' + workspaceId + '/jobs/' + lastSourceCrawl.jobId}>Theo dõi tiến độ</Link>
                        {sourceJobQuery.data?.result?.analysis_status === 'not_run_no_new_evidence' ? ' · không có bằng chứng mới nên AI chưa chạy' : ''}
                      </p>
                    ) : null}
                    {lastSourceCrawl?.sourceId === source.id && crawlCompetitorNow.error ? <p role="alert" className="mt-2 text-xs text-rose-800">{readableError(crawlCompetitorNow.error, 'Không tạo được lượt crawl.')}</p> : null}
                    {(isPublicFacebook || isOwnedPage) && updateCollectionSettings.error ? <p role="alert" className="mt-2 text-xs text-rose-800">{readableError(updateCollectionSettings.error, 'Không cập nhật được cấu hình thu thập.')}</p> : null}
                    {isPublicFacebook && expandedCompetitorId === source.id ? (
                      <div className="mt-4 space-y-4 border-t border-slate-200 pt-4">
                        <div className="flex flex-wrap gap-2 text-xs text-slate-600">
                          <Badge>{source.collection_mode === 'public_web' ? 'facebook-cli · Tier 0' : 'Collector: ' + (source.collection_mode ?? 'legacy')}</Badge>
                          {isCompetitor ? <Badge>Giới hạn: {source.collection_post_limit ?? 50} bài/lượt</Badge> : null}
                          {isCompetitor ? <Badge>Người theo dõi: {competitorAudience?.followers == null ? 'chưa công bố' : new Intl.NumberFormat('vi-VN').format(competitorAudience.followers)}</Badge> : null}
                          {isCompetitor && competitorAudience?.followers_observed_at ? <span>Quan sát {formatDateTime(competitorAudience.followers_observed_at)}</span> : null}
                        </div>
                        {isGroup ? <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm leading-6 text-amber-950"><strong>Chế độ Tier 0 chỉ đọc metadata công khai của nhóm.</strong> Bản chạy này không gọi GroupFeed, không lấy bài thảo luận hoặc bình luận; history_complete luôn false. Nếu cần đọc thảo luận, Tier 0 hiện không đáp ứng.</div> : null}
                        {isCompetitor && competitorPostsQuery.isLoading ? <LoadingBlock label="Đang tải bài viết đã lưu…" /> : null}
                        {isCompetitor && competitorPostsQuery.error ? <ErrorPanel message={readableError(competitorPostsQuery.error, 'Không tải được bài viết đối thủ.')} retryable onRetry={() => void competitorPostsQuery.refetch()} /> : null}
                        {competitorPosts.length ? (
                          <div className="space-y-3">
                            {competitorPosts.map((post) => (
                              <article key={post.id} className="rounded-lg bg-slate-50 p-3">
                                <div className="flex flex-wrap items-start justify-between gap-2">
                                  <a href={post.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-sky-800 underline">{post.title || 'Bài viết Fanpage'}</a>
                                  <span className="text-xs text-slate-500">{post.published_at ? formatDateTime(post.published_at) : 'Ngày đăng chưa công bố'}</span>
                                </div>
                                <p className="mt-2 whitespace-pre-line text-sm text-slate-700">{post.text}{post.content_truncated ? ' … [nội dung đã cắt ở giới hạn lưu]' : ''}</p>
                                {safeExternalHttpUrl(post.link_url) ? <p className="mt-2"><a href={safeExternalHttpUrl(post.link_url)!} target="_blank" rel="noopener noreferrer" className="text-xs font-medium text-sky-800 underline">Mở liên kết trong bài</a></p> : null}
                                {post.attachments?.length ? <div className="mt-2 space-y-1 text-xs text-slate-600">
                                  <p>Đính kèm: {post.attachments.map((item) => ATTACHMENT_KIND_LABELS[item.kind]).join(' · ')}. Nội dung ảnh/video chưa tải hoặc phân tích; đang ở privacy hold.</p>
                                  {post.attachments.some((item) => item.title) ? <p>{post.attachments.filter((item) => item.title).map((item) => item.title).join(' · ')}</p> : null}
                                </div> : post.attachment_metadata_status === 'none_returned' ? <p className="mt-2 text-xs text-slate-500">Meta không trả media đính kèm cho bài này.</p> : post.attachment_metadata_status === 'not_returned' ? <p className="mt-2 text-xs text-slate-500">Chưa có metadata media từ nguồn.</p> : null}
                                <p className="mt-2 text-xs text-slate-500">{formatMetrics(post.metrics) || 'Chưa công bố chỉ số tương tác'}{post.observed_at ? ' · đọc lúc ' + formatDateTime(post.observed_at) : ''}</p>
                                {Object.entries(post.metric_provenance).some(([, value]) => value.raw) ? <p className="mt-1 text-xs text-slate-500">Giá trị hiển thị gốc: {Object.entries(post.metric_provenance).filter(([, value]) => value.raw).map(([key, value]) => (MARKET_METRIC_LABELS[key] ?? key) + ': ' + value.raw).join(' · ')}</p> : null}
                              </article>
                            ))}
                            {competitorPostsQuery.hasNextPage ? <Button size="sm" variant="secondary" loading={competitorPostsQuery.isFetchingNextPage} onClick={() => void competitorPostsQuery.fetchNextPage()}>Tải thêm bài viết</Button> : null}
                          </div>
                        ) : null}
                        {isCompetitor && !competitorPostsQuery.isLoading && !competitorPostsQuery.error && competitorPosts.length === 0 ? <p className="text-sm text-slate-600">Chưa có bài viết lưu được. facebook-cli chạy Tier 0, không đăng nhập; kết quả có thể chỉ gồm một phần bài viết công khai mà Facebook trả về.</p> : null}
                        <div>
                          <h4 className="text-sm font-medium text-slate-800">{isGroup ? 'Lịch sử đọc metadata' : 'Lịch sử crawl'}</h4>
                          {competitorRunsQuery.isLoading ? <p className="mt-2 text-xs text-slate-500">Đang tải lịch sử…</p> : null}
                          {competitorRunsQuery.data?.length ? <ul className="mt-2 space-y-2">{competitorRunsQuery.data.map((run) => <li key={run.id} className="rounded-md bg-slate-50 p-2 text-xs text-slate-600"><div className="flex flex-wrap items-center gap-2"><StatusBadge label={SOURCE_STATUS[run.status]?.label ?? run.status} tone={SOURCE_STATUS[run.status]?.tone ?? 'neutral'} />{run.collector}{run.engine ? ' · ' + run.engine : ''}{run.engine_version ? ' ' + run.engine_version : ''}{run.access_tier === 0 ? ' · Tier 0, không đăng nhập' : ''} · {formatDateTime(run.created_at)}{isGroup ? ' · không có bài thảo luận trong Tier 0' : ' · ' + String(run.counters.items_saved ?? 0) + ' bài lưu'}</div>{isGroup && typeof run.coverage.group_name === 'string' ? <p className="mt-1">Nhóm đã xác minh: {run.coverage.group_name} · {String(run.coverage.group_privacy ?? 'công khai')}</p> : null}{isGroup ? <p className="mt-1">Không gọi endpoint feed; không có bài viết hoặc bình luận được thu thập.</p> : run.privacy_policy_revision_no != null ? <p className="mt-1">Chính sách nguồn: {run.privacy_policy_version ?? 'không ghi nhãn'} · phiên bản {run.privacy_policy_revision_no} · thời hạn yêu cầu {run.privacy_policy_requested_retention_days ?? '—'} ngày; hệ thống chưa thực thi thời hạn này. {run.privacy_policy_ready_for_collection === true ? 'Đủ trường cấu hình để thu thập.' : run.privacy_policy_ready_for_collection === false ? 'Thiếu trường cấu hình.' : 'Lượt cũ chưa ghi trạng thái cấu hình.'} Căn cứ pháp lý không được hệ thống xác minh.</p> : <p className="mt-1">Lượt này chưa ghi nhận phiên bản chính sách nguồn.</p>}{!isGroup ? <p className="mt-1">Bình luận đang ở trạng thái tạm giữ; cấu hình hiện tại chưa cho phép xử lý dữ liệu này.</p> : null}{run.blocked_reason ? <p className="mt-1">Lý do: {run.blocked_reason}</p> : null}{typeof run.coverage.coverage_reason === 'string' ? <p className="mt-1">Độ phủ: {run.coverage.coverage_reason}</p> : null}{Array.isArray(run.coverage.missing_fields) && run.coverage.missing_fields.length ? <p className="mt-1">Chưa có trường: {(run.coverage.missing_fields as string[]).join(', ')}</p> : null}{run.coverage.metrics_unavailable ? <p className="mt-1">Thiếu chỉ số: {String((run.coverage.metrics_unavailable as string[]).join(', '))}</p> : null}</li>)}</ul> : null}
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
          </Card>

          </section>
          <section id="website-data" className="scroll-mt-24">
          <Card title="Dữ liệu website đã trích xuất" description="Giá, gói bán và số liệu chỉ hiện khi website công khai dữ liệu có bằng chứng. Giá không rõ được để trống; số tự công bố không được coi là số liệu đã kiểm toán.">
            <div className="mb-5 flex w-fit max-w-full flex-wrap gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="Loại dữ liệu website">
              {([['product', 'Sản phẩm & giá'], ['article', 'Bài viết'], ['business_info', 'Thông tin website']] as const).map(([value, label]) => (
                <button key={value} type="button" aria-pressed={webKind === value} className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${webKind === value ? 'bg-white text-teal-800 shadow-sm' : 'text-slate-600 hover:text-slate-950'}`} onClick={() => setWebKind(value)}>{label}</button>
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

          </section>
        </div>
      ) : null}
          {marketTab === "reports" ? (
        <div id="market-panel" role="tabpanel" aria-labelledby="market-tab-reports" className="route-tab-panel">
<section id="market-reports" className="scroll-mt-24">
          {aiBudgetQuery.data ? (
            <section aria-labelledby="ai-budget-title" className="mb-5 rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 id="ai-budget-title" className="font-semibold text-slate-900">Ngân sách AI tự động</h2>
                  <p className="mt-1 text-sm text-slate-600">Giới hạn dùng chung cho các tác vụ AI tự động trong ngày Việt Nam. Yêu cầu bạn chủ động chạy được tính riêng.</p>
                </div>
                <span className="text-sm text-slate-600">Đặt lại {formatDateTime(aiBudgetQuery.data.resets_at)}</span>
              </div>
              <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
                <span>Đã dùng: <strong>{formatUsdMicro(aiBudgetQuery.data.spent_micro_usd)}</strong></span>
                <span>Đang giữ chỗ: <strong>{formatUsdMicro(aiBudgetQuery.data.reserved_micro_usd)}</strong></span>
                <span>Còn khả dụng: <strong>{formatUsdMicro(aiBudgetQuery.data.available_micro_usd)}</strong> / {formatUsdMicro(aiBudgetQuery.data.limit_micro_usd)}</span>
              </div>
              <div
                className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
                role="progressbar"
                aria-label="Mức sử dụng ngân sách AI tự động"
                aria-valuemin={0}
                aria-valuemax={aiBudgetQuery.data.limit_micro_usd}
                aria-valuenow={Math.min(aiBudgetQuery.data.limit_micro_usd, aiBudgetQuery.data.spent_micro_usd + aiBudgetQuery.data.reserved_micro_usd)}
              >
                <div
                  className="h-full rounded-full bg-pink-700 transition-[width] duration-200"
                  style={{ width: `${aiBudgetQuery.data.limit_micro_usd > 0 ? Math.min(100, ((aiBudgetQuery.data.spent_micro_usd + aiBudgetQuery.data.reserved_micro_usd) / aiBudgetQuery.data.limit_micro_usd) * 100) : 0}%` }}
                />
              </div>
              {aiBudgetQuery.data.pending_reports > 0 || aiBudgetQuery.data.unsettled_requests > 0 ? (
                <p className="mt-3 text-sm text-amber-800">
                  {aiBudgetQuery.data.pending_reports > 0 ? `${aiBudgetQuery.data.pending_reports} báo cáo đang chờ hoặc cần xử lý lại do giới hạn/cấu hình AI. ` : ''}
                  {aiBudgetQuery.data.unsettled_requests > 0 ? `${aiBudgetQuery.data.unsettled_requests} lượt gọi đang chạy hoặc chưa đối soát; phần giữ chỗ vẫn được tính vào ngân sách.` : ''}
                </p>
              ) : null}
            </section>
          ) : null}
          {aiBudgetQuery.error ? <ErrorPanel message={readableError(aiBudgetQuery.error, 'Không tải được trạng thái ngân sách AI.')} retryable onRetry={() => void aiBudgetQuery.refetch()} /> : null}
          <Card title="Báo cáo xu hướng và gợi ý" description="DeepSeek phân tích nội dung, tương tác, views, follower count và thay đổi giữa các lần crawl khi nguồn trả dữ liệu. Giá trị thiếu được để trống; kết luận có nguồn đối chiếu.">
            {reportsQuery.isLoading ? <LoadingBlock label="Đang tải báo cáo…" /> : null}
            {reportsQuery.error ? <ErrorPanel message={readableError(reportsQuery.error, 'Không tải được báo cáo.')} retryable onRetry={() => void reportsQuery.refetch()} /> : null}
            {reports.map((report) => {
              const profileContext = report.coverage.business_profile_context ?? report.report.business_profile_context;
              const privacyCoverage = report.coverage.privacy_coverage ?? report.report.privacy_coverage;
              return (
              <article key={report.id} className="mb-4 rounded-xl border border-slate-200 p-4 last:mb-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><h3 className="font-semibold text-slate-900">{report.report.headline || 'Báo cáo thị trường'}</h3><p className="mt-1 text-xs text-slate-500">Tạo {formatDateTime(report.created_at)}{report.model_name ? ' · ' + report.model_name : ''}</p></div>
                  <StatusBadge label={report.coverage.ai_status === 'completed' ? 'Đã phân tích' : 'Phân tích chưa hoàn tất'} tone={report.coverage.ai_status === 'completed' ? 'success' : 'warning'} />
                </div>
                <p className="mt-2 text-xs text-slate-600">
                  {profileContext?.status === 'applied' && report.coverage.ai_status === 'completed'
                    ? `Cá nhân hóa theo hồ sơ Owner đã áp dụng · phiên bản ${profileContext.revision ?? 'không rõ'}.`
                    : profileContext?.status === 'not_configured'
                      ? 'Chưa có hồ sơ Owner được áp dụng tại thời điểm phân tích; báo cáo chưa được cá nhân hóa theo thương hiệu.'
                      : profileContext?.status === 'revision_unavailable'
                        ? 'Không xác minh được phiên bản hồ sơ tại thời điểm phân tích; báo cáo chưa được cá nhân hóa.'
                        : profileContext?.status === 'not_used'
                          ? 'Hồ sơ Owner chưa được gửi vào AI vì lượt phân tích không chạy.'
                          : profileContext?.status === 'provider_outcome_unknown'
                            ? 'Chưa xác định được nhà cung cấp đã nhận yêu cầu; không thể xác nhận hồ sơ nào đã được dùng.'
                        : 'Báo cáo cũ không lưu trạng thái hồ sơ thương hiệu tại thời điểm phân tích.'}
                </p>
                <p className="mt-3 whitespace-pre-line text-sm text-slate-700">{report.report.summary}</p>
                {(privacyCoverage?.facebook_post_text_withheld ?? 0) > 0 ? (
                  <p role="note" className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950">
                    Nội dung {privacyCoverage?.facebook_post_text_withheld} bài Facebook đang được giữ lại, chưa gửi tới AI vì bộ lọc chưa rà soát đầy đủ dữ liệu cá nhân. Bình luận và ảnh/video cũng chưa được phân tích.
                  </p>
                ) : null}
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
              );
            })}
            {!reportsQuery.isLoading && reports.length === 0 ? <EmptyState title="Chưa có báo cáo" description="Sau khi lưu nguồn, bấm Thu thập ngay hoặc chờ lượt tự động đầu tiên. Lịch tiếp theo chạy sau mỗi 12 giờ." /> : null}
          </Card>
          </section>
        </div>
      ) : null}
        </>
      ) : null}
    </div>
  );
}
