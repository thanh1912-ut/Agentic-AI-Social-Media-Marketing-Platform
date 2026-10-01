import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { PublicCommentSettings, PublicPostComments } from './PublicPageComments';
import { marketResearchApi, marketResearchKeys, type CommentCandidatesPage, type CommentProcessing } from '@/lib/api/market-research';

const now = new Date().toISOString();
const future = new Date(Date.now() + 3600_000).toISOString();
const state: CommentProcessing = {
  source_id: 'source-a', supported: true, status: 'active', effective_status: 'active',
  collection_allowed: true, decision_id: 'decision-a', policy_revision_no: 2,
  candidate_versions_count: 2, quarantined_candidate_versions_count: 2, pending_edges: 1,
  candidate_content_status: 'privacy_hold', legal_basis_verified_by_platform: false,
  provider_transmission_allowed: false, quarantine_max_hours: 24, scope: 'local_comment_quarantine_v1',
};
const page: CommentCandidatesPage = {
  source_id: 'source-a', evidence_id: 'post-a', observation_id: 'observation-a', status: 'privacy_hold', suppressed_comments_count: 0,
  coverage: { returned_count: 2, provider_reported_count: 20, history_complete: false },
  provider_transmission_allowed: false,
  comments: [{ is_reply: false, id: 'comment-a', author_alias: 'user_name01', author_identity_known: true,
    text: 'Synthetic question', published_at: null, observed_at: now, expires_at: future,
    likes: 2, reactions: 9, reactions_precision: 'exact', reactions_raw: '9',
    reaction_breakdown: { LIKE: 2, LOVE: 7 }, reply_count: 3, content_truncated: false,
    alias_scope: 'post_read_only', content_status: 'privacy_hold' },
  { is_reply: false, id: 'comment-b', author_alias: 'user_name02', author_identity_known: false,
    text: 'Synthetic second question', published_at: null, observed_at: now, expires_at: future,
    likes: null, reactions: 1200, reactions_precision: 'approximate', reactions_raw: '1,2K',
    reaction_breakdown: {}, reply_count: null, content_truncated: false,
    alias_scope: 'post_read_only', content_status: 'privacy_hold' }],
};

