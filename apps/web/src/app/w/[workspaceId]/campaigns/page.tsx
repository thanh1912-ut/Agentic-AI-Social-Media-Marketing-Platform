'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import {
  CAMPAIGN_OBJECTIVE_LABELS,
  CAMPAIGN_STATUS_LABELS,
  PERMISSIONS,
  type CampaignBrief,
  type Campaign,
} from '@agentic/contracts';

import { Icon } from '@/components/icon';
import { useSession } from '@/components/session-gate';
import {
  Card,
  Button,
  DemoNotice,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  PageHeader,
  StatusBadge,
} from '@/components/ui';
import { useCampaignPlanJob, useCampaigns, useCreateCampaign, usePlanCampaign } from '@/lib/hooks';
import { useMocks } from '@/lib/api/config';
import { formatDate, formatNumber } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';
import { pageConnectionDisabledReason, pageConnectionReady } from '@/lib/page-connection';

function dateOffset(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function CampaignCard({ workspaceId, campaign }: { workspaceId: string; campaign: Campaign }) {
  const status = CAMPAIGN_STATUS_LABELS[campaign.status];
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 transition-colors hover:border-teal-300">
      <div className="flex flex-wrap items-start gap-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-800"><Icon name="campaign" size={20} /></span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-semibold text-slate-900"><Link href={`/w/${workspaceId}/campaigns/${campaign.id}`} className="hover:text-teal-800">{campaign.name}</Link></h2>
            <StatusBadge label={status.label} tone={status.tone} />
          </div>
          <p className="mt-1 text-xs text-slate-500">{formatDate(campaign.brief.start_date)} – {formatDate(campaign.brief.end_date)} · {CAMPAIGN_OBJECTIVE_LABELS[campaign.brief.objective]}</p>
          <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-700">{campaign.brief.key_message}</p>
          <p className="mt-1 text-xs text-slate-500">Khán giả: {campaign.brief.audience.join(' · ')}</p>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
            <p className="text-xs text-slate-500">{formatNumber(campaign.post_count)} bài · {formatNumber(campaign.approved_count)} đã duyệt · {formatNumber(campaign.published_count)} đã đăng</p>
            <Link href={`/w/${workspaceId}/campaigns/${campaign.id}`} className="inline-flex items-center gap-2 text-sm font-semibold text-teal-800">Mở chiến dịch <Icon name="arrow-right" size={16} /></Link>
          </div>
        </div>
      </div>
    </article>
  );
}

