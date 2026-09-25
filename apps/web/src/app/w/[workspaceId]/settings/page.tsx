'use client';

/**
 * Cài đặt doanh nghiệp — bản tối thiểu nhưng thật.
 *
 * Có gì: tên doanh nghiệp, vai trò, thành viên và trạng thái Page pilot.
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  ROLE_DESCRIPTIONS,
  ROLE_LABELS,
  type WorkspaceRole,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError, api, metaApi, metaQueryKeys } from '@/lib/api';
import type { ApiInviteMemberRequest, ApiInviteMemberResponse, ApiMember as Member } from '@/lib/api/types';
import { formatDate, formatDateTime, formatDeadline, formatNumber } from '@/lib/format';
import { useMembers } from '@/lib/hooks';
import { queryKeys } from '@/lib/query-keys';
import { ACTION_REQUIREMENTS, hasPermission, permissionDeniedReason } from '@/lib/permissions';
import {
  Button,
  Card,
  EmptyState,
  ErrorPanel,
  FieldRow,
  LoadingBlock,
  PermissionNotice,
  StatusBadge,
  UnavailableNotice,
  type Tone,
} from '@/components/ui';

/**
 * KHOẢNG TRỐNG HỢP ĐỒNG: `Member.status` (active/invited/suspended) chưa có bảng
 * nhãn trong `labels.ts`. Khai báo tạm ở đây, một chỗ duy nhất.
 */
const MEMBER_STATUS_LABELS: Record<Member['status'], { label: string; tone: Tone }> = {
  active: { label: 'Đang tham gia', tone: 'success' },
  invited: { label: 'Đã mời, chờ tham gia', tone: 'info' },
  suspended: { label: 'Tạm ngưng', tone: 'warning' },
};

const ROLE_TONE: Record<WorkspaceRole, Tone> = {
  owner: 'info',
  editor: 'neutral',
  viewer: 'neutral',
};

const META_STATUS: Record<
  'unconfigured' | 'configured' | 'verified' | 'error',
  { label: string; tone: Tone }
> = {
  unconfigured: { label: 'Chưa cấu hình', tone: 'neutral' },
  configured: { label: 'Chờ xác minh', tone: 'info' },
  verified: { label: 'Đã xác minh', tone: 'success' },
  error: { label: 'Cần kiểm tra', tone: 'warning' },
};

