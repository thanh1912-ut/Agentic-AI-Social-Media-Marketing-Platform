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

import { useSession } from '@/components/session-gate';
import {
  Card,
  Button,
  DemoNotice,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  StatusBadge,
} from '@/components/ui';
import { useCampaignPlanJob, useCampaigns, useCreateCampaign, usePlanCampaign } from '@/lib/hooks';
import { useMocks } from '@/lib/api/config';
import { formatDate, formatNumber } from '@/lib/format';
import { hasPermission } from '@/lib/permissions';

function dateOffset(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function CampaignCard({ workspaceId, campaign }: { workspaceId: string; campaign: Campaign }) {
  const status = CAMPAIGN_STATUS_LABELS[campaign.status];
  return (
    <Card
      title={campaign.name}
      description={`${formatDate(campaign.brief.start_date)} – ${formatDate(campaign.brief.end_date)}`}
      actions={<StatusBadge label={status.label} tone={status.tone} />}
      footer={
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-slate-500">
            {formatNumber(campaign.post_count)} bài · {formatNumber(campaign.approved_count)} đã duyệt ·{' '}
            {formatNumber(campaign.published_count)} đã đăng
          </p>
          <Link
            href={`/w/${workspaceId}/campaigns/${campaign.id}`}
            className="text-sm font-medium text-slate-900 underline"
          >
            Mở chiến dịch
          </Link>
        </div>
      }
    >
      <dl className="space-y-2 text-sm">
        <div>
          <dt className="font-medium text-slate-600">Mục tiêu</dt>
          <dd className="mt-0.5 text-slate-900">{CAMPAIGN_OBJECTIVE_LABELS[campaign.brief.objective]}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">Thông điệp chính</dt>
          <dd className="mt-0.5 text-slate-900">{campaign.brief.key_message}</dd>
        </div>
        <div>
          <dt className="font-medium text-slate-600">Khán giả</dt>
          <dd className="mt-0.5 text-slate-700">{campaign.brief.audience.join(' · ')}</dd>
        </div>
      </dl>
    </Card>
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
    const prompt = planningPrompt.trim();
    if (!prompt) return;
    planCampaign.mutate({ prompt }, { onSuccess: (accepted) => {
      setPlanJobId(accepted.job_id);
      setSelectedConceptId('');
    } });
  }

  function acceptProposal() {
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
      <header>
        <h1 className="text-lg font-semibold text-slate-900">Chiến dịch và lịch nội dung</h1>
        <p className="mt-1 text-sm text-slate-600">
          Xem brief, theo dõi bài viết và mở từng bài để chỉnh sửa hoặc gửi duyệt.
        </p>
      </header>

      {mocksEnabled ? <DemoNotice /> : null}

      {canCreate ? (
        <Card title="Đề xuất brief và 3 concept từ yêu cầu" description="DeepSeek tạo bản đề xuất dựa trên Brand Profile đã xác nhận. Không tạo campaign hoặc đăng bài cho tới khi bạn chọn concept và xác nhận.">
          <form className="space-y-3" onSubmit={requestPlan}>
            <label htmlFor="campaign-planning-prompt" className="block text-sm font-medium text-slate-700">Bạn muốn truyền thông điều gì?</label>
            <textarea id="campaign-planning-prompt" value={planningPrompt} onChange={(event) => setPlanningPrompt(event.target.value)} maxLength={4000} minLength={8} required rows={3} placeholder="Ví dụ: Lên nội dung giáo dục phụ huynh nhận biết tin nhắn giả mạo trường học, không dùng số liệu nếu chưa có nguồn." className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <Button type="submit" loading={planCampaign.isPending || proposalJob.data?.status === 'queued' || proposalJob.data?.status === 'running'} disabled={!planningPrompt.trim() || proposalJob.data?.status === 'queued' || proposalJob.data?.status === 'running'}>Đề xuất bằng AI</Button>
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
            <fieldset className="grid gap-3 md:grid-cols-3"><legend className="mb-2 text-sm font-semibold text-slate-800">Chọn concept</legend>{proposal.concepts.map((concept) => <label key={concept.id} className={`cursor-pointer rounded-lg border p-3 ${selectedConceptId === concept.id ? 'border-sky-600 bg-sky-50' : 'border-slate-200'}`}><input className="mr-2" type="radio" name="campaign-concept" checked={selectedConceptId === concept.id} onChange={() => setSelectedConceptId(concept.id)} /><span className="font-medium">{concept.title}</span><p className="mt-2 text-sm">{concept.angle}</p><p className="mt-2 text-xs text-slate-600">Hook: {concept.hook}</p><p className="mt-1 text-xs text-slate-600">CTA: {concept.cta}</p><p className="mt-1 text-xs text-slate-600">#{(concept.hashtags ?? []).join(' #')}</p></label>)}</fieldset>
            <p className="text-xs text-slate-500">Đề xuất chưa được xác minh sự thật. Hãy kiểm tra mọi claim trước khi tạo bài hoặc duyệt.</p>
            <Button onClick={acceptProposal} loading={createCampaign.isPending} disabled={!selectedConceptId}>Xác nhận concept và tạo campaign</Button>
          </div> : null}
        </Card>
      ) : null}

      {canCreate ? (
        <Card title="Tạo campaign" description="Tạo brief trước. Việc sinh nội dung chỉ khả dụng sau khi hoàn tất các bước xác nhận dữ liệu AI.">
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
            {createCampaign.isError ? <p role="alert" className="md:col-span-2 text-sm text-rose-700">Không tạo được campaign. Kiểm tra brief hoặc thử lại sau.</p> : null}
            <div className="md:col-span-2"><Button type="submit" loading={createCampaign.isPending} disabled={!name.trim() || !message.trim() || !audience.trim()}>Tạo campaign</Button></div>
          </form>
        </Card>
      ) : null}

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
          description="Hoàn tất hồ sơ thương hiệu trước, sau đó tạo campaign đầu tiên từ brief đã xác nhận."
        />
      ) : null}
      {campaigns.data && campaigns.data.items.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {campaigns.data.items.map((campaign) => (
            <CampaignCard key={campaign.id} workspaceId={workspaceId} campaign={campaign} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
