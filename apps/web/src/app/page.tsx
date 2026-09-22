'use client';

/**
 * Trang gốc `/`.
 *
 * Người dùng đã thuộc ít nhất một doanh nghiệp → chuyển thẳng vào doanh nghiệp
 * đầu tiên. Chưa thuộc doanh nghiệp nào → nói rõ lý do và việc cần làm, KHÔNG
 * bao giờ để trắng trang.
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { SessionGate, useSession } from '@/components/session-gate';
import { Button, EmptyState, LoadingBlock } from '@/components/ui';

export default function TrangGoc() {
  return (
    <SessionGate>
      <ChonDoanhNghiep />
    </SessionGate>
  );
}

function ChonDoanhNghiep() {
  const router = useRouter();
  const { user, workspaces } = useSession();

  const firstWorkspace = workspaces[0] ?? null;

  useEffect(() => {
    if (firstWorkspace) router.replace(`/w/${firstWorkspace.id}`);
  }, [firstWorkspace, router]);

  if (firstWorkspace) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10">
        <LoadingBlock label={`Đang mở doanh nghiệp ${firstWorkspace.name}…`} />
      </div>
    );
  }

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
          description="Tài khoản của bạn chưa thuộc doanh nghiệp nào trên hệ thống nên chưa có dữ liệu để hiển thị. Hãy liên hệ chủ sở hữu doanh nghiệp để được mời tham gia. Nếu bạn vừa nhận được thư mời, hãy mở liên kết trong thư đó để hoàn tất tham gia."
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
