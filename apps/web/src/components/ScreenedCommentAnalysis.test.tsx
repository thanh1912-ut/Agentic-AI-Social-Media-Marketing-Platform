import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { marketResearchApi, type CommentCandidatesPage, type CommentProcessing } from '@/lib/api/market-research';
import { ScreenedCommentAnalysis } from './ScreenedCommentAnalysis';

vi.mock('@/lib/hooks', () => ({ useJob: () => ({ data: undefined }) }));
const now = new Date().toISOString();
const accepted = { job_id: 'job-a', job: { id: 'job-a', kind: 'research_comment_analysis', status: 'queued' as const, title: 'Synthetic comment analysis', progress: null, steps: [], created_at: now, cancellable: true } };
const future = new Date(Date.now() + 3600000).toISOString();
const state: CommentProcessing = {
  source_id: 'source-a', supported: true, status: 'active', effective_status: 'active',
  collection_allowed: true, decision_id: '11111111-1111-4111-8111-111111111111', policy_revision_no: 2,
  candidate_versions_count: 2, quarantined_candidate_versions_count: 2, pending_edges: 0,
  candidate_content_status: 'privacy_hold', legal_basis_verified_by_platform: false,
  provider_transmission_allowed: false, quarantine_max_hours: 24, scope: 'local_comment_quarantine_v1',
};
const comments: NonNullable<CommentCandidatesPage['comments']> = [{
  is_reply: false, id: '22222222-2222-4222-8222-222222222222', author_alias: 'user_name01', author_identity_known: true,
  text: 'Synthetic excerpt', published_at: null, observed_at: now, expires_at: future,
  likes: 2, reactions: null, reactions_precision: 'unknown', reaction_breakdown: {}, reply_count: null,
  content_truncated: false, alias_scope: 'post_read_only', content_status: 'privacy_hold',
}];
function mount() {
  vi.spyOn(marketResearchApi, 'commentProcessing').mockResolvedValue(state);
  vi.spyOn(marketResearchApi, 'commentAnalyses').mockResolvedValue({ items: [], next_cursor: null });
  const query = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(<QueryClientProvider client={query}><ScreenedCommentAnalysis workspaceId="workspace-a" sourceId="source-a" evidenceId="post-a" comments={comments} /></QueryClientProvider>);
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function selectAndReview() {
  await userEvent.click(screen.getByRole('button', { name: 'Rà soát để phân tích bằng Gemini' }));
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Chọn đoạn 1' }));
  const editor = screen.getByRole('textbox', { name: /Bản kiểm tra đoạn 1/ });
  await userEvent.clear(editor);
  await userEvent.type(editor, 'Reviewed synthetic question');
  await userEvent.type(screen.getByRole('textbox', { name: /Tham chiếu đánh giá xử lý và gửi dữ liệu/ }), 'Synthetic assessment reference');
}

describe('screened comment analysis (synthetic API fixture)', () => {
  it('does not fetch history or send a job until explicit review and submit', async () => {
    const send = vi.spyOn(marketResearchApi, 'analyzeComments').mockResolvedValue(accepted);
    mount();
    expect(marketResearchApi.commentAnalyses).not.toHaveBeenCalled();
    expect(send).not.toHaveBeenCalled();
    await selectAndReview();
    expect(send).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: /Phân tích bản đã kiểm tra$/ }));
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1));
    const payload = send.mock.calls[0]![2];
    expect(payload.comments).toEqual([{ version_id: comments[0]!.id, text: 'Reviewed synthetic question' }]);
    expect(payload.decision_id).toBe(state.decision_id);
    expect(JSON.stringify(payload)).not.toContain('user_name01');
    expect(payload.request_key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('reuses the same request identity after an uncertain network response', async () => {
    const send = vi.spyOn(marketResearchApi, 'analyzeComments').mockRejectedValueOnce(new Error('Synthetic network failure'))
      .mockResolvedValue(accepted);
    mount();
    await selectAndReview();
    await userEvent.click(screen.getByRole('button', { name: /Phân tích bản đã kiểm tra$/ }));
    await screen.findByRole('alert');
    await userEvent.click(screen.getByRole('button', { name: /Phân tích bản đã kiểm tra$/ }));
    await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(send.mock.calls[0]![2].request_key).toBe(send.mock.calls[1]![2].request_key);
  });

  it('shows stored results and the exact screened citation without raw author identity', async () => {
    mount();
    vi.mocked(marketResearchApi.commentAnalyses).mockResolvedValue({ items: [{
      id: 'batch-a', source_id: 'source-a', job_id: 'job-a', report_job_id: 'report-job-a', report_id: 'report-a', status: 'completed', provider: 'gemini', model: 'gemini-3.8-flash',
      created_at: now, expires_at: future, coverage: {}, selected_version_ids: [comments[0]!.id],
      legal_basis_verified_by_platform: false,
      result: { topics: [{ category: 'question', topic: 'Cách dùng', summary: 'Người đọc muốn biết cách dùng.', evidence_refs: ['comment_item-a'] }], limitations: ['Synthetic coverage only'] },
      citations: [{ evidence_ref: 'comment_item-a', version_id: comments[0]!.id, evidence_id: 'post-a', observation_id: 'observation-a', evidence_version_id: 'evidence-version-a', text: 'Reviewed evidence', content_edited: true, source_content_truncated: false }],
    }], next_cursor: null });
    await userEvent.click(screen.getByRole('button', { name: 'Rà soát để phân tích bằng Gemini' }));
    expect(await screen.findByText('Người đọc muốn biết cách dùng.')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Đoạn đã dùng'));
    expect(screen.getByText(/Reviewed evidence/)).toBeInTheDocument();
    expect(screen.queryByText('user_name01')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Xem báo cáo và chọn hướng viết' })).toHaveAttribute('href', '/w/workspace-a/research?tab=reports');
  });
});
