'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useSession } from '@/components/session-gate';
import { Button, Card, EmptyState, ErrorPanel, LoadingBlock, PermissionNotice, StatusBadge, UnavailableNotice, type Tone } from '@/components/ui';
import { ApiError, facebookPostUrl, marketResearchApi, marketResearchKeys, metaApi, metaQueryKeys, type MetaPublication, type MetaPublicationStatus } from '@/lib/api';
import { formatDateTime } from '@/lib/format';
import { useCampaigns, usePosts } from '@/lib/hooks';
import { ACTION_REQUIREMENTS, hasPermission } from '@/lib/permissions';

const PUBLICATION_STATUS: Record<MetaPublicationStatus, { label: string; tone: Tone; hint: string }> = {
  queued: { label: 'Chờ gửi', tone: 'info', hint: 'Bài đã vào hàng đợi.' },
  sending: { label: 'Đang gửi', tone: 'info', hint: 'Đang gửi lên Fanpage.' },
  published: { label: 'Đã đăng', tone: 'success', hint: 'Bài đã xuất hiện trên Fanpage.' },
  failed: { label: 'Gửi thất bại', tone: 'danger', hint: 'Lỗi đã được xác định; kiểm tra nguyên nhân trước khi gửi lại.' },
  needs_reconnect: { label: 'Cần kiểm tra kết nối', tone: 'warning', hint: 'Quyền Page không còn hợp lệ; kiểm tra kết nối trước khi gửi lại.' },
  outcome_unknown: { label: 'Chưa rõ kết quả', tone: 'warning', hint: 'Hãy kiểm tra trực tiếp trên Fanpage. Gửi lại ngay có thể tạo bài trùng.' },
  not_published: { label: 'Xác nhận chưa đăng', tone: 'neutral', hint: 'Chủ sở hữu đã đối soát và xác nhận bài chưa xuất hiện trên Fanpage.' },
};

const BLOCKING_STATUSES: ReadonlySet<MetaPublicationStatus> = new Set(['queued', 'sending', 'published', 'outcome_unknown']);

