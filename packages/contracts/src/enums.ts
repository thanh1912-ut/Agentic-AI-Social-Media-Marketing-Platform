/**
 * DRAFT — Từ vựng dùng chung (shared vocabulary).
 *
 * Nguồn: brief M1 + đối chiếu pattern repo tham chiếu `agenticAI_VNS_mkt`.
 * TRẠNG THÁI: DRAFT, chờ M2/M3 review. KHÔNG tự đổi giá trị enum khi chưa thống nhất,
 * vì backend phải trả đúng các chuỗi này.
 *
 * Quy ước:
 * - snake_case cho mọi giá trị enum (khớp OpenAPI của repo tham chiếu).
 * - Mọi enum được export dạng `as const` object + type suy ra, để dùng được cả
 *   ở runtime (render nhãn tiếng Việt) lẫn compile-time.
 */

/** Trợ giúp: mọi giá trị của một object `as const`. */
export type ValueOf<T> = T[keyof T];

// ---------------------------------------------------------------------------
// 1. Vai trò & quyền
// ---------------------------------------------------------------------------

export const WORKSPACE_ROLES = {
  OWNER: 'owner',
  EDITOR: 'editor',
  VIEWER: 'viewer',
} as const;
export type WorkspaceRole = ValueOf<typeof WORKSPACE_ROLES>;

/**
 * Quyền chi tiết. Backend là nơi kiểm quyền CUỐI CÙNG; frontend chỉ dùng để
 * ẩn/hiện nút và giải thích lý do — không bao giờ là lớp bảo vệ duy nhất.
 */
export const PERMISSIONS = {
  WORKSPACE_MANAGE: 'workspace:manage',
  MEMBER_INVITE: 'member:invite',
  BRAND_EDIT: 'brand:edit',
  BRAND_CONFIRM: 'brand:confirm',
  DOCUMENT_UPLOAD: 'document:upload',
  CAMPAIGN_CREATE: 'campaign:create',
  CAMPAIGN_EDIT: 'campaign:edit',
  POST_EDIT: 'post:edit',
  POST_GENERATE: 'post:generate',
  POST_APPROVE: 'post:approve',
  POST_REJECT: 'post:reject',
  EXPORT_CREATE: 'export:create',
  CONNECTION_MANAGE: 'connection:manage',
  PUBLISH_CREATE: 'publish:create',
  METRIC_IMPORT: 'metric:import',
  RECOMMENDATION_APPLY: 'recommendation:apply',
} as const;
export type Permission = ValueOf<typeof PERMISSIONS>;

/** Ma trận quyền mặc định theo vai trò (đề xuất — M2 xác nhận). */
export const ROLE_PERMISSIONS: Record<WorkspaceRole, readonly Permission[]> = {
  owner: Object.values(PERMISSIONS),
  editor: [
    PERMISSIONS.BRAND_EDIT,
    PERMISSIONS.DOCUMENT_UPLOAD,
    PERMISSIONS.CAMPAIGN_CREATE,
    PERMISSIONS.CAMPAIGN_EDIT,
    PERMISSIONS.POST_EDIT,
    PERMISSIONS.POST_GENERATE,
    PERMISSIONS.EXPORT_CREATE,
    PERMISSIONS.METRIC_IMPORT,
  ],
  viewer: [],
};

// ---------------------------------------------------------------------------
// 2. Job nền (long-running request)
// ---------------------------------------------------------------------------

/**
 * Mọi request dài phải trả `job_id`; UI theo dõi bằng `GET /api/v1/jobs/{job_id}`.
 */
