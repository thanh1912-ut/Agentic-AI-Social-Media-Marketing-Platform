/**
 * Kho dữ liệu demo trong bộ nhớ.
 *
 * Đây là dữ liệu MẪU do frontend tự sinh, dùng khi backend chưa sẵn sàng. Mọi
 * màn hình đọc từ đây đều phải mang nhãn "Dữ liệu demo" — không được để người
 * dùng tưởng đây là số liệu thật của doanh nghiệp họ.
 *
 * Khi backend có thật, chỉ cần đặt `NEXT_PUBLIC_USE_MOCKS=0` là toàn bộ tầng này
 * bị bỏ qua; không phải sửa một dòng nào ở tầng UI.
 *
 * ⚠️ Đây là bản mẫu để demo luồng làm việc. Trường nào chưa chốt với M2/M3 đều
 * được ghi chú `CONTRACT-REQUEST`.
 */

import {
  BRAND_FIELD_KEYS,
  CAMPAIGN_OBJECTIVES,
  CAMPAIGN_STATUSES,
  CHANNELS,
  CONTENT_PILLARS,
  DOCUMENT_ERROR_CODES,
  DOCUMENT_KINDS,
  DOCUMENT_STATUSES,
  FIELD_REVIEW_STATES,
  JOB_KINDS,
  JOB_STATUSES,
  JOB_STEP_STATUSES,
  POST_FORMATS,
  POST_STATUSES,
  ROLE_PERMISSIONS,
  VERSION_SOURCES,
  type BrandProfile,
  type BrandProfileField,
  type BrandProduct,
  type Campaign,
  type DocumentUpload,
  type Job,
  type Member,
  type OnboardingState,
  type Post,
  type PostVersionList,
  type UploadLimits,
  type User,
  type Workspace,
} from '@agentic/contracts';

/** Mốc thời gian cố định để dữ liệu demo không đổi giữa các lần tải. */
export const DEMO_NOW = '2026-03-15T09:00:00Z';

const hoursAgo = (hours: number): string =>
  new Date(new Date(DEMO_NOW).getTime() - hours * 3_600_000).toISOString();

// ---------------------------------------------------------------------------
// Người dùng & doanh nghiệp
// ---------------------------------------------------------------------------

export const DEMO_ACCOUNTS = {
  owner: { email: 'chu.quan@phobac.vn', password: 'demo1234' },
  editor: { email: 'bientap@phobac.vn', password: 'demo1234' },
  viewer: { email: 'xem@phobac.vn', password: 'demo1234' },
} as const;

const owner: User = {
  id: 'usr_owner',
  email: DEMO_ACCOUNTS.owner.email,
  full_name: 'Nguyễn Minh Tuấn',
  created_at: hoursAgo(24 * 90),
};

const editor: User = {
  id: 'usr_editor',
  email: DEMO_ACCOUNTS.editor.email,
  full_name: 'Trần Thu Hà',
  created_at: hoursAgo(24 * 60),
};

const viewer: User = {
  id: 'usr_viewer',
  email: DEMO_ACCOUNTS.viewer.email,
  full_name: 'Lê Quốc Bảo',
  created_at: hoursAgo(24 * 30),
};

export const demoUsers: User[] = [owner, editor, viewer];

/** Doanh nghiệp F&B — đầy đủ dữ liệu để demo luồng hoàn chỉnh. */
export const WS_FB = 'ws_pho_bac';
/** Doanh nghiệp bán lẻ mới tạo — để demo trạng thái rỗng. */
export const WS_RETAIL = 'ws_tap_hoa_an';

const workspaceFb: Workspace = {
  id: WS_FB,
  name: 'Phở Bắc Hà Nội',
  slug: 'pho-bac-ha-noi',
  industry: 'Nhà hàng / F&B',
  role: 'owner',
  permissions: [...ROLE_PERMISSIONS.owner],
  created_at: hoursAgo(24 * 85),
};

const workspaceRetail: Workspace = {
  id: WS_RETAIL,
  name: 'Tạp hoá An Nhiên',
  slug: 'tap-hoa-an-nhien',
  industry: 'Bán lẻ',
  role: 'owner',
  permissions: [...ROLE_PERMISSIONS.owner],
  created_at: hoursAgo(24 * 3),
};