function latestPublication(publications: MetaPublication[], postId: string, version: number, pageId?: string): MetaPublication | null {
  return publications.filter((item) => item.post_id === postId && item.post_version === version)
    .filter((item) => !pageId || item.page_id === pageId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null;
}

export default function PublishingPage() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const activeId = workspace ? workspaceId : '';
  const queryClient = useQueryClient();
  const posts = usePosts(activeId);
  const campaigns = useCampaigns(activeId);
  const connection = useQuery({
    queryKey: metaQueryKeys.connection(activeId),
    queryFn: () => metaApi.connection(activeId),
    enabled: activeId !== '',
  });
  const pageConnections = useQuery({
    queryKey: marketResearchKeys.pages(activeId, 'all'),
    queryFn: () => marketResearchApi.allPages(activeId),
    enabled: activeId !== '',
  });
  const publications = useQuery({
    queryKey: metaQueryKeys.publications(activeId),
    queryFn: () => metaApi.publications(activeId),
    enabled: activeId !== '',
    refetchInterval: (query) => query.state.data?.some((item) => item.status === 'queued' || item.status === 'sending') ? 3_000 : false,
  });
  const [confirmPost, setConfirmPost] = useState<{ id: string; version: number } | null>(null);
  const [selectedPageByPost, setSelectedPageByPost] = useState<Record<string, string>>({});
  const [reconcileId, setReconcileId] = useState<string | null>(null);
  const [reconcileOutcome, setReconcileOutcome] = useState<'published' | 'not_published'>('published');
  const [externalPostId, setExternalPostId] = useState('');
  const [permalink, setPermalink] = useState('');
  const [reconcileNote, setReconcileNote] = useState('');
  const [reconcileError, setReconcileError] = useState<string | null>(null);
  const [lastJobId, setLastJobId] = useState<string | null>(null);
  const publish = useMutation({
    mutationFn: ({ postId, version, connectionId }: { postId: string; version: number; connectionId: string }) =>
      metaApi.publish(activeId, postId, version, connectionId),
    onSuccess: (result) => {
      setLastJobId(result.job_id);
      setConfirmPost(null);
      void queryClient.invalidateQueries({ queryKey: metaQueryKeys.publications(activeId) });
      void queryClient.invalidateQueries({ queryKey: ['workspaces', activeId, 'posts'] });
    },
  });
  const reconcile = useMutation({
    mutationFn: ({ id, outcome, external_post_id, permalink: link, note }: {
      id: string; outcome: 'published' | 'not_published'; external_post_id?: string; permalink?: string; note?: string;
    }) => metaApi.reconcile(activeId, id, { outcome, external_post_id, permalink: link, note }),
    onSuccess: () => {
      setReconcileId(null);
      setExternalPostId('');
      setPermalink('');
      setReconcileNote('');
      setReconcileError(null);
      void queryClient.invalidateQueries({ queryKey: metaQueryKeys.publications(activeId) });
    },
  });
  const approvedPosts = useMemo(() =>
    (posts.data?.items ?? []).filter((post) => post.status === 'approved' && !post.requires_reapproval), [posts.data]);
  const history = useMemo(() =>
    [...(publications.data ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)), [publications.data]);
  const canPublish = workspace?.role === 'owner' && hasPermission(workspace, ACTION_REQUIREMENTS.publish);
  const verifiedPages = pageConnections.data?.filter((page) => page.status === 'verified') ?? [];
  const ready = verifiedPages.length > 0 || (connection.data?.status === 'verified' && connection.data.can_publish);

  function submitReconciliation(publicationId: string) {
    setReconcileError(null);
    const id = externalPostId.trim();
    const link = permalink.trim();
    if (reconcileOutcome === 'published' && !id) {
      setReconcileError('Nếu bài đã đăng, hãy nhập ID bài Facebook để backend xác minh với Meta.');
      return;
    }
    if (link && !facebookPostUrl(link)) {
      setReconcileError('Liên kết bài phải là URL HTTPS của Facebook.');
      return;
    }
    reconcile.mutate({ id: publicationId, outcome: reconcileOutcome,
      external_post_id: id || undefined, permalink: link || undefined, note: reconcileNote.trim() || undefined });
  }

  if (!workspace) return <PermissionNotice message="Bạn không thuộc doanh nghiệp này." />;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-2">
        <h1 className="text-lg font-semibold text-slate-900">Xuất bản lên Fanpage</h1>
        <p className="max-w-3xl text-sm leading-6 text-slate-600">Chỉ gửi phiên bản đã được duyệt. Chủ sở hữu quyết định từng lần đăng và theo dõi kết quả bên dưới.</p>
      </header>

      <Card title="Kết nối Fanpage" description="Xác minh chỉ đọc Page và bài gần nhất; Meta kiểm tra quyền đăng khi owner xác nhận gửi từng bài. Thông tin truy cập không xuất hiện trên trang này.">
        {connection.isPending ? <LoadingBlock label="Đang tải kết nối…" /> : null}
        {connection.isError ? <ErrorPanel title="Không tải được kết nối" message={connection.error instanceof ApiError ? connection.error.message : 'Vui lòng tải lại trang.'} retryable onRetry={() => void connection.refetch()} /> : null}
        {connection.data ? (
          <div className="space-y-3 text-sm text-slate-700">
            <p><strong>{connection.data.status === 'unconfigured' ? 'Chưa kết nối Meta' : connection.data.page_name || 'Fanpage chưa được xác minh'}</strong>{connection.data.page_id ? ` · Page ID ${connection.data.page_id}` : ''}</p>
            <p>{connection.data.message}</p>
            {ready ? <StatusBadge label="Có thể gửi yêu cầu" tone="success" /> : (
              <UnavailableNotice title="Chưa thể đăng trực tiếp" reason={connection.data.message}
                remedy="Mở Cài đặt để kiểm tra cấu hình và xác minh Fanpage trước khi đăng."
                action={<Link href={`/w/${workspaceId}/settings`} className="font-medium underline">Mở Cài đặt</Link>} />
            )}
          </div>
        ) : null}
      </Card>

      <Card title="Bài đã duyệt" description="Hỗ trợ bài chữ hoặc một ảnh JPEG/PNG đã tải lên. Backend kiểm tra lại hash phiên bản đã duyệt trước khi gửi tới Meta.">
        {posts.isPending ? <LoadingBlock label="Đang tải bài đã duyệt…" /> : null}
        {posts.isError ? <ErrorPanel title="Không tải được bài viết" message={posts.error instanceof ApiError ? posts.error.message : 'Vui lòng tải lại bài viết.'} retryable onRetry={() => void posts.refetch()} /> : null}
        {!posts.isPending && !posts.isError && approvedPosts.length === 0 ? (
          <EmptyState title="Chưa có bài đã duyệt" description="Hoàn tất bước duyệt nội dung trong Chiến dịch để đăng lên Fanpage."
            action={<Link href={`/w/${workspaceId}/campaigns`} className="font-medium underline">Mở Chiến dịch</Link>} />
        ) : null}
        <div className="space-y-4">
          {approvedPosts.map((post) => {
            const campaign = campaigns.data?.items.find((item) => item.id === post.campaign_id);
            const candidatePages = verifiedPages.filter((page) => !campaign?.group_id || page.group_id === campaign.group_id);
            const selectedConnectionId = selectedPageByPost[post.id] || (candidatePages.length === 1 ? candidatePages[0]?.id ?? '' : '');
            const selectedPage = candidatePages.find((page) => page.id === selectedConnectionId);
            const previous = latestPublication(history, post.id, post.version, selectedPage?.page_id);
            const blocker = previous && BLOCKING_STATUSES.has(previous.status);
            const disabledReason = !canPublish ? 'Chỉ chủ sở hữu có quyền đăng bài lên Fanpage.'
              : campaigns.isPending ? 'Đang tải nhóm chiến dịch để lọc đúng Fanpage.'
              : candidatePages.length === 0 ? 'Chiến dịch chưa có Fanpage đã xác minh trong nhóm tương ứng.'
              : !selectedConnectionId ? 'Chọn Fanpage đích trước khi gửi.'
              : publications.isPending || publications.isError ? 'Cần tải lịch sử xuất bản trước để tránh gửi trùng.'
              : blocker ? `Phiên bản này đang ở trạng thái ${PUBLICATION_STATUS[previous.status].label.toLowerCase()}.` : undefined;
            const isConfirming = confirmPost?.id === post.id && confirmPost.version === post.version;
            return (
              <article key={post.id} className="rounded-xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-900">Bản {post.version} · {post.pillar}</p>
                    <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-sm text-slate-700">{post.current.caption}</p>
                    <Link href={`/w/${workspaceId}/campaigns/${post.campaign_id}/posts/${post.id}`} className="mt-2 inline-block text-xs font-medium text-slate-700 underline">Xem nội dung và lịch sử duyệt</Link>
                  </div>
                  {previous ? <StatusBadge label={PUBLICATION_STATUS[previous.status].label} tone={PUBLICATION_STATUS[previous.status].tone} /> : null}
                </div>
                {previous ? <p className="mt-2 text-xs text-slate-600">{PUBLICATION_STATUS[previous.status].hint}</p> : null}
                {isConfirming ? (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
                    <p>Gửi phiên bản {post.version} lên <strong>{selectedPage?.page_name || 'Fanpage đã chọn'}</strong> ngay bây giờ?</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button onClick={() => publish.mutate({ postId: post.id, version: post.version, connectionId: selectedConnectionId })} loading={publish.isPending} disabled={Boolean(disabledReason)} disabledReason={disabledReason}>Xác nhận đăng bản {post.version}</Button>
                      <Button variant="secondary" onClick={() => setConfirmPost(null)}>Hủy</Button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-3">
                    {candidatePages.length > 0 ? (
                      <label className="mb-3 block max-w-lg space-y-1 text-sm text-slate-700">
                        Fanpage đích{campaign?.group_id ? ' của nhóm chiến dịch' : ''}
                        <select
                          value={selectedConnectionId}
                          onChange={(event) => setSelectedPageByPost({ ...selectedPageByPost, [post.id]: event.currentTarget.value })}
                          className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2"
                        >
                          {candidatePages.length !== 1 ? <option value="">Chọn Fanpage</option> : null}
                          {candidatePages.map((page) => <option key={page.id} value={page.id}>{page.page_name || 'Fanpage'} · {page.page_id}</option>)}
                        </select>
                      </label>
                    ) : null}
                    <Button onClick={() => { publish.reset(); setConfirmPost({ id: post.id, version: post.version }); }} disabled={Boolean(disabledReason)} disabledReason={disabledReason}>Đăng bản {post.version} lên Fanpage</Button>
                    {disabledReason ? <p className="mt-1 text-xs text-slate-600">{disabledReason}</p> : null}
                  </div>
                )}
              </article>
            );
          })}
        </div>
        {publish.isError ? <ErrorPanel title="Chưa xác nhận được yêu cầu đăng"
          message={publish.error instanceof ApiError ? publish.error.message : 'Hãy tải lại lịch sử xuất bản và kiểm tra Fanpage trước khi gửi lại.'}
          onRetry={() => void publications.refetch()} retryable retryLabel="Tải lại lịch sử" /> : null}
        {lastJobId ? <p role="status" className="mt-3 text-sm text-emerald-800">Đã nhận yêu cầu đăng. <Link href={`/w/${workspaceId}/jobs/${lastJobId}`} className="font-medium underline">Xem tiến độ job</Link>.</p> : null}
      </Card>

      <Card title="Lịch sử xuất bản" description="Kết quả chưa rõ phải được đối soát trên Fanpage trước khi có hành động khác.">
        {publications.isPending ? <LoadingBlock label="Đang tải lịch sử đăng bài…" /> : null}
        {publications.isError ? <ErrorPanel title="Không tải được lịch sử xuất bản" message={publications.error instanceof ApiError ? publications.error.message : 'Vui lòng thử lại.'} retryable onRetry={() => void publications.refetch()} /> : null}
        {!publications.isPending && !publications.isError && history.length === 0 ? <EmptyState title="Chưa có lần đăng nào" description="Khi chủ sở hữu gửi bài, trạng thái sẽ xuất hiện ở đây." /> : null}
        <div className="space-y-3">
          {history.map((item) => {
            const status = PUBLICATION_STATUS[item.status];
            const link = facebookPostUrl(item.permalink);
            return (
              <article key={item.id} className="space-y-2 rounded-lg border border-slate-200 p-4 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2"><p className="font-medium text-slate-900">Bài {item.post_id} · bản {item.post_version}</p><StatusBadge label={status.label} tone={status.tone} /></div>
                <p className="text-slate-600">{status.hint}</p>
                <p className="text-xs text-slate-500">Cập nhật {formatDateTime(item.updated_at)} · Page ID {item.page_id}</p>
                {item.error ? <p role="alert" className="text-rose-800">{item.error.message}{item.error.hint ? ` ${item.error.hint}` : ''}</p> : null}
                {link ? <a href={link} target="_blank" rel="noopener noreferrer" className="font-medium text-slate-800 underline">Mở bài trên Facebook</a> : null}
                {item.status === 'outcome_unknown' && canPublish ? (
                  <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <p className="font-medium text-amber-950">Kiểm tra Page trước khi xác nhận. Không gửi lại bài lúc này.</p>
                    <Button variant="secondary" onClick={() => { setReconcileId(reconcileId === item.id ? null : item.id); setReconcileError(null); }}>Đối soát thủ công</Button>
                    {reconcileId === item.id ? (
                      <div className="space-y-3">
                        <fieldset className="space-y-1">
                          <legend className="font-medium">Kết quả kiểm tra Fanpage</legend>
                          <label className="flex gap-2"><input type="radio" name={`outcome-${item.id}`} checked={reconcileOutcome === 'published'} onChange={() => setReconcileOutcome('published')} /> Bài đã xuất hiện</label>
                          <label className="flex gap-2"><input type="radio" name={`outcome-${item.id}`} checked={reconcileOutcome === 'not_published'} onChange={() => setReconcileOutcome('not_published')} /> Bài chưa xuất hiện</label>
                        </fieldset>
                        {reconcileOutcome === 'published' ? (
                          <div className="grid gap-3 sm:grid-cols-2">
                            <label className="space-y-1">ID bài Facebook<input value={externalPostId} onChange={(event) => setExternalPostId(event.target.value)} className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                            <label className="space-y-1">Liên kết bài Facebook<input type="url" value={permalink} onChange={(event) => setPermalink(event.target.value)} className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                          </div>
                        ) : null}
                        <label className="block space-y-1">Ghi chú đối soát<input value={reconcileNote} onChange={(event) => setReconcileNote(event.target.value)} className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2" /></label>
                        {reconcileError ? <p role="alert" className="text-rose-800">{reconcileError}</p> : null}
                        {reconcile.isError ? <p role="alert" className="text-rose-800">{reconcile.error instanceof ApiError ? reconcile.error.message : 'Không lưu được kết quả đối soát.'}</p> : null}
                        <Button onClick={() => submitReconciliation(item.id)} loading={reconcile.isPending}>Lưu kết quả đối soát</Button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
                {item.status === 'needs_reconnect' ? <Link href={`/w/${workspaceId}/settings`} className="inline-block font-medium underline">Kiểm tra kết nối Fanpage</Link> : null}
              </article>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
