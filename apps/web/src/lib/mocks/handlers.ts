/**
 * Mock handlers theo đúng contract trong `@agentic/contracts`.
 *
 * Chặn ở tầng `fetch` nên toàn bộ đường đi thật vẫn được chạy: client → HTTP →
 * parse envelope lỗi. Khi cắm backend thật, không phải sửa gì ở tầng UI.
 *
 * Mọi handler ở đây phải trả ĐÚNG shape trong contract — kể cả envelope lỗi —
 * để lỗi giả cũng đi qua đúng đường xử lý như lỗi thật.
 */

import { HttpResponse, http } from 'msw';

import {
  APPROVAL_DECISIONS,
  BRAND_FIELD_KEYS,
  DOCUMENT_ERROR_CODES,
  DOCUMENT_KINDS,
  DOCUMENT_STATUSES,
  ERROR_CODES,
  JOB_KINDS,
  JOB_STATUSES,
  JOB_STEP_STATUSES,
  POST_STATUSES,
  VERSION_SOURCES,
  type AcceptedResponse,
  type ApiErrorBody,
  type ApprovalRequest,
  type DocumentUpload,
  type Job,
  type PostVersion,
  type PostVersionList,
  type SessionResponse,
} from '@agentic/contracts';

import type { ApiDocument } from '@/lib/api/types';
import type { ApiMetricImportRequest } from '@/lib/api/types';

import {
  DEMO_ACCOUNTS,
  DEMO_NOW,
  WS_FB,
  applyDemoRole,
  demoBrandProfiles,
  demoCampaigns,
  demoDocuments,
  demoJobs,
  demoMembers,
  demoOnboarding,
  demoPosts,
  demoPostVersions,
  demoUploadLimits,
  demoUsers,
  demoWorkspaces,
  getUserById,
} from './seed';

/**
 * Trạng thái phiên của bản demo.
 *
 * Lưu vào `sessionStorage` chứ không chỉ giữ trong biến: nếu chỉ giữ trong bộ nhớ
 * thì mỗi lần tải lại trang (F5, hoặc điều hướng bằng `page.goto` trong E2E) phiên
 * sẽ mất và người dùng bị đá về màn hình "chưa đăng nhập" — trong khi backend thật
 * dùng cookie nên phiên vẫn còn. Mock phải mô phỏng đúng hành vi đó.
 */
const SESSION_USER_KEY = 'agentic_demo_session_user';
const SESSION_WORKSPACE_KEY = 'agentic_demo_active_workspace';

function readStoredUserId(): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    return sessionStorage.getItem(SESSION_USER_KEY);
  } catch {
    return null;
  }
}

function readStoredWorkspaceId(): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    return sessionStorage.getItem(SESSION_WORKSPACE_KEY);
  } catch {
    return null;
  }
}

/**
 * Adapt the demo fixture to the generated HTTP DTO. These derived values are
 * only a labelled mock scenario; real mode reads these fields from the API.
 */
function demoDocumentHttpOut(document: DocumentUpload): ApiDocument {
  const isReady = document.status === DOCUMENT_STATUSES.READY;
  const isFailed =
    document.status === DOCUMENT_STATUSES.FAILED ||
    document.status === DOCUMENT_STATUSES.UNSUPPORTED;
  const isImage = document.kind === DOCUMENT_KINDS.IMAGE;

  return {
    ...document,
    extraction_status: isReady ? (isImage ? 'metadata_only' : 'extracted') : isFailed ? 'failed' : 'pending',
    knowledge_status: isReady ? (isImage ? 'not_available' : 'ready') : isFailed ? 'failed' : 'pending',
    retrieval_mode: isReady && !isImage ? 'lexical' : 'not_available',
    profile_status: isReady ? (isImage ? 'not_available' : 'ready') : isFailed ? 'failed' : 'pending',
  };
}

function writeStoredUserId(userId: string | null): void {
  if (typeof sessionStorage === 'undefined') return;
  try {
    if (userId === null) sessionStorage.removeItem(SESSION_USER_KEY);
    else sessionStorage.setItem(SESSION_USER_KEY, userId);
  } catch {
    // Chế độ riêng tư có thể chặn sessionStorage — phiên chỉ còn trong bộ nhớ.
  }
}

let signedInUserId: string | null = readStoredUserId();
let activeWorkspaceId: string = readStoredWorkspaceId() ?? WS_FB;

/** Bộ đếm để id sinh ra không trùng giữa các lần gọi. */
let sequence = 0;
const nextId = (prefix: string): string => {
  sequence += 1;
  return `${prefix}_${sequence}`;
};

