'use client';

/**
 * Hồ sơ thương hiệu — màn hình quan trọng nhất của lát cắt này.
 *
 * Ba việc màn hình này phải làm được:
 * 1. Cho người dùng XEM NGUỒN của từng thông tin AI trích xuất (tài liệu + trang/dòng
 *    + trích dẫn nguyên văn), không giấu sau bất kỳ bước nào.
 * 2. Khi nhiều tài liệu mâu thuẫn, để người dùng CHỌN — kèm nguồn của từng lựa chọn.
 * 3. Lưu kèm `version`; nếu xung đột phiên bản thì KHÔNG tự ghi đè, không tự thử lại.
 */

import { useId, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import {
  BRAND_FIELD_KEYS,
  FIELD_REVIEW_STATE_LABELS,
  FIELD_REVIEW_STATES,
  type BrandFieldKey,
  type BrandProduct,
  type BrandProfile,
  type FieldReviewState,
  type ProvenanceRef,
  type UpdateBrandProfileRequest,
} from '@agentic/contracts';

import { useSession } from '@/components/session-gate';
import { ApiError } from '@/lib/api';
import { formatDateTime, formatNumber, formatPercent } from '@/lib/format';
import { useBrandProfile, useUpdateBrandProfile } from '@/lib/hooks';
import { ACTION_REQUIREMENTS, hasPermission, permissionDeniedReason } from '@/lib/permissions';
import {
  Badge,
  Button,
  Card,
  DisabledReason,
  EmptyState,
  ErrorPanel,
  LoadingBlock,
  PermissionNotice,
  StatCard,
  StatusBadge,
  UnavailableNotice,
  VersionConflictNotice,
} from '@/components/ui';

// ---------------------------------------------------------------------------
// Cách sửa từng trường (khai báo một chỗ)
// ---------------------------------------------------------------------------

type EditControl = 'input' | 'textarea' | 'lines' | 'contact' | 'none';

const FIELD_EDIT_CONTROL: Record<BrandFieldKey, EditControl> = {
  [BRAND_FIELD_KEYS.BUSINESS_NAME]: 'input',
  [BRAND_FIELD_KEYS.INDUSTRY]: 'input',
  [BRAND_FIELD_KEYS.DESCRIPTION]: 'textarea',
  [BRAND_FIELD_KEYS.BRAND_VOICE]: 'textarea',
  [BRAND_FIELD_KEYS.TARGET_AUDIENCE]: 'lines',
  [BRAND_FIELD_KEYS.TONE_KEYWORDS]: 'lines',
  [BRAND_FIELD_KEYS.DO_NOT_USE]: 'lines',
  [BRAND_FIELD_KEYS.COMPETITORS]: 'lines',
  [BRAND_FIELD_KEYS.CONTACT]: 'contact',
  [BRAND_FIELD_KEYS.PRODUCTS]: 'none',
};

const FIELD_EDIT_HINT: Record<BrandFieldKey, string> = {
  [BRAND_FIELD_KEYS.BUSINESS_NAME]: 'Tên doanh nghiệp sẽ dùng trong nội dung.',
  [BRAND_FIELD_KEYS.INDUSTRY]: 'Ngành nghề chính, ví dụ: đồ uống, thời trang, nội thất.',
  [BRAND_FIELD_KEYS.DESCRIPTION]: 'Mô tả ngắn để AI hiểu doanh nghiệp làm gì.',
  [BRAND_FIELD_KEYS.BRAND_VOICE]: 'Giọng điệu khi viết bài, ví dụ: thân thiện, gần gũi.',
  [BRAND_FIELD_KEYS.TARGET_AUDIENCE]: 'Mỗi dòng một nhóm khách hàng.',
  [BRAND_FIELD_KEYS.TONE_KEYWORDS]: 'Mỗi dòng một từ khoá thể hiện giọng điệu.',
  [BRAND_FIELD_KEYS.DO_NOT_USE]: 'Mỗi dòng một từ hoặc cụm từ không được dùng.',
  [BRAND_FIELD_KEYS.COMPETITORS]: 'Mỗi dòng một đối thủ cần theo dõi.',
  [BRAND_FIELD_KEYS.CONTACT]:
    'Mỗi dòng một mục dạng “khoá: giá trị”, ví dụ: hotline: 0900 000 000',
  [BRAND_FIELD_KEYS.PRODUCTS]:
    'Danh sách sản phẩm có cấu trúc — bản này chỉ xem và chọn từ tài liệu, chưa sửa từng ô.',
};

const FIELD_DISPLAY_ORDER: BrandFieldKey[] = [
  BRAND_FIELD_KEYS.BUSINESS_NAME,
  BRAND_FIELD_KEYS.INDUSTRY,
  BRAND_FIELD_KEYS.DESCRIPTION,
  BRAND_FIELD_KEYS.PRODUCTS,
  BRAND_FIELD_KEYS.TARGET_AUDIENCE,
  BRAND_FIELD_KEYS.BRAND_VOICE,
  BRAND_FIELD_KEYS.TONE_KEYWORDS,
  BRAND_FIELD_KEYS.DO_NOT_USE,
  BRAND_FIELD_KEYS.COMPETITORS,
  BRAND_FIELD_KEYS.CONTACT,
];

/** Nhãn tiếng Việt cho khoá liên hệ thường gặp; khoá lạ hiển thị nguyên văn. */
const CONTACT_KEY_LABELS: Record<string, string> = {
  phone: 'Điện thoại',
  hotline: 'Hotline',
  email: 'Email',
  website: 'Website',
  address: 'Địa chỉ',
  facebook: 'Facebook',
  fanpage: 'Fanpage',
  zalo: 'Zalo',
};

// ---------------------------------------------------------------------------
// Kiểu đã chuẩn hoá — tránh union của 10 loại trường khác nhau
// ---------------------------------------------------------------------------

interface FieldLike {
  key: BrandFieldKey;
  label: string;
  value: unknown;
  state: FieldReviewState;
  confidence?: number;
  provenance: ProvenanceRef[];
  alternatives: Array<{ value: unknown; provenance: ProvenanceRef[] }>;
  updated_at?: string;
}

function asFieldLike(field: BrandProfile[BrandFieldKey]): FieldLike {
  return {
    key: field.key,
    label: field.label,
    value: field.value as unknown,
    state: field.state,
    confidence: field.confidence,
    provenance: field.provenance ?? [],
    alternatives: (field.alternatives ?? []) as FieldLike['alternatives'],
    updated_at: field.updated_at,
  };
}

function isMissingValue(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length === 0;
  return false;
}

/** Giá trị hiển thị trong ô nhập (chỉ dùng cho trường sửa được). */
function valueToDraftText(value: unknown, control: EditControl): string {
  if (control === 'input' || control === 'textarea') {
    return typeof value === 'string' ? value : '';
  }
  if (control === 'lines') {
    if (!Array.isArray(value)) return '';
    return value.filter((item): item is string => typeof item === 'string').join('\n');
  }
  if (control === 'contact') {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) return '';
    return Object.entries(value as Record<string, string>)
      .map(([key, item]) => `${key}: ${item}`)
      .join('\n');
  }
  return '';
}

