/**
 * Endpoints có kiểu — bọc `apiRequest` để component không bao giờ tự ghép URL.
 *
 * Endpoint thuộc lát cắt auth/workspace/document/job dùng DTO sinh từ OpenAPI
 * trong `src/lib/api/types.ts`. Endpoint còn lại là UI demo-only và không được
 * gọi ở real mode cho tới khi backend công bố OpenAPI tương ứng.
 *
 * ⚠️ Những chỗ đánh dấu `CONTRACT-REQUEST` là endpoint/field mình cần M2 xác nhận.
 */

import type {
  AcceptedResponse,
  AnalyticsQuery,
  AnalyticsResponse,
  ApplyRecommendationRequest,
  ApplyRecommendationResponse,
  ApprovalRecord,
  ApprovalRequest,
  Campaign,
  CreateExportRequest,
  CreateManualPostRequest,
  ExportJob,
  FacebookPage,
  GenerateContentRequest,
  GenerateContentResponse,
  InviteMemberResponse,
  ManualPublicationRequest,
  Member,
  MetricImportCommitRequest,
  MetricImportPreview,
  OnboardingState,
  Paginated,
  Post,
  PostVersionList,
  Publication,
  PublicationEvent,
  PublishRequest,
  Recommendation,
  RecommendationFeedbackRequest,
  ReextractFieldRequest,
  ReviseWithAiRequest,
  SelectPageRequest,
  SocialConnection,
  UpdateMemberRoleRequest,
  UpdatePostRequest,
} from '@agentic/contracts';

import type {
  ApiAcceptInvitationRequest,
  ApiAcceptedResponse,
  ApiBrandProfile,
  ApiConfirmBrandProfileRequest,
  ApiDocument,
  ApiForgotPasswordRequest,
  ApiInviteMemberRequest,
  ApiInviteMemberResponse,
  ApiJob,
  ApiJobEvent,
  ApiUpdateBrandProfileRequest,
  ApiLoginRequest,
  ApiLoginResponse,
  ApiMember,
  ApiResetPasswordRequest,
  ApiSelectWorkspaceRequest,
  ApiSessionResponse,
  ApiUploadLimits,
  ApiWorkspace,
} from './types';

import { apiDownload, apiRequest, apiUpload, newIdempotencyKey } from './client';

export type { ApiUser as User } from './types';

const v1 = (path: string) => path;

// ---------------------------------------------------------------------------
// Phiên & xác thực
// ---------------------------------------------------------------------------

export const authApi = {
  /** `GET /me` — trạng thái phiên hiện tại. */
  me: (signal?: AbortSignal) =>
    apiRequest<ApiSessionResponse>(v1('/me'), { signal }),

  login: (body: ApiLoginRequest) =>
    apiRequest<ApiLoginResponse>(v1('/auth/login'), { method: 'POST', body }),

  logout: () => apiRequest<void>(v1('/auth/logout'), { method: 'POST' }),

  refresh: () => apiRequest<ApiLoginResponse>(v1('/auth/refresh'), { method: 'POST' }),

  forgotPassword: (email: string) =>
    apiRequest<unknown>(v1('/auth/forgot-password'), {
      method: 'POST',
      body: { email } satisfies ApiForgotPasswordRequest,
    }),

  resetPassword: (body: ApiResetPasswordRequest) =>
    apiRequest<unknown>(v1('/auth/reset-password'), { method: 'POST', body }),

  /** Xem trước lời mời trước khi đăng nhập/tạo tài khoản. */
  previewInvitation: (token: string) =>
    apiRequest<unknown>(v1(`/auth/invitations/${encodeURIComponent(token)}`)),

  acceptInvitation: (token: string, body: ApiAcceptInvitationRequest) =>
    apiRequest<ApiLoginResponse>(
      v1(`/auth/invitations/${encodeURIComponent(token)}/accept`),
      { method: 'POST', body },
    ),
};

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

