'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { useSession } from '@/components/session-gate';
import { useBrandProfile, useBrandProfileRevisions, useUpdateBrandProfile } from '@/lib/hooks';
import { formatDateTime } from '@/lib/format';
import { ApiError } from '@/lib/api';
import { pageConnectionDisabledReason, pageConnectionReady } from '@/lib/page-connection';
import { Button, Card, EmptyState, ErrorPanel, LoadingBlock, PageHeader, StatusBadge } from '@/components/ui';

const MAX_PROFILE_CHARS = 20_000;

function legacyValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value.map((item) => {
      if (typeof item === 'string') return item;
      if (typeof item === 'object' && item !== null && 'name' in item) return String(item.name);
      return '';
    }).filter(Boolean).join(' · ');
  }
  if (typeof value === 'object' && value !== null) {
    return Object.entries(value).map(([key, item]) => `${key}: ${String(item)}`).join(' · ');
  }
  return '';
}

export default function BrandProfilePage() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const { workspaces } = useSession();
  const workspace = workspaces.find((item) => item.id === workspaceId);
  const profile = useBrandProfile(workspace ? workspaceId : '', Boolean(workspace));
  const revisions = useBrandProfileRevisions(workspace ? workspaceId : '');
  const save = useUpdateBrandProfile(workspaceId);
  const [draft, setDraft] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [showLegacy, setShowLegacy] = useState(false);
  const profileVersion = profile.data?.version;
  const profileMode = profile.data?.profile_mode;
  const profileText = profile.data?.profile_text;

  useEffect(() => {
    if (profileVersion === undefined) return;
    setDraft(profileMode === 'manual_text_v1' ? profileText ?? '' : '');
  }, [profileVersion, profileMode, profileText]);

  if (!workspace) return <p role="alert" className="p-6 text-sm text-rose-800">Bạn không có quyền truy cập workspace này.</p>;
  if (profile.isPending) return <LoadingBlock label="Đang tải hồ sơ thương hiệu…" />;
  if (profile.isError || !profile.data) return (
    <ErrorPanel title="Không tải được hồ sơ thương hiệu" message="Hãy thử tải lại trang hoặc kiểm tra kết nối." retryable onRetry={() => void profile.refetch()} />
  );

  const isOwner = workspace.role === 'owner';
  const pageReady = pageConnectionReady(workspace);
  const pageGateReason = pageConnectionDisabledReason(workspace);
  const current = profile.data;
  const dirty = draft !== (current.profile_mode === 'manual_text_v1' ? current.profile_text ?? '' : '');
  const tooLong = draft.length > MAX_PROFILE_CHARS;

  function applyProfile() {
    if (!isOwner || !pageReady || !current || !dirty || tooLong || !draft.trim()) return;
    setMessage(null);
    save.mutate({ version: current.version, profile_text: draft, confirm: false }, {
      onSuccess: () => setMessage('Đã lưu và áp dụng hồ sơ. Lưu hồ sơ không gọi AI.'),
      onError: (error) => setMessage(error instanceof ApiError && error.isVersionConflict
        ? 'Hồ sơ đã được cập nhật ở phiên khác. Tải lại rồi áp dụng lại nội dung của bạn.'
        : error.message || 'Không lưu được hồ sơ. Hãy thử lại.'),
    });
  }

  const legacy = (revisions.data ?? []).filter((item) => item.profile.profile_mode !== 'manual_text_v1');

  return (
    <div className="max-w-4xl space-y-6">
      <PageHeader
        eyebrow="Thông tin thương hiệu"
        title="Hồ sơ thương hiệu"
        description="Viết tự nhiên để Content Agent hiểu bạn đang bán gì và muốn nội dung được viết như thế nào."
        actions={<><span className="rounded-full border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600">Phiên bản {current.version}</span><StatusBadge label={current.profile_mode === 'manual_text_v1' ? 'Đang áp dụng' : 'Chưa có hồ sơ'} tone={current.profile_mode === 'manual_text_v1' ? 'success' : 'warning'} /></>}
      />

      {current.profile_mode !== 'manual_text_v1' ? (
        <EmptyState
          title="Chưa có hồ sơ do bạn viết"
          description="Hãy nhập thông tin thương hiệu vào ô bên dưới rồi bấm ‘Lưu và áp dụng’. Hồ sơ AI cũ vẫn được giữ trong lịch sử để tham khảo."
          tone="warning"
        />
      ) : null}

      {message ? <p role="status" className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-800">{message}</p> : null}
      {!pageReady ? <p role="status" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">Hồ sơ hiện tại vẫn xem được. Để áp dụng thay đổi và dùng agent, Owner cần kết nối Fanpage doanh nghiệp trong <Link className="font-medium underline" href={`/w/${workspaceId}/settings`}>Cài đặt</Link>. {pageGateReason}</p> : null}
      {save.isError && save.error instanceof ApiError && save.error.isVersionConflict ? (
        <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
          Bản trên máy chủ đã đổi. Nội dung bạn đang nhập vẫn còn trong ô; tải lại bản mới nhất rồi dán lại trước khi lưu.
          <span className="ml-3 inline-flex"><Button variant="secondary" size="sm" onClick={() => void profile.refetch()}>Tải bản mới nhất</Button></span>
        </div>
      ) : null}

      <Card><div className="space-y-4">
        <label htmlFor="brand-profile-text" className="block text-base font-semibold text-slate-950">Giới thiệu thương hiệu cho AI</label>
        <p id="brand-profile-hint" className="text-sm text-slate-600">
          Bạn có thể viết liền mạch theo cách của mình. Chẳng hạn: đang bán gì, khách hàng là ai, muốn giọng văn ra sao và điều gì không được nói.
        </p>
        <textarea
          id="brand-profile-text"
          aria-describedby="brand-profile-hint brand-profile-count"
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            setMessage(null);
          }}
          readOnly={!isOwner}
          maxLength={MAX_PROFILE_CHARS + 1}
          rows={14}
          placeholder="Ví dụ: Bên mình bán cà phê rang xay cho người pha tại nhà. Viết gần gũi như đang tư vấn, câu ngắn và tránh quảng cáo quá đà…"
          className="w-full resize-y rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm leading-6 text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 read-only:bg-slate-50"
        />
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p id="brand-profile-count" className={`text-xs ${tooLong ? 'text-rose-700' : 'text-slate-500'}`}>
            {draft.length.toLocaleString('vi-VN')} / {MAX_PROFILE_CHARS.toLocaleString('vi-VN')} ký tự
          </p>
          {isOwner ? (
            <Button onClick={applyProfile} loading={save.isPending} disabled={!pageReady || !dirty || tooLong || !draft.trim()} disabledReason={!pageReady ? pageGateReason : tooLong ? `Rút gọn hồ sơ còn tối đa ${MAX_PROFILE_CHARS.toLocaleString('vi-VN')} ký tự.` : !draft.trim() ? 'Nhập nội dung hồ sơ trước khi áp dụng.' : 'Chỉnh sửa hồ sơ để bật thao tác lưu.'}>
              Lưu và áp dụng
            </Button>
          ) : <span className="text-sm text-slate-600">Chỉ Owner mới được sửa và áp dụng hồ sơ chung.</span>}
        </div>
        <p className="text-xs text-slate-500">Hồ sơ được lưu nguyên văn, có lịch sử phiên bản. Lưu hồ sơ không gọi AI. Tài liệu tải lên được chọn riêng trong từng yêu cầu viết bài.</p>
      </div></Card>

      <Card><div className="space-y-3">
        <h2 className="font-semibold text-slate-950">Tài liệu tham khảo cho Content Agent</h2>
        <p className="text-sm text-slate-600">Tải tài liệu lên để Docling đọc chữ và bảng, sau đó chọn tài liệu cần dùng cho từng bài. Nội dung file không tự sửa hồ sơ thương hiệu.</p>
        <Link href={`/w/${workspaceId}/documents`} className="inline-flex text-sm font-medium text-teal-800 underline underline-offset-4">Mở mục Tài liệu</Link>
      </div></Card>

      {legacy.length > 0 ? (
        <Card><div className="space-y-3">
          <h2 className="font-semibold text-slate-950">Hồ sơ trước đây — chỉ tham khảo</h2>
          <p className="text-sm text-slate-600">Các phiên bản AI cũ được giữ để xem lại. Chúng không được dùng làm hồ sơ đang áp dụng; hãy tự viết lại nội dung phía trên nếu cần.</p>
          <button type="button" className="text-sm font-medium text-teal-800 underline underline-offset-4" aria-expanded={showLegacy} onClick={() => setShowLegacy((value) => !value)}>
            {showLegacy ? 'Ẩn lịch sử cũ' : `Xem ${legacy.length} phiên bản cũ`}
          </button>
          {showLegacy ? <ol className="space-y-3">{legacy.map((revision) => {
            const oldProfile = revision.profile as unknown as Record<string, unknown>;
            const fields = Object.values(oldProfile).filter((field): field is { label?: string; value?: unknown } => typeof field === 'object' && field !== null && 'key' in field);
            return <li key={revision.id} className="rounded-lg border border-slate-200 p-3">
              <p className="text-sm font-medium">Phiên bản {revision.version} · {formatDateTime(revision.created_at)}</p>
              <ul className="mt-2 space-y-1">{fields.map((field, index) => {
                const value = legacyValue(field.value);
                return value ? <li key={`${field.label}-${index}`} className="text-sm text-slate-700"><span className="font-medium">{field.label}:</span> {value}</li> : null;
              })}</ul>
            </li>;
          })}</ol> : null}
        </div></Card>
      ) : null}
    </div>
  );
}
