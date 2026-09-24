'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';

import { useSession } from '@/components/session-gate';
import { EmptyState } from '@/components/ui';
import { ApiError } from '@/lib/api';
import type { ApiMetricImportRequest, ApiRecordExperimentOutcomeRequest } from '@/lib/api/types';
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
  useAcceptedRecommendationDrafts,
  useRecommendationExperimentOutcomes,
  useRecordRecommendationExperimentOutcome,
} from '@/lib/hooks';

type MetricPoint = ApiMetricImportRequest['points'][number];
type ExperimentMetric = ApiRecordExperimentOutcomeRequest['metric'];

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

function experimentMetricLabel(metric: ExperimentMetric): string {
  switch (metric) {
    case 'reach': return 'Lượt tiếp cận trung bình';
    case 'views': return 'Lượt xem trung bình';
    case 'engagement_rate_by_reach': return 'Tương tác / tiếp cận';
    case 'click_rate_by_reach': return 'Nhấp / tiếp cận';
  }
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
  const [selectedOutcomeDraftId, setSelectedOutcomeDraftId] = useState('');
  const [experimentMetric, setExperimentMetric] = useState<ExperimentMetric>('engagement_rate_by_reach');
  const [baselineWindowFrom, setBaselineWindowFrom] = useState('');
  const [baselineWindowTo, setBaselineWindowTo] = useState('');
  const [followupWindowFrom, setFollowupWindowFrom] = useState('');
  const [followupWindowTo, setFollowupWindowTo] = useState('');
  const [minExperimentPostAge, setMinExperimentPostAge] = useState('168');
  const [maxExperimentPostAge, setMaxExperimentPostAge] = useState('168');
  const [experimentFormError, setExperimentFormError] = useState<string | null>(null);

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
  const acceptedOutcomeDrafts = useAcceptedRecommendationDrafts(
    workspace ? workspaceId : '',
    targetCampaignId,
    sourceId.trim(),
  );
  const visibleOutcomeDraftId = (acceptedOutcomeDrafts.data?.items ?? []).some((item) => item.id === selectedOutcomeDraftId)
    ? selectedOutcomeDraftId
    : acceptedOutcomeDrafts.data?.items[0]?.id ?? '';
  const experimentOutcomes = useRecommendationExperimentOutcomes(
    workspace ? workspaceId : '',
    visibleOutcomeDraftId,
  );
  const recordExperimentOutcome = useRecordRecommendationExperimentOutcome(
    workspace ? workspaceId : '',
    visibleOutcomeDraftId,
  );
  useEffect(() => {
    if (visibleOutcomeDraftId && visibleOutcomeDraftId !== selectedOutcomeDraftId) {
      setSelectedOutcomeDraftId(visibleOutcomeDraftId);
    }
  }, [selectedOutcomeDraftId, visibleOutcomeDraftId]);
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

  function submitExperimentOutcome() {
    const windowValues = [baselineWindowFrom, baselineWindowTo, followupWindowFrom, followupWindowTo];
    if (windowValues.some((value) => !value || Number.isNaN(new Date(value).getTime()))) {
      setExperimentFormError('Chọn đủ bốn mốc thời gian đo trước và sau khi áp dụng recommendation.');
      return;
    }
    const start = new Date(baselineWindowFrom);
    const baselineEnd = new Date(baselineWindowTo);
    const followupStart = new Date(followupWindowFrom);
    const end = new Date(followupWindowTo);
    if (baselineEnd < start || end < followupStart || baselineEnd >= followupStart) {
      setExperimentFormError('Hai khoảng đo phải hợp lệ và không được chồng lấn.');
      return;
    }
    const minAge = Number(minExperimentPostAge);
    const maxAge = Number(maxExperimentPostAge);
    if (!Number.isInteger(minAge) || !Number.isInteger(maxAge) || minAge < 0 || maxAge < minAge || maxAge > 24 * 365) {
      setExperimentFormError('Khoảng tuổi bài phải là số giờ nguyên hợp lệ.');
      return;
    }
    if (!visibleOutcomeDraftId || !sourceId.trim()) {
      setExperimentFormError('Chọn campaign, nguồn số liệu và brief revision đã chấp nhận.');
      return;
    }
    setExperimentFormError(null);
    recordExperimentOutcome.mutate({
      source_id: sourceId.trim(),
      metric: experimentMetric,
      baseline_window_from: start.toISOString(),
      baseline_window_to: baselineEnd.toISOString(),
      followup_window_from: followupStart.toISOString(),
      followup_window_to: end.toISOString(),
      min_post_age_hours: minAge,
      max_post_age_hours: maxAge,
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
      {dashboard.data ? (
        <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm" aria-labelledby="experiment-outcome-heading">
          <div>
            <h2 id="experiment-outcome-heading" className="text-lg font-semibold text-slate-900">Theo dõi kết quả recommendation</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">
              So sánh snapshot trước và sau khi chấp nhận brief revision, dùng cùng nguồn, cùng metric và cùng khoảng tuổi bài. Đây là số liệu quan sát, không chứng minh recommendation gây ra thay đổi.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="space-y-1 text-sm font-medium text-slate-700">
              Campaign
              <select className="w-full rounded-lg border border-slate-300 px-3 py-2" value={targetCampaignId} onChange={(event) => { setTargetCampaignId(event.target.value); setSelectedOutcomeDraftId(''); }}>
                <option value="">Chọn campaign</option>
                {(campaigns.data?.items ?? []).map((campaign) => <option key={campaign.id} value={campaign.id}>{campaign.name}</option>)}
              </select>
            </label>
            <label className="space-y-1 text-sm font-medium text-slate-700">
              Brief revision đã chấp nhận
              <select className="w-full rounded-lg border border-slate-300 px-3 py-2" value={visibleOutcomeDraftId} onChange={(event) => setSelectedOutcomeDraftId(event.target.value)}>
                <option value="">Chọn revision</option>
                {(acceptedOutcomeDrafts.data?.items ?? []).map((draft) => <option key={draft.id} value={draft.id}>Revision {draft.base_version} · {new Date(draft.created_at).toLocaleString('vi-VN')}</option>)}
              </select>
            </label>
          </div>
          {acceptedOutcomeDrafts.isError ? <p role="alert" className="text-sm text-rose-800">{shortError(acceptedOutcomeDrafts.error)}</p> : null}
          {acceptedOutcomeDrafts.isLoading && sourceId.trim() && targetCampaignId ? <p className="text-sm text-slate-600">Đang tải revision đã chấp nhận…</p> : null}
          {!acceptedOutcomeDrafts.isLoading && sourceId.trim() && targetCampaignId && acceptedOutcomeDrafts.data?.items.length === 0 ? (
            <EmptyState title="Chưa có revision được chấp nhận" description="Chấp nhận một brief revision từ recommendation để bắt đầu theo dõi kết quả." />
          ) : null}
          {!sourceId.trim() ? <p className="text-sm text-slate-600">Nhập mã nguồn số liệu ở phần trên để tìm revision và đo cùng nguồn.</p> : null}
          {visibleOutcomeDraftId ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <label className="space-y-1 text-sm text-slate-700">Metric
                  <select className="w-full rounded-lg border border-slate-300 px-3 py-2" value={experimentMetric} onChange={(event) => setExperimentMetric(event.target.value as ExperimentMetric)}>
                    <option value="reach">Lượt tiếp cận trung bình</option>
                    <option value="views">Lượt xem trung bình</option>
                    <option value="engagement_rate_by_reach">Tương tác / tiếp cận</option>
                    <option value="click_rate_by_reach">Nhấp / tiếp cận</option>
                  </select>
                </label>
                <label className="space-y-1 text-sm text-slate-700">Tuổi bài tối thiểu (giờ)<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" max={24 * 365} step="1" value={minExperimentPostAge} onChange={(event) => setMinExperimentPostAge(event.target.value)} /></label>
                <label className="space-y-1 text-sm text-slate-700">Tuổi bài tối đa (giờ)<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="number" min="0" max={24 * 365} step="1" value={maxExperimentPostAge} onChange={(event) => setMaxExperimentPostAge(event.target.value)} /></label>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="space-y-1 text-sm text-slate-700">Bắt đầu baseline<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="datetime-local" value={baselineWindowFrom} onChange={(event) => setBaselineWindowFrom(event.target.value)} /></label>
                <label className="space-y-1 text-sm text-slate-700">Kết thúc baseline<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="datetime-local" value={baselineWindowTo} onChange={(event) => setBaselineWindowTo(event.target.value)} /></label>
                <label className="space-y-1 text-sm text-slate-700">Bắt đầu follow-up<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="datetime-local" value={followupWindowFrom} onChange={(event) => setFollowupWindowFrom(event.target.value)} /></label>
                <label className="space-y-1 text-sm text-slate-700">Kết thúc follow-up<input className="w-full rounded-lg border border-slate-300 px-3 py-2" type="datetime-local" value={followupWindowTo} onChange={(event) => setFollowupWindowTo(event.target.value)} /></label>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {canApplyRecommendation ? <button type="button" disabled={recordExperimentOutcome.isPending} onClick={submitExperimentOutcome} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{recordExperimentOutcome.isPending ? 'Đang tính và lưu…' : 'Ghi nhận kết quả'}</button> : <p className="text-sm text-slate-600">Chỉ chủ workspace có thể ghi nhận outcome.</p>}
                {recordExperimentOutcome.isError ? <p role="alert" className="text-sm text-rose-800">{shortError(recordExperimentOutcome.error)}</p> : null}
                {experimentFormError ? <p role="alert" className="text-sm text-rose-800">{experimentFormError}</p> : null}
              </div>
              {experimentOutcomes.isError ? <p role="alert" className="text-sm text-rose-800">{shortError(experimentOutcomes.error)}</p> : null}
              {experimentOutcomes.data?.items.length ? (
                <div className="space-y-3">
                  <h3 className="font-semibold text-slate-900">Outcomes đã lưu</h3>
                  {experimentOutcomes.data.items.map((outcome) => (
                    <article key={outcome.id} className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
                      <p className="font-semibold text-slate-900">{experimentMetricLabel(outcome.metric)} · baseline {formatMetric(outcome.baseline.value, outcome.metric.endsWith('_rate_by_reach'))} → follow-up {formatMetric(outcome.followup.value, outcome.metric.endsWith('_rate_by_reach'))}</p>
                      <p className="mt-1">Thay đổi tuyệt đối: {formatMetric(outcome.absolute_change, outcome.metric.endsWith('_rate_by_reach'))}{outcome.metric.endsWith('_rate_by_reach') ? ' điểm %' : ''} · thay đổi tương đối: {outcome.relative_change == null ? 'không tính được (baseline bằng 0)' : formatMetric(outcome.relative_change, true)}</p>
                      <p className="mt-1 text-slate-600">Mẫu: {outcome.baseline.sample_size} → {outcome.followup.sample_size} bài · độ phủ: {formatMetric(outcome.baseline.coverage, true)} → {formatMetric(outcome.followup.coverage, true)}</p>
                      <p className="mt-1 text-xs text-slate-600">Khoảng đo baseline: {new Date(outcome.baseline.window_from).toLocaleString('vi-VN')} – {new Date(outcome.baseline.window_to).toLocaleString('vi-VN')}. Follow-up: {new Date(outcome.followup.window_from).toLocaleString('vi-VN')} – {new Date(outcome.followup.window_to).toLocaleString('vi-VN')}.</p>
                      <p className="mt-1 break-words font-mono text-xs text-slate-600">Evidence IDs: {outcome.baseline.evidence_id} → {outcome.followup.evidence_id}. Snapshot IDs: {outcome.baseline.snapshot_ids.slice(0, 3).join(', ')} → {outcome.followup.snapshot_ids.slice(0, 3).join(', ')}{outcome.baseline.snapshot_ids.length > 3 || outcome.followup.snapshot_ids.length > 3 ? ' … (còn snapshot khác)' : ''}</p>
                      <p className="mt-2 text-xs leading-5 text-slate-600">{outcome.limitations.join(' ')}</p>
                    </article>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
