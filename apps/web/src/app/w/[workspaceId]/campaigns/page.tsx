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
import { useCampaigns, useCreateCampaign } from '@/lib/hooks';
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
  const router = useRouter();
  const mocksEnabled = useMocks();
  const canCreate = hasPermission(workspace, PERMISSIONS.CAMPAIGN_CREATE);
  const [name, setName] = useState('');
  const [message, setMessage] = useState('');
  const [audience, setAudience] = useState('');
  const [objective, setObjective] = useState<CampaignBrief['objective']>('engagement');
  const [startDate, setStartDate] = useState(() => dateOffset(0));
  const [endDate, setEndDate] = useState(() => dateOffset(30));

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
