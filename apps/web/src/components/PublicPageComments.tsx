'use client';

import { useState, type FormEvent } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from './ui';
import { marketResearchApi, marketResearchKeys } from '@/lib/api/market-research';
import { ApiError } from '@/lib/api/client';

const key = marketResearchKeys.commentProcessing;
const commentKey = marketResearchKeys.commentCandidates;
const count = (value: number | null) => value == null ? 'Chưa có dữ liệu' : new Intl.NumberFormat('vi-VN').format(value);
const errorText = (error: unknown) => error instanceof ApiError ? error.message : 'Không tải hoặc lưu được dữ liệu. Thử lại.';

export function PublicCommentSettings({ workspaceId, sourceId, canManage }: {
  workspaceId: string; sourceId: string; canManage: boolean;
}) {
  const queryClient = useQueryClient();
  const [reference, setReference] = useState('');
  const state = useQuery({ queryKey: key(workspaceId, sourceId),
    queryFn: () => marketResearchApi.commentProcessing(workspaceId, sourceId), refetchInterval: 15_000 });
  const policy = useQuery({ queryKey: marketResearchKeys.privacyPolicy(workspaceId, sourceId),
    queryFn: () => marketResearchApi.privacyPolicy(workspaceId, sourceId), enabled: canManage });
  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: key(workspaceId, sourceId) });
    await queryClient.invalidateQueries({ queryKey: commentKey(workspaceId, sourceId) });
  }
  const save = useMutation({ mutationFn: () => marketResearchApi.saveCommentProcessing(workspaceId, sourceId, {
    expected_decision_id: state.data?.decision_id ?? null,
    policy_revision_no: policy.data?.revision_no ?? 0, assessment_reference: reference,
    status: 'active', valid_until: new Date(Date.now() + 7 * 86400_000).toISOString(),
  }), onSuccess: async () => { setReference(''); await refresh(); } });
  const revoke = useMutation({ mutationFn: () => marketResearchApi.revokeCommentProcessing(workspaceId, sourceId, state.data!.decision_id!), onSuccess: async () => {
    await queryClient.cancelQueries({ queryKey: commentKey(workspaceId, sourceId) });
    queryClient.removeQueries({ queryKey: commentKey(workspaceId, sourceId) });
    await refresh();
  } });
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); save.mutate(); }
  return <section className="space-y-3 border-b border-slate-200 pb-4" aria-label="Phạm vi bình luận công khai">
    <h4 className="font-medium">Bình luận công khai</h4>
    <p className="text-sm text-slate-600">Đọc bình luận từ permalink bằng facebook-cli Tier 0. Số like và reactions thuộc từng bình luận; không thống kê hành vi của một người trên nhiều Page.</p>
    {state.isLoading ? <p role="status">Đang tải phạm vi xử lý…</p> : null}
    {state.data ? <p className="text-sm">{state.data.collection_allowed ? 'Đã cấu hình: lần Crawl ngay tiếp theo sẽ đọc bình luận công khai mà nguồn trả về.' : 'Chưa mở xử lý bình luận cho nguồn này.'} {state.data.quarantined_candidate_versions_count} bản ghi đang chờ kiểm tra.</p> : null}
    <p className="text-xs text-slate-500">Dữ liệu được che thông tin liên hệ, thay tên theo từng bài, mã hóa và giữ tối đa 24 giờ cho Owner kiểm tra. Chưa gửi bình luận sang AI. Đây không phải chứng nhận căn cứ pháp lý hoặc sự đồng ý của người bình luận.</p>
    {canManage ? <details><summary className="cursor-pointer text-sm font-medium">Cấu hình hoặc thu hồi phạm vi xử lý</summary>
      <form className="mt-3 space-y-3" onSubmit={submit}>
        <label className="block text-sm" htmlFor={'comment-assessment-' + sourceId}>Tham chiếu đánh giá phạm vi xử lý của đơn vị vận hành</label>
        <input id={'comment-assessment-' + sourceId} className="w-full rounded-lg border border-slate-300 px-3 py-2" value={reference} onChange={(event) => setReference(event.currentTarget.value)} minLength={5} maxLength={1000} required placeholder="Mã hoặc vị trí hồ sơ đánh giá; không nhập thông tin cá nhân" />
        <p className="text-xs text-slate-500">Cấu hình có hiệu lực 7 ngày cho nguồn này, không hỏi lại mỗi lượt. Cần lưu mục đích và căn cứ xử lý trong phần Chính sách nguồn trước.</p>
        <div className="flex flex-wrap gap-2"><Button size="sm" type="submit" loading={save.isPending} disabled={!policy.data?.revision_no || state.isLoading || reference.trim().length < 5} disabledReason="Cần chính sách nguồn và tham chiếu đánh giá trước khi lưu.">Lưu phạm vi cho crawl</Button>
          {state.data?.decision_id && state.data.status !== 'revoked' ? <Button size="sm" variant="secondary" loading={revoke.isPending} onClick={() => revoke.mutate()}>Thu hồi và xóa bản chờ kiểm tra</Button> : null}</div>
      </form>
    </details> : <p className="text-xs text-slate-500">Chỉ Owner quản lý phạm vi và xem các bình luận chưa được kiểm tra.</p>}
    {state.error || save.error || revoke.error ? <p role="alert" className="text-sm text-rose-800">{errorText(state.error || save.error || revoke.error)}</p> : null}
  </section>;
}

