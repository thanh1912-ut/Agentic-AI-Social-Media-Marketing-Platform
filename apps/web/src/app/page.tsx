'use client';

/** Workspace chooser after authentication. */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { ROLE_LABELS } from '@agentic/contracts';

import { SessionGate, useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import { useSelectWorkspace } from '@/lib/hooks';
import { Button, EmptyState, ErrorPanel, LoadingBlock } from '@/components/ui';

export default function TrangGoc() {
  return (
    <SessionGate>
      <ChonDoanhNghiep />
    </SessionGate>
  );
}

function ChonDoanhNghiep() {
  const router = useRouter();
  const { user, session, workspaces } = useSession();
  const selectWorkspace = useSelectWorkspace();
  const onlyWorkspace = workspaces.length === 1 ? workspaces[0] : null;
  const [selectedId, setSelectedId] = useState(
    session.active_workspace_id ?? workspaces[0]?.id ?? '',
  );

  useEffect(() => {
    if (session.active_workspace_id) setSelectedId(session.active_workspace_id);
    else if (workspaces[0]) setSelectedId(workspaces[0].id);
  }, [session.active_workspace_id, workspaces]);

  useEffect(() => {
    if (onlyWorkspace) router.replace(`/w/${onlyWorkspace.id}/documents`);
  }, [onlyWorkspace, router]);

  if (onlyWorkspace) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <LoadingBlock label={`Đang mở doanh nghiệp ${onlyWorkspace.name}…`} />
      </div>
    );
  }

  if (workspaces.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <h1 className="text-lg font-semibold text-slate-900">Xin chào {user.full_name}</h1>
        <p className="mt-1 text-sm text-slate-600">
          Bạn đã đăng nhập bằng email <span className="font-medium">{user.email}</span>.
        </p>
        <div className="mt-5">
          <EmptyState
            tone="warning"
            title="Bạn chưa được cấp quyền vào doanh nghiệp nào"
            description="Tài khoản của bạn chưa thuộc doanh nghiệp nào trên hệ thống. Hãy liên hệ chủ sở hữu doanh nghiệp để được mời tham gia."
            action={
              <Button variant="secondary" onClick={() => router.push('/login')}>
                Đăng nhập bằng tài khoản khác
              </Button>
            }
          />
        </div>
      </div>
    );
  }

  const selectError = selectWorkspace.error instanceof ApiError ? selectWorkspace.error : null;

  return (
    <div className="mx-auto max-w-3xl space-y-5 px-4 py-10">
      <header>
        <h1 className="text-lg font-semibold text-slate-900">Chọn doanh nghiệp</h1>
        <p className="mt-1 text-sm text-slate-600">
          Chọn workspace bạn muốn làm việc. Quyền truy cập sẽ được máy chủ kiểm tra lại ở từng thao tác.
        </p>
      </header>
      {selectError ? (
        <ErrorPanel
          title="Không chuyển được doanh nghiệp"
          message={selectError.message}
          code={selectError.code}
          requestId={selectError.requestId}
          retryable={selectError.retryable}
          onRetry={() => selectWorkspace.mutate(selectedId)}
        />
      ) : null}
      <div className="space-y-3">
        {workspaces.map((workspace) => (
          <label
            key={workspace.id}
            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 ${
              selectedId === workspace.id ? 'border-slate-900 bg-slate-50' : 'border-slate-200'
            }`}
          >
            <input
              type="radio"
              name="workspace"
              value={workspace.id}
              checked={selectedId === workspace.id}
              onChange={() => setSelectedId(workspace.id)}
              className="mt-1"
            />
            <span>
              <span className="block font-medium text-slate-900">{workspace.name}</span>
              <span className="mt-1 block text-sm text-slate-600">
                {workspace.industry || 'Chưa khai báo ngành'} · Vai trò: {ROLE_LABELS[workspace.role]}
              </span>
            </span>
          </label>
        ))}
      </div>
      <Button
        loading={selectWorkspace.isPending}
        disabled={selectedId === ''}
        onClick={() =>
          selectWorkspace.mutate(selectedId, {
            onSuccess: (result) => {
              const workspaceId = result.active_workspace_id ?? selectedId;
              router.replace(`/w/${workspaceId}/documents`);
            },
          })
        }
      >
        Tiếp tục tới tài liệu
      </Button>
    </div>
  );
}
