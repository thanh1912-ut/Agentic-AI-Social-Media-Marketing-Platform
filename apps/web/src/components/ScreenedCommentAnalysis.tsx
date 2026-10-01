'use client';

import { useRef, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useJob } from '@/lib/hooks';
import { ApiError } from '@/lib/api/client';
import { marketResearchApi, marketResearchKeys, type CommentCandidatesPage } from '@/lib/api/market-research';
import { Button } from './ui';

type Candidate = NonNullable<CommentCandidatesPage['comments']>[number];
const labels: Record<string, string> = { question: 'Câu hỏi', need: 'Nhu cầu', feedback: 'Phản hồi', other: 'Chủ đề khác' };
const errorText = (error: unknown) => error instanceof ApiError ? error.message : 'Không lưu được lô kiểm tra. Thử lại giữ nguyên nội dung để tránh gửi trùng.';

/** Mounted only inside an Owner's bounded review view; never auto-submits. */
export function ScreenedCommentAnalysis({ workspaceId, sourceId, evidenceId, comments }: {
  workspaceId: string; sourceId: string; evidenceId: string; comments: readonly Candidate[];
}) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [reference, setReference] = useState('');
  const [submittedJob, setSubmittedJob] = useState<string | null>(null);
  const requestKey = useRef<string | null>(null);
  const historyKey = ['workspaces', workspaceId, 'comment-analyses', sourceId, evidenceId];
  const state = useQuery({ queryKey: marketResearchKeys.commentProcessing(workspaceId, sourceId),
    queryFn: () => marketResearchApi.commentProcessing(workspaceId, sourceId), enabled: open, staleTime: 0 });
  const history = useInfiniteQuery({ queryKey: historyKey,
    queryFn: ({ pageParam }) => marketResearchApi.commentAnalyses(workspaceId, sourceId, evidenceId, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: open, gcTime: 0, refetchInterval: open ? 10_000 : false,
  });
  const records = history.data?.pages.flatMap((page) => page.items) ?? [];
  const active = records.find((record) => record.status === 'queued' || record.status === 'running');
  const job = useJob(open ? (submittedJob ?? active?.job_id) : null);
  const processing = job.data?.status === 'queued' || job.data?.status === 'running' || Boolean(active);
  // An expired/replaced candidate disappears from the selectable set even if
  // the user has an old edit in memory. Polling does not rewrite an active edit.
  const selected = comments.filter((item) => Date.parse(item.expires_at) > Date.now() && item.id in drafts);
  const characters = selected.reduce((total, item) => total + drafts[item.id]!.length, 0);
  const valid = selected.length > 0 && selected.length <= 50 && characters <= 12000
    && selected.every((item) => drafts[item.id]!.trim().length > 0 && drafts[item.id]!.length <= 1500);
  const send = useMutation({ mutationFn: () => {
    requestKey.current ??= crypto.randomUUID();
    return marketResearchApi.analyzeComments(workspaceId, sourceId, {
      request_key: requestKey.current, decision_id: state.data!.decision_id!,
      policy_revision_no: state.data!.policy_revision_no!, provider_assessment_reference: reference,
      comments: selected.map((item) => ({ version_id: item.id, text: drafts[item.id]! })),
    });
  }, onSuccess: async (accepted) => {
    setSubmittedJob(accepted.job_id);
    await client.invalidateQueries({ queryKey: historyKey });
  } });
  function changeSelection(item: Candidate, checked: boolean) {
    requestKey.current = null;
    setDrafts((previous) => {
      const next = { ...previous };
      if (checked) next[item.id] = item.text ?? '';
      else delete next[item.id];
      return next;
    });
  }
  return <section className="border-t border-slate-200 pt-3" aria-label="Phân tích bình luận đã kiểm tra">
    <Button size="sm" variant="secondary" aria-expanded={open} onClick={() => setOpen(!open)}>
      {open ? 'Thu gọn phân tích bình luận' : 'Rà soát để phân tích bằng Gemini'}
    </Button>
    {open ? <div className="mt-3 space-y-4">
      <p className="text-sm text-slate-600">Chọn và sửa các đoạn tham khảo để bỏ tên người, thông tin liên hệ hoặc chi tiết riêng tư còn sót. Chỉ những bản kiểm tra đã chọn được gửi tới Gemini; bản chưa kiểm tra và trường danh tính người viết không được đưa vào yêu cầu phân tích.</p>
      <p className="text-xs text-amber-800">Tham chiếu đánh giá phải bao gồm phạm vi xử lý và gửi dữ liệu cho nhà cung cấp. Việc Owner ghi nhận không thay thế căn cứ pháp lý hay sự đồng ý cần thiết. Bản kiểm tra và phân tích giữ tối đa 90 ngày; bình luận gốc vẫn theo hạn 24 giờ.</p>
      {comments.map((item, index) => <div key={item.id} className="space-y-2">
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={item.id in drafts}
          disabled={send.isPending || processing} onChange={(event) => changeSelection(item, event.currentTarget.checked)} />Chọn đoạn {index + 1}</label>
        {item.id in drafts ? <label className="block text-sm">Bản kiểm tra đoạn {index + 1}
          <textarea rows={3} maxLength={1500} value={drafts[item.id]} disabled={send.isPending || processing}
            onChange={(event) => { requestKey.current = null; setDrafts((previous) => ({ ...previous, [item.id]: event.target.value })); }}
            className="mt-1 w-full rounded-md border border-slate-300 p-3" />
          <span className="text-xs text-slate-500">{drafts[item.id]!.length}/1.500 ký tự · {item.content_truncated ? 'Nguồn bị cắt ngắn' : 'Phiên nguồn đã lưu'}</span>
        </label> : null}
      </div>)}
      <label className="block text-sm">Tham chiếu đánh giá xử lý và gửi dữ liệu
        <input value={reference} maxLength={1000} disabled={send.isPending || processing}
          onChange={(event) => { requestKey.current = null; setReference(event.target.value); }}
          className="mt-1 w-full rounded-md border border-slate-300 p-2" placeholder="Mã hoặc tham chiếu hồ sơ đánh giá đã có; không nhập dữ liệu cá nhân" />
      </label>
      <p className="text-xs text-slate-600">{selected.length}/50 đoạn · {characters}/12.000 ký tự. Phân tích dùng ngân sách AI tự động 2 USD/workspace/ngày.</p>
      <Button size="sm" loading={send.isPending} disabled={!valid || reference.trim().length < 5 || !state.data?.collection_allowed || processing}
        disabledReason="Chọn bản kiểm tra hợp lệ, ghi tham chiếu đánh giá và bảo đảm phạm vi nguồn đang hoạt động." onClick={() => send.mutate()}>Phân tích bản đã kiểm tra</Button>
      {send.error ? <p role="alert" className="text-sm text-rose-800">{errorText(send.error)}</p> : null}
      {job.data ? <p role="status" className="text-sm">Job phân tích: {job.data.status === 'succeeded' ? 'Đã hoàn tất' : job.data.status === 'failed' ? 'Chưa hoàn tất' : job.data.status === 'queued' ? 'Đang chờ xử lý' : 'Đang xử lý'}{job.data.error?.message ? ' · ' + job.data.error.message : ''}</p> : null}
      {state.error || history.error ? <p role="alert">Không tải được phạm vi hoặc lịch sử phân tích. <Button size="sm" variant="secondary" onClick={() => { void state.refetch(); void history.refetch(); }}>Thử tải lại</Button></p> : null}
      {records.map((record) => <article key={record.id} className="space-y-2 border-l-2 border-slate-200 pl-3">
        <p className="text-sm font-medium">{new Date(record.created_at).toLocaleString('vi-VN')} · {record.status === 'completed' ? 'Đã phân tích' : record.status === 'suppressed' ? 'Đã xóa dữ liệu liên quan' : record.status === 'expired' ? 'Hết thời hạn lưu' : record.status === 'deferred_budget' ? 'Chờ ngân sách' : record.status === 'failed' ? 'Chưa phân tích được' : 'Đang chờ/xử lý'}</p>
        <p className="text-xs text-slate-500">{record.model} · {record.selected_version_ids?.length ?? 0} đoạn được chọn; không đại diện toàn bộ Page.</p>
        {record.error_code ? <details className="text-xs"><summary>Chi tiết trạng thái</summary>{record.error_code}</details> : null}
        {record.result?.topics.map((topic, index) => <div key={index}>
          <p className="text-sm font-medium">{labels[topic.category] ?? topic.category}: {topic.topic}</p><p className="text-sm">{topic.summary}</p>
          <details className="text-xs"><summary>Đoạn đã dùng</summary>{topic.evidence_refs.map((ref) => {
            const citation = record.citations?.find((item) => item.evidence_ref === ref);
            return citation ? <p key={ref} className="my-2 whitespace-pre-wrap">{citation.text}{citation.content_edited ? ' · Bản Owner đã sửa' : ''}{citation.source_content_truncated ? ' · Nguồn cắt ngắn' : ''}</p> : <p key={ref}>Nguồn không còn khả dụng.</p>;
          })}</details>
        </div>)}
        {record.result?.limitations.map((limitation, index) => <p className="text-xs text-slate-500" key={index}>{limitation}</p>)}
      </article>)}
      {history.isLoading ? <p role="status">Đang tải lịch sử phân tích…</p> : !records.length ? <p className="text-sm text-slate-500">Chưa có lô phân tích đã kiểm tra.</p> : null}
      {history.hasNextPage ? <Button size="sm" variant="secondary" loading={history.isFetchingNextPage} onClick={() => void history.fetchNextPage()}>Xem thêm lô phân tích</Button> : null}
    </div> : null}
  </section>;
}