export const demoWorkspaces: Workspace[] = [workspaceFb, workspaceRetail];

/** Đổi vai trò của người đang đăng nhập — dùng để demo UI theo vai trò. */
export function applyDemoRole(role: Workspace['role']): void {
  for (const workspace of demoWorkspaces) {
    workspace.role = role;
    workspace.permissions = [...ROLE_PERMISSIONS[role]];
  }
}

export const demoMembers: Record<string, Member[]> = {
  [WS_FB]: [
    { id: 'mem_1', user: owner, role: 'owner', status: 'active', joined_at: hoursAgo(24 * 85) },
    { id: 'mem_2', user: editor, role: 'editor', status: 'active', joined_at: hoursAgo(24 * 60) },
    {
      id: 'mem_3',
      user: null,
      role: 'viewer',
      status: 'invited',
      invited_email: 'moi-moi@pho-bac.vn',
      invitation_expires_at: new Date(
        new Date(DEMO_NOW).getTime() + 5 * 86_400_000,
      ).toISOString(),
    },
  ],
  [WS_RETAIL]: [
    { id: 'mem_4', user: owner, role: 'owner', status: 'active', joined_at: hoursAgo(24 * 3) },
  ],
};

// ---------------------------------------------------------------------------
// Onboarding
// ---------------------------------------------------------------------------

export const demoOnboarding: Record<string, OnboardingState> = {
  [WS_FB]: {
    steps: [
      { key: 'business_info', label: 'Nhập thông tin doanh nghiệp', status: 'done', href: '/brand' },
      { key: 'upload_documents', label: 'Tải tài liệu về doanh nghiệp', status: 'done', href: '/documents' },
      {
        key: 'confirm_brand',
        label: 'Xác nhận hồ sơ thương hiệu',
        status: 'in_progress',
        blocked_reason: 'Còn 3 trường AI gợi ý chưa được bạn xác nhận.',
        href: '/brand',
      },
      {
        key: 'create_campaign',
        label: 'Tạo chiến dịch đầu tiên',
        status: 'todo',
        blocked_reason: 'Cần xác nhận hồ sơ thương hiệu trước khi tạo chiến dịch.',
        href: '/campaigns',
      },
    ],
    completed_count: 2,
    total_count: 4,
  },
  [WS_RETAIL]: {
    steps: [
      { key: 'business_info', label: 'Nhập thông tin doanh nghiệp', status: 'todo', href: '/brand' },
      { key: 'upload_documents', label: 'Tải tài liệu về doanh nghiệp', status: 'todo', href: '/documents' },
      {
        key: 'confirm_brand',
        label: 'Xác nhận hồ sơ thương hiệu',
        status: 'blocked',
        blocked_reason: 'Chưa có tài liệu nào được tải lên nên chưa có gì để xác nhận.',
        href: '/brand',
      },
      {
        key: 'create_campaign',
        label: 'Tạo chiến dịch đầu tiên',
        status: 'blocked',
        blocked_reason: 'Phải hoàn thành hồ sơ thương hiệu trước.',
        href: '/campaigns',
      },
    ],
    completed_count: 0,
    total_count: 4,
  },
};

// ---------------------------------------------------------------------------
// Tài liệu
// ---------------------------------------------------------------------------

export const demoUploadLimits: UploadLimits = {
  max_file_size_bytes: 25 * 1024 * 1024,
  max_files_per_request: 10,
  accepted_kinds: [
    DOCUMENT_KINDS.PDF,
    DOCUMENT_KINDS.DOCX,
    DOCUMENT_KINDS.XLSX,
    DOCUMENT_KINDS.CSV,
    DOCUMENT_KINDS.TXT,
    DOCUMENT_KINDS.IMAGE,
  ],
  accepted_mime_types: [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv',
    'text/plain',
    'image/png',
    'image/jpeg',
  ],
};

const doc = (
  partial: Pick<DocumentUpload, 'id' | 'filename' | 'kind' | 'mime_type' | 'size' | 'status' | 'progress'> &
    Partial<DocumentUpload>,
): DocumentUpload => ({
  workspace_id: WS_FB,
  uploaded_by: owner.id,
  uploaded_at: hoursAgo(48),
  ...partial,
});

