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
import { useEffect, useRef } from 'react';

import type {
  AnalyticsQuery,
  AnalyticsResponse,
  ApprovalRequest,
  BrandProfile,
  Campaign,
  CreateExportRequest,
  CreateManualPostRequest,
  GenerateContentRequest,
  GenerateContentResponse,
  OnboardingState,
  Paginated,
  Post,
  PostVersionList,
  Publication,
  Recommendation,
  SocialConnection,
  UpdatePostRequest,
} from '@agentic/contracts';

import type {
  ApiAcceptedResponse as AcceptedResponse,
  ApiAcceptedRecommendationDraftList,
  ApiAnalyticsDashboard,
  ApiApplyRecommendationRequest,
  ApiRecommendationDraftDecisionRequest,
  ApiRecommendationFeedbackRequest,
  ApiSaveRecommendationRequest,
  ApiBrandProfile,
  ApiConfirmBrandProfileRequest,
  ApiDocument as DocumentUpload,
  ApiJob as Job,
  ApiMember as Member,
  ApiSessionResponse as SessionResponse,
  ApiUploadLimits as UploadLimits,
  ApiUpdateBrandProfileRequest,
  ApiWorkspace as Workspace,
  ApiMetricImportRequest,
  ApiMetricRecommendation,
  ApiExperimentOutcomeList,
  ApiRecordExperimentOutcomeRequest,
} from '@/lib/api/types';
import { api, useMocks } from '@/lib/api';
import {
  JOB_LIST_POLL_INTERVAL_MS,
  JOB_POLL_INTERVAL_MS,
  queryKeys,
} from '@/lib/query-keys';
import { newIdempotencyKey } from '@/lib/api/client';

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

export function useWorkspaces(): UseQueryResult<readonly Workspace[]> {
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

export function useSelectWorkspace() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (workspaceId: string) => api.workspace.select(workspaceId),
    onSuccess: (session) => {
      queryClient.setQueryData(queryKeys.me, session);
      queryClient.setQueryData(queryKeys.workspaces, session.workspaces);
    },
  });
}

export function useOnboarding(workspaceId: string): UseQueryResult<OnboardingState> {
  const mocksEnabled = useMocks();
  return useQuery({
    queryKey: queryKeys.onboarding(workspaceId),
    queryFn: () => api.workspace.onboarding(workspaceId),
    enabled: workspaceId !== '' && mocksEnabled,
  });
}

export function useMembers(workspaceId: string): UseQueryResult<readonly Member[]> {
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

export function useDocuments(workspaceId: string): UseQueryResult<readonly DocumentUpload[]> {
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
      const withinPollingLimit = data.some((doc) => {
        if (doc.status !== 'processing' && doc.status !== 'uploading' && doc.status !== 'pending') {
          return false;
        }
        const uploadedAt = Date.parse(doc.uploaded_at);
        return Number.isFinite(uploadedAt) && Date.now() - uploadedAt < 10 * 60_000;
      });
      return busy && withinPollingLimit ? JOB_LIST_POLL_INTERVAL_MS : false;
    },
  });
}

export interface UploadDocumentsVariables {
  files: File[];
  idempotencyKey: string;
}

export function useUploadDocuments(
  workspaceId: string,
): UseMutationResult<AcceptedResponse, Error, UploadDocumentsVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ files, idempotencyKey }) =>
      api.document.upload(workspaceId, files, idempotencyKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) });
    },
  });
}

export function newDocumentUploadKey(): string {
  return newIdempotencyKey('documents');
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
  const mocksEnabled = useMocks();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) => {
      if (!mocksEnabled) throw new Error('Xoá tài liệu chưa có trong HTTP OpenAPI.');
      return api.document.remove(workspaceId, documentId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents(workspaceId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Brand profile
// ---------------------------------------------------------------------------

export function useBrandProfile(
  workspaceId: string,
  enabled = true,
): UseQueryResult<ApiBrandProfile> {
  return useQuery({
    queryKey: queryKeys.brandProfile(workspaceId),
    queryFn: () => api.brand.get(workspaceId),
    enabled: workspaceId !== '' && enabled,
  });
}

export function useUpdateBrandProfile(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiUpdateBrandProfileRequest) => api.brand.update(workspaceId, body),
    onSuccess: (profile) => {
      queryClient.setQueryData(queryKeys.brandProfile(workspaceId), profile);
      void queryClient.invalidateQueries({ queryKey: queryKeys.onboarding(workspaceId) });
    },
  });
}