type DemoMetricRow = ApiMetricImportRequest['points'][number] & {
  pillar: string;
  format: string;
  measured_at: string;
};
const demoMetricsByWorkspace: Record<string, Record<string, DemoMetricRow[]>> = {};

const nowIso = (): string => new Date().toISOString();

function fail(
  status: number,
  code: string,
  message: string,
  details?: ApiErrorBody['details'],
  retryable = false,
): HttpResponse<ApiErrorBody> {
  const body: ApiErrorBody = {
    code,
    message,
    request_id: nextId('req'),
    retryable,
    ...(details ? { details } : {}),
  };
  return HttpResponse.json(body, { status });
}

const notFound = (what: string) =>
  fail(404, ERROR_CODES.NOT_FOUND, `Không tìm thấy ${what}.`);

const unauthenticated = () =>
  fail(
    401,
    ERROR_CODES.UNAUTHENTICATED,
    'Bạn chưa đăng nhập hoặc phiên làm việc đã hết hạn.',
  );

/** Phiên hiện tại, hoặc `null` khi chưa đăng nhập. */
function currentSession(): SessionResponse | null {
  const user = signedInUserId ? getUserById(signedInUserId) : undefined;
  if (!user) return null;
  return {
    user,
    workspaces: demoWorkspaces,
    active_workspace_id: activeWorkspaceId,
    expires_at: new Date(new Date(DEMO_NOW).getTime() + 8 * 3_600_000).toISOString(),
  };
}

// ---------------------------------------------------------------------------