export const JOB_STATUSES = {
  QUEUED: 'queued',
  RUNNING: 'running',
  SUCCEEDED: 'succeeded',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;
export type JobStatus = ValueOf<typeof JOB_STATUSES>;

export const JOB_STEP_STATUSES = {
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCEEDED: 'succeeded',
  FAILED: 'failed',
  SKIPPED: 'skipped',
} as const;
export type JobStepStatus = ValueOf<typeof JOB_STEP_STATUSES>;

/** Loại job — dùng để UI chọn thông điệp và bước hiển thị phù hợp. */
export const JOB_KINDS = {
  DOCUMENT_INGEST: 'document_ingest',
  BRAND_EXTRACT: 'brand_extract',
  CONTENT_GENERATE: 'content_generate',
  CONTENT_REVISE: 'content_revise',
  EXPORT_BUILD: 'export_build',
  METRIC_IMPORT: 'metric_import',
  PUBLICATION_SEND: 'publication_send',
  RECOMMENDATION_RUN: 'recommendation_run',
} as const;
export type JobKind = ValueOf<typeof JOB_KINDS>;

// ---------------------------------------------------------------------------
// 3. Tài liệu & Brand knowledge
// ---------------------------------------------------------------------------

/** Định dạng tài liệu được chấp nhận (theo brief: PDF/DOCX/XLSX/CSV/TXT/ảnh). */
export const DOCUMENT_KINDS = {
  PDF: 'pdf',
  DOCX: 'docx',
  XLSX: 'xlsx',
  CSV: 'csv',
  TXT: 'txt',
  IMAGE: 'image',
} as const;
export type DocumentKind = ValueOf<typeof DOCUMENT_KINDS>;

export const DOCUMENT_STATUSES = {
  PENDING: 'pending',
  UPLOADING: 'uploading',
  PROCESSING: 'processing',
  READY: 'ready',
  FAILED: 'failed',
  UNSUPPORTED: 'unsupported',
} as const;
export type DocumentStatus = ValueOf<typeof DOCUMENT_STATUSES>;

/** Mã lỗi xử lý tài liệu — UI phải giải thích được, không chỉ báo "lỗi". */
export const DOCUMENT_ERROR_CODES = {
  PDF_NO_TEXT_LAYER: 'pdf_no_text_layer',
  FILE_TOO_LARGE: 'file_too_large',
  UNSUPPORTED_TYPE: 'unsupported_type',
  CORRUPTED: 'corrupted',
  ENCRYPTED: 'encrypted',
  OCR_FAILED: 'ocr_failed',
  EMPTY_CONTENT: 'empty_content',
} as const;
export type DocumentErrorCode = ValueOf<typeof DOCUMENT_ERROR_CODES>;

/** Trường của Brand Profile. */
export const BRAND_FIELD_KEYS = {
  BUSINESS_NAME: 'business_name',
  INDUSTRY: 'industry',
  DESCRIPTION: 'description',
  PRODUCTS: 'products',
  TARGET_AUDIENCE: 'target_audience',
  BRAND_VOICE: 'brand_voice',
  TONE_KEYWORDS: 'tone_keywords',
  DO_NOT_USE: 'do_not_use',
  COMPETITORS: 'competitors',
  CONTACT: 'contact',
} as const;
export type BrandFieldKey = ValueOf<typeof BRAND_FIELD_KEYS>;

/** Trạng thái xác nhận của từng trường Brand Profile. */
export const FIELD_REVIEW_STATES = {
  SUGGESTED: 'suggested',
  CONFIRMED: 'confirmed',
  EDITED: 'edited',
  MISSING: 'missing',
  CONFLICT: 'conflict',
} as const;
export type FieldReviewState = ValueOf<typeof FIELD_REVIEW_STATES>;

// ---------------------------------------------------------------------------
// 4. Campaign & nội dung
// ---------------------------------------------------------------------------

export const CAMPAIGN_STATUSES = {
  DRAFT: 'draft',
  ACTIVE: 'active',
  COMPLETED: 'completed',
  ARCHIVED: 'archived',
} as const;
export type CampaignStatus = ValueOf<typeof CAMPAIGN_STATUSES>;

export const CAMPAIGN_OBJECTIVES = {
  AWARENESS: 'awareness',
  ENGAGEMENT: 'engagement',
  TRAFFIC: 'traffic',
  LEADS: 'leads',
  SALES: 'sales',
  RETENTION: 'retention',
} as const;
export type CampaignObjective = ValueOf<typeof CAMPAIGN_OBJECTIVES>;

/** Content pillar — trụ nội dung. */
export const CONTENT_PILLARS = {
  EDUCATION: 'education',
  ENTERTAINMENT: 'entertainment',
  INSPIRATION: 'inspiration',
  PROMOTION: 'promotion',
  COMMUNITY: 'community',
  BEHIND_THE_SCENES: 'behind_the_scenes',
  PRODUCT: 'product',
  TESTIMONIAL: 'testimonial',
} as const;
export type ContentPillar = ValueOf<typeof CONTENT_PILLARS>;

export const POST_FORMATS = {
  TEXT: 'text',
  IMAGE: 'image',
  CAROUSEL: 'carousel',
  VIDEO: 'video',
  REEL: 'reel',
  STORY: 'story',
} as const;
export type PostFormat = ValueOf<typeof POST_FORMATS>;

export const CHANNELS = {
  FACEBOOK_PAGE: 'facebook_page',
} as const;
export type Channel = ValueOf<typeof CHANNELS>;

/** Vòng đời nội dung. `approved` là mốc khoá version để publish. */
export const POST_STATUSES = {
  DRAFT: 'draft',
  NEEDS_REVIEW: 'needs_review',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  SCHEDULED: 'scheduled',
  PUBLISHED: 'published',
  FAILED: 'failed',
} as const;
export type PostStatus = ValueOf<typeof POST_STATUSES>;

/** Nguồn sinh ra một version — dùng cho lịch sử phiên bản. */
export const VERSION_SOURCES = {
  HUMAN: 'human',
  AI_GENERATED: 'ai_generated',
  AI_REVISED: 'ai_revised',
  IMPORTED: 'imported',
} as const;
export type VersionSource = ValueOf<typeof VERSION_SOURCES>;

export const APPROVAL_DECISIONS = {
  APPROVED: 'approved',
  REJECTED: 'rejected',
} as const;
export type ApprovalDecision = ValueOf<typeof APPROVAL_DECISIONS>;

export const EXPORT_FORMATS = {
  CSV: 'csv',
  XLSX: 'xlsx',
} as const;
export type ExportFormat = ValueOf<typeof EXPORT_FORMATS>;

// ---------------------------------------------------------------------------
// 5. Publishing
// ---------------------------------------------------------------------------

export const CONNECTION_STATUSES = {
  CONNECTED: 'connected',
  EXPIRED: 'expired',
  NEEDS_RECONNECT: 'needs_reconnect',
  REVOKED: 'revoked',
} as const;
export type ConnectionStatus = ValueOf<typeof CONNECTION_STATUSES>;

/**
 * Trạng thái xuất bản.
 *
 * LƯU Ý QUAN TRỌNG:
 * - `outcome_unknown`: đã gửi nhưng KHÔNG xác định được kết quả. TUYỆT ĐỐI không
 *   cung cấp nút "Thử lại" thông thường (sẽ gây đăng trùng). Chỉ cho phép đối soát
 *   thủ công và nhập URL nếu người dùng xác nhận bài đã lên.
 * - Export KHÔNG BAO GIỜ được hiển thị là `published`.
 */
export const PUBLICATION_STATUSES = {
  PENDING: 'pending',
  SENDING: 'sending',
  PUBLISHED: 'published',
  FAILED: 'failed',
  OUTCOME_UNKNOWN: 'outcome_unknown',
  NEEDS_RECONNECT: 'needs_reconnect',
  MANUAL_RECORDED: 'manual_recorded',
} as const;
export type PublicationStatus = ValueOf<typeof PUBLICATION_STATUSES>;

/** Nguồn của bản ghi xuất bản — API hay người dùng nhập tay. */
export const PUBLICATION_SOURCES = {
  API: 'api',
  MANUAL: 'manual',
} as const;
export type PublicationSource = ValueOf<typeof PUBLICATION_SOURCES>;

/** Khoá năng lực (capability) — UI hiển thị lý do khi chưa khả dụng. */
export const CAPABILITY_KEYS = {
  PUBLISH_NOW: 'publish_now',
  SCHEDULE: 'schedule',
  SYNC_METRICS: 'sync_metrics',
  READ_INSIGHTS: 'read_insights',
  COMMENT_MODERATION: 'comment_moderation',
} as const;
export type CapabilityKey = ValueOf<typeof CAPABILITY_KEYS>;

// ---------------------------------------------------------------------------
// 6. Analytics
// ---------------------------------------------------------------------------

/**
 * Trạng thái của một ô số liệu. Phân biệt RÕ ba thứ khác nhau:
 * - `value`   : có số thật (kể cả 0 thật → dùng `value: 0`)
 * - `no_data` : chưa có dữ liệu / ngoài cửa sổ đo
 * - `not_permitted`: không có quyền đọc chỉ số này
 * - `not_supported`: kênh không cung cấp chỉ số này
 */
export const METRIC_STATES = {
  VALUE: 'value',
  NO_DATA: 'no_data',
  NOT_PERMITTED: 'not_permitted',
  NOT_SUPPORTED: 'not_supported',
  STALE: 'stale',
} as const;
export type MetricState = ValueOf<typeof METRIC_STATES>;

/** Nguồn số liệu — phải hiển thị cho người dùng biết. */
export const METRIC_SOURCES = {
  API: 'api',
  MANUAL: 'manual',
} as const;
export type MetricSource = ValueOf<typeof METRIC_SOURCES>;

export const METRIC_KEYS = {
  IMPRESSIONS: 'impressions',
  REACH: 'reach',
  ENGAGEMENTS: 'engagements',
  REACTIONS: 'reactions',
  COMMENTS: 'comments',
  SHARES: 'shares',
  CLICKS: 'clicks',
  VIDEO_VIEWS: 'video_views',
  SAVES: 'saves',
  ENGAGEMENT_RATE: 'engagement_rate',
} as const;
export type MetricKey = ValueOf<typeof METRIC_KEYS>;

export const AGGREGATION_LEVELS = {
  POST: 'post',
  CAMPAIGN: 'campaign',
  PILLAR: 'pillar',
  FORMAT: 'format',
} as const;
export type AggregationLevel = ValueOf<typeof AGGREGATION_LEVELS>;

// ---------------------------------------------------------------------------
// 7. Recommendation
// ---------------------------------------------------------------------------

export const RECOMMENDATION_STATUSES = {
  NEW: 'new',
  ACKNOWLEDGED: 'acknowledged',
  APPLIED: 'applied',
  DISMISSED: 'dismissed',
} as const;
export type RecommendationStatus = ValueOf<typeof RECOMMENDATION_STATUSES>;

export const RECOMMENDATION_FEEDBACK = {
  USEFUL: 'useful',
  NOT_USEFUL: 'not_useful',
  ALREADY_DONE: 'already_done',
} as const;
export type RecommendationFeedback = ValueOf<typeof RECOMMENDATION_FEEDBACK>;

/** Loại hành động khi "Apply recommendation" — tạo bản nháp để người dùng xem lại. */
export const RECOMMENDATION_ACTIONS = {
  CAMPAIGN_BRIEF_REVISION: 'campaign_brief_revision',
  STRATEGY_REVISION: 'strategy_revision',
  CONTENT_BRIEF: 'content_brief',
} as const;
export type RecommendationAction = ValueOf<typeof RECOMMENDATION_ACTIONS>;

/** Độ tin cậy của bằng chứng đứng sau một recommendation. */
export const EVIDENCE_STRENGTHS = {
  STRONG: 'strong',
  MODERATE: 'moderate',
  WEAK: 'weak',
  INSUFFICIENT: 'insufficient',
} as const;
export type EvidenceStrength = ValueOf<typeof EVIDENCE_STRENGTHS>;

// ---------------------------------------------------------------------------
// 8. Nguồn dữ liệu hiển thị (demo vs thật)
// ---------------------------------------------------------------------------

/**
 * Mọi dữ liệu demo phải mang nhãn này và UI phải hiển thị — không được giả
 * thành dữ liệu thật.
 */
export const DATA_ORIGINS = {
  LIVE: 'live',
  DEMO: 'demo',
} as const;
export type DataOrigin = ValueOf<typeof DATA_ORIGINS>;