export const workspaceApi = {
  list: () => apiRequest<readonly ApiWorkspace[]>(v1('/workspaces')),

  get: (workspaceId: string) =>
    apiRequest<ApiWorkspace>(v1(`/workspaces/${workspaceId}`)),

  select: (workspaceId: string) =>
    apiRequest<ApiSessionResponse>(v1('/me/active-workspace'), {
      method: 'PUT',
      body: { workspace_id: workspaceId } satisfies ApiSelectWorkspaceRequest,
    }),

  /** Mock-only: hiện không có trong OpenAPI; useOnboarding tắt endpoint khi mocks=0. */
  onboarding: (workspaceId: string) =>
    apiRequest<OnboardingState>(v1(`/workspaces/${workspaceId}/onboarding`)),

  members: (workspaceId: string) =>
    apiRequest<readonly ApiMember[]>(v1(`/workspaces/${workspaceId}/members`)),

  inviteMember: (workspaceId: string, body: ApiInviteMemberRequest) =>
    apiRequest<ApiInviteMemberResponse>(v1(`/workspaces/${workspaceId}/members`), {
      method: 'POST',
      body,
    }),

  updateMemberRole: (
    workspaceId: string,
    memberId: string,
    body: UpdateMemberRoleRequest,
  ) =>
    apiRequest<Member>(v1(`/workspaces/${workspaceId}/members/${memberId}`), {
      method: 'PATCH',
      body,
    }),

  removeMember: (workspaceId: string, memberId: string) =>
    apiRequest<void>(v1(`/workspaces/${workspaceId}/members/${memberId}`), {
      method: 'DELETE',
    }),

  /** Gửi lại thư mời khi lần trước `outcome = email_failed`. */
  resendInvitation: (workspaceId: string, memberId: string) =>
    apiRequest<InviteMemberResponse>(
      v1(`/workspaces/${workspaceId}/members/${memberId}/resend-invitation`),
      { method: 'POST' },
    ),
};

// ---------------------------------------------------------------------------
// Tài liệu
// ---------------------------------------------------------------------------

export const documentApi = {
  /** Hạn mức upload — đọc TRƯỚC khi người dùng chọn tệp. */
  limits: (workspaceId: string) =>
    apiRequest<ApiUploadLimits>(v1(`/workspaces/${workspaceId}/documents/limits`)),

  list: (workspaceId: string) =>
    apiRequest<readonly ApiDocument[]>(v1(`/workspaces/${workspaceId}/documents`)),

  get: (workspaceId: string, documentId: string) =>
    apiRequest<ApiDocument>(v1(`/workspaces/${workspaceId}/documents/${documentId}`)),

  /**
   * Upload nhiều tệp trong MỘT request. Trả 202 kèm job để UI theo dõi tiến độ.
   * Dùng khoá chống trùng để bấm hai lần không tạo hai job.
   */
  upload: (workspaceId: string, files: File[], idempotencyKey: string) => {
    const form = new FormData();
    for (const file of files) form.append('files', file);
    return apiUpload<ApiAcceptedResponse>(
      v1(`/workspaces/${workspaceId}/documents`),
      form,
      { idempotencyKey },
    );
  },

  /** Mock-only: DELETE chưa được công bố trong OpenAPI và bị ẩn ở real mode. */
  remove: (workspaceId: string, documentId: string) =>
    apiRequest<void>(v1(`/workspaces/${workspaceId}/documents/${documentId}`), {
      method: 'DELETE',
    }),

  /** Đọc lại một tài liệu bị lỗi (vd PDF scan sau khi bật OCR). */
  reprocess: (workspaceId: string, documentId: string) =>
    apiRequest<ApiAcceptedResponse>(
      v1(`/workspaces/${workspaceId}/documents/${documentId}/reprocess`),
      { method: 'POST' },
    ),
};

// ---------------------------------------------------------------------------
// Brand profile
// ---------------------------------------------------------------------------

export const brandApi = {
  /** `GET /workspaces/{company_id}/brand-profile` — HTTP DTO from OpenAPI. */
  get: (workspaceId: string) =>
    apiRequest<ApiBrandProfile>(v1(`/workspaces/${workspaceId}/brand-profile`)),

  /** Lưu kèm `version` — lệch version sẽ nhận 409 `version_conflict`. */
  update: (workspaceId: string, body: ApiUpdateBrandProfileRequest) =>
    apiRequest<ApiBrandProfile>(v1(`/workspaces/${workspaceId}/brand-profile`), {
      method: 'PATCH',
      body,
    }),

  /** Xác nhận revision hiện tại, không tạo revision mới. */
  confirm: (workspaceId: string, body: ApiConfirmBrandProfileRequest) =>
    apiRequest<ApiBrandProfile>(v1(`/workspaces/${workspaceId}/brand-profile/confirm`), {
      method: 'POST',
      body,
    }),

  /** Nhờ AI trích xuất lại một trường từ tài liệu đã tải lên. */
  reextract: (workspaceId: string, body: ReextractFieldRequest) =>
    apiRequest<AcceptedResponse>(
      v1(`/workspaces/${workspaceId}/brand-profile/reextract`),
      { method: 'POST', body },
    ),
};