export const handlers = [
  // ----- Phiên & xác thực -----
  http.get('*/api/v1/me', () => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json(session);
  }),

  http.post('*/api/v1/auth/refresh', () => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json({ ...session, access_token: 'demo-access-token' });
  }),

  http.post('*/api/v1/auth/login', async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    const email = (body.email ?? '').trim().toLowerCase();
    const password = body.password ?? '';

    const account = Object.values(DEMO_ACCOUNTS).find((item) => item.email === email);
    const user = demoUsers.find((item) => item.email === email);

    if (!account || !user || password !== account.password) {
      return fail(
        401,
        ERROR_CODES.UNAUTHENTICATED,
        'Email hoặc mật khẩu không đúng. Vui lòng kiểm tra lại.',
      );
    }

    signedInUserId = user.id;
    writeStoredUserId(user.id);
    // Vai trò suy ra từ tài khoản demo để màn hình đổi theo đúng vai.
    if (user.id === 'usr_owner') applyDemoRole('owner');
    else if (user.id === 'usr_editor') applyDemoRole('editor');
    else applyDemoRole('viewer');

    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json({ ...session, access_token: 'demo-access-token' });
  }),

  http.post('*/api/v1/auth/logout', () => {
    signedInUserId = null;
    writeStoredUserId(null);
    return new HttpResponse(null, { status: 204 });
  }),

  http.post('*/api/v1/auth/forgot-password', async ({ request }) => {
    await request.json();
    // Cố ý trả cùng một câu trả lời dù email có tồn tại hay không —
    // không được để lộ tài khoản nào đang có trong hệ thống.
    return HttpResponse.json({
      sent: true,
      message:
        'Nếu email này có tài khoản, hệ thống đã gửi hướng dẫn đặt lại mật khẩu. Hãy kiểm tra hộp thư (kể cả thư rác).',
    });
  }),

  // ----- Workspace -----
  http.get('*/api/v1/workspaces', () => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json(demoWorkspaces);
  }),

  http.get('*/api/v1/workspaces/:workspaceId', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const workspace = demoWorkspaces.find((item) => item.id === params.workspaceId);
    return workspace ? HttpResponse.json(workspace) : notFound('doanh nghiệp');
  }),

  http.put('*/api/v1/me/active-workspace', async ({ request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const body = (await request.json()) as { workspace_id?: string };
    const workspace = demoWorkspaces.find((item) => item.id === body.workspace_id);
    if (!workspace) return notFound('doanh nghiệp');
    activeWorkspaceId = workspace.id;
    try {
      sessionStorage.setItem(SESSION_WORKSPACE_KEY, activeWorkspaceId);
    } catch {
      // Session storage can be unavailable in private browsing.
    }
    return HttpResponse.json({ ...session, active_workspace_id: workspace.id });
  }),

  http.get('*/api/v1/workspaces/:workspaceId/onboarding', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const state = demoOnboarding[params.workspaceId as string];
    return state ? HttpResponse.json(state) : notFound('tiến độ nhập doanh nghiệp');
  }),

  http.get('*/api/v1/workspaces/:workspaceId/members', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json(demoMembers[params.workspaceId as string] ?? []);
  }),

  // ----- Tài liệu -----
  http.get('*/api/v1/workspaces/:workspaceId/documents/limits', () => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json(demoUploadLimits);
  }),

  http.get('*/api/v1/workspaces/:workspaceId/documents', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json(
      (demoDocuments[params.workspaceId as string] ?? []).map(demoDocumentHttpOut),
    );
  }),

  http.post('*/api/v1/workspaces/:workspaceId/documents', async ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();

    const workspaceId = params.workspaceId as string;
    const form = await request.formData();
    const files = form.getAll('files').filter((entry): entry is File => entry instanceof File);

    if (files.length === 0) {
      return fail(
        400,
        ERROR_CODES.VALIDATION_ERROR,
        'Chưa chọn tệp nào để tải lên.',
        { fields: [{ field: 'files', message: 'Cần ít nhất một tệp.' }] },
      );
    }

    const list = demoDocuments[workspaceId] ?? [];
    const created: DocumentUpload[] = [];

    for (const file of files) {
      const kind = inferKind(file.name, file.type);
      if (!kind) {
        return fail(
          415,
          ERROR_CODES.UNPROCESSABLE,
          `Định dạng tệp “${file.name}” chưa được hỗ trợ.`,
          { fields: [{ field: 'files', message: 'Chỉ nhận PDF, DOCX, XLSX, CSV, TXT và ảnh.' }] },
        );
      }
      if (file.size > demoUploadLimits.max_file_size_bytes) {
        return fail(
          413,
          ERROR_CODES.VALIDATION_ERROR,
          `Tệp “${file.name}” vượt quá dung lượng cho phép.`,
          { fields: [{ field: 'files', message: 'Tối đa 25 MB mỗi tệp.' }] },
        );
      }

      created.push({
        id: nextId('doc'),
        workspace_id: workspaceId,
        filename: file.name,
        kind,
        mime_type: file.type || 'application/octet-stream',
        size: file.size,
        status: DOCUMENT_STATUSES.PROCESSING,
        progress: 10,
        job_id: 'job_brand_extract',
        uploaded_by: session.user.id,
        uploaded_at: nowIso(),
      });
    }

    demoDocuments[workspaceId] = [...created, ...list];

    const job = demoJobs['job_brand_extract'];
    if (!job) {
      return fail(
        500,
        ERROR_CODES.INTERNAL_ERROR,
        'Không tạo được tác vụ xử lý tài liệu.',
        undefined,
        true,
      );
    }
    const accepted: AcceptedResponse = { job_id: job.id, job };
    return HttpResponse.json(accepted, { status: 202 });
  }),

  http.post(
    '*/api/v1/workspaces/:workspaceId/documents/:documentId/reprocess',
    ({ params }) => {
      const session = currentSession();
      if (!session) return unauthenticated();

      const list = demoDocuments[params.workspaceId as string] ?? [];
      const target = list.find((item) => item.id === params.documentId);
      if (!target) return notFound('tài liệu');

      target.status = DOCUMENT_STATUSES.PROCESSING;
      target.progress = 5;
      target.error = undefined;
      target.job_id = 'job_brand_extract';

      const job = demoJobs['job_brand_extract'];
      if (!job) {
        return fail(
          500,
          ERROR_CODES.INTERNAL_ERROR,
          'Không tạo được tác vụ đọc lại tài liệu.',
          undefined,
          true,
        );
      }

      const accepted: AcceptedResponse = { job_id: job.id, job };
      return HttpResponse.json(accepted, { status: 202 });
    },
  ),

  http.delete('*/api/v1/workspaces/:workspaceId/documents/:documentId', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();

    const workspaceId = params.workspaceId as string;
    const list = demoDocuments[workspaceId] ?? [];
    const index = list.findIndex((item) => item.id === params.documentId);
    if (index === -1) return notFound('tài liệu');

    list.splice(index, 1);
    return new HttpResponse(null, { status: 204 });
  }),

  // ----- Hồ sơ thương hiệu -----
  http.get('*/api/v1/workspaces/:workspaceId/brand-profile', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const profile = demoBrandProfiles[params.workspaceId as string];
    return profile ? HttpResponse.json(profile) : notFound('hồ sơ thương hiệu');
  }),

  http.patch('*/api/v1/workspaces/:workspaceId/brand-profile', async ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();

    const profile = demoBrandProfiles[params.workspaceId as string];
    if (!profile) return notFound('hồ sơ thương hiệu');

    const body = (await request.json()) as {
      version?: number;
      fields?: Array<{ key: string; value: unknown }>;
      confirm?: boolean;
    };

    /*
     * Mô phỏng xung đột phiên bản: gửi lên version cũ hơn (hoặc bằng 0) sẽ nhận
     * 409 để màn hình demo được luồng "tải bản mới" thay vì ghi đè im lặng.
     */
    if (typeof body.version !== 'number' || body.version < profile.version) {
      return fail(
        409,
        ERROR_CODES.VERSION_CONFLICT,
        'Hồ sơ thương hiệu vừa được người khác cập nhật. Bạn đang sửa một bản cũ.',
        {
          current_version: profile.version,
          your_version: body.version ?? 0,
        },
      );
    }

    for (const change of body.fields ?? []) {
      const existing = (profile as unknown as Record<string, { value?: unknown; state?: string }>)[
        change.key
      ];
      if (existing) {
        existing.value = change.value;
        existing.state = 'edited';
      }
    }

    profile.version += 1;
    profile.updated_at = nowIso();
    if (body.confirm === true) {
      for (const key of Object.values(BRAND_FIELD_KEYS)) {
        const field = profile[key];
        if (field.value !== null && field.value !== undefined && field.value !== '') {
          field.state = 'confirmed';
        }
      }
      profile.confirmed_at = nowIso();
      profile.confirmed_by = session.user.id;
      profile.completeness = 1;
    } else {
      profile.confirmed_at = undefined;
      profile.confirmed_by = undefined;
    }

    return HttpResponse.json(profile);
  }),

  http.post('*/api/v1/workspaces/:workspaceId/brand-profile/confirm', async ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();

    const profile = demoBrandProfiles[params.workspaceId as string];
    if (!profile) return notFound('hồ sơ thương hiệu');

    const body = (await request.json()) as { version?: number };
    if (body.version !== profile.version) {
      return fail(
        409,
        ERROR_CODES.VERSION_CONFLICT,
        'Hồ sơ thương hiệu vừa được người khác cập nhật. Bạn đang xác nhận một bản cũ.',
        { current_version: profile.version, your_version: body.version ?? 0 },
      );
    }

    let confirmedFields = 0;
    for (const key of Object.values(BRAND_FIELD_KEYS)) {
      const field = profile[key];
      if (field.value !== null && field.value !== undefined && field.value !== '') {
        field.state = 'confirmed';
        confirmedFields += 1;
      }
    }
    profile.confirmed_at = nowIso();
    profile.confirmed_by = session.user.id;
    profile.completeness = confirmedFields / Object.values(BRAND_FIELD_KEYS).length;
    profile.updated_at = nowIso();

    return HttpResponse.json(profile);
  }),

  // ----- Job -----
  http.get('*/api/v1/jobs/:jobId', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const job = demoJobs[params.jobId as string];
    if (!job) return notFound('tác vụ');
    return HttpResponse.json(job);
  }),

  http.post('*/api/v1/jobs/:jobId/cancel', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();

    const job = demoJobs[params.jobId as string];
    if (!job) return notFound('tác vụ');

    if (!job.cancellable) {
      return fail(
        409,
        ERROR_CODES.STATE_CONFLICT,
        'Tác vụ đã kết thúc nên không thể huỷ.',
      );
    }

    job.status = JOB_STATUSES.CANCELLED;
    job.cancellable = false;
    job.finished_at = nowIso();
    return HttpResponse.json(job);
  }),

  http.post('*/api/v1/jobs/:jobId/retry', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();

    const job = demoJobs[params.jobId as string];
    if (!job) return notFound('tác vụ');

    if (job.status !== JOB_STATUSES.FAILED && job.status !== JOB_STATUSES.CANCELLED) {
      return fail(
        409,
        ERROR_CODES.STATE_CONFLICT,
        'Chỉ có thể thử lại tác vụ đã thất bại hoặc đã huỷ.',
      );
    }

    const retried: Job = {
      ...job,
      status: JOB_STATUSES.QUEUED,
      error: undefined,
      finished_at: undefined,
      created_at: nowIso(),
      cancellable: true,
      steps: job.steps.map((step) => ({
        key: step.key,
        label: step.label,
        status: JOB_STEP_STATUSES.PENDING,
      })),
    };
    demoJobs[job.id] = retried;

    const accepted: AcceptedResponse = { job_id: retried.id, job: retried };
    return HttpResponse.json(accepted, { status: 202 });
  }),

  // ----- Chiến dịch & nội dung (dữ liệu cho các lát cắt sau) -----
  http.get('*/api/v1/workspaces/:workspaceId/campaigns/:campaignId', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const campaign = (demoCampaigns[params.workspaceId as string] ?? []).find(
      (item) => item.id === params.campaignId,
    );
    return campaign ? HttpResponse.json(campaign) : notFound('chiến dịch');
  }),

  http.get('*/api/v1/workspaces/:workspaceId/campaigns', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const items = demoCampaigns[params.workspaceId as string] ?? [];
    return HttpResponse.json({ items, total: items.length, page: 1, page_size: 20 });
  }),

  http.get('*/api/v1/workspaces/:workspaceId/posts', ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const campaignId = new URL(request.url).searchParams.get('campaign_id');
    let items = demoPosts[params.workspaceId as string] ?? [];
    if (campaignId) items = items.filter((post) => post.campaign_id === campaignId);
    return HttpResponse.json({ items, total: items.length, page: 1, page_size: 100 });
  }),

  http.get('*/api/v1/workspaces/:workspaceId/posts/:postId', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const post = (demoPosts[params.workspaceId as string] ?? []).find(
      (item) => item.id === params.postId,
    );
    return post ? HttpResponse.json(post) : notFound('bài viết');
  }),

  http.get('*/api/v1/workspaces/:workspaceId/posts/:postId/versions', ({ params }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const post = (demoPosts[params.workspaceId as string] ?? []).find(
      (item) => item.id === params.postId,
    );
    if (!post) return notFound('bài viết');
    const existing = demoPostVersions[post.id];
    if (existing) return HttpResponse.json(existing);
    const versions: PostVersionList = {
      post_id: post.id,
      current_version: post.version,
      versions: [post.current],
    };
    demoPostVersions[post.id] = versions;
    return HttpResponse.json(versions);
  }),

  http.patch('*/api/v1/workspaces/:workspaceId/posts/:postId', async ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const post = (demoPosts[params.workspaceId as string] ?? []).find(
      (item) => item.id === params.postId,
    );
    if (!post) return notFound('bài viết');
    const body = (await request.json()) as {
      version?: number;
      caption?: string;
      hashtags?: string[];
      note?: string;
    };
    if (body.version !== post.version) {
      return fail(
        409,
        ERROR_CODES.VERSION_CONFLICT,
        'Bài viết vừa được người khác cập nhật. Bạn đang sửa một bản cũ.',
        { current_version: post.version, your_version: body.version ?? 0 },
      );
    }
    const nextVersion = post.version + 1;
    const next: PostVersion = {
      ...post.current,
      version: nextVersion,
      caption: body.caption ?? post.current.caption,
      hashtags: body.hashtags ?? post.current.hashtags,
      source: VERSION_SOURCES.HUMAN,
      created_by: session.user.id,
      created_by_name: session.user.full_name,
      created_at: nowIso(),
      note: body.note,
      approved_at: undefined,
      approved_by: undefined,
    };
    const previousStatus = post.status;
    post.current = next;
    post.version = nextVersion;
    post.updated_at = nowIso();
    if (previousStatus === POST_STATUSES.APPROVED || post.requires_reapproval) {
      post.status = POST_STATUSES.DRAFT;
      post.requires_reapproval = true;
    }
    const history = demoPostVersions[post.id] ?? {
      post_id: post.id,
      current_version: nextVersion,
      versions: [],
    };
    history.current_version = nextVersion;
    history.versions = [next, ...history.versions];
    history.pending_approval_version = undefined;
    demoPostVersions[post.id] = history;
    return HttpResponse.json(post);
  }),

  http.post(
    '*/api/v1/workspaces/:workspaceId/posts/:postId/submit-approval',
    async ({ params, request }) => {
      const session = currentSession();
      if (!session) return unauthenticated();
      const post = (demoPosts[params.workspaceId as string] ?? []).find(
        (item) => item.id === params.postId,
      );
      if (!post) return notFound('bài viết');
      const body = (await request.json()) as { version?: number };
      if (body.version !== post.version) {
        return fail(
          409,
          ERROR_CODES.VERSION_CONFLICT,
          'Bài viết vừa được cập nhật. Hãy tải bản mới nhất trước khi gửi duyệt.',
          { current_version: post.version, your_version: body.version ?? 0 },
        );
      }
      post.status = POST_STATUSES.NEEDS_REVIEW;
      post.requires_reapproval = false;
      const history = demoPostVersions[post.id];
      if (history) history.pending_approval_version = post.version;
      return HttpResponse.json(post);
    },
  ),

  http.post(
    '*/api/v1/workspaces/:workspaceId/posts/:postId/approval',
    async ({ params, request }) => {
      const session = currentSession();
      if (!session) return unauthenticated();
      const post = (demoPosts[params.workspaceId as string] ?? []).find(
        (item) => item.id === params.postId,
      );
      if (!post) return notFound('bài viết');
      const body = (await request.json()) as ApprovalRequest;
      if (body.version !== post.version) {
        return fail(
          409,
          ERROR_CODES.VERSION_CONFLICT,
          'Bài viết đã đổi phiên bản. Hãy tải lại trước khi quyết định.',
          { current_version: post.version, your_version: body.version ?? 0 },
        );
      }
      if (body.decision === APPROVAL_DECISIONS.APPROVED) {
        post.status = POST_STATUSES.APPROVED;
        post.rejection_reason = undefined;
        post.current.approved_at = nowIso();
        post.current.approved_by = session.user.id;
      } else {
        post.status = POST_STATUSES.REJECTED;
        post.rejection_reason = body.reason ?? 'Chưa có lý do từ chối.';
        post.current.approved_at = undefined;
        post.current.approved_by = undefined;
      }
      const history = demoPostVersions[post.id];
      if (history) history.pending_approval_version = undefined;
      return HttpResponse.json(post);
    },
  ),

  http.post('*/api/v1/workspaces/:workspaceId/posts/generate', async ({ request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const body = (await request.json()) as { count?: number; campaign_id?: string };
    const count = body.count;
    if (!body.campaign_id || typeof count !== 'number' || !Number.isInteger(count) || count < 1 || count > 10) {
      return fail(400, ERROR_CODES.VALIDATION_ERROR, 'Số bài phải nằm trong khoảng từ 1 đến 10.');
    }
    const id = nextId('job_content_generate');
    const job: Job = {
      id,
      kind: JOB_KINDS.CONTENT_GENERATE,
      status: JOB_STATUSES.QUEUED,
      title: `Đang tạo ${count} bài viết nháp`,
      progress: 0,
      steps: [
        { key: 'prepare', label: 'Chuẩn bị brief và hồ sơ thương hiệu', status: JOB_STEP_STATUSES.PENDING },
        { key: 'generate', label: 'AI tạo nội dung', status: JOB_STEP_STATUSES.PENDING },
        { key: 'review', label: 'Kiểm tra nội dung', status: JOB_STEP_STATUSES.PENDING },
      ],
      created_at: nowIso(),
      cancellable: true,
    };
    demoJobs[id] = job;
    const accepted: AcceptedResponse = { job_id: id, job };
    return HttpResponse.json(accepted, { status: 202 });
  }),

  http.post('*/api/v1/workspaces/:workspaceId/exports', async ({ request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const body = (await request.json()) as { campaign_id?: string; format?: string };
    if (!body.campaign_id || (body.format !== 'csv' && body.format !== 'xlsx')) {
      return fail(400, ERROR_CODES.VALIDATION_ERROR, 'Hãy chọn chiến dịch và định dạng tệp cần xuất.');
    }
    const id = nextId('job_export');
    const job: Job = {
      id,
      kind: JOB_KINDS.EXPORT_BUILD,
      status: JOB_STATUSES.QUEUED,
      title: `Đang dựng tệp ${body.format.toUpperCase()}`,
      progress: 0,
      steps: [
        { key: 'collect', label: 'Tập hợp nội dung đã chọn', status: JOB_STEP_STATUSES.PENDING },
        { key: 'build', label: 'Dựng tệp xuất', status: JOB_STEP_STATUSES.PENDING },
      ],
      created_at: nowIso(),
      cancellable: true,
    };
    demoJobs[id] = job;
    const accepted: AcceptedResponse = { job_id: id, job };
    return HttpResponse.json(accepted, { status: 202 });
  }),

  // ----- Nhập số liệu & analytics manual-snapshot API -----
  http.post('*/api/v1/workspaces/:workspaceId/metrics/import', async ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const workspaceId = params.workspaceId as string;
    const body = (await request.json()) as ApiMetricImportRequest;
    if (!body.source_id || !body.measured_at || !Array.isArray(body.points) || body.points.length === 0) {
      return fail(422, ERROR_CODES.VALIDATION_ERROR, 'Snapshot số liệu chưa hợp lệ.');
    }
    const existingRows = (demoMetricsByWorkspace[workspaceId] ?? {})[body.source_id] ?? [];
    const duplicates = body.points.some((point) => existingRows.some(
      (row) => row.post_id === point.post_id && row.measured_at === body.measured_at,
    ));
    if (duplicates) return fail(409, ERROR_CODES.STATE_CONFLICT, 'Snapshot này đã được nhập.');
    const postMap = new Map((demoPosts[workspaceId] ?? []).map((post) => [post.id, post]));
    const imported = body.points.flatMap((point) => {
      const post = postMap.get(point.post_id);
      return post ? [{ ...point, pillar: post.pillar, format: post.format, measured_at: body.measured_at }] : [];
    });
    if (imported.length !== body.points.length) return notFound('bài viết');
    demoMetricsByWorkspace[workspaceId] ??= {};
    demoMetricsByWorkspace[workspaceId][body.source_id] = [...existingRows, ...imported];
    return HttpResponse.json({
      source_id: body.source_id,
      imported_count: imported.length,
      measured_at: body.measured_at,
      snapshot_fingerprint: `demo:${workspaceId}:${body.source_id}:${body.measured_at}`.slice(0, 160),
    }, { status: 201 });
  }),

  http.get('*/api/v1/workspaces/:workspaceId/analytics/dashboard', ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const workspaceId = params.workspaceId as string;
    const sourceId = new URL(request.url).searchParams.get('source_id') ?? '';
    const imported = demoMetricsByWorkspace[workspaceId]?.[sourceId] ?? [];
    const latest = new Map<string, DemoMetricRow>();
    for (const row of [...imported].sort((a, b) => b.measured_at.localeCompare(a.measured_at))) {
      if (!latest.has(row.post_id)) latest.set(row.post_id, row);
    }
    const postById = new Map((demoPosts[workspaceId] ?? []).map((post) => [post.id, post]));
    const rows: DemoMetricRow[] = imported.length > 0
      ? [...latest.values()]
      : (demoPosts[workspaceId] ?? []).map((post, index) => ({
          post_id: post.id,
          post_age_hours: 48 + index * 24,
          reach: [5200, 4100, 6100][index] ?? 3000,
          views: null,
          engagements: [310, 205, 250][index] ?? 120,
          clicks: null,
          spend: null,
          attributed_revenue: null,
          attribution_valid: false,
          pillar: post.pillar,
          format: post.format,
          measured_at: DEMO_NOW,
        }));
    const sampled = (key: 'reach' | 'views' | 'engagements' | 'clicks') => rows
      .map((row) => row[key]).filter((value): value is number => value != null);
    const values = (key: 'reach' | 'views' | 'engagements' | 'clicks') => sampled(key);
    const reachValues = values('reach');
    const sum = (items: number[]) => items.reduce((total, item) => total + item, 0);
    const ratio = (numeratorKey: 'engagements' | 'clicks') => {
      const pairs = rows.filter((row) => row[numeratorKey] != null && row.reach != null && row.reach > 0);
      const denominator = sum(pairs.map((row) => row.reach as number));
      return denominator > 0 ? sum(pairs.map((row) => row[numeratorKey] as number)) / denominator : null;
    };
    const period = rows.map((row) => row.measured_at).sort();
    const start = period[0] ?? DEMO_NOW;
    const end = period.at(-1) ?? DEMO_NOW;
    const metricSpecs = [
      { metric: 'reach', values: reachValues, value: reachValues.length ? sum(reachValues) / reachValues.length : null },
      { metric: 'views', values: values('views'), value: values('views').length ? sum(values('views')) / values('views').length : null },
      { metric: 'engagement_rate_by_reach', values: rows.filter((row) => row.engagements != null && row.reach != null), value: ratio('engagements') },
      { metric: 'click_rate_by_reach', values: rows.filter((row) => row.clicks != null && row.reach != null), value: ratio('clicks') },
      { metric: 'cpa', values: [], value: null },
      { metric: 'roas', values: [], value: null },
    ];
    const observations = metricSpecs.map((spec) => ({
      metric: spec.metric,
      value: spec.value,
      numerator: null,
      denominator: null,
      sample_size: rows.length,
      coverage: rows.length ? spec.values.length / rows.length : 0,
      measured_from: start,
      measured_to: end,
      unavailable_reason: spec.value == null ? 'insufficient_data' : null,
    }));
    const evidence = metricSpecs.map((spec) => ({
      evidence_id: `ev:demo:${spec.metric}`,
      description: `${spec.metric}: demo snapshot, n=${rows.length}`,
      post_ids: rows.map((row) => row.post_id),
      metric_names: [spec.metric],
    }));
    const dimensions = ['pillar', 'format'] as const;
    const groups = dimensions.flatMap((dimension) => {
      const names = [...new Set(rows.map((row) => row[dimension]))];
      return names.map((name) => {
        const group = rows.filter((row) => row[dimension] === name);
        const reach = group.map((row) => row.reach).filter((value): value is number => value != null);
        const engagementPairs = group.filter((row) => row.engagements != null && row.reach != null && row.reach > 0);
        const clickPairs = group.filter((row) => row.clicks != null && row.reach != null && row.reach > 0);
        return {
          dimension,
          name,
          post_count: group.length,
          average_reach: reach.length ? sum(reach) / reach.length : null,
          average_views: null,
          engagement_rate_by_reach: engagementPairs.length ? sum(engagementPairs.map((row) => row.engagements as number)) / sum(engagementPairs.map((row) => row.reach as number)) : null,
          click_rate_by_reach: clickPairs.length ? sum(clickPairs.map((row) => row.clicks as number)) / sum(clickPairs.map((row) => row.reach as number)) : null,
        };
      });
    });
    void postById;
    return HttpResponse.json({
      source_id: sourceId,
      source_label: imported.length ? 'Nhập thủ công (demo)' : 'Bản demo',
      freshness_at: end,
      groups,
      report: {
        report_id: `report:demo:${workspaceId}:${sourceId}`,
        page_id: sourceId,
        period_start: start,
        period_end: end,
        observations,
        evidence,
        notes: ['Dữ liệu minh họa — không phải kết quả thật.', 'Số liệu mô tả không chứng minh quan hệ nhân quả.'],
      },
    });
  }),

  http.get('*/api/v1/workspaces/:workspaceId/analytics/recommendation', ({ params, request }) => {
    const session = currentSession();
    if (!session) return unauthenticated();
    const workspaceId = params.workspaceId as string;
    const sourceId = new URL(request.url).searchParams.get('source_id') ?? '';
    const sampleSize = demoMetricsByWorkspace[workspaceId]?.[sourceId]?.length ?? (demoPosts[workspaceId] ?? []).length;
    return HttpResponse.json({
      status: 'abstain',
      observation: 'Bản demo chưa có đủ số bài trong mỗi trụ để đề xuất thử nghiệm.',
      metric: 'engagement_rate_by_reach',
      confidence: 0,
      sample_size: sampleSize,
      evidence_ids: [],
      limitations: ['Dữ liệu minh họa; cần ít nhất 5 bài cho mỗi trụ được so sánh.'],
      created_at: DEMO_NOW,
    });
  }),

  // ----- Xuất bản (chưa có gì để demo ở lát cắt này) -----
  http.get('*/api/v1/workspaces/:workspaceId/connections', () => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json([]);
  }),

  http.get('*/api/v1/workspaces/:workspaceId/publications', () => {
    const session = currentSession();
    if (!session) return unauthenticated();
    return HttpResponse.json({ items: [], total: 0, page: 1, page_size: 100 });
  }),
];

