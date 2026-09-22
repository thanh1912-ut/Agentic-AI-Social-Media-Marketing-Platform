'use client';

/**
 * Khung khu vực làm việc của một doanh nghiệp.
 *
 * Việc duy nhất của layout này: bảo đảm `workspaceId` trên URL thật sự nằm trong
 * danh sách doanh nghiệp mà người dùng được cấp quyền. Nếu không, người dùng phải
 * đọc được lý do — tuyệt đối không render một khung trống.
 */

import type { ReactNode } from 'react';
import { useParams, useRouter } from 'next/navigation';

import { AppShell } from '@/components/app-shell';
import { useSession } from '@/components/session-gate';
import { Button, PermissionNotice } from '@/components/ui';

export default function WorkspaceLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;

  if (!workspace) {
    return (
      <AppShell>
        <div className="mx-auto max-w-2xl space-y-4 py-6">
          <h1 className="text-lg font-semibold text-slate-900">Không mở được doanh nghiệp này</h1>
          <PermissionNotice
            message={`Bạn không thuộc doanh nghiệp này${
              workspaceId ? ` (mã doanh nghiệp: ${workspaceId})` : ''
            }, nên không xem được dữ liệu bên trong. Hãy kiểm tra lại đường dẫn, hoặc nhờ chủ sở hữu doanh nghiệp mời bạn vào làm việc.`}
          />
          <p className="text-sm text-slate-600">
            Danh sách doanh nghiệp bạn đang tham gia:{' '}
            {workspaces.length > 0
              ? workspaces.map((item) => item.name).join(', ')
              : 'chưa có doanh nghiệp nào.'}
          </p>
          <div>
            <Button variant="secondary" onClick={() => router.push('/')}>
              Về trang chủ
            </Button>
          </div>
        </div>
      </AppShell>
    );
  }

  return <AppShell>{children}</AppShell>;
}
