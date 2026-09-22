'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';

import {
  CAMPAIGN_OBJECTIVE_LABELS,
  CAMPAIGN_STATUS_LABELS,
  type Campaign,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import {
  Card,
  DemoNotice,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  StatusBadge,
} from '@/components/ui';
import { useCampaigns } from '@/lib/hooks';
import { useMocks } from '@/lib/api/config';
import { formatDate, formatNumber } from '@/lib/format';

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
  const mocksEnabled = useMocks();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">Chiến dịch và lịch nội dung</h1>
        <p className="mt-1 text-sm text-slate-600">
          Xem brief, theo dõi bài viết và mở từng bài để chỉnh sửa hoặc gửi duyệt.
        </p>
      </header>

      {mocksEnabled ? <DemoNotice /> : null}

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
