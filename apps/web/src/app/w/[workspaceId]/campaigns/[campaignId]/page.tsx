'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';

import {
  CAMPAIGN_OBJECTIVE_LABELS,
  CAMPAIGN_STATUS_LABELS,
  CONTENT_PILLAR_LABELS,
  EXPORT_FORMATS,
  POST_FORMATS,
  POST_FORMAT_LABELS,
  POST_STATUS_LABELS,
  PERMISSIONS,
  type CampaignBrief,
  type ContentPillar,
  type PostFormat,
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
  useCreatePost,
  useGenerateContent,
  usePosts,
  useUpdateCampaign,
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
  const createPost = useCreatePost(workspaceId, campaignId);
  const createExport = useCreateExport(workspaceId);
  const updateCampaign = useUpdateCampaign(workspaceId, campaignId);
  const mocksEnabled = useMocks();
  const [count, setCount] = useState('3');
  const [format, setFormat] = useState<'csv' | 'xlsx'>(EXPORT_FORMATS.XLSX);
  const [manualCaption, setManualCaption] = useState('');
  const [manualHashtags, setManualHashtags] = useState('');
  const [manualPillar, setManualPillar] = useState<ContentPillar>('product');
  const [manualFormat, setManualFormat] = useState<PostFormat>(POST_FORMATS.TEXT);
  const [editingBrief, setEditingBrief] = useState(false);
  const [briefName, setBriefName] = useState('');
  const [briefObjective, setBriefObjective] = useState<CampaignBrief['objective']>('awareness');
  const [briefAudience, setBriefAudience] = useState('');
  const [briefMessage, setBriefMessage] = useState('');
  const [briefMustInclude, setBriefMustInclude] = useState('');
  const [briefMustAvoid, setBriefMustAvoid] = useState('');
  const [briefStartDate, setBriefStartDate] = useState('');
  const [briefEndDate, setBriefEndDate] = useState('');

  useEffect(() => {
    const current = campaign.data;
    if (!current || editingBrief) return;
    setBriefName(current.name);
    setBriefObjective(current.brief.objective);
    setBriefAudience(current.brief.audience.join('\n'));
    setBriefMessage(current.brief.key_message);
    setBriefMustInclude((current.brief.must_include ?? []).join('\n'));
    setBriefMustAvoid((current.brief.must_avoid ?? []).join('\n'));
    setBriefStartDate(current.brief.start_date);
    setBriefEndDate(current.brief.end_date);
  }, [campaign.data, editingBrief]);

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
  const canEditPosts = hasPermission(workspace, PERMISSIONS.POST_EDIT);
  const canExport = hasPermission(workspace, PERMISSIONS.EXPORT_CREATE);
  const canEditBrief = hasPermission(workspace, PERMISSIONS.CAMPAIGN_EDIT);

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

  function submitManualPost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const hashtags = manualHashtags.split(/[\s,]+/).map((item) => item.trim()).filter(Boolean);
    createPost.mutate(
      { pillar: manualPillar, format: manualFormat, caption: manualCaption.trim(), hashtags },
      {
        onSuccess: (post) => router.push(`/w/${workspaceId}/campaigns/${campaignId}/posts/${post.id}`),
      },
    );
  }

  function submitBrief(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const splitLines = (value: string) => value.split(/[\n;,]/).map((item) => item.trim()).filter(Boolean);
    const audience = splitLines(briefAudience);
    if (audience.length === 0 || !briefName.trim() || !briefMessage.trim()) return;
    updateCampaign.mutate(
      {
        version: data.version,
        name: briefName.trim(),
        brief: {
          objective: briefObjective,
          objective_note: data.brief.objective_note,
          audience,
          product_ids: [...data.brief.product_ids],
          key_message: briefMessage.trim(),
          must_include: splitLines(briefMustInclude),
          must_avoid: splitLines(briefMustAvoid),
          start_date: briefStartDate,
          end_date: briefEndDate,
        },
        pillars: [...data.pillars],
        channels: [...data.channels],
      },
      { onSuccess: () => setEditingBrief(false) },
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
        {editingBrief ? (
          <form onSubmit={submitBrief} className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label htmlFor="edit-campaign-name" className="block text-sm font-medium text-slate-700">Tên chiến dịch</label>
                <input id="edit-campaign-name" required maxLength={200} value={briefName} onChange={(event) => setBriefName(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="edit-campaign-objective" className="block text-sm font-medium text-slate-700">Mục tiêu</label>
                <select id="edit-campaign-objective" value={briefObjective} onChange={(event) => setBriefObjective(event.target.value as CampaignBrief['objective'])} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
                  {Object.entries(CAMPAIGN_OBJECTIVE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div className="md:col-span-2">
                <label htmlFor="edit-campaign-audience" className="block text-sm font-medium text-slate-700">Khán giả mục tiêu</label>
                <textarea id="edit-campaign-audience" required rows={2} value={briefAudience} onChange={(event) => setBriefAudience(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
                <p className="mt-1 text-xs text-slate-500">Mỗi dòng một nhóm khách hàng.</p>
              </div>
              <div className="md:col-span-2">
                <label htmlFor="edit-campaign-message" className="block text-sm font-medium text-slate-700">Thông điệp chính</label>
                <textarea id="edit-campaign-message" required maxLength={2000} rows={3} value={briefMessage} onChange={(event) => setBriefMessage(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="edit-campaign-includes" className="block text-sm font-medium text-slate-700">Bắt buộc có</label>
                <textarea id="edit-campaign-includes" rows={2} value={briefMustInclude} onChange={(event) => setBriefMustInclude(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="edit-campaign-avoids" className="block text-sm font-medium text-slate-700">Cần tránh</label>
                <textarea id="edit-campaign-avoids" rows={2} value={briefMustAvoid} onChange={(event) => setBriefMustAvoid(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="edit-campaign-start" className="block text-sm font-medium text-slate-700">Ngày bắt đầu</label>
                <input id="edit-campaign-start" type="date" required value={briefStartDate} onChange={(event) => setBriefStartDate(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="edit-campaign-end" className="block text-sm font-medium text-slate-700">Ngày kết thúc</label>
                <input id="edit-campaign-end" type="date" required min={briefStartDate} value={briefEndDate} onChange={(event) => setBriefEndDate(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
            </div>
            {updateCampaign.error ? (
              <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                <p>{updateCampaign.error instanceof ApiError && updateCampaign.error.isVersionConflict ? 'Brief đã được người khác cập nhật. Không có thay đổi nào của bạn bị ghi đè.' : updateCampaign.error instanceof ApiError ? updateCampaign.error.message : 'Không lưu được brief.'}</p>
                {updateCampaign.error instanceof ApiError && updateCampaign.error.isVersionConflict ? (
                  <div className="mt-2"><Button variant="secondary" onClick={() => { setEditingBrief(false); void campaign.refetch(); }}>Tải phiên bản mới nhất</Button></div>
                ) : null}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" loading={updateCampaign.isPending} disabled={!briefName.trim() || !briefMessage.trim() || !briefAudience.trim()}>Lưu brief · v{data.version + 1}</Button>
              <Button type="button" variant="secondary" disabled={updateCampaign.isPending} onClick={() => { updateCampaign.reset(); setEditingBrief(false); }}>Hủy</Button>
            </div>
          </form>
        ) : (
          <>
            <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
              <div><dt className="font-medium text-slate-600">Mục tiêu</dt><dd className="mt-1">{CAMPAIGN_OBJECTIVE_LABELS[data.brief.objective]}</dd></div>
              <div><dt className="font-medium text-slate-600">Kênh</dt><dd className="mt-1">Facebook Page</dd></div>
              <div className="sm:col-span-2"><dt className="font-medium text-slate-600">Khán giả</dt><dd className="mt-1">{data.brief.audience.join(' · ')}</dd></div>
              <div className="sm:col-span-2"><dt className="font-medium text-slate-600">Thông điệp chính</dt><dd className="mt-1">{data.brief.key_message}</dd></div>
              <div><dt className="font-medium text-slate-600">Bắt buộc có</dt><dd className="mt-1">{data.brief.must_include?.join(' · ') || '—'}</dd></div>
              <div><dt className="font-medium text-slate-600">Cần tránh</dt><dd className="mt-1">{data.brief.must_avoid?.join(' · ') || '—'}</dd></div>
            </dl>
            {canEditBrief ? (
              <div className="mt-4"><Button variant="secondary" onClick={() => { updateCampaign.reset(); setEditingBrief(true); }}>Chỉnh sửa brief</Button></div>
            ) : (
              <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.CAMPAIGN_EDIT)} requiredPermission={PERMISSIONS.CAMPAIGN_EDIT} />
            )}
          </>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Tạo bài thủ công" description="Bạn vẫn có thể viết, sửa, duyệt và xuất bài khi chưa bật xử lý AI.">
          {!canEditPosts ? (
            <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_EDIT)} requiredPermission={PERMISSIONS.POST_EDIT} />
          ) : (
            <form onSubmit={submitManualPost} className="space-y-3">
              <div>
                <label htmlFor="manual-pillar" className="block text-sm font-medium text-slate-700">Trụ nội dung</label>
                <select id="manual-pillar" value={manualPillar} onChange={(event) => setManualPillar(event.target.value as ContentPillar)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
                  {Object.entries(CONTENT_PILLAR_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="manual-format" className="block text-sm font-medium text-slate-700">Định dạng</label>
                <select id="manual-format" value={manualFormat} onChange={(event) => setManualFormat(event.target.value as PostFormat)} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm">
                  {Object.entries(POST_FORMAT_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="manual-caption" className="block text-sm font-medium text-slate-700">Nội dung</label>
                <textarea id="manual-caption" required maxLength={10000} rows={5} value={manualCaption} onChange={(event) => setManualCaption(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <div>
                <label htmlFor="manual-hashtags" className="block text-sm font-medium text-slate-700">Hashtag</label>
                <input id="manual-hashtags" value={manualHashtags} onChange={(event) => setManualHashtags(event.target.value)} placeholder="#monviet #bepmoc" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
              </div>
              {createPost.error ? <p role="alert" className="text-sm text-rose-700">{createPost.error instanceof ApiError ? createPost.error.message : 'Không tạo được bản nháp.'}</p> : null}
              <Button type="submit" loading={createPost.isPending} disabled={!manualCaption.trim()}>Tạo bản nháp</Button>
            </form>
          )}
        </Card>

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
