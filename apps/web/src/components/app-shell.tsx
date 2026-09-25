'use client';

import Link from 'next/link';
import { useParams, usePathname, useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { ROLE_LABELS } from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { Badge, Button, DemoBadge } from '@/components/ui';
import { ApiError, api } from '@/lib/api';
import { environmentLabel, useMocks } from '@/lib/api/config';
import { useSelectWorkspace } from '@/lib/hooks';

interface NavItem {
  href: string;
  label: string;
  /** Mô tả ngắn cho trình đọc màn hình và tooltip. */
  description: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: '', label: 'Tổng quan', description: 'Tình trạng hồ sơ và việc cần làm' },
  { href: '/brand', label: 'Hồ sơ thương hiệu', description: 'Thông tin doanh nghiệp đã xác nhận' },
  { href: '/documents', label: 'Tài liệu', description: 'Tải lên và xem tình trạng xử lý' },
  { href: '/campaigns', label: 'Chiến dịch', description: 'Chiến dịch và lịch nội dung' },
  { href: '/publishing', label: 'Xuất bản', description: 'Kết nối Facebook và tình trạng đăng bài' },
  { href: '/fanpages', label: 'Fanpage & thị trường', description: 'Nhóm Fanpage, nguồn đối thủ và báo cáo xu hướng' },
  { href: '/analytics', label: 'Hiệu quả', description: 'Số liệu và nguồn dữ liệu' },
  { href: '/analytics#recommendation', label: 'Đề xuất', description: 'Thử nghiệm dựa trên số liệu nhập' },
  { href: '/settings', label: 'Cài đặt', description: 'Thành viên và kết nối' },
];

/**
 * Khung ứng dụng: chọn doanh nghiệp, điều hướng, và nhãn môi trường.
 *
 * Nhãn vai trò hiển thị thường trực để người dùng luôn biết mình đang ở vai nào —
 * đây là cách rẻ nhất để giảm câu hỏi "sao tôi không bấm được nút này".
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const { user, workspaces } = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const selectWorkspace = useSelectWorkspace();
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const logout = useMutation({
    mutationFn: () => api.auth.logout(),
    onSuccess: () => {
      queryClient.clear();
      router.replace('/login');
    },
  });

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const base = `/w/${workspaceId}`;
  const mocksOn = useMocks();
  const envLabel = environmentLabel();

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-900">Agentic Marketing</span>
            {mocksOn ? <DemoBadge label="Bản demo" /> : null}
            {envLabel ? <Badge tone="info">{envLabel}</Badge> : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {workspace ? (
              workspaces.length > 1 ? (
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <span className="sr-only">Chọn doanh nghiệp</span>
                  <select
                    aria-label="Chọn doanh nghiệp"
                    value={workspace.id}
                    disabled={selectWorkspace.isPending}
                    onChange={(event) => {
                      const nextWorkspaceId = event.currentTarget.value;
                      selectWorkspace.mutate(nextWorkspaceId, {
                        onSuccess: (session) => {
                          router.push(`/w/${session.active_workspace_id ?? nextWorkspaceId}`);
                        },
                      });
                    }}
                    className="max-w-56 rounded-lg border border-slate-300 bg-white px-2 py-1.5"
                  >
                    {workspaces.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                  <span className="text-xs text-slate-500">{ROLE_LABELS[workspace.role]}</span>
                </label>
              ) : (
                <span className="text-sm text-slate-700">
                  {workspace.name}
                  <span className="ml-2 text-xs text-slate-500">
                    Vai trò: {ROLE_LABELS[workspace.role]}
                  </span>
                </span>
              )
            ) : null}
            <span className="text-sm text-slate-500">{user.full_name}</span>
            <Button
              variant="ghost"
              size="sm"
              loading={logout.isPending}
              onClick={() => {
                setLogoutError(null);
                logout.mutate(undefined, {
                  onError: (error) => {
                    setLogoutError(
                      error instanceof ApiError
                        ? error.message
                        : 'Không thể kết thúc phiên. Hãy thử lại.',
                    );
                  },
                });
              }}
            >
              Đăng xuất
            </Button>
          </div>
        </div>
        {logoutError ? (
          <p role="alert" className="mx-auto max-w-7xl px-4 pb-2 text-sm text-rose-800">
            {logoutError}
          </p>
        ) : null}
        {selectWorkspace.error ? (
          <p role="alert" className="mx-auto max-w-7xl px-4 pb-2 text-sm text-rose-800">
            {selectWorkspace.error instanceof ApiError
              ? selectWorkspace.error.message
              : 'Không chuyển được doanh nghiệp. Hãy thử lại.'}
          </p>
        ) : null}

        {workspace ? (
          <nav aria-label="Khu vực làm việc" className="mx-auto max-w-7xl px-4">
            <ul className="table-scroll flex gap-1 pb-1">
              {NAV_ITEMS.map((item) => {
                const href = `${base}${item.href}`;
                const navPath = item.href.split('#')[0] ?? '';
                const isActive =
                  navPath === ''
                    ? pathname === base
                    : pathname.startsWith(`${base}${navPath}`);
                return (
                  <li key={item.href}>
                    <Link
                      href={href}
                      title={item.description}
                      aria-current={isActive ? 'page' : undefined}
                      className={`inline-flex whitespace-nowrap rounded-t-lg px-3 py-2 text-sm ${
                        isActive
                          ? 'border-b-2 border-slate-900 font-medium text-slate-900'
                          : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        ) : null}
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {children}
      </main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-500">
        Dữ liệu số liệu luôn ghi rõ nguồn và thời điểm đồng bộ. Khi chưa có số, hệ thống hiển thị
        dấu “—” kèm lý do thay vì coi là 0.
      </footer>
    </div>
  );
}