export const demoDocuments: Record<string, DocumentUpload[]> = {
  [WS_FB]: [
    doc({
      id: 'doc_menu',
      filename: 'thuc-don-pho-bac-2026.pdf',
      kind: DOCUMENT_KINDS.PDF,
      mime_type: 'application/pdf',
      size: 1_842_000,
      status: DOCUMENT_STATUSES.READY,
      progress: 100,
      extracted: { pages: 6, characters: 12_480 },
      uploaded_at: hoursAgo(50),
      processed_at: hoursAgo(50),
    }),
    doc({
      id: 'doc_brand_book',
      filename: 'brand-book-pho-bac.docx',
      kind: DOCUMENT_KINDS.DOCX,
      mime_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      size: 640_000,
      status: DOCUMENT_STATUSES.READY,
      progress: 100,
      extracted: { pages: 14, characters: 26_900 },
      uploaded_at: hoursAgo(49),
      processed_at: hoursAgo(49),
    }),
    doc({
      id: 'doc_khao_sat',
      filename: 'ket-qua-khao-sat-khach-hang.xlsx',
      kind: DOCUMENT_KINDS.XLSX,
      mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size: 320_000,
      status: DOCUMENT_STATUSES.READY,
      progress: 100,
      extracted: { rows: 412 },
      uploaded_at: hoursAgo(30),
      processed_at: hoursAgo(30),
    }),
    doc({
      id: 'doc_scan',
      filename: 'menu-scan-ban-chup.pdf',
      kind: DOCUMENT_KINDS.PDF,
      mime_type: 'application/pdf',
      size: 8_400_000,
      status: DOCUMENT_STATUSES.FAILED,
      progress: 40,
      error: {
        code: DOCUMENT_ERROR_CODES.PDF_NO_TEXT_LAYER,
        message: 'PDF này là ảnh scan, không có lớp văn bản để đọc.',
        hint: 'Hãy tải lên bản PDF có thể chọn/copy chữ, hoặc xuất lại từ Word.',
      },
      uploaded_at: hoursAgo(28),
    }),
    doc({
      id: 'doc_processing',
      filename: 'ghi-chu-hop-nhom-marketing.txt',
      kind: DOCUMENT_KINDS.TXT,
      mime_type: 'text/plain',
      size: 12_400,
      status: DOCUMENT_STATUSES.PROCESSING,
      progress: 65,
      job_id: 'job_brand_extract',
      uploaded_at: hoursAgo(1),
    }),
  ],
  [WS_RETAIL]: [],
};

// ---------------------------------------------------------------------------
// Hồ sơ thương hiệu
// ---------------------------------------------------------------------------

const field = <T,>(
  key: BrandProfileField<T>['key'],
  label: string,
  value: T | null,
  state: BrandProfileField<T>['state'],
  extra: Partial<BrandProfileField<T>> = {},
): BrandProfileField<T> => ({ key, label, value, state, provenance: [], ...extra });

