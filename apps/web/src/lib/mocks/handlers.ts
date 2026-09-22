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
  DOCUMENT_ERROR_CODES,
  DOCUMENT_KINDS,
  DOCUMENT_STATUSES,
  ERROR_CODES,
  JOB_KINDS,
  JOB_STATUSES,
  JOB_STEP_STATUSES,
  type AcceptedResponse,
  type ApiErrorBody,
  type DocumentUpload,
  type Job,
  type SessionResponse,
} from '@agentic/contracts';

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

function readStoredUserId(): string | null {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    return sessionStorage.getItem(SESSION_USER_KEY);
  } catch {
    return null;
  }
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
let activeWorkspaceId: string = WS_FB;

/** Bộ đếm để id sinh ra không trùng giữa các lần gọi. */
let sequence = 0;
const nextId = (prefix: string): string => {
  sequence += 1;
  return `${prefix}_${sequence}`;
};

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
    return HttpResponse.json(session);
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
    return HttpResponse.json(demoDocuments[params.workspaceId as string] ?? []);
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
      profile.confirmed_at = nowIso();
      profile.confirmed_by = session.user.id;
      profile.completeness = 1;
    }

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
