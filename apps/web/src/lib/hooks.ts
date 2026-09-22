'use client';

/**
 * Hook dữ liệu.
 *
 * Toàn bộ trạng thái server đi qua đây — component không tự gọi API. Nhờ vậy
 * chính sách làm mới và query key nằm một chỗ, không bị lệch giữa các màn hình.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import type {
  AcceptedResponse,
  AnalyticsQuery,
  AnalyticsResponse,
  BrandProfile,
  Campaign,
  DocumentUpload,
  Job,
  Member,
  OnboardingState,
  Paginated,
  Post,
  PostVersionList,
  Publication,
  Recommendation,
  SessionResponse,
  SocialConnection,
  UpdateBrandProfileRequest,
  UploadLimits,
  Workspace,
} from '@agentic/contracts';

import { api } from '@/lib/api';
import {
  JOB_LIST_POLL_INTERVAL_MS,
  JOB_POLL_INTERVAL_MS,
  queryKeys,
} from '@/lib/query-keys';

// ---------------------------------------------------------------------------
// Phiên & workspace
// ---------------------------------------------------------------------------

export function useMe(): UseQueryResult<SessionResponse> {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => api.auth.me(signal),
    staleTime: 60_000,
  });
}

export function useWorkspaces(): UseQueryResult<Workspace[]> {
  return useQuery({
    queryKey: queryKeys.workspaces,
    queryFn: () => api.workspace.list(),
  });
}

export function useWorkspace(workspaceId: string): UseQueryResult<Workspace> {
  return useQuery({
    queryKey: queryKeys.workspace(workspaceId),
    queryFn: () => api.workspace.get(workspaceId),
    enabled: workspaceId !== '',
  });
}

export function useOnboarding(workspaceId: string): UseQueryResult<OnboardingState> {
  return useQuery({
    queryKey: queryKeys.onboarding(workspaceId),
    queryFn: () => api.workspace.onboarding(workspaceId),
    enabled: workspaceId !== '',
  });
}

export function useMembers(workspaceId: string): UseQueryResult<Member[]> {
  return useQuery({
    queryKey: queryKeys.members(workspaceId),
    queryFn: () => api.workspace.members(workspaceId),
    enabled: workspaceId !== '',
  });
}

// ---------------------------------------------------------------------------
// Tài liệu
// ---------------------------------------------------------------------------

export function useUploadLimits(workspaceId: string): UseQueryResult<UploadLimits> {
  return useQuery({
    queryKey: queryKeys.documentLimits(workspaceId),
    queryFn: () => api.document.limits(workspaceId),
    enabled: workspaceId !== '',
    // Hạn mức ít đổi — không cần gọi lại thường xuyên.
    staleTime: 5 * 60_000,
  });
}

export function useDocuments(workspaceId: string): UseQueryResult<DocumentUpload[]> {
  return useQuery({
    queryKey: queryKeys.documents(workspaceId),
    queryFn: () => api.document.list(workspaceId),
    enabled: workspaceId !== '',
    // Có tài liệu đang xử lý thì hỏi lại cho tới khi xong.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const busy = data.some(
        (doc) =>
          doc.status === 'processing' ||
          doc.status === 'uploading' ||
          doc.status === 'pending',
      );
      return busy ? JOB_LIST_POLL_INTERVAL_MS : false;
    },
  });
}

export function useUploadDocuments(
  workspaceId: string,
): UseMutationResult<AcceptedResponse, Error, File[]> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (files: File[]) => api.document.upload(workspaceId, files),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) });
    },
  });
}

export function useReprocessDocument(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      api.document.reprocess(workspaceId, documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) });
    },
  });
}

export function useDeleteDocument(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => api.document.remove(workspaceId, documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Brand profile
// ---------------------------------------------------------------------------

export function useBrandProfile(workspaceId: string): UseQueryResult<BrandProfile> {
  return useQuery({
    queryKey: queryKeys.brandProfile(workspaceId),
    queryFn: () => api.brand.get(workspaceId),
    enabled: workspaceId !== '',
  });
}

export function useUpdateBrandProfile(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateBrandProfileRequest) =>
      api.brand.update(workspaceId, body),
    onSuccess: (profile) => {
      queryClient.setQueryData(queryKeys.brandProfile(workspaceId), profile);
      void queryClient.invalidateQueries({ queryKey: queryKeys.onboarding(workspaceId) });
    },
  });
}

/** Nhờ AI trích xuất lại một trường — trả job để theo dõi. */
export function useReextractBrandField(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { key: BrandProfile['business_name']['key']; document_ids?: string[] }) =>
      api.brand.reextract(workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.brandProfile(workspaceId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Job nền
// ---------------------------------------------------------------------------

/**
 * Theo dõi một job.
 *
 * Tự dừng hỏi khi job đã kết thúc — không để trình duyệt gọi mãi.
 */
export function useJob(jobId: string | null | undefined): UseQueryResult<Job> {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ''),
    queryFn: ({ signal }) => api.job.get(jobId as string, signal),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'running' || status === 'queued') return JOB_POLL_INTERVAL_MS;
      return false;
    },
  });
}