export default function TrangCaiDat() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, workspaces } = useSession();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<ApiInviteMemberRequest['role']>('editor');
  const [inviteResult, setInviteResult] = useState<ApiInviteMemberResponse | null>(null);

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const activeId = workspace ? workspaceId : '';

  const membersQuery = useMembers(activeId);
  const metaConnectionQuery = useQuery({
    queryKey: metaQueryKeys.connection(activeId),
    queryFn: () => metaApi.connection(activeId),
    enabled: activeId !== '',
  });
  const refreshMembers = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.members(activeId) });
  };
  const inviteMutation = useMutation({
    mutationFn: (body: ApiInviteMemberRequest) => api.workspace.inviteMember(activeId, body),
    onSuccess: async (result) => {
      setInviteResult(result);
      await refreshMembers();
    },
  });
  const resendMutation = useMutation({
    mutationFn: (memberId: string) => api.workspace.resendInvitation(activeId, memberId),
    onSuccess: async (result) => {
      setInviteResult(result);
      await refreshMembers();
    },
  });

  if (!workspace) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold text-slate-900">Không mở được cài đặt</h1>
        <PermissionNotice message="Bạn không thuộc doanh nghiệp này, nên không xem được cài đặt và thành viên của doanh nghiệp." />
        <Button variant="secondary" onClick={() => router.push('/')}>
          Về trang chủ
        </Button>
      </div>
    );
  }

  const loadError = membersQuery.error instanceof ApiError ? membersQuery.error : null;
  const members = membersQuery.data ?? null;
  const canInvite = hasPermission(workspace, ACTION_REQUIREMENTS.inviteMember);
  const inviteDeniedReason = permissionDeniedReason(workspace, ACTION_REQUIREMENTS.inviteMember);
  const connection = metaConnectionQuery.data;
  const connectionStatus = connection ? META_STATUS[connection.status] : null;

  function submitInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = inviteEmail.trim();
    if (!email) return;
    setInviteResult(null);
    inviteMutation.mutate({ email, role: inviteRole });
  }

  const inviteMessage = inviteResult
    ? inviteResult.outcome === 'sent'
      ? 'Đã chuyển lời mời tới dịch vụ email.'
      : inviteResult.outcome === 'email_failed'
        ? 'Email chưa được gửi. Chuyển liên kết này cho người được mời qua kênh riêng.'
        : inviteResult.outcome === 'already_invited'
          ? 'Địa chỉ này đã có lời mời đang chờ. Dùng nút gửi lại trong danh sách.'
          : 'Người này đã là thành viên của doanh nghiệp.'
    : null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">Cài đặt</h1>
        <p className="mt-1 text-sm text-slate-600">
          Thông tin doanh nghiệp, vai trò của bạn và những kết nối ra bên ngoài.
        </p>
      </header>

      <Card title="Doanh nghiệp" description="Thông tin nhận từ máy chủ, không sửa được ở màn hình này.">
        <dl>
          <FieldRow label="Tên doanh nghiệp">{workspace.name}</FieldRow>
          <FieldRow label="Đường dẫn định danh (slug)">
            <code className="font-mono text-sm">{workspace.slug}</code>
          </FieldRow>
          <FieldRow label="Ngành" hint="Do máy chủ trả về; để trống nghĩa là chưa khai báo.">
            {workspace.industry && workspace.industry.trim() !== '' ? (
              workspace.industry
            ) : (
              <span className="text-slate-700">
                — <span className="text-xs text-slate-500">Doanh nghiệp chưa khai báo ngành.</span>
              </span>
            )}
          </FieldRow>
          <FieldRow label="Ngày tạo">{formatDate(workspace.created_at)}</FieldRow>
        </dl>
      </Card>

      <Card title="Vai trò của bạn" description="Vai trò quyết định những việc bạn làm được trong doanh nghiệp.">
        <dl>
          <FieldRow label="Người dùng">
            {user.full_name} · <span className="text-slate-600">{user.email}</span>
          </FieldRow>
          <FieldRow
            label="Vai trò"
            hint={ROLE_DESCRIPTIONS[workspace.role]}
          >
            <StatusBadge label={ROLE_LABELS[workspace.role]} tone={ROLE_TONE[workspace.role]} />
          </FieldRow>
          <FieldRow
            label="Quyền đang có"
            hint="Danh sách quyền do máy chủ cấp; giao diện chỉ dùng để ẩn/hiện nút, máy chủ vẫn kiểm tra lại."
          >
            {workspace.permissions.length > 0 ? (
              <span className="text-sm text-slate-700">
                {formatNumber(workspace.permissions.length)} quyền
              </span>
            ) : (
              <span className="text-slate-700">
                — <span className="text-xs text-slate-500">
                  Vai trò này không có quyền ghi nào; bạn chỉ xem được dữ liệu.
                </span>
              </span>
            )}
          </FieldRow>
        </dl>
      </Card>

      <Card
        title="Thành viên"
        description="Ai đang tham gia doanh nghiệp này và với vai trò nào."
        actions={
          canInvite ? (
            <Button onClick={() => { setInviteOpen((open) => !open); setInviteResult(null); }}>
              {inviteOpen ? 'Đóng biểu mẫu' : 'Mời thành viên'}
            </Button>
          ) : (
            <div className="flex flex-col items-end gap-1">
              <Button disabled disabledReason={inviteDeniedReason}>Mời thành viên</Button>
              <p className="max-w-xs text-right text-xs text-slate-500">{inviteDeniedReason}</p>
            </div>
          )
        }
      >
        {inviteOpen && canInvite ? (
          <form onSubmit={submitInvitation} className="mb-5 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-sm text-slate-600">
              Gửi lời mời với quyền biên tập hoặc chỉ xem. Nếu email chưa được cấu hình, bạn sẽ nhận liên kết để chuyển riêng.
            </p>
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_12rem_auto] sm:items-end">
              <div>
                <label htmlFor="member-invite-email" className="block text-sm font-medium text-slate-700">Email</label>
                <input
                  id="member-invite-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={inviteEmail}
                  onChange={(event) => setInviteEmail(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                />
              </div>
              <div>
                <label htmlFor="member-invite-role" className="block text-sm font-medium text-slate-700">Vai trò</label>
                <select
                  id="member-invite-role"
                  value={inviteRole}
                  onChange={(event) => setInviteRole(event.target.value as ApiInviteMemberRequest['role'])}
                  className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                >
                  <option value="editor">Biên tập viên</option>
                  <option value="viewer">Chỉ xem</option>
                </select>
              </div>
              <Button type="submit" loading={inviteMutation.isPending}>
                {inviteMutation.isPending ? 'Đang gửi…' : 'Tạo lời mời'}
              </Button>
            </div>
            {inviteMutation.error instanceof ApiError ? (
              <ErrorPanel
                title="Không tạo được lời mời"
                message={inviteMutation.error.message}
                code={inviteMutation.error.code}
                requestId={inviteMutation.error.requestId}
                retryable={inviteMutation.error.retryable}
                onRetry={() => inviteMutation.mutate({ email: inviteEmail.trim(), role: inviteRole })}
              />
            ) : null}
            {resendMutation.error instanceof ApiError ? (
              <ErrorPanel
                title="Không gửi lại được lời mời"
                message={resendMutation.error.message}
                code={resendMutation.error.code}
                requestId={resendMutation.error.requestId}
                retryable={resendMutation.error.retryable}
                onRetry={() => {
                  const memberId = resendMutation.variables;
                  if (memberId) resendMutation.mutate(memberId);
                }}
              />
            ) : null}
            {inviteResult && inviteMessage ? (
              <div role="status" className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-700">
                <p>{inviteMessage}</p>
                {inviteResult.invite_url ? (
                  <p className="mt-2 break-all">
                    <a className="font-medium text-slate-900 underline" href={inviteResult.invite_url}>
                      {inviteResult.invite_url}
                    </a>
                  </p>
                ) : null}
              </div>
            ) : null}
          </form>
        ) : null}
        {membersQuery.isPending ? (
          <LoadingBlock label="Đang tải danh sách thành viên…" />
        ) : membersQuery.isError ? (
          loadError?.isForbidden ? (
            <PermissionNotice
              message={loadError.message}
              requiredPermission={loadError.requiredPermission ?? undefined}
            />
          ) : (
            <ErrorPanel
              title="Không tải được danh sách thành viên"
              message={loadError?.message ?? 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'}
              code={loadError?.code}
              requestId={loadError?.requestId}
              retryable={loadError?.retryable ?? true}
              onRetry={() => void membersQuery.refetch()}
            />
          )
        ) : members === null || members.length === 0 ? (
          <EmptyState
            title="Chưa có thành viên nào"
            description="Máy chủ không trả về thành viên nào cho doanh nghiệp này. Nếu bạn cho rằng đây là sai sót, hãy liên hệ đội kỹ thuật."
          />
        ) : (
          <div className="table-scroll">
            <table className="w-full min-w-[720px] border-collapse text-left text-sm">
              <caption className="sr-only">Danh sách thành viên và vai trò trong doanh nghiệp</caption>
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                  <th scope="col" className="px-3 py-2 font-medium">
                    Thành viên
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Vai trò
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Trạng thái
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Thời gian
                  </th>
                  {canInvite ? (
                    <th scope="col" className="px-3 py-2 text-right font-medium">Thao tác</th>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {members.map((member) => {
                  const statusMeta = MEMBER_STATUS_LABELS[member.status];
                  const email =
                    member.user?.email && member.user.email.trim() !== ''
                      ? member.user.email
                      : (member.invited_email ?? '');
                  const displayName = member.user?.full_name.trim()
                    ? member.user.full_name
                    : member.status === 'invited'
                      ? 'Lời mời đang chờ'
                      : 'Chưa có tên hiển thị';
                  return (
                    <tr key={member.id} className="border-b border-slate-100 align-top">
                      <td className="px-3 py-3">
                        <p className="font-medium text-slate-900">
                          {displayName}
                        </p>
                        <p className="text-xs text-slate-600">
                          {email !== '' ? (
                            <code className="font-mono">{email}</code>
                          ) : (
                            '— Máy chủ không trả về email cho thành viên này.'
                          )}
                        </p>
                      </td>
                      <td className="px-3 py-3">
                        <StatusBadge
                          label={ROLE_LABELS[member.role]}
                          tone={ROLE_TONE[member.role]}
                        />
                        <p className="mt-1 text-xs text-slate-500">{ROLE_DESCRIPTIONS[member.role]}</p>
                      </td>
                      <td className="px-3 py-3">
                        <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
                      </td>
                      <td className="px-3 py-3 text-xs text-slate-600">
                        {member.status === 'invited' ? (
                          <>
                            <p>
                              Lời mời hết hạn: {formatDeadline(member.invitation_expires_at ?? null)}
                            </p>
                            <p className="text-slate-500">
                              {member.invitation_expires_at
                                ? `Hạn cụ thể: ${formatDateTime(member.invitation_expires_at)}`
                                : 'Máy chủ không trả về hạn của lời mời này.'}
                            </p>
                          </>
                        ) : member.joined_at ? (
                          <p>Tham gia: {formatDateTime(member.joined_at)}</p>
                        ) : (
                          <p className="text-slate-500">
                            — Máy chủ không trả về mốc thời gian tham gia.
                          </p>
                        )}
                      </td>
                      {canInvite ? (
                        <td className="px-3 py-3 text-right">
                          {member.status === 'invited' ? (
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              loading={resendMutation.isPending && resendMutation.variables === member.id}
                              onClick={() => {
                                setInviteOpen(true);
                                setInviteResult(null);
                                resendMutation.mutate(member.id);
                              }}
                            >
                              Gửi lại lời mời
                            </Button>
                          ) : null}
                        </td>
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Kết nối Facebook" description="Xem trạng thái Page. Thêm Page ID và Page Access Token trong Fanpage & thị trường.">
        {metaConnectionQuery.isPending ? (
          <LoadingBlock label="Đang kiểm tra trạng thái Fanpage…" />
        ) : metaConnectionQuery.isError ? (
          <ErrorPanel
            title="Không tải được kết nối Fanpage"
            message={metaConnectionQuery.error instanceof ApiError ? metaConnectionQuery.error.message : 'Vui lòng tải lại trạng thái kết nối.'}
            onRetry={() => void metaConnectionQuery.refetch()}
            retryable
          />
        ) : connection && connectionStatus ? (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge label={connectionStatus.label} tone={connectionStatus.tone} />
              <p className="text-sm text-slate-700">{connection.message}</p>
            </div>
            {connection.page_id ? (
              <dl>
                <FieldRow label="Fanpage">{connection.page_name || 'Chưa có tên Page'}</FieldRow>
                <FieldRow label="Page ID"><code>{connection.page_id}</code></FieldRow>
                <FieldRow label="Quyền hiện có">
                  {connection.can_publish ? 'Có thể gửi yêu cầu đăng; Meta kiểm tra quyền lúc gửi' : 'Chưa thể gửi yêu cầu đăng'} ·{' '}
                  {connection.can_sync_metrics ? 'có thể đồng bộ số liệu' : 'chưa thể đồng bộ số liệu'}
                </FieldRow>
              </dl>
            ) : null}
            {connection.status === 'unconfigured' ? (
              <UnavailableNotice
                title="Chưa cấu hình Fanpage"
                reason="Workspace chưa có Fanpage đã kết nối."
                remedy="Chủ workspace có thể thêm Page ID và Page Access Token trong trang Fanpage & thị trường."
              />
            ) : null}
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" onClick={() => void metaConnectionQuery.refetch()} loading={metaConnectionQuery.isFetching}>
                Tải lại trạng thái
              </Button>
              <Link href={'/w/' + workspaceId + '/fanpages'} className="inline-flex items-center rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
                Quản lý Fanpage
              </Link>
            </div>
          </div>
        ) : null}
      </Card>

      <p className="text-xs text-slate-500">
        Cần xem lại tiến độ nhập thông tin doanh nghiệp?{' '}
        <Link className="underline" href={`/w/${workspaceId}`}>
          Về màn hình chính
        </Link>
        .
      </p>
    </div>
  );
}
