'use client';

import Image from 'next/image';
import { useEffect, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';

import { ROLE_LABELS } from '@agentic/contracts';
import { SessionGate, useSession } from '@/components/session-gate';
import { Button, ErrorPanel, LoadingBlock } from '@/components/ui';
import { ApiError, api, workspaceApi } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';
import { useSelectWorkspace } from '@/lib/hooks';

export default function TrangGoc() {
  return <SessionGate><ChonDoanhNghiep /></SessionGate>;
}

function ChonDoanhNghiep() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, session, workspaces } = useSession();
  const selectWorkspace = useSelectWorkspace();
  const [selectedId, setSelectedId] = useState(session.active_workspace_id ?? workspaces[0]?.id ?? '');
  const [connectNew, setConnectNew] = useState(workspaces.length === 0);

  useEffect(() => {
    if (session.active_workspace_id) setSelectedId(session.active_workspace_id);
    else if (workspaces[0]) setSelectedId(workspaces[0].id);
  }, [session.active_workspace_id, workspaces]);

  const selected = workspaces.find((workspace) => workspace.id === selectedId) ?? null;
  const onlyWorkspace = workspaces.length === 1 ? workspaces[0] : undefined;
  const onlyActiveWorkspace = onlyWorkspace?.page_connection_state === 'active';
  useEffect(() => {
    if (onlyActiveWorkspace && onlyWorkspace) router.replace(`/w/${onlyWorkspace.id}/brand`);
  }, [onlyActiveWorkspace, onlyWorkspace, router]);

  if (onlyActiveWorkspace && onlyWorkspace) return <div className="mx-auto max-w-3xl px-4 py-10"><LoadingBlock label={`Đang mở ${onlyWorkspace.name}…`} /></div>;

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-10 sm:px-8 sm:py-16">
      <header className="max-w-2xl">
        <p className="text-sm font-semibold text-pink-800">AGENTIC MARKETING</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">Chọn doanh nghiệp để bắt đầu</h1>
        <p className="mt-3 text-base leading-7 text-slate-600">
          Xin chào {user.full_name}. Mỗi Fanpage doanh nghiệp có một không gian riêng; thành viên khác chỉ tham gia qua lời mời.
        </p>
      </header>

      {workspaces.length > 0 ? (
        <section className="mt-10">
          <h2 className="text-lg font-semibold text-slate-900">Doanh nghiệp của bạn</h2>
          <div className="mt-4 divide-y divide-slate-200 border-y border-slate-200">
            {workspaces.map((workspace) => (
              <label key={workspace.id} className="flex cursor-pointer items-center gap-4 py-4">
                <input type="radio" name="workspace" value={workspace.id} checked={selectedId === workspace.id}
                  onChange={() => { setSelectedId(workspace.id); setConnectNew(false); }} className="accent-pink-700" />
                {workspace.page_avatar_url ? (
                  <Image src={workspace.page_avatar_url} alt="" width={48} height={48} unoptimized className="h-12 w-12 rounded-full object-cover" />
                ) : <span className="grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-lg font-semibold text-slate-500">{workspace.name.slice(0, 1).toUpperCase()}</span>}
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-semibold text-slate-950">{workspace.name}</span>
                  <span className="mt-1 block text-sm text-slate-600">
                    {ROLE_LABELS[workspace.role]} · {workspace.page_connection_state === 'active' ? 'Đã xác minh Fanpage' : workspace.page_connection_state === 'needs_reconnect' ? 'Cần kết nối lại' : 'Chưa kết nối Fanpage'}
                  </span>
                </span>
                {workspace.page_connection_state === 'active' ? <span className="text-sm text-emerald-800">Sẵn sàng</span> : null}
              </label>
            ))}
          </div>
          {selected?.page_connection_state === 'active' ? (
            <Button className="mt-5" loading={selectWorkspace.isPending} onClick={() => selectWorkspace.mutate(selected.id, {
              onSuccess: () => router.replace(`/w/${selected.id}/brand`),
            })}>Mở không gian làm việc</Button>
          ) : selected && selected.role !== 'owner' ? (
            <p className="mt-5 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">Owner của doanh nghiệp cần kết nối hoặc xác minh lại Fanpage. Bạn vẫn có thể xem dữ liệu cũ sau khi được cấp quyền.</p>
          ) : selected && !connectNew ? (
            <PageActivationForm key={selected.id} workspaceId={selected.id} onActivated={async () => {
              queryClient.clear();
              const refreshed = await api.auth.me();
              queryClient.setQueryData(queryKeys.me, refreshed);
              queryClient.setQueryData(queryKeys.workspaces, refreshed.workspaces);
              router.replace(`/w/${selected.id}/brand`);
            }} />
          ) : null}
          <button type="button" onClick={() => setConnectNew((value) => !value)} className="mt-6 text-sm font-medium text-pink-800 underline underline-offset-4">
            {connectNew ? 'Quay lại danh sách doanh nghiệp' : 'Thêm Fanpage doanh nghiệp khác'}
          </button>
        </section>
      ) : null}

      {connectNew ? <PageActivationForm onActivated={async (workspaceId) => {
        queryClient.clear();
        const refreshed = await api.auth.me();
        queryClient.setQueryData(queryKeys.me, refreshed);
        queryClient.setQueryData(queryKeys.workspaces, refreshed.workspaces);
        await selectWorkspace.mutateAsync(workspaceId);
        router.replace(`/w/${workspaceId}/brand`);
      }} /> : null}
    </main>
  );
}