const brandProfileFb: BrandProfile = {
  id: 'brand_pho_bac',
  workspace_id: WS_FB,
  version: 7,
  business_name: field(BRAND_FIELD_KEYS.BUSINESS_NAME, 'Tên doanh nghiệp', 'Phở Bắc Hà Nội', FIELD_REVIEW_STATES.CONFIRMED, {
    provenance: [
      {
        document_id: 'doc_brand_book',
        document_name: 'brand-book-pho-bac.docx',
        page: 1,
        quote: 'Phở Bắc Hà Nội — thương hiệu phở gia truyền ba đời tại Hà Nội.',
      },
    ],
    updated_at: hoursAgo(20),
  }),
  industry: field(BRAND_FIELD_KEYS.INDUSTRY, 'Ngành hàng', 'Nhà hàng / F&B', FIELD_REVIEW_STATES.CONFIRMED, {
    provenance: [
      { document_id: 'doc_brand_book', document_name: 'brand-book-pho-bac.docx', page: 2, quote: 'Lĩnh vực: nhà hàng ăn uống, chuyên phở bò.' },
    ],
  }),
  description: field(
    BRAND_FIELD_KEYS.DESCRIPTION,
    'Giới thiệu doanh nghiệp',
    'Quán phở gia truyền ba đời, nấu nước dùng từ xương bò ủ 12 tiếng, phục vụ bữa sáng và bữa trưa cho khách văn phòng và gia đình.',
    FIELD_REVIEW_STATES.EDITED,
    {
      provenance: [
        { document_id: 'doc_brand_book', document_name: 'brand-book-pho-bac.docx', page: 3, quote: 'Nước dùng ủ từ xương bò trong 12 tiếng, không dùng bột ngọt.' },
      ],
      updated_at: hoursAgo(6),
      updated_by: owner.id,
    },
  ),
  products: field(
    BRAND_FIELD_KEYS.PRODUCTS,
    'Sản phẩm chính',
    [
      { id: 'prd_1', name: 'Phở bò tái nạm', description: 'Bát phở đầy đủ tái và nạm.', price_range: '55.000 – 70.000đ', usp: ['Nước dùng ủ 12 tiếng'] },
      { id: 'prd_2', name: 'Phở gà ta', description: 'Gà ta thả vườn, nước dùng trong.', price_range: '50.000 – 65.000đ' },
      { id: 'prd_3', name: 'Quẩy giòn', price_range: '10.000đ' },
    ],
    FIELD_REVIEW_STATES.CONFIRMED,
    {
      provenance: [
        { document_id: 'doc_menu', document_name: 'thuc-don-pho-bac-2026.pdf', page: 1, quote: 'PHỞ BÒ TÁI NẠM 65.000đ — PHỞ GÀ TA 60.000đ — QUẨY 10.000đ' },
      ],
    },
  ),
  /* AI gợi ý, chưa xác nhận → UI hiển thị "cần xác nhận" + độ tin cậy. */
  target_audience: field(
    BRAND_FIELD_KEYS.TARGET_AUDIENCE,
    'Khách hàng mục tiêu',
    ['Dân văn phòng 25–40 tuổi quanh khu phố cổ', 'Gia đình đi ăn sáng cuối tuần'],
    FIELD_REVIEW_STATES.SUGGESTED,
    {
      confidence: 0.72,
      provenance: [
        { document_id: 'doc_khao_sat', document_name: 'ket-qua-khao-sat-khach-hang.xlsx', sheet: 'Sheet1', row: 12, quote: 'Khách đi làm buổi sáng, ăn nhanh trong 20 phút.' },
      ],
    },
  ),
  brand_voice: field(
    BRAND_FIELD_KEYS.BRAND_VOICE,
    'Giọng điệu thương hiệu',
    'Thân thiện, mộc mạc, nói về nghề nấu phở như kể chuyện gia đình. Không dùng từ ngữ hoa mỹ.',
    FIELD_REVIEW_STATES.SUGGESTED,
    {
      confidence: 0.64,
      provenance: [
        { document_id: 'doc_brand_book', document_name: 'brand-book-pho-bac.docx', page: 5, quote: 'Giọng điệu: gần gũi, như người nhà nói chuyện.' },
      ],
    },
  ),
  tone_keywords: field(
    BRAND_FIELD_KEYS.TONE_KEYWORDS,
    'Từ khoá giọng điệu',
    ['mộc mạc', 'gia truyền', 'nóng hổi', 'chuẩn vị Bắc'],
    FIELD_REVIEW_STATES.CONFIRMED,
  ),
  do_not_use: field(
    BRAND_FIELD_KEYS.DO_NOT_USE,
    'Từ ngữ cần tránh',
    ['ngon nhất Việt Nam', 'số 1', 'rẻ nhất'],
    FIELD_REVIEW_STATES.CONFIRMED,
    {
      provenance: [
        { document_id: 'doc_brand_book', document_name: 'brand-book-pho-bac.docx', page: 6, quote: 'Không dùng các từ mang tính so sánh tuyệt đối: ngon nhất, số 1, rẻ nhất.' },
      ],
    },
  ),
  /*
   * CONFLICT: hai tài liệu nói khác nhau về kênh bán — đây là trường hợp UI phải
   * cho người dùng CHỌN, không được tự lấy một giá trị.
   */
  competitors: field(
    BRAND_FIELD_KEYS.COMPETITORS,
    'Đối thủ chính',
    ['Phở Thìn', 'Phở Sướng'],
    FIELD_REVIEW_STATES.CONFLICT,
    {
      provenance: [
        { document_id: 'doc_brand_book', document_name: 'brand-book-pho-bac.docx', page: 8, quote: 'Đối thủ trực tiếp: Phở Thìn, Phở Sướng.' },
      ],
      alternatives: [
        {
          value: ['Phở Thìn', 'Phở Sướng'],
          provenance: [
            { document_id: 'doc_brand_book', document_name: 'brand-book-pho-bac.docx', page: 8, quote: 'Đối thủ trực tiếp: Phở Thìn, Phở Sướng.' },
          ],
        },
        {
          value: ['Phở Thìn', 'Phở Sướng', 'Phở 10 Lý Quốc Sư'],
          provenance: [
            { document_id: 'doc_khao_sat', document_name: 'ket-qua-khao-sat-khach-hang.xlsx', sheet: 'Sheet1', row: 40, quote: 'Khách còn nhắc tới Phở 10 Lý Quốc Sư.' },
          ],
        },
      ],
    },
  ),
  /* Thiếu hẳn → UI phải nói "còn thiếu", không được để trống im lặng. */
  contact: field<Record<string, string>>(BRAND_FIELD_KEYS.CONTACT, 'Thông tin liên hệ', null, FIELD_REVIEW_STATES.MISSING),
  confirmed_at: undefined,
  completeness: 0.7,
  updated_at: hoursAgo(6),
};

