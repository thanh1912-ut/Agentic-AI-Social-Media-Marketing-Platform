'use client';

import Link from 'next/link';
import { useParams, usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import { ROLE_LABELS } from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { Badge, Button, DemoBadge } from '@/components/ui';
import { environmentLabel, useMocks } from '@/lib/api/config';

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
  { href: '/analytics', label: 'Hiệu quả', description: 'Số liệu và nguồn dữ liệu' },
  { href: '/recommendations', label: 'Đề xuất', description: 'Khuyến nghị dựa trên số liệu' },
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
              <span className="text-sm text-slate-700">
                {workspace.name}
                <span className="ml-2 text-xs text-slate-500">
                  Vai trò: {ROLE_LABELS[workspace.role]}
                </span>
              </span>
            ) : null}
            <span className="text-sm text-slate-500">{user.full_name}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void fetch('/api/v1/auth/logout', {
                  method: 'POST',
                  credentials: 'include',
                }).finally(() => window.location.assign('/login'));
              }}
            >
              Đăng xuất
            </Button>
          </div>
        </div>

        {workspace ? (
          <nav aria-label="Khu vực làm việc" className="mx-auto max-w-7xl px-4">
            <ul className="table-scroll flex gap-1 pb-1">
              {NAV_ITEMS.map((item) => {
                const href = `${base}${item.href}`;
                const isActive =
                  item.href === ''
                    ? pathname === base
                    : pathname.startsWith(href);
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

      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>

      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-500">
        Dữ liệu số liệu luôn ghi rõ nguồn và thời điểm đồng bộ. Khi chưa có số, hệ thống hiển thị
        dấu “—” kèm lý do thay vì coi là 0.
      </footer>
    </div>
  );
}