export function useConfirmBrandProfile(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiConfirmBrandProfileRequest) => api.brand.confirm(workspaceId, body),
    onSuccess: (profile) => {
      queryClient.setQueryData(queryKeys.brandProfile(workspaceId), profile);
      void queryClient.invalidateQueries({ queryKey: queryKeys.onboarding(workspaceId) });
    },
  });
}

/** Nhờ AI trích xuất lại một trường — trả job để theo dõi. */
export function useReextractBrandField(workspaceId: string) {
  const mocksEnabled = useMocks();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { key: BrandProfile['business_name']['key']; document_ids?: string[] }) => {
      if (!mocksEnabled) throw new Error('Tái trích xuất Brand Profile chưa có trong HTTP OpenAPI.');
      return api.brand.reextract(workspaceId, body);
    },
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
  const pollingStartedAt = useRef<number | null>(null);

  useEffect(() => {
    pollingStartedAt.current = null;
    return () => {
      pollingStartedAt.current = null;
    };
  }, [jobId]);

  return useQuery({
    queryKey: queryKeys.job(jobId ?? ''),
    queryFn: ({ signal }) => {
      if (!jobId) throw new Error('Thiếu mã job.');
      if (pollingStartedAt.current === null) pollingStartedAt.current = Date.now();
      return api.job.get(jobId, signal);
    },
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      if (query.state.status === 'error') return false;
      const status = query.state.data?.status;
      const withinPollingLimit =
        pollingStartedAt.current !== null &&
        Date.now() - pollingStartedAt.current < 10 * 60_000;
      if ((status === 'running' || status === 'queued') && withinPollingLimit) {
        return JOB_POLL_INTERVAL_MS;
      }
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

export function useCreateCampaign(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Campaign>) => api.campaign.create(workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.campaigns(workspaceId) });
    },
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

export function useCreatePost(workspaceId: string, campaignId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateManualPostRequest) => api.post.create(workspaceId, campaignId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.posts(workspaceId, campaignId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.campaign(workspaceId, campaignId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.campaigns(workspaceId) });
    },
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

export function useUpdatePost(workspaceId: string, postId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdatePostRequest) => api.post.update(workspaceId, postId, body),
    onSuccess: (post) => {
      queryClient.setQueryData(queryKeys.post(workspaceId, postId), post);
      void queryClient.invalidateQueries({ queryKey: queryKeys.postVersions(workspaceId, postId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.posts(workspaceId, post.campaign_id) });
    },
  });
}

export function useGenerateContent(workspaceId: string) {
  return useMutation<GenerateContentResponse, Error, GenerateContentRequest>({
    mutationFn: (body) => api.post.generate(workspaceId, body),
  });
}

export function useSubmitApproval(workspaceId: string, postId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (version: number) => api.approval.submit(workspaceId, postId, version),
    onSuccess: (post) => {
      queryClient.setQueryData(queryKeys.post(workspaceId, postId), post);
      void queryClient.invalidateQueries({ queryKey: queryKeys.posts(workspaceId, post.campaign_id) });
    },
  });
}

export function useDecideApproval(workspaceId: string, postId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApprovalRequest) => api.approval.decide(workspaceId, postId, body),
    onSuccess: (post) => {
      queryClient.setQueryData(queryKeys.post(workspaceId, postId), post);
      void queryClient.invalidateQueries({ queryKey: queryKeys.posts(workspaceId, post.campaign_id) });
    },
  });
}