const brandProfileRetail: BrandProfile = {
  id: 'brand_an_nhien',
  workspace_id: WS_RETAIL,
  version: 1,
  business_name: field<string>(BRAND_FIELD_KEYS.BUSINESS_NAME, 'Tên doanh nghiệp', null, FIELD_REVIEW_STATES.MISSING),
  industry: field<string>(BRAND_FIELD_KEYS.INDUSTRY, 'Ngành hàng', null, FIELD_REVIEW_STATES.MISSING),
  description: field<string>(BRAND_FIELD_KEYS.DESCRIPTION, 'Giới thiệu doanh nghiệp', null, FIELD_REVIEW_STATES.MISSING),
  products: field<BrandProduct[]>(BRAND_FIELD_KEYS.PRODUCTS, 'Sản phẩm chính', null, FIELD_REVIEW_STATES.MISSING),
  target_audience: field<string[]>(BRAND_FIELD_KEYS.TARGET_AUDIENCE, 'Khách hàng mục tiêu', null, FIELD_REVIEW_STATES.MISSING),
  brand_voice: field<string>(BRAND_FIELD_KEYS.BRAND_VOICE, 'Giọng điệu thương hiệu', null, FIELD_REVIEW_STATES.MISSING),
  tone_keywords: field<string[]>(BRAND_FIELD_KEYS.TONE_KEYWORDS, 'Từ khoá giọng điệu', null, FIELD_REVIEW_STATES.MISSING),
  do_not_use: field<string[]>(BRAND_FIELD_KEYS.DO_NOT_USE, 'Từ ngữ cần tránh', null, FIELD_REVIEW_STATES.MISSING),
  competitors: field<string[]>(BRAND_FIELD_KEYS.COMPETITORS, 'Đối thủ chính', null, FIELD_REVIEW_STATES.MISSING),
  contact: field<Record<string, string>>(BRAND_FIELD_KEYS.CONTACT, 'Thông tin liên hệ', null, FIELD_REVIEW_STATES.MISSING),
  completeness: 0,
  updated_at: hoursAgo(3),
};

export const demoBrandProfiles: Record<string, BrandProfile> = {
  [WS_FB]: brandProfileFb,
  [WS_RETAIL]: brandProfileRetail,
};

// ---------------------------------------------------------------------------
// Job nền
// ---------------------------------------------------------------------------