function PageActivationForm({ workspaceId, onActivated }: { workspaceId?: string; onActivated: (workspaceId: string) => Promise<void> }) {
  const [pageId, setPageId] = useState('');
  const [token, setToken] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const apiError = error instanceof ApiError ? error : null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      const body = { page_id: pageId.trim(), page_access_token: token };
      const workspace = workspaceId
        ? await workspaceApi.reconnectPage(workspaceId, body)
        : await workspaceApi.createFromPage(body);
      setToken('');
      await onActivated(workspace.id);
    } catch (caught) {
      setError(caught);
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="mt-10 max-w-2xl border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold text-slate-950">{workspaceId ? 'Kết nối Fanpage cho doanh nghiệp này' : 'Thêm Fanpage doanh nghiệp'}</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">Máy chủ sẽ xác minh Page ID và token bằng một yêu cầu chỉ đọc, rồi lấy tên và ảnh đại diện do Meta cung cấp. Token được mã hóa ở backend và không hiển thị lại.</p>
      <form id="page-activation-form" onSubmit={submit} className="mt-5 space-y-4">
        <label className="block text-sm font-medium text-slate-800">Page ID
          <input required inputMode="numeric" pattern="[0-9]{1,32}" value={pageId} onChange={(event) => setPageId(event.target.value)} autoComplete="off" className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2.5 text-base" />
        </label>
        <label className="block text-sm font-medium text-slate-800">Page Access Token
          <textarea required minLength={20} maxLength={4096} rows={3} value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" spellCheck={false} className="mt-1 block w-full resize-y rounded-lg border border-slate-300 px-3 py-2.5 font-mono text-sm" />
        </label>
        <p className="text-xs leading-5 text-slate-500">Chỉ kết nối Page bạn có quyền quản lý. Không dán token vào nội dung thương hiệu, tài liệu hoặc nơi công khai.</p>
        {apiError ? <ErrorPanel title="Chưa kết nối được Fanpage" message={apiError.message} code={apiError.code} requestId={apiError.requestId} retryable={apiError.retryable} onRetry={() => document.querySelector<HTMLFormElement>('#page-activation-form')?.requestSubmit()} /> : error ? <p role="alert" className="text-sm text-rose-700">Không kết nối được. Hãy thử lại.</p> : null}
        <Button type="submit" loading={pending}>{pending ? 'Đang xác minh…' : 'Xác minh và tiếp tục'}</Button>
      </form>
    </section>
  );
}