export function useCancelJob(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.job.cancel(jobId),
    onSuccess: (job) => {
      queryClient.setQueryData(queryKeys.job(jobId), job);
    },
  });
}

/**
 * Thử lại job.
 *
 * CHỈ dùng cho job xử lý tài liệu / sinh nội dung. Với việc xuất bản có kết quả
 * `outcome_unknown`, phải đi qua luồng đối soát thủ công — không có nút thử lại.
 */
export function useRetryJob(jobId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.job.retry(jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.job(jobId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Campaign & nội dung
// ---------------------------------------------------------------------------

export function useCampaigns(workspaceId: string): UseQueryResult<Paginated<Campaign>> {
  return useQuery({
    queryKey: queryKeys.campaigns(workspaceId),
    queryFn: () => api.campaign.list(workspaceId),
    enabled: workspaceId !== '',
  });
}

export function useCampaign(
  workspaceId: string,
  campaignId: string,
): UseQueryResult<Campaign> {
  return useQuery({
    queryKey: queryKeys.campaign(workspaceId, campaignId),
    queryFn: () => api.campaign.get(workspaceId, campaignId),
    enabled: workspaceId !== '' && campaignId !== '',
  });
}

export function usePosts(
  workspaceId: string,
  campaignId?: string,
): UseQueryResult<Paginated<Post>> {
  return useQuery({
    queryKey: queryKeys.posts(workspaceId, campaignId),
    queryFn: () => api.post.list(workspaceId, campaignId),
    enabled: workspaceId !== '',
  });
}

export function usePost(workspaceId: string, postId: string): UseQueryResult<Post> {
  return useQuery({
    queryKey: queryKeys.post(workspaceId, postId),
    queryFn: () => api.post.get(workspaceId, postId),
    enabled: workspaceId !== '' && postId !== '',
  });
}

export function usePostVersions(
  workspaceId: string,
  postId: string,
): UseQueryResult<PostVersionList> {
  return useQuery({
    queryKey: queryKeys.postVersions(workspaceId, postId),
    queryFn: () => api.post.versions(workspaceId, postId),
    enabled: workspaceId !== '' && postId !== '',
  });
}

// ---------------------------------------------------------------------------
// Publishing
// ---------------------------------------------------------------------------

export function useConnections(workspaceId: string): UseQueryResult<SocialConnection[]> {
  return useQuery({
    queryKey: queryKeys.connections(workspaceId),
    queryFn: () => api.publishing.connections(workspaceId),
    enabled: workspaceId !== '',
  });
}

export function usePublications(
  workspaceId: string,
  postId?: string,
): UseQueryResult<Paginated<Publication>> {
  return useQuery({
    queryKey: queryKeys.publications(workspaceId, postId),
    queryFn: () => api.publishing.publications(workspaceId, postId),
    enabled: workspaceId !== '',
    // Bài đang gửi thì hỏi lại cho tới khi có kết quả.
    refetchInterval: (query) => {
      const items = query.state.data?.items;
      if (!items) return false;
      const inFlight = items.some(
        (item) => item.status === 'pending' || item.status === 'sending',
      );
      return inFlight ? JOB_POLL_INTERVAL_MS : false;
    },
  });
}

// ---------------------------------------------------------------------------
// Analytics & recommendation
// ---------------------------------------------------------------------------

export function useAnalytics(
  workspaceId: string,
  query: AnalyticsQuery,
): UseQueryResult<AnalyticsResponse> {
  const key = JSON.stringify(query);
  return useQuery({
    queryKey: queryKeys.analytics(workspaceId, key),
    queryFn: ({ signal }) => api.analytics.query(workspaceId, query, signal),
    enabled: workspaceId !== '',
    // Số liệu không cần tươi từng giây.
    staleTime: 5 * 60_000,
  });
}

export function useRecommendations(
  workspaceId: string,
  campaignId?: string,
): UseQueryResult<Paginated<Recommendation>> {
  return useQuery({
    queryKey: queryKeys.recommendations(workspaceId, campaignId),
    queryFn: () => api.recommendation.list(workspaceId, campaignId),
    enabled: workspaceId !== '',
  });
}