/** Job đang chạy — dùng để demo thanh tiến độ có bước. */
const jobBrandExtract: Job = {
  id: 'job_brand_extract',
    kind: JOB_KINDS.BRAND_EXTRACT,
    status: JOB_STATUSES.RUNNING,
    title: 'Đang đọc tài liệu và trích xuất hồ sơ thương hiệu',
    progress: 60,
    steps: [
      { key: 'upload', label: 'Nhận tệp', status: JOB_STEP_STATUSES.SUCCEEDED, finished_at: hoursAgo(1) },
      { key: 'extract', label: 'Đọc nội dung tệp', status: JOB_STEP_STATUSES.SUCCEEDED, finished_at: hoursAgo(1) },
      { key: 'understand', label: 'Phân tích thông tin thương hiệu', status: JOB_STEP_STATUSES.RUNNING, progress: 60 },
      { key: 'merge', label: 'Gộp vào hồ sơ thương hiệu', status: JOB_STEP_STATUSES.PENDING },
    ],
    created_at: hoursAgo(1),
    started_at: hoursAgo(1),
    cancellable: true,
};
/** Job đã xong — demo trạng thái thành công. */
const jobDocumentIngest: Job = {
  id: 'job_document_ingest',
    kind: JOB_KINDS.DOCUMENT_INGEST,
    status: JOB_STATUSES.SUCCEEDED,
    title: 'Đã xử lý 3 tài liệu',
    progress: 100,
    steps: [
      { key: 'upload', label: 'Nhận tệp', status: JOB_STEP_STATUSES.SUCCEEDED, finished_at: hoursAgo(50) },
      { key: 'extract', label: 'Đọc nội dung tệp', status: JOB_STEP_STATUSES.SUCCEEDED, finished_at: hoursAgo(50) },
      { key: 'index', label: 'Đánh chỉ mục để tra cứu', status: JOB_STEP_STATUSES.SUCCEEDED, finished_at: hoursAgo(50) },
    ],
    result: { document_ids: ['doc_menu', 'doc_brand_book', 'doc_khao_sat'] },
    created_at: hoursAgo(50),
    started_at: hoursAgo(50),
    finished_at: hoursAgo(50),
    cancellable: false,
};
/** Job thất bại có `hint` — demo lỗi giải thích được, không chỉ báo "lỗi". */
const jobFailedScan: Job = {
  id: 'job_failed_scan',
    kind: JOB_KINDS.DOCUMENT_INGEST,
    status: JOB_STATUSES.FAILED,
    title: 'Không đọc được tệp menu-scan-ban-chup.pdf',
    progress: 40,
    steps: [
      { key: 'upload', label: 'Nhận tệp', status: JOB_STEP_STATUSES.SUCCEEDED, finished_at: hoursAgo(28) },
      {
        key: 'extract',
        label: 'Đọc nội dung tệp',
        status: JOB_STEP_STATUSES.FAILED,
        error: {
          code: DOCUMENT_ERROR_CODES.PDF_NO_TEXT_LAYER,
          message: 'PDF này là ảnh scan, không có lớp văn bản để đọc.',
        },
      },
      { key: 'index', label: 'Đánh chỉ mục để tra cứu', status: JOB_STEP_STATUSES.SKIPPED },
    ],
    error: {
      code: DOCUMENT_ERROR_CODES.PDF_NO_TEXT_LAYER,
      message: 'PDF này là ảnh scan, không có lớp văn bản để đọc.',
      hint: 'Hãy tải lên bản PDF có thể chọn/copy chữ, hoặc xuất lại từ Word.',
      retryable: false,
    },
    created_at: hoursAgo(28),
    started_at: hoursAgo(28),
    finished_at: hoursAgo(28),
    cancellable: false,
};

/** Bảng tra job theo id. */
export const demoJobs: Record<string, Job> = {
  [jobBrandExtract.id]: jobBrandExtract,
  [jobDocumentIngest.id]: jobDocumentIngest,
  [jobFailedScan.id]: jobFailedScan,
};

// ---------------------------------------------------------------------------
// Chiến dịch & nội dung (cho các lát cắt sau — dữ liệu tối thiểu)
// ---------------------------------------------------------------------------

