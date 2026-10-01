'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useJob } from '@/lib/hooks';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from './ui';
import { ScreenedCommentAnalysis } from './ScreenedCommentAnalysis';
import { marketResearchApi, marketResearchKeys, type CommentSuppressionRequest } from '@/lib/api/market-research';
import { ApiError } from '@/lib/api/client';

const key = marketResearchKeys.commentProcessing;
const commentKey = marketResearchKeys.commentCandidates;
const count = (value: number | null) => value == null ? 'Chưa có dữ liệu' : new Intl.NumberFormat('vi-VN').format(value);
const errorText = (error: unknown) => error instanceof ApiError ? error.message : 'Không tải hoặc lưu được dữ liệu. Thử lại.';

export function PublicCommentSettings({ workspaceId, sourceId, canManage, collector = 'public_web' }: {
  workspaceId: string; sourceId: string; canManage: boolean; collector?: 'public_web' | 'meta_api';
}) {
  const queryClient = useQueryClient();
  const [reference, setReference] = useState('');
  const [submittedJobId, setSubmittedJobId] = useState<string | null>(null);
  const handledJob = useRef<string | null>(null);
  const state = useQuery({ queryKey: key(workspaceId, sourceId),
    queryFn: () => marketResearchApi.commentProcessing(workspaceId, sourceId), refetchInterval: 15_000 });
  const job = useJob(collector === 'meta_api' ? (submittedJobId ?? state.data?.job_id) : null);
  const collecting = job.data?.status === 'queued' || job.data?.status === 'running'
    || Boolean(state.data?.job_id && !job.data);
  useEffect(() => {
    if (!job.data || !['succeeded', 'failed', 'cancelled'].includes(job.data.status) || handledJob.current === job.data.id) return;
    handledJob.current = job.data.id;
    void queryClient.invalidateQueries({ queryKey: key(workspaceId, sourceId) });
    void queryClient.invalidateQueries({ queryKey: commentKey(workspaceId, sourceId) });
  }, [job.data, queryClient, workspaceId, sourceId]);
  const collect = useMutation({ mutationFn: () => marketResearchApi.crawlComments(workspaceId, sourceId),
    onSuccess: async (result) => { setSubmittedJobId(result.job_id); await queryClient.invalidateQueries({ queryKey: key(workspaceId, sourceId) }); } });
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
  return <section className="space-y-3 border-b border-slate-200 pb-4" aria-label="Phạm vi xử lý bình luận">
    <h4 className="font-medium">{collector === 'meta_api' ? 'Bình luận Fanpage công ty' : 'Bình luận công khai'}</h4>
    <p className="text-sm text-slate-600">{collector === 'meta_api' ? 'Meta API đọc bình luận và replies theo cursor của các bài đã lưu; không lấy danh tính người viết. Like là số lượt thích của từng bình luận, không phải toàn bộ reactions.' : 'Đọc bình luận từ permalink bằng facebook-cli Tier 0. Số like và reactions thuộc từng bình luận; không thống kê hành vi của một người trên nhiều Page.'}</p>
    {state.isLoading ? <p role="status">Đang tải phạm vi xử lý…</p> : null}
    {state.data ? <p className="text-sm">{state.data.collection_allowed ? collector === 'meta_api' ? 'Đã cấu hình phạm vi local: có thể đọc các lô bình luận của bài đã lưu.' : 'Đã cấu hình: lần Crawl ngay tiếp theo sẽ đọc bình luận công khai mà nguồn trả về.' : 'Chưa mở xử lý bình luận cho nguồn này.'} {state.data.quarantined_candidate_versions_count} bản ghi đang chờ kiểm tra.</p> : null}
    <p className="text-xs text-slate-500">Dữ liệu được che thông tin liên hệ, thay tên theo từng bài, mã hóa và giữ tối đa 24 giờ cho Owner kiểm tra. Bản chờ kiểm tra chưa được gửi sang AI; phân tích chỉ nhận bản Owner đã kiểm tra và chọn riêng. Đây không phải chứng nhận căn cứ pháp lý hoặc sự đồng ý của người bình luận.</p>
    {collector === 'meta_api' ? <div className="space-y-2">
      <p className="text-xs text-slate-600">Còn {state.data?.pending_edges ?? '—'} luồng phân trang/replies chưa hoàn tất. Hết cursor chỉ phản ánh dữ liệu Meta cho phép đọc; không chứng minh có cả bình luận ẩn/xóa.</p>
      {canManage ? <Button size="sm" variant="secondary" loading={collect.isPending} disabled={!state.data?.collection_allowed || !state.data.pending_edges || collecting}
        disabledReason={collecting ? 'Job bình luận đang chờ hoặc xử lý.' : 'Cần phạm vi hiện hành và bài đã Crawl có bình luận chưa xử lý.'}
        onClick={() => collect.mutate()}>Thu thập bình luận và replies</Button> : null}
      {(submittedJobId ?? state.data?.job_id) ? <p className="text-xs" role="status">Job bình luận: {job.data?.status ?? 'đang kiểm tra'} · <Link className="underline" href={'/w/' + workspaceId + '/jobs/' + (submittedJobId ?? state.data?.job_id)}>Theo dõi tiến độ</Link></p> : null}
      {collect.error || job.error ? <p role="alert" className="text-sm text-rose-800">{errorText(collect.error || job.error)}</p> : null}
      {job.data?.error ? <p role="alert" className="text-sm text-rose-800">{job.data.error.message}</p> : null}
    </div> : null}
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

function SuppressCommentControl({ workspaceId, sourceId, commentId }: {
  workspaceId: string; sourceId: string; commentId: string;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState<CommentSuppressionRequest['reason']>('privacy_risk');
  const remove = useMutation({
    mutationFn: () => marketResearchApi.suppressComment(workspaceId, sourceId, commentId, { reason }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] === 'workspaces'
        && query.queryKey[1] === workspaceId && query.queryKey.includes('reports') });
      // Remove every cached candidate in this source before fetching again:
      // known descendants may appear on other pages of the same post.
      const queryKey = commentKey(workspaceId, sourceId);
      await queryClient.cancelQueries({ queryKey });
      await queryClient.resetQueries({ queryKey });
      await queryClient.invalidateQueries({ queryKey: key(workspaceId, sourceId) });
    },
  });
  if (!confirming) return <Button size="sm" variant="secondary" onClick={() => setConfirming(true)}>Loại bình luận khỏi nghiên cứu</Button>;
  return <div className="mt-2 space-y-2" role="group" aria-label="Xác nhận loại bình luận">
    <p className="text-xs text-slate-600">Xóa nội dung và số liệu của bình luận này cùng các replies đã lưu. Lượt crawl sau sẽ bỏ qua mã nguồn này. Đây là xóa dữ liệu trong ứng dụng, không xóa bình luận trên Facebook.</p>
    <label className="block text-xs" htmlFor={'suppression-reason-' + commentId}>Lý do loại dữ liệu</label>
    <select id={'suppression-reason-' + commentId} value={reason} onChange={(event) => setReason(event.currentTarget.value as CommentSuppressionRequest['reason'])} disabled={remove.isPending} className="rounded-md border border-slate-300 p-2 text-sm">
      <option value="privacy_risk">Có thông tin cá nhân cần loại</option>
      <option value="subject_request">Có yêu cầu xóa dữ liệu</option>
      <option value="out_of_scope">Ngoài phạm vi nghiên cứu</option>
    </select>
    <div className="flex flex-wrap gap-2"><Button size="sm" loading={remove.isPending} onClick={() => remove.mutate()}>Xóa và ngăn nhập lại</Button><Button size="sm" variant="secondary" disabled={remove.isPending} onClick={() => setConfirming(false)}>Giữ lại</Button></div>
    {remove.error ? <p role="alert" className="text-xs text-rose-800">{errorText(remove.error)}</p> : null}
  </div>;
}