/** Suy ra loại tài liệu từ tên/đuôi tệp. */
function inferKind(filename: string, mimeType: string): DocumentUpload['kind'] | null {
  const extension = filename.toLowerCase().split('.').pop() ?? '';
  switch (extension) {
    case 'pdf':
      return DOCUMENT_KINDS.PDF;
    case 'docx':
      return DOCUMENT_KINDS.DOCX;
    case 'xlsx':
      return DOCUMENT_KINDS.XLSX;
    case 'csv':
      return DOCUMENT_KINDS.CSV;
    case 'txt':
      return DOCUMENT_KINDS.TXT;
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'webp':
      return DOCUMENT_KINDS.IMAGE;
    default:
      break;
  }
  if (mimeType.startsWith('image/')) return DOCUMENT_KINDS.IMAGE;
  return null;
}

/** Dùng cho test: đặt lại trạng thái phiên. */
export function resetMockSession(): void {
  signedInUserId = null;
  activeWorkspaceId = WS_FB;
}

export const JOB_KIND_LABELS: Record<string, string> = {
  [JOB_KINDS.DOCUMENT_INGEST]: 'Xử lý tài liệu',
  [JOB_KINDS.BRAND_EXTRACT]: 'Trích xuất hồ sơ thương hiệu',
};

export { DOCUMENT_ERROR_CODES };