export default function CampaignsPage() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId);
  const campaigns = useCampaigns(workspace ? workspaceId : '');
  const createCampaign = useCreateCampaign(workspaceId);
  const planCampaign = usePlanCampaign(workspaceId);
  const [planJobId, setPlanJobId] = useState<string | null>(null);
  const proposalJob = useCampaignPlanJob(workspaceId, planJobId);
  const proposal = proposalJob.data?.proposal;
  const router = useRouter();
  const mocksEnabled = useMocks();
  const canCreate = hasPermission(workspace, PERMISSIONS.CAMPAIGN_CREATE);
  const pageReady = pageConnectionReady(workspace);
  const pageGateReason = pageConnectionDisabledReason(workspace);
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  const [audience, setAudience] = useState('');
  const [objective, setObjective] = useState<CampaignBrief['objective']>('engagement');
  const [startDate, setStartDate] = useState(() => dateOffset(0));
  const [endDate, setEndDate] = useState(() => dateOffset(30));
  const [planningPrompt, setPlanningPrompt] = useState('');
  const [selectedConceptId, setSelectedConceptId] = useState('');

  function requestPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pageReady) return;
    const prompt = planningPrompt.trim();
    if (!prompt) return;
    planCampaign.mutate({ prompt }, { onSuccess: (accepted) => {
      setPlanJobId(accepted.job_id);
      setSelectedConceptId('');
    } });
  }

  function acceptProposal() {
    if (!pageReady) return;
    if (!proposal) return;
    const concept = proposal.concepts.find((item) => item.id === selectedConceptId) ?? proposal.concepts[0];
    if (!concept) return;
    createCampaign.mutate({
      name: proposal.campaign_name,
      brief: {
        objective: proposal.objective,
        audience: [...proposal.audience],
        product_ids: [],
        key_message: proposal.key_message,
        must_include: [...(proposal.must_include ?? [])],
        must_avoid: [...(proposal.must_avoid ?? [])],
        start_date: proposal.start_date,
        end_date: proposal.end_date,
      },
      content_plan: {
        strategy_summary: `${proposal.topic}. ${concept.angle}`,
        slots: [{
          id: concept.id,
          scheduled_date: proposal.start_date,
          pillar: proposal.pillars[0] ?? 'education',
          format: concept.format,
          topic: `${concept.title}: ${proposal.topic}`,
        }],
      },
      pillars: [...proposal.pillars],
      channels: ['facebook_page'],
    }, { onSuccess: (campaign) => router.push(`/w/${workspaceId}/campaigns/${campaign.id}`) });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pageReady) return;
    const audiences = audience.split(/[\n;,]/).map((item) => item.trim()).filter(Boolean);
    if (!name.trim() || !message.trim() || audiences.length === 0) return;
    createCampaign.mutate(
      {
        name: name.trim(),
        brief: {
          objective,
          audience: audiences,
          product_ids: [],
          key_message: message.trim(),
          must_include: [],
          must_avoid: [],
          start_date: startDate,
          end_date: endDate,
        },
        pillars: ['product', 'education'],
        channels: ['facebook_page'],
      },
      { onSuccess: (campaign) => router.push(`/w/${workspaceId}/campaigns/${campaign.id}`) },
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Kế hoạch nội dung"
        title="Chiến dịch"
        description="Từ ý tưởng đến bài đã duyệt. Quản lý brief, bản nháp và lịch nội dung ở một nơi."
        actions={canCreate ? <a href="#create-campaign" className="inline-flex items-center gap-2 rounded-xl bg-teal-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-900"><Icon name="plus" size={17} /> Tạo chiến dịch</a> : undefined}
      />

      {mocksEnabled ? <DemoNotice /> : null}
      {!pageReady ? <p role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">Có thể xem chiến dịch cũ. Tạo chiến dịch và dùng AI chỉ mở sau khi Owner kết nối Fanpage tại <Link className="font-medium underline" href={`/w/${workspaceId}/settings`}>Cài đặt</Link>. {pageGateReason}</p> : null}

      <section aria-label="Danh sách chiến dịch" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-slate-900">Chiến dịch của bạn</h2>
          {campaigns.data ? <span className="text-xs text-slate-500">{formatNumber(campaigns.data.items.length)} chiến dịch đang hiển thị</span> : null}
        </div>
      {campaigns.isPending ? <LoadingBlock label="Đang tải danh sách chiến dịch…" /> : null}
      {campaigns.isError ? (
        <ErrorPanel
          title="Không tải được chiến dịch"
          message="Hệ thống chưa tải được danh sách chiến dịch. Bạn có thể thử lại mà không tạo thêm dữ liệu."
          retryable
          onRetry={() => void campaigns.refetch()}
        />
      ) : null}
      {campaigns.data && campaigns.data.items.length === 0 ? (
        <EmptyState
          title="Chưa có chiến dịch nào"
          description="Viết và áp dụng hồ sơ thương hiệu, rồi tạo chiến dịch đầu tiên bằng yêu cầu AI hoặc brief của bạn."
        />
      ) : null}
      {campaigns.data && campaigns.data.items.length > 0 ? (
        <div className="grid gap-3 xl:grid-cols-2">
          {campaigns.data.items.map((campaign) => (
            <CampaignCard key={campaign.id} workspaceId={workspaceId} campaign={campaign} />
          ))}
        </div>
      ) : null}
      </section>

      {canCreate ? <div id="create-campaign" className="scroll-mt-24 border-t border-slate-200 pt-6"><h2 className="text-lg font-semibold text-slate-900">Bắt đầu một chiến dịch</h2><p className="mt-1 text-sm text-slate-600">Nhờ AI lên ý tưởng từ hồ sơ bạn viết, hoặc tự xây brief theo kế hoạch đã có.</p></div> : null}

      {canCreate ? (
        <Card variant="panel" title="Lên ý tưởng cùng AI" description="Nhận brief và 3 hướng nội dung từ yêu cầu của bạn. Chỉ tạo chiến dịch sau khi bạn chọn và xác nhận.">
          <form className="space-y-3" onSubmit={requestPlan}>
            <label htmlFor="campaign-planning-prompt" className="block text-sm font-medium text-slate-700">Bạn muốn truyền thông điều gì?</label>
            <textarea id="campaign-planning-prompt" value={planningPrompt} onChange={(event) => setPlanningPrompt(event.target.value)} maxLength={4000} minLength={8} required rows={3} placeholder="Ví dụ: Lên nội dung giáo dục phụ huynh nhận biết tin nhắn giả mạo trường học, không dùng số liệu nếu chưa có nguồn." className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <Button type="submit" loading={planCampaign.isPending || proposalJob.data?.status === 'queued' || proposalJob.data?.status === 'running'} disabled={!pageReady || !planningPrompt.trim() || proposalJob.data?.status === 'queued' || proposalJob.data?.status === 'running'} disabledReason={!pageReady ? pageGateReason : !planningPrompt.trim() ? 'Nhập yêu cầu trước khi gửi.' : undefined}>Đề xuất bằng AI</Button>
          </form>
          {planCampaign.error ? <p role="alert" className="mt-3 text-sm text-rose-700">{planCampaign.error instanceof Error ? planCampaign.error.message : 'Không gửi được yêu cầu lập kế hoạch.'}</p> : null}
          {planJobId ? <div role="status" aria-live="polite" className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
            <p className="font-medium">Tác vụ {proposalJob.data?.status ?? 'đang tải'} · <Link className="underline" href={`/w/${workspaceId}/jobs/${planJobId}`}>mở tiến trình</Link></p>
            {proposalJob.data?.error ? <p className="mt-1 text-rose-700">{String(proposalJob.data.error.message ?? 'Không thể lập kế hoạch.')}</p> : null}
            {proposalJob.data?.status === 'succeeded' && !proposal ? <p className="mt-1 text-rose-700">Tác vụ kết thúc nhưng không có đề xuất đọc được. Mở chi tiết tác vụ để xem lỗi.</p> : null}
          </div> : null}
          {proposal ? <div className="mt-4 space-y-4 border-t border-slate-200 pt-4">
            <div><h2 className="font-semibold text-slate-900">{proposal.campaign_name}</h2><p className="mt-1 text-sm text-slate-600">{proposal.topic} · {proposal.objective} · {proposal.start_date}–{proposal.end_date}</p><p className="mt-2 text-sm text-slate-800">{proposal.key_message}</p><p className="mt-1 text-xs text-slate-600">Khán giả: {proposal.audience.join(' · ')} · Giọng: {proposal.tone}</p></div>
            {(proposal.assumptions ?? []).length ? <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Giả định cần kiểm tra: {(proposal.assumptions ?? []).join(' · ')}</p> : null}
            <fieldset className="grid gap-3 md:grid-cols-3"><legend className="mb-2 text-sm font-semibold text-slate-800">Chọn concept</legend>{proposal.concepts.map((concept) => <label key={concept.id} className={`cursor-pointer rounded-lg border p-3 ${selectedConceptId === concept.id ? 'border-teal-600 bg-teal-50' : 'border-slate-200'}`}><input className="mr-2" type="radio" name="campaign-concept" checked={selectedConceptId === concept.id} onChange={() => setSelectedConceptId(concept.id)} /><span className="font-medium">{concept.title}</span><p className="mt-2 text-sm">{concept.angle}</p><p className="mt-2 text-xs text-slate-600">Hook: {concept.hook}</p><p className="mt-1 text-xs text-slate-600">CTA: {concept.cta}</p><p className="mt-1 text-xs text-slate-600">#{(concept.hashtags ?? []).join(' #')}</p></label>)}</fieldset>
            <p className="text-xs text-slate-500">Đề xuất chưa được xác minh sự thật. Hãy kiểm tra mọi claim trước khi tạo bài hoặc duyệt.</p>
            {createCampaign.error ? <p role="alert" className="text-sm text-rose-700">{createCampaign.error instanceof Error ? createCampaign.error.message : 'Không tạo được chiến dịch. Kiểm tra đề xuất rồi thử lại.'}</p> : null}
            <Button onClick={acceptProposal} loading={createCampaign.isPending} disabled={!pageReady || !selectedConceptId} disabledReason={!pageReady ? pageGateReason : 'Chọn một concept trước khi tạo chiến dịch.'}>Xác nhận concept và tạo chiến dịch</Button>
          </div> : null}
        </Card>
      ) : null}

      {canCreate ? (
        <details className="rounded-2xl border border-slate-200 bg-white">
          <summary className="cursor-pointer px-5 py-4 font-semibold text-slate-900">Tự viết brief chiến dịch <span className="ml-2 text-sm font-normal text-slate-500">Dành cho khi bạn đã có kế hoạch</span></summary>
          <div className="px-5 pb-5">
          <form className="grid gap-4 md:grid-cols-2" onSubmit={submit}>
            <div>
              <label htmlFor="campaign-name" className="block text-sm font-medium text-slate-700">Tên chiến dịch</label>
              <input id="campaign-name" required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="campaign-objective" className="block text-sm font-medium text-slate-700">Mục tiêu</label>
              <select id="campaign-objective" value={objective} onChange={(event) => setObjective(event.target.value as CampaignBrief['objective'])} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
                {Object.entries(CAMPAIGN_OBJECTIVE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </div>
            <div className="md:col-span-2">
              <label htmlFor="campaign-message" className="block text-sm font-medium text-slate-700">Thông điệp chính</label>
              <textarea id="campaign-message" required maxLength={2000} rows={2} value={message} onChange={(event) => setMessage(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div className="md:col-span-2">
              <label htmlFor="campaign-audience" className="block text-sm font-medium text-slate-700">Khán giả mục tiêu</label>
              <textarea id="campaign-audience" required rows={2} value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="Phân cách nhóm khách bằng dấu phẩy hoặc xuống dòng" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="campaign-start" className="block text-sm font-medium text-slate-700">Ngày bắt đầu</label>
              <input id="campaign-start" type="date" required value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <div>
              <label htmlFor="campaign-end" className="block text-sm font-medium text-slate-700">Ngày kết thúc</label>
              <input id="campaign-end" type="date" required min={startDate} value={endDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </div>
            {createCampaign.isError ? <p role="alert" className="md:col-span-2 text-sm text-rose-700">Không tạo được chiến dịch. Kiểm tra brief hoặc thử lại sau.</p> : null}
            <div className="md:col-span-2"><Button type="submit" loading={createCampaign.isPending} disabled={!pageReady || !name.trim() || !message.trim() || !audience.trim()} disabledReason={!pageReady ? pageGateReason : 'Nhập tên, thông điệp và đối tượng trước khi tạo chiến dịch.'}>Tạo chiến dịch</Button></div>
          </form>
          </div>
        </details>
      ) : null}
    </div>
  );
}