export function useCreateExport(workspaceId: string) {
  return useMutation({
    mutationFn: (body: CreateExportRequest) => api.export.create(workspaceId, body),
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

export function useManualAnalyticsDashboard(
  workspaceId: string,
  sourceId: string,
): UseQueryResult<ApiAnalyticsDashboard> {
  return useQuery({
    queryKey: queryKeys.analytics(workspaceId, `manual:${sourceId}`),
    queryFn: ({ signal }) => api.analytics.dashboard(workspaceId, sourceId, signal),
    enabled: workspaceId !== '' && sourceId.trim() !== '',
    staleTime: 60_000,
  });
}

export function useManualMetricRecommendation(
  workspaceId: string,
  sourceId: string,
): UseQueryResult<ApiMetricRecommendation> {
  return useQuery({
    queryKey: queryKeys.recommendations(workspaceId, `manual:${sourceId}`),
    queryFn: ({ signal }) => api.analytics.recommendation(workspaceId, sourceId, signal),
    enabled: workspaceId !== '' && sourceId.trim() !== '',
    staleTime: 60_000,
  });
}

export function useImportMetricSnapshot(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiMetricImportRequest) => api.analytics.importSnapshot(workspaceId, body),
    onSuccess: (_response, body) => {
      void queryClient.invalidateQueries({
        queryKey: ['workspaces', workspaceId, 'analytics'],
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.recommendations(workspaceId, `manual:${body.source_id}`),
      });
    },
  });
}

export function useSaveManualRecommendation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiSaveRecommendationRequest) => api.analytics.saveRecommendation(workspaceId, body),
    onSuccess: (_record, body) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.recommendations(workspaceId, `manual:${body.source_id}`),
      });
    },
  });
}

export function useManualRecommendationFeedback(workspaceId: string) {
  return useMutation({
    mutationFn: ({ recommendationId, body }: {
      recommendationId: string;
      body: ApiRecommendationFeedbackRequest;
    }) => api.analytics.recommendationFeedback(workspaceId, recommendationId, body),
  });
}

export function useApplyManualRecommendation(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ recommendationId, body }: {
      recommendationId: string;
      body: ApiApplyRecommendationRequest;
    }) => api.analytics.applyRecommendation(workspaceId, recommendationId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.campaigns(workspaceId) });
    },
  });
}

export function useDecideManualRecommendationDraft(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ draftId, body }: {
      draftId: string;
      body: ApiRecommendationDraftDecisionRequest;
    }) => api.analytics.decideRecommendationDraft(workspaceId, draftId, body),
    onSuccess: (draft) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.campaign(workspaceId, draft.campaign_id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.campaigns(workspaceId) });
      void queryClient.invalidateQueries({
        queryKey: ['workspaces', workspaceId, 'analytics'],
      });
    },
  });
}

export function useAcceptedRecommendationDrafts(
  workspaceId: string,
  campaignId: string,
  sourceId: string,
): UseQueryResult<ApiAcceptedRecommendationDraftList> {
  return useQuery({
    queryKey: queryKeys.analytics(workspaceId, `accepted-drafts:${campaignId}:${sourceId}`),
    queryFn: ({ signal }) => api.analytics.acceptedRecommendationDrafts(workspaceId, campaignId, sourceId, signal),
    enabled: workspaceId !== '' && campaignId !== '' && sourceId.trim() !== '',
    staleTime: 30_000,
  });
}

export function useRecommendationExperimentOutcomes(
  workspaceId: string,
  draftId: string,
): UseQueryResult<ApiExperimentOutcomeList> {
  return useQuery({
    queryKey: queryKeys.analytics(workspaceId, `experiment-outcomes:${draftId}`),
    queryFn: ({ signal }) => api.analytics.experimentOutcomes(workspaceId, draftId, signal),
    enabled: workspaceId !== '' && draftId !== '',
    staleTime: 30_000,
  });
}

export function useRecordRecommendationExperimentOutcome(workspaceId: string, draftId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiRecordExperimentOutcomeRequest) =>
      api.analytics.recordExperimentOutcome(workspaceId, draftId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.analytics(workspaceId, `experiment-outcomes:${draftId}`),
      });
    },
  });
}
