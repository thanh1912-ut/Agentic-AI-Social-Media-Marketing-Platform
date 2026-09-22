/**
 * Query key tập trung.
 *
 * Lý do gom một chỗ: nếu mỗi component tự viết mảng key, việc làm mới dữ liệu
 * sau khi ghi sẽ bỏ sót màn hình và người dùng thấy số liệu cũ.
 */

export const queryKeys = {
  me: ['me'] as const,

  workspaces: ['workspaces'] as const,
  workspace: (workspaceId: string) => ['workspaces', workspaceId] as const,
  onboarding: (workspaceId: string) => ['workspaces', workspaceId, 'onboarding'] as const,
  members: (workspaceId: string) => ['workspaces', workspaceId, 'members'] as const,

  documents: (workspaceId: string) => ['workspaces', workspaceId, 'documents'] as const,
  documentLimits: (workspaceId: string) =>
    ['workspaces', workspaceId, 'documents', 'limits'] as const,

  brandProfile: (workspaceId: string) =>
    ['workspaces', workspaceId, 'brand-profile'] as const,

  job: (jobId: string) => ['jobs', jobId] as const,
  jobs: (workspaceId: string) => ['workspaces', workspaceId, 'jobs'] as const,

  campaigns: (workspaceId: string) => ['workspaces', workspaceId, 'campaigns'] as const,
  campaign: (workspaceId: string, campaignId: string) =>
    ['workspaces', workspaceId, 'campaigns', campaignId] as const,

  posts: (workspaceId: string, campaignId?: string) =>
    ['workspaces', workspaceId, 'posts', campaignId ?? 'all'] as const,
  post: (workspaceId: string, postId: string) =>
    ['workspaces', workspaceId, 'posts', postId] as const,
  postVersions: (workspaceId: string, postId: string) =>
    ['workspaces', workspaceId, 'posts', postId, 'versions'] as const,
  approvals: (workspaceId: string) =>
    ['workspaces', workspaceId, 'approvals'] as const,

  publications: (workspaceId: string, postId?: string) =>
    ['workspaces', workspaceId, 'publications', postId ?? 'all'] as const,
  publication: (workspaceId: string, publicationId: string) =>
    ['workspaces', workspaceId, 'publications', publicationId] as const,
  connections: (workspaceId: string) =>
    ['workspaces', workspaceId, 'connections'] as const,
  connectionPages: (workspaceId: string, connectionId: string) =>
    ['workspaces', workspaceId, 'connections', connectionId, 'pages'] as const,

  analytics: (workspaceId: string, filters: string) =>
    ['workspaces', workspaceId, 'analytics', filters] as const,

  recommendations: (workspaceId: string, campaignId?: string) =>
    ['workspaces', workspaceId, 'recommendations', campaignId ?? 'all'] as const,
};

/**
 * Nhịp làm mới khi job đang chạy. 2 giây đủ nhanh để người dùng thấy tiến độ
 * nhích, đủ chậm để không spam backend.
 */
export const JOB_POLL_INTERVAL_MS = 2_000;

/** Nhịp làm mới khi có job đang chạy ở danh sách. */
export const JOB_LIST_POLL_INTERVAL_MS = 5_000;
