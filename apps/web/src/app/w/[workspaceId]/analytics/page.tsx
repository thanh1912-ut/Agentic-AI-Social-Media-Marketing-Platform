'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';

import { useSession } from '@/components/session-gate';
import { EmptyState } from '@/components/ui';
import { ApiError } from '@/lib/api';
import type { ApiMetricImportRequest } from '@/lib/api/types';
import {
  useApplyManualRecommendation,
  useCampaigns,
  useDecideManualRecommendationDraft,
  useManualRecommendationFeedback,
  useSaveManualRecommendation,
  useImportMetricSnapshot,
  useManualAnalyticsDashboard,
  useManualMetricRecommendation,
  usePosts,
} from '@/lib/hooks';

type MetricPoint = ApiMetricImportRequest['points'][number];

function localDateTimeValue(): string {
  const date = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
  return date.toISOString().slice(0, 16);
}

function formatMetric(value: number | null | undefined, percent = false): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('vi-VN', {
    style: percent ? 'percent' : 'decimal',
    maximumFractionDigits: percent ? 2 : 0,
  }).format(value);
}

function shortError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'Không thể tải số liệu. Hãy thử lại sau.';
}

export default function AnalyticsPage() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const posts = usePosts(workspace ? workspaceId : '');
  const campaigns = useCampaigns(workspace ? workspaceId : '');
  const [sourceId, setSourceId] = useState('');
  const [measuredAt, setMeasuredAt] = useState('');
  const [selectedPostId, setSelectedPostId] = useState('');
  const [postAgeHours, setPostAgeHours] = useState('168');
  const [reach, setReach] = useState('');
  const [views, setViews] = useState('');
  const [engagements, setEngagements] = useState('');
  const [clicks, setClicks] = useState('');
  const [spend, setSpend] = useState('');
  const [attributedRevenue, setAttributedRevenue] = useState('');
  const [attributionValid, setAttributionValid] = useState(false);
  const [pendingPoints, setPendingPoints] = useState<MetricPoint[]>([]);
  const [formError, setFormError] = useState<string | null>(null);
  const [targetCampaignId, setTargetCampaignId] = useState('');

  useEffect(() => setMeasuredAt(localDateTimeValue()), []);
  useEffect(() => {
    if (!selectedPostId && posts.data?.items[0]) setSelectedPostId(posts.data.items[0].id);
  }, [posts.data, selectedPostId]);
  useEffect(() => {
    if (!targetCampaignId && campaigns.data?.items[0]) setTargetCampaignId(campaigns.data.items[0].id);
  }, [campaigns.data, targetCampaignId]);

  const dashboard = useManualAnalyticsDashboard(workspace ? workspaceId : '', sourceId.trim());
  const recommendation = useManualMetricRecommendation(workspace ? workspaceId : '', sourceId.trim());
  const saveRecommendation = useSaveManualRecommendation(workspace ? workspaceId : '');
  const feedbackRecommendation = useManualRecommendationFeedback(workspace ? workspaceId : '');
  const applyRecommendation = useApplyManualRecommendation(workspace ? workspaceId : '');
  const decideDraft = useDecideManualRecommendationDraft(workspace ? workspaceId : '');
  const importSnapshot = useImportMetricSnapshot(workspace ? workspaceId : '');
  const postsById = useMemo(
    () => new Map((posts.data?.items ?? []).map((post) => [post.id, post])),
    [posts.data],
  );
  const savedRecommendation = saveRecommendation.data?.source_id === sourceId.trim()
    ? saveRecommendation.data
    : null;
  const applyResult = applyRecommendation.data;
  const appliedRecord = applyResult && applyResult.recommendation.id === savedRecommendation?.id
    ? applyResult.recommendation
    : null;
  const recommendationRecord = appliedRecord ?? (feedbackRecommendation.data?.id === savedRecommendation?.id
    ? feedbackRecommendation.data
    : savedRecommendation);
  const appliedDraft = applyResult && applyResult.recommendation.id === recommendationRecord?.id
    ? applyResult.created_draft
    : null;
  const decidedDraft = decideDraft.data?.id === appliedDraft?.id ? decideDraft.data : appliedDraft;
  const canApplyRecommendation = workspace?.permissions.includes('recommendation:apply') ?? false;

  function parseOptionalNumber(value: string, label: string, integer = false): number | null {
    if (value.trim() === '') return null;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`${label} phải là số 0 trở lên.`);
    if (integer && !Number.isInteger(parsed)) throw new Error(`${label} phải là số nguyên.`);
    return parsed;
  }

  function addPoint() {
    setFormError(null);
    try {
      if (!selectedPostId) throw new Error('Hãy chọn bài viết cần nhập số liệu.');
      const point: MetricPoint = {
        post_id: selectedPostId,
        post_age_hours: Number(postAgeHours),
        reach: parseOptionalNumber(reach, 'Lượt tiếp cận', true),
        views: parseOptionalNumber(views, 'Lượt xem', true),
        engagements: parseOptionalNumber(engagements, 'Tương tác', true),
        clicks: parseOptionalNumber(clicks, 'Lượt nhấp', true),
        spend: parseOptionalNumber(spend, 'Chi phí'),
        attributed_revenue: parseOptionalNumber(attributedRevenue, 'Doanh thu gán nguồn'),
        attribution_valid: attributionValid,
      };
      if (!Number.isInteger(point.post_age_hours) || point.post_age_hours < 0) {
        throw new Error('Tuổi bài viết phải là số giờ nguyên, từ 0 trở lên.');
      }
      if ([point.reach, point.views, point.engagements, point.clicks, point.spend, point.attributed_revenue].every((value) => value == null)) {
        throw new Error('Hãy nhập ít nhất một chỉ số.');
      }
      if (attributionValid && (point.spend == null || point.attributed_revenue == null)) {
        throw new Error('Để xác nhận gán nguồn, cần nhập cả chi phí và doanh thu.');
      }
      if (pendingPoints.some((row) => row.post_id === point.post_id)) {
        throw new Error('Bài viết đã có trong snapshot này.');
      }
      setPendingPoints((current) => [...current, point]);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Dữ liệu chưa hợp lệ.');
    }
  }

  function submitSnapshot() {
    setFormError(null);
    if (!sourceId.trim()) return setFormError('Nhập mã nguồn, ví dụ ID Facebook Page.');
    if (!measuredAt || Number.isNaN(new Date(measuredAt).getTime())) return setFormError('Chọn thời điểm đo hợp lệ.');
    if (pendingPoints.length === 0) return setFormError('Thêm ít nhất một bài trước khi lưu snapshot.');
    importSnapshot.mutate({
      source_id: sourceId.trim(),
      measured_at: new Date(measuredAt).toISOString(),
      points: pendingPoints,
    }, {
      onSuccess: () => setPendingPoints([]),
    });
  }

  if (!workspace) {
    return <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">Không tìm thấy workspace hoặc bạn không có quyền truy cập.</div>;
  }

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-slate-950">Hiệu quả nội dung</h1>
        <p className="max-w-3xl text-sm leading-6 text-slate-600">
          Nhập snapshot từ Meta hoặc số liệu đã ghi thủ công. Báo cáo dùng snapshot mới nhất của mỗi bài; số thiếu được giữ là “—”, không tính thành 0.
        </p>
      </header>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Nhập snapshot số liệu</h2>
        <p className="mt-1 text-sm text-slate-600">Chọn một nguồn và thời điểm đo chung, sau đó thêm từng bài vào snapshot trước khi lưu.</p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="space-y-1 text-sm font-medium text-slate-700">
            Mã nguồn / Facebook Page ID
            <input className="w-full rounded-lg border border-slate-300 px-3 py-2" value={sourceId} onChange={(event) => setSourceId(event.target.value)} placeholder="vd: 1234567890" />
          </label>
          <label className="space-y-1 text-sm font-medium text-slate-700">
            Thời điểm đo
            <input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="datetime-local" value={measuredAt} onChange={(event) => setMeasuredAt(event.target.value)} />
          </label>
        </div>

        {posts.isError ? <p role="alert" className="mt-3 text-sm text-rose-800">{shortError(posts.error)}</p> : null}
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="space-y-1 text-sm text-slate-700 sm:col-span-2 lg:col-span-2">
            Bài viết
            <select className="w-full rounded-lg border border-slate-300 px-3 py-2" value={selectedPostId} onChange={(event) => setSelectedPostId(event.target.value)}>
              <option value="">Chọn bài viết</option>
              {(posts.data?.items ?? []).map((post) => (
                <option key={post.id} value={post.id}>{post.pillar} · {post.current.caption.slice(0, 70)}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-sm text-slate-700">Tuổi bài (giờ)<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" step="1" value={postAgeHours} onChange={(event) => setPostAgeHours(event.target.value)} /></label>
          <label className="space-y-1 text-sm text-slate-700">Lượt tiếp cận<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" value={reach} onChange={(event) => setReach(event.target.value)} /></label>
          <label className="space-y-1 text-sm text-slate-700">Lượt xem<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" value={views} onChange={(event) => setViews(event.target.value)} /></label>
          <label className="space-y-1 text-sm text-slate-700">Tương tác<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" value={engagements} onChange={(event) => setEngagements(event.target.value)} /></label>
          <label className="space-y-1 text-sm text-slate-700">Lượt nhấp<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" value={clicks} onChange={(event) => setClicks(event.target.value)} /></label>
          <label className="space-y-1 text-sm text-slate-700">Chi phí<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" step="0.01" value={spend} onChange={(event) => setSpend(event.target.value)} /></label>
          <label className="space-y-1 text-sm text-slate-700">Doanh thu gán nguồn<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" step="0.01" value={attributedRevenue} onChange={(event) => setAttributedRevenue(event.target.value)} /></label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={attributionValid} onChange={(event) => setAttributionValid(event.target.checked)} />
          Đã xác minh cửa sổ và phương pháp gán doanh thu cho snapshot này
        </label>
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="button" onClick={addPoint} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50">Thêm bài vào snapshot</button>
          <button type="button" onClick={submitSnapshot} disabled={importSnapshot.isPending || pendingPoints.length === 0} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">{importSnapshot.isPending ? 'Đang lưu…' : `Lưu ${pendingPoints.length} bài`}</button>
          {pendingPoints.length > 0 ? <button type="button" onClick={() => setPendingPoints([])} className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100">Xóa danh sách</button> : null}
        </div>
        {formError ? <p role="alert" className="mt-3 text-sm text-rose-800">{formError}</p> : null}
        {importSnapshot.isError ? <p role="alert" className="mt-3 text-sm text-rose-800">{shortError(importSnapshot.error)}</p> : null}
        {importSnapshot.isSuccess ? <p role="status" className="mt-3 text-sm text-emerald-800">Đã lưu {importSnapshot.data.imported_count} dòng số liệu cho snapshot {importSnapshot.data.snapshot_fingerprint.slice(0, 12)}.</p> : null}
        {pendingPoints.length > 0 ? (
          <ul className="mt-4 divide-y divide-slate-100 rounded-xl border border-slate-200">
            {pendingPoints.map((point) => {
              const post = postsById.get(point.post_id);
              return <li key={point.post_id} className="flex items-start justify-between gap-3 p-3 text-sm"><span className="min-w-0"><strong>{post?.pillar ?? 'Bài viết'}</strong><span className="ml-2 text-slate-600">{post?.current.caption.slice(0, 80) ?? point.post_id}</span><span className="ml-2 text-slate-500">Tiếp cận: {point.reach ?? '—'} · tương tác: {point.engagements ?? '—'}</span></span><button type="button" className="text-slate-600 underline" onClick={() => setPendingPoints((current) => current.filter((row) => row.post_id !== point.post_id))}>Bỏ</button></li>;
            })}
          </ul>
        ) : null}
      </section>

      <section className="space-y-3" aria-label="Báo cáo và đề xuất">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div><h2 className="text-lg font-semibold text-slate-900">Báo cáo snapshot</h2><p className="text-sm text-slate-600">Nguồn: {sourceId || 'chưa chọn'} · tuổi bài mặc định 0–30 ngày.</p></div>
          {dashboard.data?.freshness_at ? <span className="text-xs text-slate-500">Đo gần nhất: {new Date(dashboard.data.freshness_at).toLocaleString('vi-VN')}</span> : null}
        </div>
        {dashboard.isError ? <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{shortError(dashboard.error)}</p> : null}
        {dashboard.isLoading && sourceId.trim() ? <p className="text-sm text-slate-600">Đang tải báo cáo…</p> : null}
        {!dashboard.data && !dashboard.isLoading && !dashboard.isError ? (
          <EmptyState
            title="Chưa có snapshot số liệu"
            description={sourceId.trim() ? 'Nhập và lưu snapshot cho nguồn này để xem báo cáo hiệu quả nội dung.' : 'Nhập mã nguồn ở trên, sau đó thêm số liệu bài viết để bắt đầu theo dõi hiệu quả.'}
          />
        ) : null}
        {dashboard.data ? (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(dashboard.data.report.observations ?? []).map((observation) => (
                <article key={observation.metric} className="rounded-xl border border-slate-200 bg-white p-4">
                  <p className="text-xs font-medium text-slate-600">{observation.metric}</p>
                  <p className="mt-1 text-2xl font-semibold text-slate-950">{formatMetric(observation.value, observation.metric.endsWith('_rate_by_reach'))}</p>
                  <p className="mt-1 text-xs text-slate-500">{observation.value == null ? observation.unavailable_reason : `n=${observation.sample_size}; độ phủ ${formatMetric(observation.coverage, true)}`}</p>
                </article>
              ))}
            </div>
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <caption className="px-4 py-3 text-left font-semibold text-slate-900">Kết quả theo trụ nội dung và định dạng</caption>
                <thead className="bg-slate-50 text-left text-xs text-slate-600"><tr><th className="px-4 py-2">Nhóm</th><th className="px-4 py-2">Số bài</th><th className="px-4 py-2">Tiếp cận TB</th><th className="px-4 py-2">Tương tác / tiếp cận</th><th className="px-4 py-2">Nhấp / tiếp cận</th></tr></thead>
                <tbody className="divide-y divide-slate-100">{dashboard.data.groups.map((group) => <tr key={`${group.dimension}:${group.name}`}><th scope="row" className="px-4 py-2 text-left font-medium text-slate-800">{group.dimension === 'pillar' ? 'Trụ' : 'Định dạng'} · {group.name}</th><td className="px-4 py-2">{group.post_count}</td><td className="px-4 py-2">{formatMetric(group.average_reach)}</td><td className="px-4 py-2">{formatMetric(group.engagement_rate_by_reach, true)}</td><td className="px-4 py-2">{formatMetric(group.click_rate_by_reach, true)}</td></tr>)}</tbody>
              </table>
            </div>
            <p className="text-xs leading-5 text-slate-500">{(dashboard.data.report.notes ?? []).join(' ')}</p>
          </>
        ) : null}
        {dashboard.data ? (
          <article id="recommendation" className="scroll-mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5">
            <h3 className="text-base font-semibold text-amber-950">Đề xuất thử nghiệm</h3>
            {recommendation.isLoading ? <p className="mt-2 text-sm text-amber-900">Đang đánh giá dữ liệu…</p> : null}
            {recommendation.isError ? <p role="alert" className="mt-2 text-sm text-rose-800">{shortError(recommendation.error)}</p> : null}
            {recommendation.data ? (
              <div className="mt-2 space-y-2 text-sm text-amber-950">
                <p><strong>{recommendation.data.status === 'proposed' ? 'Có đề xuất' : 'Chưa đủ bằng chứng'}</strong> · {recommendation.data.observation}</p>
                {recommendation.data.hypothesis ? <p>Giả thuyết: {recommendation.data.hypothesis}</p> : null}
                {recommendation.data.action ? <p>Thử nghiệm: {recommendation.data.action}</p> : null}
                {recommendation.data.threshold ? <p>Ngưỡng kiểm tra: {recommendation.data.threshold}</p> : null}
                <p>Mẫu: {recommendation.data.sample_size} bài · độ tin cậy: {formatMetric(recommendation.data.confidence, true)}</p>
                <p>{recommendation.data.limitations.join(' ')}</p>
                {(recommendation.data.evidence_ids ?? []).map((evidenceId) => <p key={evidenceId} className="font-mono text-xs">Bằng chứng: {evidenceId}</p>)}
                {recommendation.data.status === 'proposed' && !savedRecommendation ? (
                  <button
                    type="button"
                    disabled={saveRecommendation.isPending}
                    onClick={() => saveRecommendation.mutate({ source_id: sourceId.trim() })}
                    className="mt-2 rounded-lg bg-amber-900 px-3 py-2 font-medium text-white disabled:opacity-50"
                  >
                    {saveRecommendation.isPending ? 'Đang lưu…' : 'Lưu đề xuất có bằng chứng'}
                  </button>
                ) : null}
                {saveRecommendation.isError ? <p role="alert" className="text-rose-800">{shortError(saveRecommendation.error)}</p> : null}
              </div>
            ) : null}
            {recommendationRecord ? (
              <div className="mt-4 space-y-3 border-t border-amber-200 pt-4 text-sm text-amber-950">
                <p>Trạng thái xử lý: <strong>{recommendationRecord.lifecycle_status}</strong></p>
                {recommendationRecord.feedback ? <p>Feedback: {recommendationRecord.feedback.value}{recommendationRecord.feedback.note ? ` · ${recommendationRecord.feedback.note}` : ''}</p> : null}
                {recommendationRecord.lifecycle_status !== 'applied' ? (
                  <div className="flex flex-wrap gap-2">
                    <button type="button" disabled={feedbackRecommendation.isPending} onClick={() => feedbackRecommendation.mutate({ recommendationId: recommendationRecord.id, body: { value: 'useful' } })} className="rounded-lg border border-amber-800 px-3 py-2 font-medium">Hữu ích</button>
                    <button type="button" disabled={feedbackRecommendation.isPending} onClick={() => feedbackRecommendation.mutate({ recommendationId: recommendationRecord.id, body: { value: 'not_useful' } })} className="rounded-lg border border-amber-800 px-3 py-2 font-medium">Không hữu ích</button>
                    <button type="button" disabled={feedbackRecommendation.isPending} onClick={() => feedbackRecommendation.mutate({ recommendationId: recommendationRecord.id, body: { value: 'already_done' } })} className="rounded-lg border border-amber-800 px-3 py-2 font-medium">Đã làm rồi</button>
                  </div>
                ) : null}
                {feedbackRecommendation.isError ? <p role="alert" className="text-rose-800">{shortError(feedbackRecommendation.error)}</p> : null}
                {canApplyRecommendation && recommendationRecord.lifecycle_status !== 'dismissed' && recommendationRecord.feedback?.value !== 'already_done' && !appliedDraft ? (
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="min-w-64 flex-1 space-y-1">
                      Campaign nhận bản nháp
                      <select className="w-full rounded-lg border border-amber-300 bg-white px-3 py-2" value={targetCampaignId} onChange={(event) => setTargetCampaignId(event.target.value)}>
                        <option value="">Chọn campaign</option>
                        {(campaigns.data?.items ?? []).map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
                      </select>
                    </label>
                    <button
                      type="button"
                      disabled={!targetCampaignId || applyRecommendation.isPending}
                      onClick={() => applyRecommendation.mutate({
                        recommendationId: recommendationRecord.id,
                        body: { campaign_id: targetCampaignId, evidence_ids: recommendationRecord.recommendation.evidence_ids },
                      })}
                      className="rounded-lg bg-slate-900 px-3 py-2 font-medium text-white disabled:opacity-50"
                    >
                      {applyRecommendation.isPending ? 'Đang tạo bản nháp…' : 'Tạo brief revision để xem lại'}
                    </button>
                  </div>
                ) : null}
                {campaigns.isError ? <p role="alert" className="text-rose-800">Không tải được campaign để áp dụng đề xuất.</p> : null}
                {!canApplyRecommendation ? <p>Chỉ chủ workspace có quyền tạo và chấp nhận brief revision.</p> : null}
                {applyRecommendation.isError ? <p role="alert" className="text-rose-800">{shortError(applyRecommendation.error)}</p> : null}
                {appliedDraft && decidedDraft ? (
                  <div className="space-y-3 rounded-xl border border-amber-300 bg-white p-4">
                    <div><strong>Bản nháp brief · phiên bản gốc {decidedDraft.base_version}</strong><p>{applyRecommendation.data?.notice}</p></div>
                    {decidedDraft.changes.map((change) => (
                      <div key={change.field} className="space-y-1 rounded-lg bg-amber-50 p-3">
                        <p className="font-semibold">{change.label}</p>
                        <p>Trước: {JSON.stringify(change.before)}</p>
                        <p>Đề xuất: {JSON.stringify(change.after)}</p>
                        <p>{change.rationale}</p>
                      </div>
                    ))}
                    <p>Trạng thái bản nháp: <strong>{decidedDraft.status}</strong>. Campaign chỉ đổi sau khi chấp nhận.</p>
                    {decidedDraft.status === 'pending_review' && canApplyRecommendation ? (
                      <div className="flex gap-2">
                        <button type="button" disabled={decideDraft.isPending} onClick={() => decideDraft.mutate({ draftId: decidedDraft.id, body: { decision: 'accepted' } })} className="rounded-lg bg-emerald-800 px-3 py-2 font-medium text-white disabled:opacity-50">Chấp nhận revision</button>
                        <button type="button" disabled={decideDraft.isPending} onClick={() => decideDraft.mutate({ draftId: decidedDraft.id, body: { decision: 'discarded' } })} className="rounded-lg border border-slate-300 px-3 py-2 font-medium disabled:opacity-50">Bỏ bản nháp</button>
                      </div>
                    ) : null}
                    {decideDraft.isError ? <p role="alert" className="text-rose-800">{shortError(decideDraft.error)}</p> : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </article>
        ) : null}
      </section>
    </div>
  );
}
