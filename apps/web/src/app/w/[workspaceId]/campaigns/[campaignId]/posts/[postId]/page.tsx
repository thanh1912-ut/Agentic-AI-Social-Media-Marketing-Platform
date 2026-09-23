'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from 'react';

import {
  APPROVAL_DECISIONS,
  PERMISSIONS,
  POST_STATUS_LABELS,
  VERSION_SOURCES,
  type ReviseWithAiRequest,
  type PostVersion,
  type PostMedia,
} from '@agentic/contracts';

import { ApiError, apiDownload, saveBlob } from '@/lib/api';
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
  useJob,
  useRevisePostWithAi,
  useSubmitApproval,
  useUpdatePost,
  useUploadMediaAsset,
} from '@/lib/hooks';
import { formatDateTime } from '@/lib/format';

const SOURCE_LABELS: Record<PostVersion['source'], string> = {
  [VERSION_SOURCES.HUMAN]: 'Người dùng sửa',
  [VERSION_SOURCES.AI_GENERATED]: 'AI tạo',
  [VERSION_SOURCES.AI_REVISED]: 'AI sửa',
  [VERSION_SOURCES.IMPORTED]: 'Nhập từ nơi khác',
};

function PostMediaPreview({ media, onRemove }: { media: PostMedia; onRemove?: () => void }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(media.source === 'uploaded');
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let disposed = false;
    let objectUrl: string | null = null;
    setPreviewUrl(null);
    setFailed(false);
    if (media.source !== 'uploaded') {
      setLoading(false);
      return () => { disposed = true; };
    }
    setLoading(true);
    void apiDownload(media.url).then((blob) => {
      if (disposed) return;
      objectUrl = URL.createObjectURL(blob);
      setPreviewUrl(objectUrl);
      setLoading(false);
    }).catch(() => {
      if (!disposed) {
        setFailed(true);
        setLoading(false);
      }
    });
    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [media.source, media.url]);

  async function download() {
    try {
      const blob = await apiDownload(media.url);
      saveBlob(blob, media.filename || 'brand-image');
    } catch {
      setFailed(true);
    }
  }

  return (
    <figure className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="flex aspect-video items-center justify-center bg-slate-50">
        {previewUrl ? <Image src={previewUrl} alt={media.alt} width={1280} height={720} unoptimized className="h-full w-full object-contain" /> :
          <p className="px-4 text-center text-sm text-slate-600">{loading ? 'Đang tải ảnh…' : failed ? 'Không tải được ảnh.' : media.alt}</p>}
      </div>
      <figcaption className="space-y-2 p-3">
        <p className="break-words text-sm font-medium text-slate-800">{media.filename || media.alt || 'Ảnh đính kèm'}</p>
        {media.alt ? <p className="text-xs text-slate-600">Mô tả: {media.alt}</p> : null}
        <div className="flex flex-wrap gap-2">
          {media.source === 'uploaded' ? <button type="button" onClick={() => void download()} className="text-sm font-medium text-sky-700 underline">Tải ảnh</button> : null}
          {onRemove ? <button type="button" onClick={onRemove} className="text-sm font-medium text-rose-700 underline">Gỡ khỏi bản nháp</button> : null}
        </div>
      </figcaption>
    </figure>
  );
}

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
  const uploadMedia = useUploadMediaAsset(workspaceId);
  const reviseWithAi = useRevisePostWithAi(workspaceId, postId);
  const submitApproval = useSubmitApproval(workspaceId, postId);
  const decideApproval = useDecideApproval(workspaceId, postId);
  const mocksEnabled = useMocks();
  const [caption, setCaption] = useState('');
  const [hashtags, setHashtags] = useState('');
  const [selectedMedia, setSelectedMedia] = useState<PostMedia[]>([]);
  const [mediaChanged, setMediaChanged] = useState(false);
  const [mediaAltText, setMediaAltText] = useState('');
  const [note, setNote] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [compareVersion, setCompareVersion] = useState<number | null>(null);
  const [revisionInstruction, setRevisionInstruction] = useState('');
  const [revisionScope, setRevisionScope] = useState<NonNullable<ReviseWithAiRequest['scope']>>('all');
  const [revisionJobId, setRevisionJobId] = useState<string | null>(null);
  const refreshedRevisionJob = useRef<string | null>(null);
  const revisionJob = useJob(revisionJobId);

  useEffect(() => {
    if (!post.data) return;
    setCaption(post.data.current.caption);
    setHashtags(post.data.current.hashtags.join(' '));
    setSelectedMedia(post.data.current.media.filter((item) => item.source === 'uploaded'));
    setMediaChanged(false);
    setNote('');
  }, [post.data]);

  const selectedVersion = useMemo(
    () => versions.data?.versions.find((item) => item.version === compareVersion) ?? null,
    [compareVersion, versions.data?.versions],
  );

  useEffect(() => {
    const job = revisionJob.data;
    if (!job || job.status !== 'succeeded' || refreshedRevisionJob.current === job.id) return;
    refreshedRevisionJob.current = job.id;
    void post.refetch();
    void versions.refetch();
  }, [post, revisionJob.data, versions]);

  if (post.isPending || versions.isPending) return <LoadingBlock label="Đang tải bài viết và lịch sử phiên bản…" />;
  if (post.isError || versions.isError || !post.data) {
    return <ErrorPanel title="Không tải được bài viết" message="Không thể mở bài viết này. Hãy thử lại." retryable onRetry={() => { void post.refetch(); void versions.refetch(); }} />;
  }

  const current = post.data;
  const postStatus = POST_STATUS_LABELS[current.status];
  const canEdit = hasPermission(workspace, PERMISSIONS.POST_EDIT);
  const canGenerate = hasPermission(workspace, PERMISSIONS.POST_GENERATE);
  const canApprove = hasPermission(workspace, PERMISSIONS.POST_APPROVE);
  const canSubmit = canEdit && (current.status === 'draft' || current.status === 'rejected' || current.requires_reapproval);
  const apiError = update.error instanceof ApiError ? update.error : null;
  const hasBlockingError = apiError?.isVersionConflict ?? false;
  const previewMedia = mediaChanged ? selectedMedia : current.current.media;
  const postLocked = current.status === 'scheduled' || current.status === 'published';

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    update.mutate({
      version: current.version,
      caption: caption.trim(),
      hashtags: hashtags.split(/\s+/).map((item) => item.trim()).filter(Boolean),
      ...(mediaChanged ? { media: selectedMedia.map((item) => ({ asset_id: item.asset_id ?? item.id, alt_text: item.alt })) } : {}),
      note: note.trim() || undefined,
    });
  }

  function uploadImage(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    if (!file || selectedMedia.length >= 10) return;
    uploadMedia.mutate({ file, altText: mediaAltText.trim() }, {
      onSuccess: (asset) => {
        const media: PostMedia = {
          id: asset.id,
          asset_id: asset.id,
          url: asset.content_path,
          alt: mediaAltText.trim() || asset.alt_text,
          width: asset.width,
          height: asset.height,
          mime_type: asset.mime_type,
          source: 'uploaded',
          filename: asset.filename,
          size_bytes: asset.size_bytes,
          sha256: asset.content_sha256,
        };
        setSelectedMedia((items) => items.some((item) => item.id === media.id) ? items : [...items, media]);
        setMediaChanged(true);
      },
    });
  }

  function requestAiRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const instruction = revisionInstruction.trim();
    if (!instruction) return;
    reviseWithAi.mutate({ version: current.version, instruction, scope: revisionScope }, {
      onSuccess: (accepted) => setRevisionJobId(accepted.job_id),
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

      <Card title="Yêu cầu AI sửa" description="AI dùng Brand Profile đã xác nhận và nguồn phù hợp để tạo phiên bản mới. Bài vẫn cần người dùng duyệt; AI không đăng bài.">
        {canGenerate ? <form onSubmit={requestAiRevision} className="space-y-3">
          <div>
            <label htmlFor="ai-revision-instruction" className="block text-sm font-medium text-slate-700">Bạn muốn sửa thế nào?</label>
            <textarea id="ai-revision-instruction" value={revisionInstruction} onChange={(event) => setRevisionInstruction(event.target.value)} maxLength={2000} required rows={3} placeholder="Ví dụ: viết ngắn hơn, giữ giọng thân thiện và kết thúc bằng lời mời ghé quán." className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900" />
          </div>
          <div>
            <label htmlFor="ai-revision-scope" className="block text-sm font-medium text-slate-700">Phạm vi sửa</label>
            <select id="ai-revision-scope" value={revisionScope} onChange={(event) => setRevisionScope(event.target.value as NonNullable<ReviseWithAiRequest['scope']>)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900 sm:max-w-sm">
              <option value="caption">Caption, hook và CTA</option>
              <option value="hashtags">Hashtag</option>
              <option value="media">Mô tả ảnh (không tạo hoặc thay ảnh)</option>
              <option value="all">Tất cả nội dung AI hỗ trợ</option>
            </select>
          </div>
          <Button type="submit" loading={reviseWithAi.isPending || revisionJob.data?.status === 'queued' || revisionJob.data?.status === 'running'} disabled={!revisionInstruction.trim() || current.status === 'scheduled' || current.status === 'published'} disabledReason={current.status === 'scheduled' || current.status === 'published' ? 'Bài đã lên lịch hoặc đã đăng.' : 'Nhập yêu cầu sửa trước.'}>Tạo phiên bản AI sửa</Button>
          {!canGenerate ? <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_GENERATE)} requiredPermission={PERMISSIONS.POST_GENERATE} /> : null}
          {reviseWithAi.error ? <ErrorPanel title="Không gửi được yêu cầu AI sửa" message={reviseWithAi.error instanceof ApiError ? reviseWithAi.error.message : 'Hãy thử lại.'} code={reviseWithAi.error instanceof ApiError ? reviseWithAi.error.code : undefined} requestId={reviseWithAi.error instanceof ApiError ? reviseWithAi.error.requestId : undefined} retryable={reviseWithAi.error instanceof ApiError ? reviseWithAi.error.retryable : false} onRetry={() => reviseWithAi.reset()} /> : null}
          {revisionJobId && revisionJob.data ? <div role="status" aria-live="polite" className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-700">
            <p className="font-medium">{revisionJob.data.title} · {revisionJob.data.status}</p>
            {revisionJob.data.error ? <p className="mt-1 text-rose-700">{revisionJob.data.error.message}</p> : null}
            {revisionJob.data.status === 'succeeded' ? <p className="mt-1">Phiên bản mới đã được tải vào trình biên tập. Kiểm tra nội dung rồi gửi duyệt.</p> : null}
            <Link className="mt-2 inline-block underline" href={`/w/${workspaceId}/jobs/${revisionJobId}`}>Xem tiến trình tác vụ</Link>
          </div> : null}
          {revisionJob.isError ? <p role="alert" className="text-sm text-rose-700">Không theo dõi được tác vụ AI sửa. Hãy mở tác vụ hoặc tải lại trang.</p> : null}
        </form> : <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_GENERATE)} requiredPermission={PERMISSIONS.POST_GENERATE} />}
      </Card>

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
            <section className="space-y-3 rounded-lg border border-slate-200 p-3" aria-labelledby="post-media-heading">
              <div>
                <h2 id="post-media-heading" className="text-sm font-semibold text-slate-900">Ảnh cho bài viết</h2>
                <p className="mt-1 text-xs text-slate-600">Tệp được lưu riêng trong workspace. Gắn hoặc gỡ ảnh sẽ tạo phiên bản mới khi bạn lưu bài.</p>
              </div>
              {canEdit ? <>
                <div>
                  <label htmlFor="post-media-alt" className="block text-sm font-medium text-slate-700">Mô tả ảnh (alt text)</label>
                  <input id="post-media-alt" value={mediaAltText} onChange={(event) => setMediaAltText(event.target.value)} maxLength={500} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" placeholder="Ví dụ: Tô phở bò đặt trên bàn gỗ cạnh rau thơm" />
                </div>
                <div>
                  <label htmlFor="post-media-file" className="block text-sm font-medium text-slate-700">Tải ảnh JPEG, PNG hoặc WebP</label>
                  <input id="post-media-file" type="file" accept="image/jpeg,image/png,image/webp" onChange={uploadImage} disabled={uploadMedia.isPending || selectedMedia.length >= 10 || postLocked} className="mt-1 block w-full text-sm text-slate-700" />
                  <p className="mt-1 text-xs text-slate-500">Tối đa 10 ảnh cho mỗi phiên bản. Ảnh chỉ được gắn vào bài sau khi bấm lưu phiên bản.</p>
                </div>
              </> : <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_EDIT)} requiredPermission={PERMISSIONS.POST_EDIT} />}
              {postLocked ? <p role="note" className="text-sm text-amber-800">Bài đã lên lịch hoặc đã đăng và không thể sửa.</p> : null}
              {uploadMedia.isPending ? <p role="status" className="text-sm text-slate-600">Đang kiểm tra và tải ảnh lên…</p> : null}
              {uploadMedia.error ? <p role="alert" className="text-sm text-rose-700">{uploadMedia.error instanceof ApiError ? uploadMedia.error.message : 'Không tải được ảnh.'}</p> : null}
              {mediaChanged ? <p role="status" className="text-sm text-sky-800">Thay đổi ảnh chưa lưu. Bấm “Lưu thành phiên bản mới” để gắn ảnh vào bài.</p> : null}
              {previewMedia.length ? <div className="grid gap-3 sm:grid-cols-2">
                {previewMedia.map((media) => <PostMediaPreview key={media.id} media={media} onRemove={canEdit && !postLocked && media.source === 'uploaded' ? () => { setSelectedMedia((items) => items.filter((item) => item.id !== media.id)); setMediaChanged(true); } : undefined} />)}
              </div> : <p className="text-sm text-slate-600">Phiên bản này chưa có ảnh đính kèm.</p>}
            </section>
            {canEdit ? <Button type="submit" loading={update.isPending} disabled={caption.trim() === '' || uploadMedia.isPending || postLocked} disabledReason={postLocked ? 'Bài đã lên lịch hoặc đã đăng; hãy tạo bài mới nếu cần nội dung khác.' : uploadMedia.isPending ? 'Chờ tải ảnh xong trước khi lưu phiên bản.' : 'Caption không được để trống.'}>Lưu thành phiên bản mới</Button> : <PermissionNotice message={permissionDeniedReason(workspace, PERMISSIONS.POST_EDIT)} requiredPermission={PERMISSIONS.POST_EDIT} />}
          </form>
        </Card>

        <Card title="Preview Facebook" description="Bản xem trước không phải thao tác đăng bài.">
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3"><div className="flex size-8 items-center justify-center rounded-full bg-slate-900 text-xs font-semibold text-white">PB</div><div><p className="text-sm font-semibold">Phở Bắc Hà Nội</p><p className="text-xs text-slate-500">Bây giờ · 🌐</p></div></div>
            {previewMedia.filter((media) => media.source === 'uploaded').map((media) => <PostMediaPreview key={`facebook-${media.id}`} media={media} />)}
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