// ---------------------------------------------------------------------------
// Job nền
// ---------------------------------------------------------------------------

export const jobApi = {
  /** UI theo dõi mọi request dài bằng endpoint này. */
  get: (jobId: string, signal?: AbortSignal) =>
    apiRequest<ApiJob>(v1(`/jobs/${jobId}`), { signal }),

  events: (jobId: string, afterSeq?: number) =>
    apiRequest<readonly ApiJobEvent[]>(v1(`/jobs/${jobId}/events`), {
      query: { after_seq: afterSeq },
    }),

  cancel: (jobId: string) =>
    apiRequest<ApiJob>(v1(`/jobs/${jobId}/cancel`), { method: 'POST' }),

  /**
   * Thử lại job. KHÔNG dùng cho job xuất bản có kết quả `outcome_unknown` —
   * trường hợp đó phải đi qua luồng đối soát thủ công.
   */
  retry: (jobId: string) =>
    apiRequest<ApiAcceptedResponse>(v1(`/jobs/${jobId}/retry`), { method: 'POST' }),
};

// ---------------------------------------------------------------------------
// Campaign & nội dung
// ---------------------------------------------------------------------------

export const campaignApi = {
  list: (
    workspaceId: string,
    params: { page?: number; page_size?: number; status?: string } = {},
  ) =>
    apiRequest<Paginated<Campaign>>(v1(`/workspaces/${workspaceId}/campaigns`), {
      query: params,
    }),

  get: (workspaceId: string, campaignId: string) =>
    apiRequest<Campaign>(v1(`/workspaces/${workspaceId}/campaigns/${campaignId}`)),

  create: (workspaceId: string, body: Partial<Campaign>) =>
    apiRequest<Campaign>(v1(`/workspaces/${workspaceId}/campaigns`), {
      method: 'POST',
      body,
    }),

  update: (workspaceId: string, campaignId: string, body: Partial<Campaign>) =>
    apiRequest<Campaign>(v1(`/workspaces/${workspaceId}/campaigns/${campaignId}`), {
      method: 'PATCH',
      body,
    }),

  /** Áp dụng một `BriefRevisionDraft` do recommendation tạo ra. */
  acceptBriefRevision: (
    workspaceId: string,
    campaignId: string,
    draftId: string,
  ) =>
    apiRequest<Campaign>(
      v1(`/workspaces/${workspaceId}/campaigns/${campaignId}/brief-revisions/${draftId}/accept`),
      { method: 'POST' },
    ),
};

export const postApi = {
  create: (workspaceId: string, campaignId: string, body: CreateManualPostRequest) =>
    apiRequest<Post>(v1(`/workspaces/${workspaceId}/campaigns/${campaignId}/posts`), {
      method: 'POST',
      body,
    }),

  list: (workspaceId: string, campaignId?: string) =>
    apiRequest<Paginated<Post>>(v1(`/workspaces/${workspaceId}/posts`), {
      query: { campaign_id: campaignId, page_size: 100 },
    }),

  get: (workspaceId: string, postId: string) =>
    apiRequest<Post>(v1(`/workspaces/${workspaceId}/posts/${postId}`)),

  /** Lịch sử phiên bản để so sánh. */
  versions: (workspaceId: string, postId: string) =>
    apiRequest<PostVersionList>(
      v1(`/workspaces/${workspaceId}/posts/${postId}/versions`),
    ),

  /** Sửa tay. Gửi kèm `version` đang giữ; lệch → 409. */
  update: (workspaceId: string, postId: string, body: UpdatePostRequest) =>
    apiRequest<Post>(v1(`/workspaces/${workspaceId}/posts/${postId}`), {
      method: 'PATCH',
      body,
    }),

  /** Yêu cầu AI sửa — sinh version MỚI, không ghi đè version hiện tại. */
  reviseWithAi: (workspaceId: string, postId: string, body: ReviseWithAiRequest) =>
    apiRequest<AcceptedResponse>(
      v1(`/workspaces/${workspaceId}/posts/${postId}/revise`),
      { method: 'POST', body },
    ),

  /** Sinh tối đa 10 bài mỗi lần — trả job để theo dõi. */
  generate: (workspaceId: string, body: GenerateContentRequest) =>
    apiRequest<GenerateContentResponse>(
      v1(`/workspaces/${workspaceId}/posts/generate`),
      { method: 'POST', body },
    ),

  remove: (workspaceId: string, postId: string) =>
    apiRequest<void>(v1(`/workspaces/${workspaceId}/posts/${postId}`), {
      method: 'DELETE',
    }),
};