export function PublicPostComments({ workspaceId, sourceId, evidenceId, canReview }: {
  workspaceId: string; sourceId: string; evidenceId: string; canReview: boolean;
}) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const query = useInfiniteQuery({
    queryKey: [...commentKey(workspaceId, sourceId), evidenceId],
    queryFn: ({ pageParam }) => marketResearchApi.commentCandidates(workspaceId, sourceId, evidenceId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: open && canReview, gcTime: 0, staleTime: 0, refetchInterval: open ? 15_000 : false,
  });
  const first = query.data?.pages[0];
  const comments = query.data?.pages.flatMap((page) => page.comments ?? []).filter((c) => Date.parse(c.expires_at) > Date.now()) ?? [];
  async function toggle() {
    if (open) {
      setOpen(false);
      const queryKey = [...commentKey(workspaceId, sourceId), evidenceId];
      await queryClient.cancelQueries({ queryKey });
      queryClient.removeQueries({ queryKey });
    } else {
      setOpen(true);
    }
  }
  return <div className="mt-3 border-t border-slate-100 pt-3">
    <Button size="sm" variant="secondary" disabled={!canReview} disabledReason="Bình luận đang chờ kiểm tra; chỉ Owner được xem." aria-expanded={open} onClick={() => void toggle()}>{open ? 'Ẩn bình luận' : 'Xem bình luận và tương tác'}</Button>
    {open && canReview ? <div className="mt-3 space-y-3">
      <p className="text-xs text-amber-800">Bình luận đã che thông tin phổ biến, đang chờ kiểm tra. Mã người viết chỉ có ý nghĩa trong bài/lượt này; chưa phải dữ liệu đã vô danh.</p>
      {query.isLoading ? <p role="status">Đang đọc bình luận đã lưu…</p> : null}
      {query.error ? <p role="alert">{errorText(query.error)} <Button size="sm" variant="secondary" onClick={() => void query.refetch()}>Thử lại</Button></p> : null}
      {!query.isError && first ? <p className="text-xs text-slate-500">Đã nhận {String(first.coverage?.returned_count ?? 0)} bình luận{typeof first.coverage?.provider_reported_count === 'number' ? ' / nguồn công bố ' + first.coverage?.provider_reported_count : ''}. Chưa xác minh đầy đủ lịch sử; replies chưa được đọc trong Tier 0.</p> : null}
      {!query.isError && first?.status === 'processing_required' ? <p className="text-sm">Owner cần ghi nhận phạm vi xử lý, sau đó Crawl ngay để đọc bình luận.</p> : null}
      {!query.isError && first?.status === 'no_candidates' ? <p className="text-sm">Không có bình luận còn trong thời hạn kiểm tra. Nguồn có thể không trả bình luận hoặc bản chờ đã hết hạn.</p> : null}
      {!query.isError ? comments.map((c) => <article key={c.id} className="border-l-2 border-slate-200 pl-3">
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600"><strong>{c.author_alias ?? 'Bình luận chưa rõ tác giả'}{c.author_identity_known ? '' : ' · chưa xác định tác giả'}</strong><span>Like: {count(c.likes)}</span><span>Reactions: {c.reactions_precision === 'approximate' ? '≈ ' : c.reactions_precision === 'lower_bound' ? '≥ ' : ''}{count(c.reactions)}{c.reactions_raw ? ' (nguồn: ' + c.reactions_raw + ')' : ''}</span><span>Phản hồi: {count(c.reply_count)}</span></div>
        <p className="mt-1 whitespace-pre-wrap break-words text-sm">{c.text || '(Không có chữ được trả về)'}</p>
        {c.content_truncated ? <p className="text-xs text-amber-800">Nội dung vượt giới hạn và đã được cắt; không phải toàn bộ bình luận.</p> : null}
        <p className="mt-1 text-xs text-slate-500">{c.published_at ? 'Đăng ' + new Date(c.published_at).toLocaleString('vi-VN') : 'Không có thời điểm đăng từ nguồn'}</p>
      </article>) : null}
      {query.hasNextPage ? <Button variant="secondary" size="sm" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>Xem thêm bình luận đã lưu</Button> : null}
    </div> : null}
  </div>;
}