function mount(element: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
  return client;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Public Page comment review (synthetic API fixtures)', () => {
  it('never fetches candidate content for a non-Owner', () => {
    const read = vi.spyOn(marketResearchApi, 'commentCandidates');
    mount(<PublicPostComments workspaceId="workspace-a" sourceId="source-a" evidenceId="post-a" canReview={false} />);
    expect(screen.getByRole('button', { name: /Xem bình luận và tương tác/ })).toBeDisabled();
    expect(read).not.toHaveBeenCalled();
  });

  it('separates comment likes/reactions, qualifies unknown authors, and evicts content on hide', async () => {
    vi.spyOn(marketResearchApi, 'commentCandidates').mockResolvedValue(page);
    const client = mount(<PublicPostComments workspaceId="workspace-a" sourceId="source-a" evidenceId="post-a" canReview />);
    await userEvent.click(screen.getByRole('button', { name: 'Xem bình luận và tương tác' }));
    await screen.findByText('Synthetic question');
    const first = screen.getByText('Synthetic question').closest('article')!;
    expect(within(first).getByText('Like: 2')).toBeInTheDocument();
    expect(within(first).getByText('Reactions: 9 (nguồn: 9)')).toBeInTheDocument();
    expect(screen.getByText(/user_name02 · chưa xác định tác giả/)).toBeInTheDocument();
    expect(screen.getByText('Reactions: ≈ 1.200 (nguồn: 1,2K)')).toBeInTheDocument();
    expect(screen.getByText(/Chưa xác minh đầy đủ lịch sử/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Ẩn bình luận' }));
    await waitFor(() => expect(client.getQueryData([...marketResearchKeys.commentCandidates('workspace-a', 'source-a'), 'post-a'])).toBeUndefined());
    expect(screen.queryByText('Synthetic question')).not.toBeInTheDocument();
  });

  it('does not render expired candidates and keeps missing counts distinct from zero', async () => {
    vi.spyOn(marketResearchApi, 'commentCandidates').mockResolvedValue({ ...page, comments: [
      { ...page.comments![0]!, text: 'Expired synthetic text', expires_at: '2000-01-01T00:00:00Z' },
      { ...page.comments![1]!, likes: 0 },
    ] });
    mount(<PublicPostComments workspaceId="workspace-a" sourceId="source-a" evidenceId="post-a" canReview />);
    await userEvent.click(screen.getByRole('button', { name: 'Xem bình luận và tương tác' }));
    await screen.findByText('Synthetic second question');
    expect(screen.queryByText('Expired synthetic text')).not.toBeInTheDocument();
    expect(screen.getByText('Like: 0')).toBeInTheDocument();
    expect(screen.getByText('Phản hồi: Chưa có dữ liệu')).toBeInTheDocument();
  });

  it('requires a deliberate erasure action and discards stale source content after confirmation', async () => {
    const after = { ...page, comments: [page.comments![1]!], suppressed_comments_count: 1 };
    vi.spyOn(marketResearchApi, 'commentCandidates').mockResolvedValueOnce(page).mockResolvedValue(after);
    const erase = vi.spyOn(marketResearchApi, 'suppressComment').mockResolvedValue({
      suppression_id: 'suppression-a', identities_suppressed: 1, versions_erased: 1,
      reply_edges_stopped: 0, provider_transmission_allowed: false,
    });
    const client = mount(<PublicPostComments workspaceId="workspace-a" sourceId="source-a" evidenceId="post-a" canReview />);
    client.setQueryData(marketResearchKeys.commentCandidates('workspace-other', 'source-a'), 'unrelated fixture cache');
    await userEvent.click(screen.getByRole('button', { name: 'Xem bình luận và tương tác' }));
    const article = (await screen.findByText('Synthetic question')).closest('article')!;
    await userEvent.click(within(article).getByRole('button', { name: 'Loại bình luận khỏi nghiên cứu' }));
    expect(erase).not.toHaveBeenCalled();
    await userEvent.selectOptions(within(article).getByLabelText('Lý do loại dữ liệu'), 'subject_request');
    await userEvent.click(within(article).getByRole('button', { name: 'Xóa và ngăn nhập lại' }));
    await waitFor(() => expect(erase).toHaveBeenCalledWith('workspace-a', 'source-a', 'comment-a', { reason: 'subject_request' }));
    await waitFor(() => expect(screen.queryByText('Synthetic question')).not.toBeInTheDocument());
    expect(await screen.findByText('Synthetic second question')).toBeInTheDocument();
    expect(screen.getByText('Đã loại 1 bình luận và ngăn nhập lại theo mã nguồn.')).toBeInTheDocument();
    expect(client.getQueryData(marketResearchKeys.commentCandidates('workspace-other', 'source-a'))).toBe('unrelated fixture cache');
  });

  it('uses the same workspace policy cache as the source editor and saves its current revision', async () => {
    vi.spyOn(marketResearchApi, 'commentProcessing').mockResolvedValue(state);
    const policy = { source_id: 'source-a', purpose: 'Synthetic purpose', processing_basis_reference: 'Synthetic assessment',
      policy_version: 'test-v1', requested_retention_days: 90, revision_no: 2, configured: true,
      collection_ready: true, legal_basis_verified: false as const, configured_by: 'owner-a', configured_at: now,
      retention_enforcement_status: 'not_enforced' as const, comments_content_status: 'privacy_hold' as const };
    vi.spyOn(marketResearchApi, 'privacyPolicy').mockResolvedValue(policy);
    const save = vi.spyOn(marketResearchApi, 'saveCommentProcessing').mockResolvedValue(state);
    const client = mount(<PublicCommentSettings workspaceId="workspace-a" sourceId="source-a" canManage />);
    await screen.findByText(/Đã cấu hình/);
    await userEvent.click(screen.getByText('Cấu hình hoặc thu hồi phạm vi xử lý'));
    await waitFor(() => expect(client.getQueryData(marketResearchKeys.privacyPolicy('workspace-a', 'source-a'))).toBeDefined());
    client.setQueryData(marketResearchKeys.privacyPolicy('workspace-a', 'source-a'), { ...policy, revision_no: 3 });
    await userEvent.type(screen.getByLabelText('Tham chiếu đánh giá phạm vi xử lý của đơn vị vận hành'), 'synthetic assessment ref');
    await userEvent.click(screen.getByRole('button', { name: 'Lưu phạm vi cho crawl' }));
    await waitFor(() => expect(save).toHaveBeenCalledWith('workspace-a', 'source-a', expect.objectContaining({ policy_revision_no: 3 })));
    expect(marketResearchKeys.commentCandidates('workspace-a', 'source-a').slice(0, 2)).toEqual(['workspaces', 'workspace-a']);
  });
  it('starts owned comment collection only after a click, then polls the durable job', async () => {
    vi.spyOn(marketResearchApi, 'commentProcessing').mockResolvedValue(state);
    vi.spyOn(marketResearchApi, 'privacyPolicy').mockRejectedValue(new Error('Synthetic unconfigured policy'));
    const accepted = { job_id: 'comment-job-a', job: { id: 'comment-job-a', kind: 'research_comments',
      status: 'queued' as const, title: 'Synthetic owned comments', progress: null, steps: [], created_at: now, cancellable: true } };
    const collect = vi.spyOn(marketResearchApi, 'crawlComments').mockResolvedValue(accepted);
    const poll = vi.spyOn(api.job, 'get').mockResolvedValue({ ...accepted.job, kind: 'market_research', progress: 0 });
    mount(<PublicCommentSettings workspaceId="workspace-a" sourceId="source-a" canManage collector="meta_api" />);
    const button = await screen.findByRole('button', { name: /Thu thập bình luận và replies/ });
    await waitFor(() => expect(button).toBeEnabled());
    expect(collect).not.toHaveBeenCalled();
    expect(poll).not.toHaveBeenCalled();
    await userEvent.click(button);
    await waitFor(() => expect(collect).toHaveBeenCalledExactlyOnceWith('workspace-a', 'source-a'));
    await waitFor(() => expect(poll).toHaveBeenCalledWith('comment-job-a', expect.any(AbortSignal)));
    expect(button).toBeDisabled();
    expect(screen.getByRole('link', { name: 'Theo dõi tiến độ' })).toHaveAttribute('href', '/w/workspace-a/jobs/comment-job-a');
    expect(screen.queryByText(/Tier 0/)).not.toBeInTheDocument();
  });

  it('does not offer an owned crawl without active scope or to a non-Owner', async () => {
    vi.spyOn(marketResearchApi, 'commentProcessing').mockResolvedValue({ ...state, collection_allowed: false });
    vi.spyOn(marketResearchApi, 'privacyPolicy').mockRejectedValue(new Error('Synthetic unconfigured policy'));
    const collect = vi.spyOn(marketResearchApi, 'crawlComments');
    mount(<PublicCommentSettings workspaceId="workspace-a" sourceId="source-a" canManage collector="meta_api" />);
    expect(await screen.findByRole('button', { name: /Thu thập bình luận và replies/ })).toBeDisabled();
    cleanup();
    mount(<PublicCommentSettings workspaceId="workspace-a" sourceId="source-a" canManage={false} collector="meta_api" />);
    expect(screen.queryByRole('button', { name: /Thu thập bình luận và replies/ })).not.toBeInTheDocument();
    expect(collect).not.toHaveBeenCalled();
  });

  it('restores owned job polling after reload and links replies to the visible parent', async () => {
    vi.spyOn(marketResearchApi, 'commentProcessing').mockResolvedValue({ ...state, job_id: 'running-comment-job' });
    vi.spyOn(marketResearchApi, 'privacyPolicy').mockRejectedValue(new Error('Synthetic unconfigured policy'));
    const poll = vi.spyOn(api.job, 'get').mockResolvedValue({ id: 'running-comment-job', kind: 'market_research',
      status: 'running', title: 'Synthetic owned comments', progress: 0, steps: [], created_at: now, cancellable: true });
    vi.spyOn(marketResearchApi, 'commentCandidates').mockResolvedValue({ ...page,
      coverage: { returned_count: 2, pending_edges: 1 }, comments: [page.comments![0]!,
        { ...page.comments![1]!, is_reply: true, parent_version_id: 'comment-a' }] });
    mount(<><PublicCommentSettings workspaceId="workspace-a" sourceId="source-a" canManage collector="meta_api" />
      <PublicPostComments workspaceId="workspace-a" sourceId="source-a" evidenceId="post-a" canReview collector="meta_api" /></>);
    await waitFor(() => expect(poll).toHaveBeenCalledWith('running-comment-job', expect.any(AbortSignal)));
    await userEvent.click(screen.getByRole('button', { name: 'Xem bình luận và tương tác' }));
    const link = await screen.findByRole('link', { name: 'Phản hồi cho bình luận đã lưu' });
    expect(link).toHaveAttribute('href', '#comment-comment-a');
    expect(screen.getByText('Synthetic question').closest('article')).toHaveAttribute('id', 'comment-comment-a');
    expect(screen.queryByText(/replies chưa được đọc trong Tier 0/)).not.toBeInTheDocument();
  });

});