export const approvalApi = {
  /** Gửi duyệt đúng version hiện tại. */
  submit: (workspaceId: string, postId: string, version: number) =>
    apiRequest<Post>(v1(`/workspaces/${workspaceId}/posts/${postId}/submit-approval`), {
      method: 'POST',
      body: { version },
    }),

  /** Duyệt/từ chối ĐÚNG version người duyệt đã đọc. */
  decide: (workspaceId: string, postId: string, body: ApprovalRequest) =>
    apiRequest<Post>(v1(`/workspaces/${workspaceId}/posts/${postId}/approval`), {
      method: 'POST',
      body,
    }),

  history: (workspaceId: string, postId: string) =>
    apiRequest<ApprovalRecord[]>(
      v1(`/workspaces/${workspaceId}/posts/${postId}/approvals`),
    ),

  /** Hàng chờ duyệt của workspace. */
  queue: (workspaceId: string) =>
    apiRequest<Paginated<Post>>(v1(`/workspaces/${workspaceId}/approvals`), {
      query: { page_size: 50 },
    }),
};

export const exportApi = {
  create: (workspaceId: string, body: CreateExportRequest) =>
    apiRequest<AcceptedResponse>(v1(`/workspaces/${workspaceId}/exports`), {
      method: 'POST',
      body,
      headers: { 'Idempotency-Key': newIdempotencyKey('export') },
    }),

  get: (workspaceId: string, exportId: string) =>
    apiRequest<ExportJob>(v1(`/workspaces/${workspaceId}/exports/${exportId}`)),

  /**
   * Tải tệp export.
   *
   * ⚠️ Export là TỆP — không phải hành vi đăng bài. UI tuyệt đối không hiển thị
   * export thành "đã đăng".
   */
  download: (workspaceId: string, exportId: string) =>
    apiDownload(`/workspaces/${workspaceId}/exports/${exportId}/download`),
};

// ---------------------------------------------------------------------------
// Publishing
// ---------------------------------------------------------------------------

