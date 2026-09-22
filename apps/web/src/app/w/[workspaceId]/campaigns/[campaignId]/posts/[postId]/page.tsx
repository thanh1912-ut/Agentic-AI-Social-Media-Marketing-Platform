'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useMemo, useState, type FormEvent } from 'react';

import {
  APPROVAL_DECISIONS,
  PERMISSIONS,
  POST_STATUS_LABELS,
  VERSION_SOURCES,
  type PostVersion,
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
  VersionConflictNotice,
} from '@/components/ui';
import { useMocks } from '@/lib/api/config';
import {
  useDecideApproval,
  usePost,
  usePostVersions,
  useSubmitApproval,
  useUpdatePost,
} from '@/lib/hooks';
import { formatDateTime } from '@/lib/format';

const SOURCE_LABELS: Record<PostVersion['source'], string> = {
  [VERSION_SOURCES.HUMAN]: 'Người dùng sửa',
  [VERSION_SOURCES.AI_GENERATED]: 'AI tạo',
  [VERSION_SOURCES.AI_REVISED]: 'AI sửa',
  [VERSION_SOURCES.IMPORTED]: 'Nhập từ nơi khác',
};

export default function PostEditorPage() {
  const params = useParams<{ workspaceId?: string; campaignId?: string; postId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const campaignId = params?.campaignId ?? '';
  const postId = params?.postId ?? '';
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId);
  const post = usePost(workspace ? workspaceId : '', postId);
  const versions = usePostVersions(workspace ? workspaceId : '', postId);
  const update = useUpdatePost(workspaceId, postId);
  const submitApproval = useSubmitApproval(workspaceId, postId);
  const decideApproval = useDecideApproval(workspaceId, postId);
  const mocksEnabled = useMocks();
  const [caption, setCaption] = useState('');
  const [hashtags, setHashtags] = useState('');
  const [note, setNote] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [compareVersion, setCompareVersion] = useState<number | null>(null);

  useEffect(() => {
    if (!post.data) return;
    setCaption(post.data.current.caption);
    setHashtags(post.data.current.hashtags.join(' '));
    setNote('');
  }, [post.data]);

  const selectedVersion = useMemo(
    () => versions.data?.versions.find((item) => item.version === compareVersion) ?? null,
    [compareVersion, versions.data?.versions],
  );

  if (post.isPending || versions.isPending) return <LoadingBlock label="Đang tải bài viết và lịch sử phiên bản…" />;
  if (post.isError || versions.isError || !post.data) {
    return <ErrorPanel title="Không tải được bài viết" message="Không thể mở bài viết này. Hãy thử lại." retryable onRetry={() => { void post.refetch(); void versions.refetch(); }} />;
  }

  const current = post.data;
  const postStatus = POST_STATUS_LABELS[current.status];
  const canEdit = hasPermission(workspace, PERMISSIONS.POST_EDIT);
  const canApprove = hasPermission(workspace, PERMISSIONS.POST_APPROVE);
  const canSubmit = canEdit && (current.status === 'draft' || current.status === 'rejected' || current.requires_reapproval);
  const apiError = update.error instanceof ApiError ? update.error : null;
  const hasBlockingError = apiError?.isVersionConflict ?? false;

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    update.mutate({
      version: current.version,
      caption: caption.trim(),
      hashtags: hashtags.split(/\s+/).map((item) => item.trim()).filter(Boolean),
      note: note.trim() || undefined,
    });
  }

  function decide(decision: 'approved' | 'rejected') {
    decideApproval.mutate({
      version: current.version,
      decision,
      reason: decision === APPROVAL_DECISIONS.REJECTED ? rejectionReason.trim() || 'Hãy chỉnh lại nội dung theo feedback.' : undefined,
    });
  }

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-slate-500"><Link href={`/w/${workspaceId}/campaigns/${campaignId}`} className="underline">Chiến dịch</Link> / bài viết</p>
          <h1 className="mt-1 text-lg font-semibold text-slate-900">Biên tập bài viết</h1>
          <p className="mt-1 text-sm text-slate-600">Phiên bản {current.version} · cập nhật {formatDateTime(current.updated_at)}</p>
        </div>
        <StatusBadge label={current.requires_reapproval ? 'Cần duyệt lại' : postStatus.label} tone={current.requires_reapproval ? 'warning' : postStatus.tone} />
      </header>

      {mocksEnabled ? <DemoNotice /> : null}
      {current.requires_reapproval ? <div role="note" className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">Bài đã từng được duyệt nhưng đã có thay đổi mới. Phải gửi duyệt lại đúng phiên bản {current.version} trước khi đăng.</div> : null}
      {current.rejection_reason ? <div role="note" className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900"><strong>Lý do bị từ chối:</strong> {current.rejection_reason}</div> : null}

      {hasBlockingError ? <VersionConflictNotice currentVersion={apiError?.currentVersion} onReload={() => { void post.refetch(); void versions.refetch(); }} /> : null}
      {update.error && !hasBlockingError ? <ErrorPanel title="Không lưu được phiên bản mới" message={apiError?.message ?? 'Hãy thử lại.'} code={apiError?.code} requestId={apiError?.requestId} retryable={apiError?.retryable} onRetry={() => update.reset()} /> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card title="Nội dung bài viết" description="Mỗi lần lưu tạo phiên bản mới. Bản cũ vẫn giữ nguyên để đối chiếu.">
          <form onSubmit={save} className="space-y-4">
            <div>
              <label htmlFor="post-caption" className="block text-sm font-medium text-slate-700">Caption</label>
              <textarea id="post-caption" rows={12} value={caption} onChange={(event) => setCaption(event.target.value)} disabled={!canEdit} className="prose-caption mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 disabled:bg-slate-100" />
            </div>
            <div>
              <label htmlFor="post-hashtags" className="block text-sm font-medium text-slate-700">Hashtag</label>
              <input id="post-hashtags" value={hashtags} onChange={(event) => setHashtags(event.target.value)} disabled={!canEdit} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 disabled:bg-slate-100" />
            </div>
            <div>
              <label htmlFor="post-note" className="block text-sm font-medium text-slate-700">Ghi chú phiên bản (không bắt buộc)</label>
              <input id="post-note" value={note} onChange={(event) => setNote(event.target.value)} disabled={!canEdit} placeholder="Ví dụ: sửa CTA theo feedback của chủ quán" className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 disabled:bg-slate-100" />
            </div>
            {canEdit ? <Button type="submit" loading={update.isPending} disabled={caption.trim() === ''} disabledReason="Caption không được để trống.">Lưu thành phiên bản mới</Button> : <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_EDIT)} requiredPermission={PERMISSIONS.POST_EDIT} />}
          </form>
        </Card>

        <Card title="Preview Facebook" description="Bản xem trước không phải thao tác đăng bài.">
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3"><div className="flex size-8 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">PB</div><div><p className="text-sm font-semibold">Phở Bắc Hà Nội</p><p className="text-xs text-slate-500">Bây giờ · 🌐</p></div></div>
            <div className="px-4 py-4"><p className="prose-caption text-sm text-slate-800">{caption || 'Caption sẽ hiển thị ở đây.'}</p><p className="mt-3 text-sm text-sky-700">{hashtags}</p></div>
            <div className="border-t border-slate-100 px-4 py-3 text-xs text-slate-500">Bản {current.version} · chưa đăng</div>
          </div>
        </Card>
      </div>

      <Card title="Duyệt nội dung" description="AI review chỉ là feedback. Quyết định cuối cùng vẫn cần người có quyền duyệt.">
        {current.current.review ? <div className="space-y-3"><p className="text-sm text-slate-700">{current.current.review.summary}</p><div className="grid gap-2 sm:grid-cols-3">{current.current.review.checks.map((check) => <div key={check.key} className={`rounded-lg border px-3 py-2 text-sm ${check.status === 'fail' ? 'border-rose-200 bg-rose-50 text-rose-900' : check.status === 'warn' ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-emerald-200 bg-emerald-50 text-emerald-900'}`}><p className="font-medium">{check.label}</p><p className="mt-1 text-xs">{check.message}</p></div>)}</div></div> : <p className="text-sm text-slate-600">Chưa có feedback AI cho phiên bản này.</p>}
        <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-slate-100 pt-4">
          {canSubmit ? <Button onClick={() => submitApproval.mutate(current.version)} loading={submitApproval.isPending}>Gửi duyệt bản {current.version}</Button> : null}
          {current.status === 'needs_review' && canApprove ? <><Button onClick={() => decide('approved')} loading={decideApproval.isPending}>Duyệt bản {current.version}</Button><div><label htmlFor="reject-reason" className="block text-xs font-medium text-slate-600">Lý do nếu từ chối</label><input id="reject-reason" value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} className="mt-1 w-64 rounded-lg border border-slate-300 px-3 py-2 text-sm" /></div><Button variant="danger" onClick={() => decide('rejected')} loading={decideApproval.isPending}>Từ chối</Button></> : null}
          {!canSubmit && current.status !== 'needs_review' && !canApprove ? <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_APPROVE)} requiredPermission={PERMISSIONS.POST_APPROVE} /> : null}
        </div>
        {submitApproval.error ? <p role="alert" className="mt-3 text-sm text-rose-700">Không gửi duyệt được. Hãy tải bản mới nhất nếu phiên bản đã thay đổi.</p> : null}
        {decideApproval.error ? <p role="alert" className="mt-3 text-sm text-rose-700">Không ghi được quyết định. Hãy tải lại bài viết.</p> : null}
      </Card>

      <Card title="Lịch sử phiên bản" description="Chọn một phiên bản cũ để so sánh với bản hiện tại.">
        {versions.data?.versions.length ? <div className="space-y-3">{versions.data.versions.map((version) => <div key={version.version} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-3"><div><p className="text-sm font-medium text-slate-900">Bản {version.version} · {SOURCE_LABELS[version.source]}</p><p className="mt-1 text-xs text-slate-500">{formatDateTime(version.created_at)} · {version.created_by_name}</p></div><Button variant={compareVersion === version.version ? 'primary' : 'secondary'} size="sm" onClick={() => setCompareVersion(compareVersion === version.version ? null : version.version)}>So sánh</Button></div>)}</div> : <EmptyState title="Chưa có lịch sử phiên bản" description="Bài viết chưa có phiên bản nào để so sánh." />}
        {selectedVersion && selectedVersion.version !== current.version ? <div className="mt-4 grid gap-3 border-t border-slate-100 pt-4 md:grid-cols-2"><div><p className="text-sm font-semibold text-slate-900">Bản hiện tại · {current.version}</p><p className="prose-caption mt-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{current.current.caption}</p></div><div><p className="text-sm font-semibold text-slate-900">Bản đã chọn · {selectedVersion.version}</p><p className="prose-caption mt-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">{selectedVersion.caption}</p></div></div> : null}
      </Card>
    </div>
  );
}
