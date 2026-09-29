'use client';

import Link from 'next/link';
import { useParams, usePathname, useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type ReactNode } from 'react';

import { ROLE_LABELS } from '@agentic/contracts';
import { useSession } from '@/components/session-gate';
import { Badge, DemoBadge } from '@/components/ui';
import { BrandMark, Icon, type IconName } from '@/components/icon';
import { ApiError, api } from '@/lib/api';
import { environmentLabel, useMocks } from '@/lib/api/config';
import { useSelectWorkspace } from '@/lib/hooks';

const NAV_GROUPS: { label: string; items: { href: string; label: string; icon: IconName }[] }[] = [
  { label: 'Không gian làm việc', items: [
    { href: '', label: 'Tổng quan', icon: 'home' },
    { href: '/brand', label: 'Hồ sơ thương hiệu', icon: 'brand' },
    { href: '/documents', label: 'Tài liệu', icon: 'document' },
  ] },
  { label: 'Nội dung & tăng trưởng', items: [
    { href: '/campaigns', label: 'Chiến dịch', icon: 'campaign' },
    { href: '/publishing', label: 'Xuất bản', icon: 'publish' },
    { href: '/research', label: 'Nghiên cứu', icon: 'globe' },
    { href: '/analytics', label: 'Hiệu quả & đề xuất', icon: 'chart' },
  ] },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const { user, workspaces } = useSession();
  const router = useRouter();
  const queryClient = useQueryClient();
  const selectWorkspace = useSelectWorkspace();
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menu = useRef<HTMLDialogElement>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const base = `/w/${workspaceId}`;
  const mocksOn = useMocks();
  const envLabel = environmentLabel();
  const active = (href: string) => href ? pathname.startsWith(`${base}${href}`) : pathname === base;
  const allItems = [...NAV_GROUPS.flatMap((group) => group.items), { href: '/settings', label: 'Cài đặt', icon: 'settings' as const }];
  const pageLabel = allItems.find((item) => active(item.href))?.label ?? 'Khu vực làm việc';

  const logout = useMutation({
    mutationFn: () => api.auth.logout(),
    onSuccess: () => { queryClient.clear(); router.replace('/login'); },
    onError: (error) => setLogoutError(error instanceof ApiError ? error.message : 'Không thể kết thúc phiên. Hãy thử lại.'),
  });

  useEffect(() => { menu.current?.close(); }, [pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const media = window.matchMedia('(min-width: 1024px)');
    const closeOnDesktop = () => { if (media.matches) menu.current?.close(); };
    media.addEventListener('change', closeOnDesktop);
    return () => { document.body.style.overflow = previousOverflow; media.removeEventListener('change', closeOnDesktop); };
  }, [menuOpen]);

  function navigation(mobile = false) {
    return <>
      <div className="sidebar-brand">
        <Link href={workspace ? base : '/'} className="brand-lockup" onClick={() => menu.current?.close()}>
          <BrandMark /><span>Agentic Marketing</span>
        </Link>
        {mobile ? <button type="button" className="sidebar-icon-button" aria-label="Đóng menu" onClick={() => menu.current?.close()}><Icon name="close" /></button> : null}
      </div>
      {workspace ? <div className="sidebar-workspace">
        <span className="workspace-avatar">{workspace.name.trim().slice(0, 1).toUpperCase()}</span>
        <div className="min-w-0 flex-1">
          {workspaces.length > 1 ? <select aria-label="Chọn doanh nghiệp" value={workspace.id} disabled={selectWorkspace.isPending} onChange={(event) => {
            const nextWorkspaceId = event.currentTarget.value;
            selectWorkspace.mutate(nextWorkspaceId, { onSuccess: (session) => { menu.current?.close(); router.push(`/w/${session.active_workspace_id ?? nextWorkspaceId}`); } });
          }}>{workspaces.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select> : <p className="truncate text-sm font-semibold">{workspace.name}</p>}
          <p className="mt-1 text-xs text-slate-500">{ROLE_LABELS[workspace.role]}</p>
        </div>
      </div> : null}
      {workspace ? <nav aria-label={mobile ? 'Menu di động' : 'Khu vực làm việc'} className="sidebar-nav">
        {NAV_GROUPS.map((group) => <div key={group.label} className="sidebar-nav-group">
          <p className="sidebar-group-label">{group.label}</p>
          <ul>{group.items.map((item) => <li key={item.href}>
            <Link href={`${base}${item.href}`} aria-current={active(item.href) ? 'page' : undefined} className={`sidebar-link ${active(item.href) ? 'is-active' : ''}`} onClick={() => menu.current?.close()}>
              <Icon name={item.icon} size={19} /><span>{item.label}</span>{active(item.href) ? <span className="nav-active-dot" /> : null}
            </Link>
          </li>)}</ul>
        </div>)}
      </nav> : null}
      <div className="sidebar-bottom">
        {workspace ? <Link href={`${base}/settings`} className={`sidebar-link ${active('/settings') ? 'is-active' : ''}`} aria-current={active('/settings') ? 'page' : undefined} onClick={() => menu.current?.close()}><Icon name="settings" size={19} />Cài đặt</Link> : null}
        <div className="sidebar-user">
          <span className="user-avatar">{user.full_name.trim().slice(0, 1).toUpperCase()}</span>
          <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{user.full_name}</p><span className="text-xs text-slate-500">Tài khoản của bạn</span></div>
          <button type="button" className="sidebar-icon-button" aria-label="Đăng xuất" title="Đăng xuất" disabled={logout.isPending} onClick={() => { setLogoutError(null); logout.mutate(); }}><Icon name="logout" size={18} /></button>
        </div>
      </div>
    </>;
  }

  return <div className="app-frame">
    <a href="#main-content" className="skip-link">Bỏ qua menu, đến nội dung</a>
    <aside className="app-sidebar">{navigation()}</aside>
    <dialog ref={menu} className="mobile-nav-dialog" aria-label="Điều hướng" onClose={() => { setMenuOpen(false); menuButton.current?.focus(); }} onClick={(event) => { if (event.target === event.currentTarget) menu.current?.close(); }}>
      <div className="mobile-sidebar">{navigation(true)}</div>
    </dialog>
    <div className="app-body">
      <header className="app-topbar">
        <div className="flex min-w-0 items-center gap-3">
          <button ref={menuButton} type="button" className="mobile-menu-button" aria-label="Mở menu" aria-haspopup="dialog" aria-expanded={menuOpen} onClick={() => { menu.current?.showModal(); setMenuOpen(true); }}><Icon name="menu" /></button>
          <div className="breadcrumb"><span className="hidden sm:inline">Không gian làm việc</span><Icon name="chevron-right" size={14} className="hidden sm:block" /><span className="truncate font-medium text-slate-800">{pageLabel}</span></div>
        </div>
        <div className="flex shrink-0 items-center gap-2">{mocksOn ? <DemoBadge label="Bản demo" /> : <span className="workspace-live"><span />Không gian của bạn</span>}{!mocksOn && envLabel ? <Badge tone="info">{envLabel}</Badge> : null}</div>
      </header>
      <main id="main-content" tabIndex={-1} className="app-main">
        {logoutError ? <p role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{logoutError}</p> : null}
        {selectWorkspace.error ? <p role="alert" className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{selectWorkspace.error instanceof ApiError ? selectWorkspace.error.message : 'Không chuyển được doanh nghiệp. Hãy thử lại.'}</p> : null}
        {children}
      </main>
      <footer className="app-footer"><span>Agentic Marketing</span><span>Nội dung của bạn. Quyết định của bạn.</span></footer>
    </div>
  </div>;
}