export function PublicPostComments({ workspaceId, sourceId, evidenceId, canReview, collector = 'public_web' }: {
  workspaceId: string; sourceId: string; evidenceId: string; canReview: boolean; collector?: 'public_web' | 'meta_api';
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
      {!query.isError && first ? <p className="text-xs text-slate-500">{collector === 'meta_api' ? 'Đã nhận ' + String(first.coverage?.returned_count ?? 0) + ' bình luận và replies; ' + String(first.coverage?.received_root_comments ?? 0) + ' bình luận gốc' : 'Đã nhận ' + String(first.coverage?.returned_count ?? 0) + ' bình luận'}{typeof first.coverage?.provider_reported_count === 'number' ? ' / nguồn công bố ' + first.coverage?.provider_reported_count + (collector === 'meta_api' ? ' ở luồng bình luận gốc' : '') : ''}{collector === 'meta_api' ? ' · Còn ' + String(first.coverage?.pending_edges ?? 0) + ' luồng chưa hoàn tất. Chưa xác minh đầy đủ lịch sử; bình luận ẩn/xóa có thể không được Meta trả về.' : '. Chưa xác minh đầy đủ lịch sử; replies chưa được đọc trong Tier 0.'}</p> : null}
      {!query.isError && (first?.suppressed_comments_count ?? 0) > 0 ? <p className="text-xs text-slate-500">Đã loại {first!.suppressed_comments_count} bình luận và ngăn nhập lại theo mã nguồn.</p> : null}
      {!query.isError && first?.status === 'processing_required' ? <p className="text-sm">Owner cần ghi nhận phạm vi xử lý, sau đó Crawl ngay để đọc bình luận.</p> : null}
      {!query.isError && first?.status === 'no_candidates' ? <p className="text-sm">Không có bình luận còn trong thời hạn kiểm tra. Nguồn có thể không trả bình luận hoặc bản chờ đã hết hạn.</p> : null}
      {!query.isError ? comments.map((c) => <article key={c.id} id={'comment-' + c.id} className="border-l-2 border-slate-200 pl-3">
        {c.is_reply ? <p className="text-xs text-slate-500">{c.parent_version_id && comments.some((parent) => parent.id === c.parent_version_id) ? <a className="underline" href={'#comment-' + c.parent_version_id}>Phản hồi cho bình luận đã lưu</a> : 'Phản hồi; bình luận cha không nằm trong phần đang xem.'}</p> : null}
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600"><strong>{c.author_alias ?? 'Bình luận chưa rõ tác giả'}{c.author_identity_known ? '' : ' · chưa xác định tác giả'}</strong><span>Like: {count(c.likes)}</span><span>Reactions: {c.reactions_precision === 'approximate' ? '≈ ' : c.reactions_precision === 'lower_bound' ? '≥ ' : ''}{count(c.reactions)}{c.reactions_raw ? ' (nguồn: ' + c.reactions_raw + ')' : ''}</span><span>Phản hồi: {count(c.reply_count)}</span></div>
        <p className="mt-1 whitespace-pre-wrap break-words text-sm">{c.text || '(Không có chữ được trả về)'}</p>
        {c.content_truncated ? <p className="text-xs text-amber-800">Nội dung vượt giới hạn và đã được cắt; không phải toàn bộ bình luận.</p> : null}
        <p className="mt-1 text-xs text-slate-500">{c.published_at ? 'Đăng ' + new Date(c.published_at).toLocaleString('vi-VN') : 'Không có thời điểm đăng từ nguồn'}</p>
        <SuppressCommentControl workspaceId={workspaceId} sourceId={sourceId} commentId={c.id} />
      </article>) : null}
      <ScreenedCommentAnalysis workspaceId={workspaceId} sourceId={sourceId} evidenceId={evidenceId} comments={comments} />
      {query.hasNextPage ? <Button variant="secondary" size="sm" loading={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>Xem thêm bình luận đã lưu</Button> : null}
    </div> : null}
  </div>;
}
