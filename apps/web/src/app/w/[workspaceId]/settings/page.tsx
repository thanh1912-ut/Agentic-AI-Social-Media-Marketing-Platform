'use client';

/**
 * Cài đặt doanh nghiệp — bản tối thiểu nhưng thật.
 *
 * Có gì: tên doanh nghiệp, vai trò của bạn, danh sách thành viên.
 * Chưa có gì: kết nối Facebook. Phần chưa có phải nói rõ lý do cụ thể, không được
 * để một nút chết không giải thích.
 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import {
  ROLE_DESCRIPTIONS,
  ROLE_LABELS,
  type WorkspaceRole,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import type { ApiMember as Member } from '@/lib/api/types';
import { formatDate, formatDateTime, formatDeadline, formatNumber } from '@/lib/format';
import { useMembers } from '@/lib/hooks';
import { ACTION_REQUIREMENTS, hasPermission, permissionDeniedReason } from '@/lib/permissions';
import {
  Button,
  Card,
  DisabledReason,
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

export default function TrangCaiDat() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const { user, workspaces } = useSession();

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const activeId = workspace ? workspaceId : '';

  const membersQuery = useMembers(activeId);

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
  const canManageConnection = hasPermission(workspace, ACTION_REQUIREMENTS.manageConnection);
  const inviteDeniedReason = permissionDeniedReason(workspace, ACTION_REQUIREMENTS.inviteMember);
  const inviteDisabledReason = canInvite
    ? 'Màn hình mời thành viên chưa có trong bản dựng này, nên nút này chưa hoạt động.'
    : inviteDeniedReason;
  const connectionDisabledReason =
    'Nút kết nối chưa hoạt động vì luồng uỷ quyền OAuth với Facebook chưa có trong bản dựng này.';
  const connectionDeniedReason = canManageConnection
    ? connectionDisabledReason
    : `${connectionDisabledReason} ${permissionDeniedReason(
        workspace,
        ACTION_REQUIREMENTS.manageConnection,
      )}`;

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
          <div className="flex flex-col items-end gap-1">
            <Button disabled disabledReason={inviteDisabledReason}>
              Mời thành viên
            </Button>
            <p className="max-w-xs text-right text-xs text-slate-500">{inviteDisabledReason}</p>
          </div>
        }
      >
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
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
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
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Kết nối Facebook" description="Kênh đăng bài của doanh nghiệp.">
        <div className="space-y-3">
          <UnavailableNotice
            title="Chưa kết nối được Facebook trong bản dựng này"
            reason="Luồng uỷ quyền OAuth với Facebook chưa được nối: máy chủ mới có đặc tả endpoint POST /api/v1/workspaces/{id}/connections/facebook/start ở dạng DRAFT và chưa cấu hình Meta App ID/secret, nên chưa thể xin quyền cho Page hay lấy danh sách Page."
            remedy="Chờ bản cập nhật có luồng kết nối; trong lúc đó hãy đăng bài thủ công trên Facebook. Khi luồng kết nối hoạt động, mục này sẽ cho chọn Page và hiện trạng thái token."
          />
          <div>
            <Button disabled disabledReason={connectionDeniedReason}>
              Kết nối Facebook Page
            </Button>
            <div className="mt-1">
              <DisabledReason>{connectionDeniedReason}</DisabledReason>
            </div>
          </div>
          <p className="text-sm text-slate-600">
            Quyền cần cho việc này:{' '}
            <code className="font-mono">{ACTION_REQUIREMENTS.manageConnection}</code>. Bạn xem được
            trạng thái nhưng không tự kết nối được.
          </p>
        </div>
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