const campaignActive: Campaign = {
  id: 'cmp_khai_truong',
  workspace_id: WS_FB,
  name: 'Chiến dịch tháng 3 — Khách văn phòng',
  status: CAMPAIGN_STATUSES.ACTIVE,
  content_plan: {
    strategy_summary: 'Nhấn vào bữa trưa nhanh gọn, nước dùng ninh 12 tiếng và thông tin giá rõ ràng.',
    slots: [
      { id: 'slot-trua-1', scheduled_date: '2026-03-04', pillar: CONTENT_PILLARS.PRODUCT, format: POST_FORMATS.IMAGE, topic: 'Bát phở nóng hổi cho giờ nghỉ trưa' },
      { id: 'slot-trua-2', scheduled_date: '2026-03-11', pillar: CONTENT_PILLARS.BEHIND_THE_SCENES, format: POST_FORMATS.TEXT, topic: 'Nước dùng ninh từ sáng sớm' },
    ],
  },
  brief: {
    objective: CAMPAIGN_OBJECTIVES.TRAFFIC,
    objective_note: 'Kéo khách văn phòng quanh phố cổ tới ăn trưa trong tháng 3.',
    audience: ['Dân văn phòng 25–40 tuổi', 'Khách quen ăn trưa hằng ngày'],
    product_ids: ['prd_1', 'prd_2'],
    key_message: 'Bát phở nóng hổi, nước dùng ủ 12 tiếng, sẵn sàng trong 5 phút.',
    must_include: ['Nước dùng ủ 12 tiếng'],
    must_avoid: ['ngon nhất', 'số 1'],
    start_date: '2026-03-01',
    end_date: '2026-03-31',
  },
  pillars: [CONTENT_PILLARS.PRODUCT, CONTENT_PILLARS.BEHIND_THE_SCENES],
  channels: [CHANNELS.FACEBOOK_PAGE],
  version: 3,
  post_count: 5,
  approved_count: 2,
  published_count: 1,
  created_by: owner.id,
  created_at: hoursAgo(24 * 12),
  updated_at: hoursAgo(20),
};

export const demoCampaigns: Record<string, Campaign[]> = {
  [WS_FB]: [campaignActive],
  [WS_RETAIL]: [],
};

const captionApproved =
  'Trưa nay ăn gì?\n\nBát phở bò tái nạm với nước dùng ủ 12 tiếng từ xương bò, chan nóng hổi ngay khi bạn ngồi xuống. Từ lúc gọi tới lúc có bát phở chỉ khoảng 5 phút — vừa đủ cho một bữa trưa gọn gàng.\n\nQuán mở 6h–14h mỗi ngày.';

const postApproved: Post = {
  id: 'post_1',
  campaign_id: campaignActive.id,
  workspace_id: WS_FB,
  channel: CHANNELS.FACEBOOK_PAGE,
  pillar: CONTENT_PILLARS.PRODUCT,
  format: POST_FORMATS.IMAGE,
  status: POST_STATUSES.APPROVED,
  version: 3,
  current: {
    version: 3,
    caption: captionApproved,
    hashtags: ['#phobachanoi', '#bualunchuyenvanphong'],
    media: [],
    source: VERSION_SOURCES.HUMAN,
    created_by: editor.id,
    created_by_name: editor.full_name,
    created_at: hoursAgo(20),
  },
  publish_mode: 'scheduled',
  scheduled_at: new Date(new Date(DEMO_NOW).getTime() + 26 * 3_600_000).toISOString(),
  requires_reapproval: false,
  created_at: hoursAgo(30),
  updated_at: hoursAgo(20),
};

