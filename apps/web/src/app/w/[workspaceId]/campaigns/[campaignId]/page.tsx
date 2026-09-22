'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';

import {
  CAMPAIGN_OBJECTIVE_LABELS,
  CAMPAIGN_STATUS_LABELS,
  CONTENT_PILLAR_LABELS,
  EXPORT_FORMATS,
  POST_FORMAT_LABELS,
  POST_STATUS_LABELS,
  PERMISSIONS,
} from '@agentic/contracts';

import { ApiError } from '@/lib/api';
import { hasPermission, permissionDeniedReason } from '@/lib/permissions';
import { useSession } from '@/components/session-gate';
import {
  Button,
  Card,
  DemoNotice,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  PermissionNotice,
  StatusBadge,
} from '@/components/ui';
import {
  useCampaign,
  useCreateExport,
  useGenerateContent,
  usePosts,
} from '@/lib/hooks';
import { useMocks } from '@/lib/api/config';
import { formatDate, formatDateTime } from '@/lib/format';

export default function CampaignDetailPage() {
  const params = useParams<{ workspaceId?: string; campaignId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const campaignId = params?.campaignId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId);
  const campaign = useCampaign(workspace ? workspaceId : '', campaignId);
  const posts = usePosts(workspace ? workspaceId : '', campaignId);
  const generate = useGenerateContent(workspaceId);
  const createExport = useCreateExport(workspaceId);
  const mocksEnabled = useMocks();
  const [count, setCount] = useState('3');
  const [format, setFormat] = useState<'csv' | 'xlsx'>(EXPORT_FORMATS.XLSX);

  if (campaign.isPending || posts.isPending) {
    return <LoadingBlock label="Đang tải chiến dịch và lịch nội dung…" />;
  }
  if (campaign.isError || posts.isError || !campaign.data) {
    return (
      <ErrorPanel
        title="Không tải được chiến dịch"
        message="Không thể mở chiến dịch này. Hãy thử lại hoặc quay về danh sách chiến dịch."
        retryable
        onRetry={() => {
          void campaign.refetch();
          void posts.refetch();
        }}
      />
    );
  }

  const data = campaign.data;
  const status = CAMPAIGN_STATUS_LABELS[data.status];
  const canGenerate = hasPermission(workspace, PERMISSIONS.POST_GENERATE);
  const canExport = hasPermission(workspace, PERMISSIONS.EXPORT_CREATE);

  function submitGenerate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = Number(count);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 10) return;
    generate.mutate(
      { campaign_id: data.id, count: parsed },
      { onSuccess: (accepted) => router.push(`/w/${workspaceId}/jobs/${accepted.job_id}`) },
    );
  }

  function submitExport() {
    createExport.mutate(
      { campaign_id: data.id, format },
      { onSuccess: (accepted) => router.push(`/w/${workspaceId}/jobs/${accepted.job_id}`) },
    );
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-500">
            <Link href={`/w/${workspaceId}/campaigns`} className="underline">Chiến dịch</Link> / chi tiết
          </p>
          <h1 className="mt-1 text-lg font-semibold text-slate-900">{data.name}</h1>
          <p className="mt-1 text-sm text-slate-600">
            {formatDate(data.brief.start_date)} – {formatDate(data.brief.end_date)} · phiên bản {data.version}
          </p>
        </div>
        <StatusBadge label={status.label} tone={status.tone} />
      </header>

      {mocksEnabled ? <DemoNotice /> : null}

      <Card title="Brief chiến dịch" description="Thông tin đầu vào để AI tạo nội dung — chưa tự động thay đổi campaign.">
        <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
          <div><dt className="font-medium text-slate-600">Mục tiêu</dt><dd className="mt-1">{CAMPAIGN_OBJECTIVE_LABELS[data.brief.objective]}</dd></div>
          <div><dt className="font-medium text-slate-600">Kênh</dt><dd className="mt-1">Facebook Page</dd></div>
          <div className="sm:col-span-2"><dt className="font-medium text-slate-600">Khán giả</dt><dd className="mt-1">{data.brief.audience.join(' · ')}</dd></div>
          <div className="sm:col-span-2"><dt className="font-medium text-slate-600">Thông điệp chính</dt><dd className="mt-1">{data.brief.key_message}</dd></div>
          <div><dt className="font-medium text-slate-600">Bắt buộc có</dt><dd className="mt-1">{data.brief.must_include?.join(' · ') || '—'}</dd></div>
          <div><dt className="font-medium text-slate-600">Cần tránh</dt><dd className="mt-1">{data.brief.must_avoid?.join(' · ') || '—'}</dd></div>
        </dl>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Tạo nội dung bằng AI" description="Mỗi lần tạo tối đa 10 bài. Kết quả là bản nháp, vẫn cần chỉnh sửa và duyệt.">
          {!canGenerate ? (
            <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_GENERATE)} requiredPermission={PERMISSIONS.POST_GENERATE} />
          ) : (
            <form onSubmit={submitGenerate} className="flex flex-wrap items-end gap-3">
              <div>
                <label htmlFor="generate-count" className="block text-sm font-medium text-slate-700">Số bài muốn tạo</label>
                <input id="generate-count" type="number" min={1} max={10} value={count} onChange={(event) => setCount(event.target.value)} className="mt-1 w-28 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
                <p className="mt-1 text-xs text-slate-500">Từ 1 đến 10 bài mỗi lần.</p>
              </div>
              <Button type="submit" loading={generate.isPending}>Tạo bản nháp</Button>
            </form>
          )}
          {generate.error ? <p role="alert" className="mt-3 text-sm text-rose-700">{generate.error instanceof ApiError ? generate.error.message : 'Không tạo được job.'}</p> : null}
        </Card>

        <Card title="Xuất nội dung" description="Xuất tệp là tải xuống, không phải đăng bài lên Facebook.">
          {!canExport ? (
            <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.EXPORT_CREATE)} requiredPermission={PERMISSIONS.EXPORT_CREATE} />
          ) : (
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label htmlFor="export-format" className="block text-sm font-medium text-slate-700">Định dạng</label>
                <select id="export-format" value={format} onChange={(event) => setFormat(event.target.value as 'csv' | 'xlsx')} className="mt-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
                  <option value={EXPORT_FORMATS.XLSX}>Excel (XLSX)</option>
                  <option value={EXPORT_FORMATS.CSV}>CSV</option>
                </select>
              </div>
              <Button variant="secondary" onClick={submitExport} loading={createExport.isPending}>Tạo tệp xuất</Button>
            </div>
          )}
          {createExport.error ? <p role="alert" className="mt-3 text-sm text-rose-700">Không tạo được tệp xuất. Hãy thử lại.</p> : null}
        </Card>
      </div>

      <Card title="Lịch nội dung" description="Mở một bài để xem preview Facebook, sửa, xem lịch sử và gửi duyệt.">
        {!posts.data || posts.data.items.length === 0 ? (
          <EmptyState title="Chưa có bài viết" description="Tạo bản nháp bằng AI hoặc chờ backend trả về nội dung cho campaign này." />
        ) : (
          <div className="table-scroll">
            <table className="min-w-[760px] w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
                <tr><th className="px-3 py-3">Bài viết</th><th className="px-3 py-3">Trụ nội dung</th><th className="px-3 py-3">Định dạng</th><th className="px-3 py-3">Trạng thái</th><th className="px-3 py-3">Cập nhật</th><th className="px-3 py-3" /></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {posts.data.items.map((post) => {
                  const postStatus = POST_STATUS_LABELS[post.status];
                  return <tr key={post.id}>
                    <td className="max-w-sm px-3 py-3"><p className="font-medium text-slate-900">{post.current.caption.slice(0, 90)}{post.current.caption.length > 90 ? '…' : ''}</p><p className="mt-1 text-xs text-slate-500">Bản {post.version}</p></td>
                    <td className="px-3 py-3 text-slate-700">{CONTENT_PILLAR_LABELS[post.pillar]}</td>
                    <td className="px-3 py-3 text-slate-700">{POST_FORMAT_LABELS[post.format]}</td>
                    <td className="px-3 py-3"><StatusBadge label={post.requires_reapproval ? 'Cần duyệt lại' : postStatus.label} tone={post.requires_reapproval ? 'warning' : postStatus.tone} /></td>
                    <td className="px-3 py-3 text-slate-600">{formatDateTime(post.updated_at)}</td>
                    <td className="px-3 py-3"><Link href={`/w/${workspaceId}/campaigns/${data.id}/posts/${post.id}`} className="font-medium text-slate-900 underline">Mở bài</Link></td>
                  </tr>;
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