type ParseResult = { ok: true; value: unknown } | { ok: false; error: string };

function parseDraftText(key: BrandFieldKey, raw: string): ParseResult {
  const control = FIELD_EDIT_CONTROL[key];

  if (control === 'input' || control === 'textarea') {
    return { ok: true, value: raw.trim() };
  }

  if (control === 'lines') {
    return {
      ok: true,
      value: raw
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line !== ''),
    };
  }

  if (control === 'contact') {
    const record: Record<string, string> = {};
    for (const line of raw.split('\n')) {
      const trimmed = line.trim();
      if (trimmed === '') continue;
      const separator = trimmed.indexOf(':');
      if (separator <= 0) {
        return {
          ok: false,
          error: `Dòng “${trimmed}” chưa đúng dạng “khoá: giá trị”. Ví dụ: hotline: 0900 000 000.`,
        };
      }
      const contactKey = trimmed.slice(0, separator).trim();
      const contactValue = trimmed.slice(separator + 1).trim();
      if (contactKey === '') {
        return {
          ok: false,
          error: `Dòng “${trimmed}” thiếu tên mục trước dấu hai chấm.`,
        };
      }
      record[contactKey] = contactValue;
    }
    return { ok: true, value: record };
  }

  return {
    ok: false,
    error: 'Trường này chưa hỗ trợ sửa trực tiếp trong bản dựng hiện tại.',
  };
}

function provenanceLocation(ref: ProvenanceRef): string {
  const parts: string[] = [];
  if (typeof ref.page === 'number') parts.push(`Trang ${formatNumber(ref.page)}`);
  if (ref.sheet) parts.push(`Sheet “${ref.sheet}”`);
  if (typeof ref.row === 'number') parts.push(`Dòng ${formatNumber(ref.row)}`);
  return parts.length > 0
    ? parts.join(' · ')
    : 'Tài liệu không kèm số trang/dòng cho đoạn trích này.';
}

// ---------------------------------------------------------------------------
// Khối hiển thị
// ---------------------------------------------------------------------------

/**
 * Danh sách nguồn — bắt buộc mở được, không giấu sau thao tác phụ.
 *
 * Dùng nút + vùng mở rộng (mẫu disclosure của WAI-ARIA) thay vì `<details>`:
 * nút có `aria-expanded`/`aria-controls` rõ ràng, và trình đọc màn hình luôn đọc
 * được đây là nút mở nguồn.
 */