const postNeedsReview: Post = {
  id: 'post_2',
  campaign_id: campaignActive.id,
  workspace_id: WS_FB,
  channel: CHANNELS.FACEBOOK_PAGE,
  pillar: CONTENT_PILLARS.BEHIND_THE_SCENES,
  format: POST_FORMATS.CAROUSEL,
  status: POST_STATUSES.NEEDS_REVIEW,
  version: 2,
  current: {
    version: 2,
    caption:
      '4 giờ sáng ở Phở Bắc.\n\nNồi nước dùng bắt đầu được ninh từ lúc cả phố còn ngủ. Ba đời nhà mình vẫn giữ đúng một cách: xương bò ủ đủ 12 tiếng, không bột ngọt.\n\nẢnh 1: Nồi nước dùng lúc 4h sáng.\nẢnh 2: Hành lá thái tại quán.\nẢnh 3: Bát phở thành phẩm.',
    hashtags: ['#hautruong', '#phobachanoi'],
    media: [],
    source: VERSION_SOURCES.AI_REVISED,
    created_by: editor.id,
    created_by_name: editor.full_name,
    created_at: hoursAgo(8),
    note: 'Nhờ AI viết ngắn lại và thêm phần mô tả ảnh.',
    review: {
      score: 82,
      summary: 'Nội dung đúng giọng điệu thương hiệu. Có một điểm cần lưu ý về từ ngữ.',
      checks: [
        { key: 'brand_voice', label: 'Giọng điệu thương hiệu', status: 'pass', message: 'Mộc mạc, gần gũi, đúng giọng điệu đã xác nhận.' },
        { key: 'banned_words', label: 'Từ ngữ cần tránh', status: 'pass', message: 'Không dùng từ bị cấm.' },
        { key: 'length', label: 'Độ dài', status: 'warn', message: 'Caption hơi dài so với bài trước đó của quán.', char_start: 0, char_end: 20 },
      ],
    },
  },
  requires_reapproval: false,
  created_at: hoursAgo(10),
  updated_at: hoursAgo(8),
};

/**
 * Bài ĐÃ DUYỆT nhưng bị sửa tiếp → `requires_reapproval: true`.
 * UI phải nói rõ "cần duyệt lại", không được để publish im lặng.
 */
const postApprovedThenEdited: Post = {
  id: 'post_3',
  campaign_id: campaignActive.id,
  workspace_id: WS_FB,
  channel: CHANNELS.FACEBOOK_PAGE,
  pillar: CONTENT_PILLARS.PROMOTION,
  format: POST_FORMATS.IMAGE,
  status: POST_STATUSES.APPROVED,
  version: 4,
  current: {
    version: 4,
    caption:
      'Combo trưa 55.000đ: phở bò tái nạm + trà đá.\n\nÁp dụng 11h–13h các ngày trong tuần. Không áp dụng ngày lễ.',
    hashtags: ['#combotrua'],
    media: [],
    source: VERSION_SOURCES.HUMAN,
    created_by: editor.id,
    created_by_name: editor.full_name,
    created_at: hoursAgo(3),
    note: 'Sửa giá combo sau khi đã duyệt.',
  },
  requires_reapproval: true,
  created_at: hoursAgo(40),
  updated_at: hoursAgo(3),
};

export const demoPosts: Record<string, Post[]> = {
  [WS_FB]: [postApproved, postNeedsReview, postApprovedThenEdited],
  [WS_RETAIL]: [],
};

export const demoPostVersions: Record<string, PostVersionList> = {
  post_3: {
    post_id: 'post_3',
    current_version: 4,
    pending_approval_version: undefined,
    versions: [
      {
        version: 4,
        caption: postApprovedThenEdited.current.caption,
        hashtags: postApprovedThenEdited.current.hashtags,
        media: [],
        source: VERSION_SOURCES.HUMAN,
        created_by: editor.id,
        created_by_name: editor.full_name,
        created_at: hoursAgo(3),
        note: 'Sửa giá combo sau khi đã duyệt.',
      },
      {
        version: 3,
        caption: 'Combo trưa 59.000đ: phở bò tái nạm + trà đá.\n\nÁp dụng 11h–13h các ngày trong tuần.',
        hashtags: ['#combotrua'],
        media: [],
        source: VERSION_SOURCES.HUMAN,
        created_by: editor.id,
        created_by_name: editor.full_name,
        created_at: hoursAgo(20),
      },
      {
        version: 1,
        caption: 'Bữa trưa tiết kiệm cùng Phở Bắc Hà Nội! Combo phở + trà đá chỉ 59.000đ.',
        hashtags: ['#combotrua', '#phobachanoi'],
        media: [],
        source: VERSION_SOURCES.AI_GENERATED,
        created_by: editor.id,
        created_by_name: editor.full_name,
        created_at: hoursAgo(40),
      },
    ],
  },
};

/** Người đang đăng nhập. Đổi được để demo giao diện theo vai trò. */
export let currentUserId: string = owner.id;
export function setCurrentUser(userId: string): void {
  currentUserId = userId;
}
export function getUserById(userId: string): User | undefined {
  return demoUsers.find((user) => user.id === userId);
}
