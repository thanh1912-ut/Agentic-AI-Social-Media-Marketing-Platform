import Link from 'next/link';

/** Read only the pinned metadata returned by the campaign API; never raw comments. */
export function CampaignResearchOrigin({ workspaceId, brief }: { workspaceId: string; brief: unknown }) {
  if (!brief || typeof brief !== 'object') return null;
  const data = brief as Record<string, unknown>;
  if (data.market_research_context_invalidated) return <section role="note" className="border-l-2 border-amber-500 pl-4 text-sm">
    <p className="font-medium">Nguồn hướng viết không còn khả dụng</p>
    <p className="mt-1">Dữ liệu liên quan đã bị xóa hoặc hết thời hạn. Chọn hướng viết mới trước khi yêu cầu AI tạo nội dung.</p>
    <Link className="mt-2 inline-block underline" href={'/w/' + workspaceId + '/research?tab=reports'}>Mở Nghiên cứu</Link>
  </section>;
  const context = data.market_research_context;
  if (!context || typeof context !== 'object') return null;
  const pin = context as Record<string, unknown>;
  if (typeof pin.report_id !== 'string' || !/^[a-f0-9-]{36}$/i.test(pin.report_id)) return null;
  const comments = Array.isArray(pin.comment_analysis_refs) ? pin.comment_analysis_refs.length : 0;
  const website = Array.isArray(pin.web_snapshot_ids) ? pin.web_snapshot_ids.length : 0;
  const evidence = Array.isArray(pin.evidence) ? pin.evidence.length : 0;
  return <section aria-label="Nguồn của hướng viết đã chọn" className="border-l-2 border-slate-300 pl-4 text-sm">
    <p className="font-medium">Nguồn của hướng viết đã chọn</p>
    <p className="mt-1 text-slate-600">{evidence} nguồn văn bản · {website} snapshot website · {comments} lô bình luận đã kiểm tra. Phiên bằng chứng được giữ cố định; sửa brief không tự thay nguồn.</p>
    {comments ? <p className="mt-1 text-slate-600">Bình luận là phần tổng hợp AI từ các đoạn được chọn, không đại diện toàn bộ Fanpage.</p> : null}
    <Link className="mt-2 inline-block underline" href={'/w/' + workspaceId + '/research?tab=reports#research-report-' + pin.report_id}>Xem báo cáo đã chọn</Link>
  </section>;
}