function ProvenanceList({ refs }: { refs: ProvenanceRef[] }) {
  const [open, setOpen] = useState(false);
  const regionId = useId();

  if (refs.length === 0) return null;

  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={regionId}
        onClick={() => setOpen((previous) => !previous)}
        className="rounded text-sm font-medium text-slate-800 underline"
      >
        {open ? 'Ẩn nguồn' : `Xem nguồn (${formatNumber(refs.length)})`}
      </button>
      <ul id={regionId} hidden={!open} className="mt-2 space-y-3">
        {refs.map((ref, index) => (
          <li key={`${ref.document_id}-${index}`} className="text-sm text-slate-700">
            <p className="font-medium text-slate-900">{ref.document_name}</p>
            <p className="text-xs text-slate-500">{provenanceLocation(ref)}</p>
            <blockquote className="prose-caption mt-1 border-l-2 border-slate-300 pl-3 text-slate-700">
              “{ref.quote}”
            </blockquote>
          </li>
        ))}
      </ul>
    </div>
  );
}

function MissingValue({ reason }: { reason: string }) {
  return (
    <div>
      <p className="text-sm text-slate-900">—</p>
      <p className="mt-0.5 text-xs text-slate-500">{reason}</p>
    </div>
  );
}

function BrandProductsView({ products }: { products: BrandProduct[] }) {
  return (
    <ul className="space-y-2">
      {products.map((product) => (
        <li key={product.id} className="rounded-lg border border-slate-200 px-3 py-2">
          <p className="text-sm font-medium text-slate-900">{product.name}</p>
          {product.description ? (
            <p className="mt-0.5 text-sm text-slate-700">{product.description}</p>
          ) : null}
          <p className="mt-0.5 text-xs text-slate-500">
            {product.price_range
              ? `Khoảng giá: ${product.price_range}`
              : 'Chưa có khoảng giá trong tài liệu.'}
            {product.usp && product.usp.length > 0
              ? ` · Điểm nổi bật: ${product.usp.join('; ')}`
              : ''}
          </p>
        </li>
      ))}
    </ul>
  );
}