export const publishingApi = {
  connections: (workspaceId: string) =>
    apiRequest<SocialConnection[]>(v1(`/workspaces/${workspaceId}/connections`)),

  /** Bắt đầu OAuth. Trả URL để trình duyệt chuyển sang — token do BACKEND giữ. */
  startFacebookConnect: (workspaceId: string, returnTo: string) =>
    apiRequest<{ authorize_url: string }>(
      v1(`/workspaces/${workspaceId}/connections/facebook/start`),
      { method: 'POST', body: { return_to: returnTo } },
    ),

  pages: (workspaceId: string, connectionId: string) =>
    apiRequest<FacebookPage[]>(
      v1(`/workspaces/${workspaceId}/connections/${connectionId}/pages`),
    ),

  selectPage: (
    workspaceId: string,
    connectionId: string,
    body: SelectPageRequest,
  ) =>
    apiRequest<SocialConnection>(
      v1(`/workspaces/${workspaceId}/connections/${connectionId}/page`),
      { method: 'PUT', body },
    ),

  disconnect: (workspaceId: string, connectionId: string) =>
    apiRequest<void>(v1(`/workspaces/${workspaceId}/connections/${connectionId}`), {
      method: 'DELETE',
    }),

  publications: (workspaceId: string, postId?: string) =>
    apiRequest<Paginated<Publication>>(v1(`/workspaces/${workspaceId}/publications`), {
      query: { post_id: postId, page_size: 100 },
    }),

  getPublication: (workspaceId: string, publicationId: string) =>
    apiRequest<Publication>(v1(`/workspaces/${workspaceId}/publications/${publicationId}`)),

  /** Dòng thời gian để người dùng đối soát khi `outcome_unknown`. */
  publicationEvents: (workspaceId: string, publicationId: string) =>
    apiRequest<PublicationEvent[]>(
      v1(`/workspaces/${workspaceId}/publications/${publicationId}/events`),
    ),

  publish: (workspaceId: string, body: PublishRequest) =>
    apiRequest<AcceptedResponse>(v1(`/workspaces/${workspaceId}/publications`), {
      method: 'POST',
      body,
    }),

  /**
   * Ghi nhận đăng thủ công. Dùng khi API chưa khả dụng hoặc khi lần gửi trước
   * `outcome_unknown` và người dùng đã tự kiểm tra trên Facebook.
   */
  recordManual: (workspaceId: string, body: ManualPublicationRequest) =>
    apiRequest<Publication>(v1(`/workspaces/${workspaceId}/publications/manual`), {
      method: 'POST',
      body,
    }),

  /**
   * Thử lại lần gửi thất bại.
   * KHÔNG gọi hàm này cho `outcome_unknown` — backend sẽ trả 409 `state_conflict`.
   */
  retry: (workspaceId: string, publicationId: string) =>
    apiRequest<AcceptedResponse>(
      v1(`/workspaces/${workspaceId}/publications/${publicationId}/retry`),
      { method: 'POST' },
    ),

  /** Đồng bộ số liệu từ Page đã kết nối. */
  syncMetrics: (workspaceId: string) =>
    apiRequest<AcceptedResponse>(v1(`/workspaces/${workspaceId}/metrics/sync`), {
      method: 'POST',
    }),
};

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export const analyticsApi = {
  /** Bảng hiệu suất + metadata nguồn/cửa sổ đo/độ mới. */
  query: (workspaceId: string, query: AnalyticsQuery, signal?: AbortSignal) =>
    apiRequest<AnalyticsResponse>(v1(`/workspaces/${workspaceId}/analytics`), {
      query: query as unknown as Record<string, string | number | boolean>,
      signal,
    }),

  /** Xem trước tệp số liệu TRƯỚC khi ghi vào hệ thống. */
  previewImport: (workspaceId: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return apiUpload<MetricImportPreview>(
      v1(`/workspaces/${workspaceId}/metrics/import/preview`),
      form,
      { idempotencyKey: newIdempotencyKey('metric-preview') },
    );
  },

  commitImport: (workspaceId: string, body: MetricImportCommitRequest) =>
    apiRequest<AcceptedResponse>(v1(`/workspaces/${workspaceId}/metrics/import`), {
      method: 'POST',
      body,
    }),
};

// ---------------------------------------------------------------------------
// Recommendation
// ---------------------------------------------------------------------------

export const recommendationApi = {
  list: (workspaceId: string, campaignId?: string) =>
    apiRequest<Paginated<Recommendation>>(
      v1(`/workspaces/${workspaceId}/recommendations`),
      { query: { campaign_id: campaignId, page_size: 50 } },
    ),

  get: (workspaceId: string, recommendationId: string) =>
    apiRequest<Recommendation>(
      v1(`/workspaces/${workspaceId}/recommendations/${recommendationId}`),
    ),

  feedback: (
    workspaceId: string,
    recommendationId: string,
    body: RecommendationFeedbackRequest,
  ) =>
    apiRequest<Recommendation>(
      v1(`/workspaces/${workspaceId}/recommendations/${recommendationId}/feedback`),
      { method: 'POST', body },
    ),

  /**
   * Áp dụng khuyến nghị. KHÔNG tự đổi campaign đang chạy — tạo bản nháp
   * (`BriefRevisionDraft`) để người dùng xem lại.
   */
  apply: (
    workspaceId: string,
    recommendationId: string,
    body: ApplyRecommendationRequest,
  ) =>
    apiRequest<ApplyRecommendationResponse>(
      v1(`/workspaces/${workspaceId}/recommendations/${recommendationId}/apply`),
      { method: 'POST', body },
    ),
};

export const api = {
  auth: authApi,
  workspace: workspaceApi,
  document: documentApi,
  brand: brandApi,
  job: jobApi,
  campaign: campaignApi,
  post: postApi,
  approval: approvalApi,
  export: exportApi,
  publishing: publishingApi,
  analytics: analyticsApi,
  recommendation: recommendationApi,
};