function FieldValueView({
  fieldKey,
  value,
  missingReason,
}: {
  fieldKey: BrandFieldKey;
  value: unknown;
  missingReason: string;
}) {
  if (isMissingValue(value)) return <MissingValue reason={missingReason} />;

  const control = FIELD_EDIT_CONTROL[fieldKey];

  if (control === 'contact') {
    const entries = Object.entries(value as Record<string, string>);
    return (
      <dl className="space-y-1">
        {entries.map(([key, item]) => (
          <div key={key} className="flex flex-wrap gap-2 text-sm">
            <dt className="font-medium text-slate-600">{CONTACT_KEY_LABELS[key] ?? key}:</dt>
            <dd className="text-slate-900">{item === '' ? '—' : item}</dd>
          </div>
        ))}
      </dl>
    );
  }

  if (Array.isArray(value)) {
    const items = value.filter((item) => typeof item === 'string') as string[];
    if (items.length > 0) {
      return (
        <ul className="list-inside list-disc space-y-0.5 text-sm text-slate-900">
          {items.map((item, index) => (
            <li key={`${item}-${index}`}>{item}</li>
          ))}
        </ul>
      );
    }
  }

  if (fieldKey === BRAND_FIELD_KEYS.PRODUCTS && Array.isArray(value)) {
    return <BrandProductsView products={value as BrandProduct[]} />;
  }

  if (typeof value === 'string') {
    return <p className="prose-caption text-sm text-slate-900">{value}</p>;
  }

  // Giá trị có cấu trúc lạ: vẫn hiển thị nguyên văn để người dùng thấy đúng dữ liệu.
  return (
    <div>
      <pre className="prose-caption overflow-x-auto rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-800">
        {JSON.stringify(value, null, 2)}
      </pre>
      <p className="mt-0.5 text-xs text-slate-500">
        Giá trị này có cấu trúc mà màn hình chưa có cách hiển thị riêng, nên hiện nguyên văn.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Trang
// ---------------------------------------------------------------------------

export default function TrangHoSoThuongHieu() {
  const params = useParams<{ workspaceId?: string }>();
  const workspaceId = params?.workspaceId ?? '';
  const router = useRouter();
  const { workspaces } = useSession();

  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;
  const activeId = workspace ? workspaceId : '';

  const brandQuery = useBrandProfile(activeId);
  const update = useUpdateBrandProfile(activeId);

  const [textDrafts, setTextDrafts] = useState<Partial<Record<BrandFieldKey, string>>>({});
  const [choiceDrafts, setChoiceDrafts] = useState<
    Partial<Record<BrandFieldKey, number | 'current'>>
  >({});
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!workspace) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold text-slate-900">Không mở được hồ sơ thương hiệu</h1>
        <PermissionNotice message="Bạn không thuộc doanh nghiệp này, nên không xem được hồ sơ thương hiệu của doanh nghiệp." />
        <Button variant="secondary" onClick={() => router.push('/')}>
          Về trang chủ
        </Button>
      </div>
    );
  }

  const canEdit = hasPermission(workspace, ACTION_REQUIREMENTS.editBrand);
  const canConfirm = hasPermission(workspace, ACTION_REQUIREMENTS.confirmBrand);
  const editDeniedReason = permissionDeniedReason(workspace, ACTION_REQUIREMENTS.editBrand);
  const confirmDeniedReason = permissionDeniedReason(workspace, ACTION_REQUIREMENTS.confirmBrand);

  if (brandQuery.isPending) {
    return <LoadingBlock label="Đang tải hồ sơ thương hiệu…" />;
  }

  const loadError = brandQuery.error instanceof ApiError ? brandQuery.error : null;

  if (brandQuery.isError) {
    if (loadError?.isForbidden) {
      const permission = loadError.details.permission;
      return (
        <PermissionNotice
          message={loadError.message}
          requiredPermission={typeof permission === 'string' ? permission : undefined}
        />
      );
    }

    return (
      <ErrorPanel
        title="Không tải được hồ sơ thương hiệu"
        message={loadError?.message ?? 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'}
        code={loadError?.code}
        requestId={loadError?.requestId}
        retryable={loadError?.retryable ?? true}
        onRetry={() => void brandQuery.refetch()}
      />
    );
  }

  const profile = brandQuery.data;
  const fields = FIELD_DISPLAY_ORDER.map((key) => asFieldLike(profile[key]));
  const fieldsWithValue = fields.filter((field) => !isMissingValue(field.value)).length;
  const awaiting = fields.filter(
    (field) =>
      field.state === FIELD_REVIEW_STATES.SUGGESTED || field.state === FIELD_REVIEW_STATES.CONFLICT,
  ).length;
  const missing = fields.filter((field) => field.state === FIELD_REVIEW_STATES.MISSING).length;
  const completeness =
    typeof profile.completeness === 'number' && Number.isFinite(profile.completeness)
      ? profile.completeness
      : null;

  const conflictError = update.error instanceof ApiError && update.error.isVersionConflict
    ? update.error
    : null;
  const saveError = update.error && !conflictError ? update.error : null;

  function draftTextFor(field: FieldLike): string | null {
    const control = FIELD_EDIT_CONTROL[field.key];
    if (control === 'none') return null;
    const draft = textDrafts[field.key];
    if (draft === undefined) return null;
    const original = valueToDraftText(field.value, control);
    return draft === original ? null : draft;
  }

  // Thứ tự xét phải GIỐNG `buildSaveFields`: lựa chọn radio trước, bản nháp gõ tay sau —
  // nếu không, danh sách "sẽ gửi lên" và dữ liệu thật gửi đi sẽ lệch nhau.
  const pendingChanges = fields
    .map((field) => {
      const draft = draftTextFor(field);
      const choice = choiceDrafts[field.key];
      if (typeof choice === 'number') {
        const alternative = field.alternatives[choice];
        return {
          key: field.key,
          label: field.label,
          text:
            alternative === undefined
              ? '(lựa chọn không còn tồn tại trong bản mới)'
              : `Chọn giá trị từ tài liệu: ${JSON.stringify(alternative.value)}`,
        };
      }
      if (draft !== null) {
        const parsed = parseDraftText(field.key, draft);
        return {
          key: field.key,
          label: field.label,
          text: parsed.ok
            ? Array.isArray(parsed.value)
              ? (parsed.value as string[]).join('; ')
              : parsed.value !== null &&
                  typeof parsed.value === 'object' &&
                  !Array.isArray(parsed.value)
                ? Object.entries(parsed.value as Record<string, string>)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join('; ')
                : String(parsed.value)
            : '(chưa đúng định dạng)',
        };
      }
      return null;
    })
    .filter((item): item is { key: BrandFieldKey; label: string; text: string } => item !== null);

  const pendingDraftText = pendingChanges.map((item) => `${item.label}: ${item.text}`).join('\n');
  const hasPendingChanges = pendingChanges.length > 0;

  function buildSaveFields(): { fields: UpdateBrandProfileRequest['fields']; error: string | null } {
    const payload: UpdateBrandProfileRequest['fields'] = [];

    for (const field of fields) {
      const choice = choiceDrafts[field.key];

      if (typeof choice === 'number') {
        const alternative = field.alternatives[choice];
        if (alternative === undefined) {
          return {
            fields: [],
            error: `Lựa chọn cho trường “${field.label}” không còn trong bản mới nhất. Hãy tải bản mới nhất rồi chọn lại.`,
          };
        }
        payload.push({ key: field.key, value: alternative.value });
        continue;
      }

      const draft = draftTextFor(field);
      if (draft === null) continue;

      const parsed = parseDraftText(field.key, draft);
      if (!parsed.ok) {
        return { fields: [], error: `Trường “${field.label}”: ${parsed.error}` };
      }
      payload.push({ key: field.key, value: parsed.value });
    }

    return { fields: payload, error: null };
  }

  function handleSave(confirm: boolean) {
    const built = buildSaveFields();
    if (built.error !== null) {
      setFormError(built.error);
      return;
    }
    if (built.fields.length === 0 && !confirm) {
      setFormError('Bạn chưa thay đổi trường nào nên chưa có gì để lưu.');
      return;
    }

    setFormError(null);
    setNotice(null);
    update.mutate(
      {
        version: profile.version,
        fields: built.fields,
        ...(confirm ? { confirm: true } : {}),
      },
      {
        onSuccess: () => {
          setTextDrafts({});
          setChoiceDrafts({});
          setNotice(
            confirm
              ? 'Đã lưu và xác nhận hồ sơ thương hiệu. Các trường vừa gửi được đánh dấu đã xác nhận.'
              : 'Đã lưu thay đổi vào hồ sơ thương hiệu.',
          );
        },
      },
    );
  }

  /** Tải bản mới nhất: người dùng đã được cảnh báo phải chép lại bản nháp trước. */
  function handleReloadAfterConflict() {
    setTextDrafts({});
    setChoiceDrafts({});
    setFormError(null);
    setNotice(
      'Đã tải bản mới nhất từ máy chủ. Thay đổi chưa lưu của bạn đã bị xoá — nếu chưa chép lại thì hãy nhập lại.',
    );
    void brandQuery.refetch();
  }

  const saveDisabledReason = !canEdit
    ? editDeniedReason
    : conflictError
      ? 'Bản trên máy chủ đã thay đổi. Hãy bấm “Tải bản mới nhất” rồi lưu lại — hệ thống không tự ghi đè.'
      : !hasPendingChanges
        ? 'Bạn chưa thay đổi trường nào nên chưa có gì để lưu.'
        : undefined;

  const confirmDisabledReason = !canConfirm
    ? confirmDeniedReason
    : conflictError
      ? 'Bản trên máy chủ đã thay đổi. Hãy bấm “Tải bản mới nhất” rồi xác nhận lại.'
      : profile.confirmed_at && !hasPendingChanges
        ? 'Hồ sơ đã được xác nhận và chưa có thay đổi mới nên không cần xác nhận lại.'
        : undefined;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold text-slate-900">Hồ sơ thương hiệu</h1>
          <Badge tone="neutral">Bản {formatNumber(profile.version)}</Badge>
          {profile.confirmed_at ? (
            <StatusBadge label="Hồ sơ đã xác nhận" tone="success" />
          ) : (
            <StatusBadge label="Hồ sơ chưa xác nhận toàn bộ" tone="warning" />
          )}
        </div>
        <p className="text-sm text-slate-600">
          Cập nhật lần cuối {formatDateTime(profile.updated_at)}
          {profile.confirmed_at
            ? ` · Xác nhận lúc ${formatDateTime(profile.confirmed_at)}`
            : ' · Chưa được xác nhận toàn bộ.'}
        </p>
        <p className="text-sm text-slate-600">
          Mọi giá trị AI trích xuất đều kèm nguồn: bấm “Xem nguồn” ở từng trường để đọc tài liệu,
          số trang/dòng và đoạn trích nguyên văn.
        </p>
      </header>

      {notice ? (
        <div
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
        >
          {notice}
        </div>
      ) : null}

      {conflictError ? (
        <div className="space-y-3">
          <VersionConflictNotice
            currentVersion={conflictError.currentVersion}
            onReload={handleReloadAfterConflict}
          />
          {hasPendingChanges ? (
            <div className="rounded-lg border border-amber-300 bg-white px-4 py-3">
              <h2 className="text-sm font-semibold text-amber-900">
                Thay đổi chưa lưu của bạn — hãy chép lại trước khi tải bản mới
              </h2>
              <p className="mt-1 text-sm text-amber-900">
                Bấm “Tải bản mới nhất” sẽ xoá phần bên dưới và không thể khôi phục. Hệ thống không tự
                lưu, cũng không tự thử lại, để không ghi đè thay đổi của đồng nghiệp.
              </p>
              <label htmlFor="unsaved-draft" className="mt-2 block text-sm font-medium text-slate-700">
                Nội dung chưa lưu (bôi đen rồi sao chép)
              </label>
              <textarea
                id="unsaved-draft"
                readOnly
                rows={Math.min(12, Math.max(3, pendingChanges.length + 1))}
                value={pendingDraftText}
                className="prose-caption mt-1 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-900"
              />
            </div>
          ) : null}
        </div>
      ) : null}

      {!canEdit ? (
        <PermissionNotice
          message={`${editDeniedReason} Bạn vẫn xem được toàn bộ giá trị và nguồn tài liệu, nhưng không sửa hay lưu được.`}
          requiredPermission={ACTION_REQUIREMENTS.editBrand}
        />
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Độ hoàn thiện hồ sơ"
          value={completeness === null ? '—' : formatPercent(completeness * 100, 0)}
          hint={
            completeness === null
              ? 'Máy chủ chưa trả về độ hoàn thiện nên chưa hiển thị được con số.'
              : 'Tỉ lệ trường đã được xác nhận, do máy chủ tính.'
          }
          tone={completeness !== null && completeness < 1 ? 'warning' : 'neutral'}
        />
        <StatCard
          label="Trường cần bạn xác nhận"
          value={formatNumber(awaiting)}
          hint="Gồm trường AI gợi ý và trường tài liệu mâu thuẫn."
          tone={awaiting > 0 ? 'warning' : 'neutral'}
        />
        <StatCard
          label="Trường còn thiếu"
          value={formatNumber(missing)}
          hint="Chưa thấy trong tài liệu và chưa có người nhập."
          tone={missing > 0 ? 'warning' : 'neutral'}
        />
        <StatCard
          label="Trường đã có giá trị"
          value={formatNumber(fieldsWithValue)}
          hint={`Trên tổng số ${formatNumber(fields.length)} trường của hồ sơ.`}
        />
      </div>

      {fieldsWithValue === 0 ? (
        <EmptyState
          tone="info"
          title="Hồ sơ chưa có thông tin nào"
          description="Chưa trường nào có giá trị: tài liệu tải lên chưa được đọc xong hoặc chưa có tài liệu. Hãy tải tài liệu doanh nghiệp lên để hệ thống trích xuất, hoặc tự nhập tay ở từng trường bên dưới rồi bấm “Lưu thay đổi”."
          action={
            <Link className="text-sm font-medium text-slate-900 underline" href={`/w/${workspaceId}/documents`}>
              Mở trang Tài liệu
            </Link>
          }
        />
      ) : null}

      <div className="space-y-4">
        {fields.map((field) => {
          const stateMeta = FIELD_REVIEW_STATE_LABELS[field.state];
          const control = FIELD_EDIT_CONTROL[field.key];
          const draft = textDrafts[field.key];
          const chosen = choiceDrafts[field.key];
          const inputId = `brand-field-${field.key}`;
          const hintId = `brand-field-${field.key}-hint`;
          const originalText = valueToDraftText(field.value, control);
          const currentValue = draft === undefined ? originalText : draft;
          const hasConflictChoices = field.state === FIELD_REVIEW_STATES.CONFLICT;
          const missingReason = canEdit
            ? 'Chưa có thông tin này trong tài liệu đã tải lên và chưa có người nhập tay. Bạn có thể nhập ở ô bên dưới rồi bấm “Lưu thay đổi”.'
            : 'Chưa có thông tin này trong tài liệu đã tải lên. Vai trò của bạn không được sửa hồ sơ — hãy nhờ chủ sở hữu bổ sung.';

          return (
            <Card
              key={field.key}
              title={field.label}
              actions={<StatusBadge label={stateMeta.label} tone={stateMeta.tone} />}
              footer={
                field.updated_at
                  ? `Cập nhật lần cuối: ${formatDateTime(field.updated_at)}`
                  : 'Chưa có mốc thời gian cập nhật cho trường này.'
              }
            >
              <div className="space-y-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Giá trị hiện tại
                  </p>
                  <div className="mt-1">
                    <FieldValueView
                      fieldKey={field.key}
                      value={field.value}
                      missingReason={missingReason}
                    />
                  </div>
                </div>

                {field.state === FIELD_REVIEW_STATES.SUGGESTED ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
                    <p className="text-sm font-semibold text-amber-900">
                      Giá trị do AI gợi ý — cần bạn xác nhận
                    </p>
                    <p className="mt-0.5 text-sm text-amber-900">
                      {typeof field.confidence === 'number'
                        ? `Độ tin cậy máy chủ báo: ${formatPercent(field.confidence * 100, 0)}.`
                        : 'Máy chủ chưa trả về độ tin cậy cho trường này nên chưa hiển thị được con số.'}{' '}
                      Giá trị này chưa phải thông tin chính thức cho tới khi bạn lưu hoặc xác nhận hồ sơ.
                    </p>
                  </div>
                ) : null}

                {hasConflictChoices ? (
                  <fieldset className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-3">
                    <legend className="px-1 text-sm font-semibold text-amber-900">
                      Tài liệu của bạn không thống nhất
                    </legend>
                    <p className="text-sm text-amber-900">
                      Các tài liệu đã tải lên ghi những giá trị khác nhau cho trường “{field.label}”.
                      Hãy chọn giá trị đúng; hệ thống chỉ dùng giá trị bạn chọn.
                    </p>
                    <div className="mt-2 space-y-3">
                      <div>
                        <label className="flex items-start gap-2 text-sm text-slate-900">
                          <input
                            type="radio"
                            name={`brand-choice-${field.key}`}
                            checked={chosen === undefined || chosen === 'current'}
                            onChange={() => {
                              // Chọn radio thì bỏ bản nháp gõ tay của trường này.
                              setTextDrafts((previousDrafts) => {
                                const nextDrafts = { ...previousDrafts };
                                delete nextDrafts[field.key];
                                return nextDrafts;
                              });
                              setChoiceDrafts((previous) => ({
                                ...previous,
                                [field.key]: 'current',
                              }));
                            }}
                            className="mt-0.5"
                          />
                          <span>
                            Giữ giá trị hiện tại: <strong>{field.value === null || field.value === undefined ? '—' : JSON.stringify(field.value)}</strong>
                            <span className="mt-0.5 block text-xs text-slate-600">
                              Chưa chốt giá trị nào — trường vẫn ở trạng thái cần bạn xử lý.
                            </span>
                          </span>
                        </label>
                      </div>

                      {field.alternatives.map((alternative, index) => (
                        <div key={`${field.key}-alt-${index}`}>
                          <label className="flex items-start gap-2 text-sm text-slate-900">
                            <input
                              type="radio"
                              name={`brand-choice-${field.key}`}
                              checked={chosen === index}
                              onChange={() => {
                                // Chọn radio thì bỏ bản nháp gõ tay của trường này.
                                setTextDrafts((previousDrafts) => {
                                  const nextDrafts = { ...previousDrafts };
                                  delete nextDrafts[field.key];
                                  return nextDrafts;
                                });
                                setChoiceDrafts((previous) => ({
                                  ...previous,
                                  [field.key]: index,
                                }));
                              }}
                              className="mt-0.5"
                            />
                            <span>
                              Chọn giá trị này:{' '}
                              <strong>{JSON.stringify(alternative.value)}</strong>
                            </span>
                          </label>
                          <div className="ml-6">
                            {alternative.provenance.length > 0 ? (
                              <ProvenanceList refs={alternative.provenance} />
                            ) : (
                              <p className="mt-1 text-xs text-slate-500">
                                Lựa chọn này không kèm nguồn tài liệu — hãy cân nhắc trước khi chọn.
                              </p>
                            )}
                          </div>
                        </div>
                      ))}

                      {field.alternatives.length === 0 ? (
                        <p className="text-sm text-amber-900">
                          Máy chủ báo trường này mâu thuẫn nhưng không gửi kèm lựa chọn nào. Hãy nhập
                          tay giá trị đúng ở ô bên dưới và bấm “Lưu thay đổi”.
                        </p>
                      ) : null}
                    </div>
                  </fieldset>
                ) : null}

                {control !== 'none' ? (
                  canEdit ? (
                    <div>
                      <label htmlFor={inputId} className="block text-sm font-medium text-slate-700">
                        Sửa “{field.label}”
                      </label>
                      {control === 'textarea' ? (
                        <textarea
                          id={inputId}
                          rows={4}
                          value={currentValue}
                          aria-describedby={hintId}
                          onChange={(event) => {
                            // Gõ tay thì bỏ lựa chọn radio của trường này để chỉ còn
                            // MỘT ý định lưu, tránh việc bản nháp và giá trị gửi lên lệch nhau.
                            setChoiceDrafts((previousChoices) => {
                              const nextChoices = { ...previousChoices };
                              delete nextChoices[field.key];
                              return nextChoices;
                            });
                            setTextDrafts((previous) => ({
                              ...previous,
                              [field.key]: event.target.value,
                            }));
                          }}
                          className="prose-caption mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                        />
                      ) : control === 'lines' || control === 'contact' ? (
                        <textarea
                          id={inputId}
                          rows={4}
                          value={currentValue}
                          aria-describedby={hintId}
                          onChange={(event) => {
                            // Gõ tay thì bỏ lựa chọn radio của trường này để chỉ còn
                            // MỘT ý định lưu, tránh việc bản nháp và giá trị gửi lên lệch nhau.
                            setChoiceDrafts((previousChoices) => {
                              const nextChoices = { ...previousChoices };
                              delete nextChoices[field.key];
                              return nextChoices;
                            });
                            setTextDrafts((previous) => ({
                              ...previous,
                              [field.key]: event.target.value,
                            }));
                          }}
                          className="prose-caption mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                        />
                      ) : (
                        <input
                          id={inputId}
                          type="text"
                          value={currentValue}
                          aria-describedby={hintId}
                          onChange={(event) => {
                            // Gõ tay thì bỏ lựa chọn radio của trường này để chỉ còn
                            // MỘT ý định lưu, tránh việc bản nháp và giá trị gửi lên lệch nhau.
                            setChoiceDrafts((previousChoices) => {
                              const nextChoices = { ...previousChoices };
                              delete nextChoices[field.key];
                              return nextChoices;
                            });
                            setTextDrafts((previous) => ({
                              ...previous,
                              [field.key]: event.target.value,
                            }));
                          }}
                          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                        />
                      )}
                      <p id={hintId} className="mt-1 text-xs text-slate-500">
                        {FIELD_EDIT_HINT[field.key]}
                      </p>
                      {draft !== undefined && draft !== originalText ? (
                        <p className="mt-1 text-xs font-medium text-sky-800">
                          Trường này có thay đổi chưa lưu.
                        </p>
                      ) : null}
                    </div>
                  ) : (
                    <p className="text-sm text-slate-600">
                      Ô sửa đã bị khoá: {editDeniedReason}
                    </p>
                  )
                ) : (
                  <UnavailableNotice
                    title="Chưa sửa được danh sách sản phẩm"
                    reason={FIELD_EDIT_HINT[BRAND_FIELD_KEYS.PRODUCTS]}
                    remedy="Chọn giá trị đúng từ tài liệu (nếu mục “Tài liệu của bạn không thống nhất” xuất hiện), hoặc sửa sản phẩm trong tài liệu gốc rồi tải lên lại."
                  />
                )}

                {field.provenance.length > 0 ? (
                  <ProvenanceList refs={field.provenance} />
                ) : (
                  <p className="text-xs text-slate-500">
                    {isMissingValue(field.value)
                      ? 'Chưa có nguồn tài liệu cho trường này.'
                      : 'Máy chủ không gửi nguồn tài liệu cho giá trị này — hãy kiểm tra lại trước khi dùng.'}
                  </p>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      <Card
        title="Lưu thay đổi"
        description="Hệ thống lưu kèm bản hiện tại để không ghi đè thay đổi của người khác."
      >
        <div className="space-y-3">
          {formError ? (
            <p role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-900">
              {formError}
            </p>
          ) : null}

          {hasPendingChanges ? (
            <div>
              <p className="text-sm font-medium text-slate-700">
                {formatNumber(pendingChanges.length)} trường sẽ được gửi lên:
              </p>
              <ul className="mt-1 list-inside list-disc text-sm text-slate-700">
                {pendingChanges.map((item) => (
                  <li key={item.key}>
                    <span className="font-medium">{item.label}</span>: {item.text}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-sm text-slate-600">
              Chưa có thay đổi nào. Sửa một trường ở trên rồi bấm “Lưu thay đổi”.
            </p>
          )}

          <div className="flex flex-wrap gap-3">
            <Button
              loading={update.isPending}
              disabled={saveDisabledReason !== undefined}
              disabledReason={saveDisabledReason}
              onClick={() => handleSave(false)}
            >
              Lưu thay đổi
            </Button>
            <Button
              variant="secondary"
              loading={update.isPending}
              disabled={confirmDisabledReason !== undefined}
              disabledReason={confirmDisabledReason}
              onClick={() => handleSave(true)}
            >
              Xác nhận hồ sơ
            </Button>
          </div>

          {saveDisabledReason !== undefined || confirmDisabledReason !== undefined ? (
            <DisabledReason>
              {[saveDisabledReason, confirmDisabledReason]
                .filter((reason): reason is string => reason !== undefined)
                .filter((reason, index, list) => list.indexOf(reason) === index)
                .join(' ')}
            </DisabledReason>
          ) : null}

          {saveError ? (
            <ErrorPanel
              title="Không lưu được hồ sơ thương hiệu"
              message={
                saveError instanceof ApiError
                  ? saveError.message
                  : 'Đã xảy ra lỗi không xác định. Vui lòng thử lại.'
              }
              code={saveError instanceof ApiError ? saveError.code : null}
              requestId={saveError instanceof ApiError ? saveError.requestId : null}
              retryable={saveError instanceof ApiError ? saveError.retryable : false}
              onRetry={hasPendingChanges ? () => handleSave(false) : undefined}
            />
          ) : null}
        </div>
      </Card>
    </div>
  );
}
