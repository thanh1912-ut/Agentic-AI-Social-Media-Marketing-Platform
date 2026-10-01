/** Tenant-scoped Page groups and market-research API. */

import { apiRequest } from './client';
import type { ApiAcceptedResponse } from './types';
import type { components } from './schema';

export type CommentProcessing = components['schemas']['CommentProcessingOut'];
export type CommentProcessingRequest = components['schemas']['CommentProcessingIn'];
export type CommentCandidatesPage = components['schemas']['CommentCandidatesPage'];
export type CommentSuppressionRequest = components['schemas']['CommentSuppressionIn'];
export type CommentSuppressionResult = components['schemas']['CommentSuppressionOut'];

export interface MarketGroup {
  id: string;
  name: string;
  industry: string;
  region: string;
  locale: string;
  keywords: string[];
  active: boolean;
  page_count: number;
  source_count: number;
  next_due_at: string | null;
  last_cycle_at: string | null;
}

export interface PageConnection {
  id: string;
  group_id: string;
  page_id: string;
  page_name: string | null;
  status: 'configured' | 'verified' | 'error' | 'needs_reconnect';
  verified_at: string | null;
  last_error_code: string | null;
  active: boolean;
}

export type ResearchSourceType =
  | 'website'
  | 'owned_facebook_page'
  | 'competitor_facebook_page'
  | 'facebook_group';

export interface ResearchSource {
  id: string;
  group_id: string;
  source_type: ResearchSourceType;
  name: string;
  url: string;
  competitor_name: string | null;
  status: string;
  active: boolean;
  next_due_at: string | null;
  last_crawled_at: string | null;
  error: { code?: string; message?: string; retryable?: boolean } | null;
  connection_id: string | null;
  crawl_mode?: 'legacy' | 'site_catalog';
  crawl_page_limit?: number;
  render_mode?: 'http_only' | 'javascript';
  resource_hosts?: string[];
  schedule_enabled?: boolean;
  collection_mode?: 'legacy' | 'public_web' | 'meta_api' | 'manual';
  collection_post_limit?: number;
  collection_status?: string;
  collection_last_method?: string | null;
  last_collection_attempt_at?: string | null;
  last_collection_success_at?: string | null;
}

export interface ResearchPrivacyPolicy {
  source_id: string;
  configured: boolean;
  collection_ready: boolean;
  legal_basis_verified: false;
  revision_no: number | null;
  purpose: string | null;
  processing_basis_reference: string | null;
  policy_version: string | null;
  requested_retention_days: number | null;
  configured_by: string | null;
  configured_at: string | null;
  retention_enforcement_status: 'not_enforced';
  comments_content_status: 'privacy_hold';
}

export interface CompetitorPost {
  reaction_breakdown?: Record<string, number>;
  comment_coverage?: Record<string, unknown>;
  id: string;
  source_id: string;
  external_id: string | null;
  url: string;
  title: string;
  text: string;
  published_at: string | null;
  observed_at: string | null;
  metrics: Record<string, number | null>;
  link_url: string | null;
  attachments: ResearchPostAttachment[];
  attachment_metadata_status: 'returned' | 'none_returned' | 'not_returned' | 'truncated';
  metric_provenance: Record<string, {
    raw?: string | null;
    precision?: string | null;
    missing_reason?: string | null;
  }>;
  content_truncated: boolean;
}

export interface ResearchPostAttachment {
  kind: 'image' | 'video' | 'link' | 'other' | 'unknown';
  provider_type: string | null;
  title: string | null;
  description: string | null;
  target_url: string | null;
  content_status: 'metadata_only_privacy_hold';
}

export interface CompetitorPostsPage {
  posts: CompetitorPost[];
  next_cursor: string | null;
  followers: number | null;
  followers_observed_at: string | null;
  followers_missing_reason: string | null;
}

export interface CompetitorCollectionRun {
  id: string;
  source_id: string;
  job_id: string;
  collector: string;
  engine?: string | null;
  engine_version?: string | null;
  access_tier?: number | null;
  privacy_policy_revision_id?: string | null;
  privacy_policy_revision_no?: number | null;
  privacy_policy_version?: string | null;
  privacy_policy_ready_for_collection?: boolean | null;
  privacy_policy_legal_basis_verified?: false | null;
  privacy_policy_requested_retention_days?: number | null;
  retention_enforcement_status?: 'not_enforced';
  comments_content_status?: 'privacy_hold';
  status: string;
  post_limit: number;
  counters: Record<string, unknown>;
  coverage: Record<string, unknown>;
  blocked_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface WebOffer {
  id: string;
  offer_key: string;
  price_kind: 'exact' | 'from' | 'range' | 'contact' | 'free' | 'unknown' | string;
  price: string | null;
  original_price: string | null;
  low_price: string | null;
  high_price: string | null;
  currency: string | null;
  availability: string | null;
  billing_unit: string | null;
  seller: string | null;
  offer_url: string;
  provenance: Record<string, unknown>;
}

export interface WebItem {
  id: string;
  source_id: string;
  kind: 'product' | 'article' | 'business_info' | string;
  title: string;
  url: string;
  observed_at: string | null;
  data: Record<string, unknown> | null;
  offers: WebOffer[];
}

export interface WebItemsPage {
  items: WebItem[];
  next_cursor: string | null;
}

export interface MarketReport {
  id: string;
  group_id: string;
  window_start: string;
  window_end: string;
  report: {
    headline?: string;
    summary?: string;
    analysis_status?: string;
    privacy_coverage?: {
      facebook_post_text_withheld?: number;
      facebook_post_text_sent?: number;
      comments_content_status?: string;
      media_content_status?: string;
    };
    business_profile_context?: {
      status: 'applied' | 'not_configured' | 'revision_unavailable' | 'legacy_unknown' | string;
      brand_id?: string;
      revision_id?: string;
      revision?: number;
    };
    trends?: Array<{
      title: string;
      explanation: string;
      evidence_ids: string[];
      web_snapshot_ids?: string[];
      confidence: number;
    }>;
    suggestions?: Array<{
      title: string;
      angle: string;
      hook: string;
      format: string;
      evidence_ids: string[];
      web_snapshot_ids?: string[];
    }>;
    evidence_refs?: Array<{
      id: string;
      title: string;
      url: string;
      published_at: string | null;
      observed_at?: string | null;
      previous_observed_at?: string | null;
      metrics?: Record<string, number | null>;
      metric_delta?: Record<string, number | null>;
      comments?: string[];
      content_processing_status?: string | null;
    }>;
  };
  evidence_ids: string[];
  coverage: {
    sources?: Array<{
      source_id: string;
      status: string;
      items_seen?: number;
      items_saved?: number;
      metrics_available?: string[];
      metrics_unavailable?: string[];
      metrics_partial?: Record<string, { observed_posts: number; total_posts: number }>;
      message?: string;
    }>;
    ai_status?: string;
    business_profile_context?: {
      status: 'applied' | 'not_configured' | 'revision_unavailable' | 'legacy_unknown' | string;
      brand_id?: string;
      revision_id?: string;
      revision?: number;
    };
    web_snapshot_ids?: string[];
    metrics_note?: string;
    privacy_coverage?: {
      facebook_post_text_withheld?: number;
      facebook_post_text_sent?: number;
      comments_content_status?: string;
      media_content_status?: string;
    };
  };
  model_name: string | null;
  created_at: string;
}

export interface ResearchAIBudget {
  budget_date: string;
  resets_at: string;
  currency: 'USD';
  limit_micro_usd: number;
  reserved_micro_usd: number;
  spent_micro_usd: number;
  available_micro_usd: number;
  unsettled_requests: number;
  pending_reports: number;
}

interface CreateGroup {
  name: string;
  industry: string;
  region: string;
  locale: string;
  keywords: string[];
}

interface CreateResearchSource {
  group_id: string;
  source_type: ResearchSourceType;
  name: string;
  url: string;
  competitor_name?: string;
  connection_id?: string;
}

interface ImportObservation {
  url: string;
  title: string;
  text: string;
  observed_at?: string;
  published_at?: string;
  metrics: Record<string, number | null>;
  comments: string[];
}

function path(workspaceId: string): string {
  return '/workspaces/' + encodeURIComponent(workspaceId) + '/market-research';
}

export const marketResearchKeys = {
  groups: (workspaceId: string) => ['workspaces', workspaceId, 'market-research', 'groups'] as const,
  pages: (workspaceId: string, groupId: string) =>
    ['workspaces', workspaceId, 'market-research', groupId, 'pages'] as const,
  sources: (workspaceId: string, groupId?: string) =>
    ['workspaces', workspaceId, 'market-research', 'sources', groupId ?? 'all'] as const,
  reports: (workspaceId: string, groupId: string) =>
    ['workspaces', workspaceId, 'market-research', groupId, 'reports'] as const,
  aiBudget: (workspaceId: string) => ['workspaces', workspaceId, 'market-research', 'ai-budget'] as const,
  webItems: (workspaceId: string, groupId: string, kind: string) =>
    ['workspaces', workspaceId, 'market-research', groupId, 'web-items', kind] as const,
  competitorPosts: (workspaceId: string, sourceId: string) =>
    ['workspaces', workspaceId, 'market-research', 'competitor-posts', sourceId] as const,
  competitorRuns: (workspaceId: string, sourceId: string) =>
    ['workspaces', workspaceId, 'market-research', 'competitor-runs', sourceId] as const,
  privacyPolicy: (workspaceId: string, sourceId: string) =>
    ['workspaces', workspaceId, 'market-research', 'privacy-policy', sourceId] as const,
  commentProcessing: (workspaceId: string, sourceId: string) =>
    ['workspaces', workspaceId, 'market-research', 'comment-processing', sourceId] as const,
  commentCandidates: (workspaceId: string, sourceId: string) =>
    ['workspaces', workspaceId, 'market-research', 'comment-candidates', sourceId] as const,
};

export const marketResearchApi = {
  aiBudget: (workspaceId: string) =>
    apiRequest<ResearchAIBudget>(path(workspaceId) + '/ai-budget'),
  groups: (workspaceId: string) =>
    apiRequest<MarketGroup[]>(path(workspaceId) + '/groups'),
  createGroup: (workspaceId: string, body: CreateGroup) =>
    apiRequest<MarketGroup>(path(workspaceId) + '/groups', { method: 'POST', body }),
  pages: (workspaceId: string, groupId: string) =>
    apiRequest<PageConnection[]>(path(workspaceId) + '/groups/' + encodeURIComponent(groupId) + '/pages'),
  allPages: (workspaceId: string) =>
    apiRequest<PageConnection[]>(path(workspaceId) + '/pages'),
  connectPage: (workspaceId: string, groupId: string, body: { page_id: string; page_access_token: string }) =>
    apiRequest<PageConnection>(path(workspaceId) + '/groups/' + encodeURIComponent(groupId) + '/pages', {
      method: 'POST',
      body,
    }),
  disconnectPage: (workspaceId: string, connectionId: string) =>
    apiRequest<void>(path(workspaceId) + '/pages/' + encodeURIComponent(connectionId), { method: 'DELETE' }),
  sources: (workspaceId: string, groupId?: string) =>
    apiRequest<ResearchSource[]>(path(workspaceId) + '/sources', {
      query: { group_id: groupId },
    }),
  createSource: (workspaceId: string, body: CreateResearchSource) =>
    apiRequest<ResearchSource>(path(workspaceId) + '/sources', { method: 'POST', body }),
  deleteSource: (workspaceId: string, sourceId: string) =>
    apiRequest<void>(path(workspaceId) + '/sources/' + encodeURIComponent(sourceId), { method: 'DELETE' }),
  privacyPolicy: (workspaceId: string, sourceId: string) =>
    apiRequest<ResearchPrivacyPolicy>(
      path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/privacy-policy',
    ),
  savePrivacyPolicy: (workspaceId: string, sourceId: string, body: {
    purpose: string;
    processing_basis_reference: string;
    policy_version: string;
    requested_retention_days: number;
  }) => apiRequest<ResearchPrivacyPolicy>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/privacy-policy',
    { method: 'PUT', body },
  ),
  updateCrawlSettings: (workspaceId: string, sourceId: string, body: {
    crawl_mode: 'legacy' | 'site_catalog';
    crawl_page_limit: number;
    render_mode: 'http_only' | 'javascript';
    resource_hosts: string[];
    schedule_enabled: boolean;
  }) => apiRequest<ResearchSource>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/crawl-settings',
    { method: 'PATCH', body },
  ),
  updateCollectionSettings: (workspaceId: string, sourceId: string, body: {
    collector: 'public_web' | 'meta_api' | 'manual';
    schedule_enabled: boolean;
    post_limit: number;
  }) => apiRequest<ResearchSource>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/collection-settings',
    { method: 'PATCH', body },
  ),
  crawlSource: (workspaceId: string, sourceId: string) =>
    apiRequest<ApiAcceptedResponse>(
      path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/crawl',
      { method: 'POST' },
    ),
  competitorCollectionRuns: (workspaceId: string, sourceId: string) =>
    apiRequest<CompetitorCollectionRun[]>(
      path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/collection-runs',
    ),
  commentProcessing: (workspaceId: string, sourceId: string) => apiRequest<CommentProcessing>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/comment-processing',
  ),
  saveCommentProcessing: (workspaceId: string, sourceId: string, body: CommentProcessingRequest) => apiRequest<CommentProcessing>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/comment-processing', { method: 'PUT', body },
  ),
  revokeCommentProcessing: (workspaceId: string, sourceId: string, decisionId: string) => apiRequest<CommentProcessing>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/comment-processing/revoke',
    { method: 'POST', body: { expected_decision_id: decisionId } },
  ),
  commentCandidates: (workspaceId: string, sourceId: string, evidenceId: string, cursor?: string) => apiRequest<CommentCandidatesPage>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/posts/' + encodeURIComponent(evidenceId) + '/comments',
    { query: { limit: 25, cursor } },
  ),
  suppressComment: (workspaceId: string, sourceId: string, versionId: string, body: CommentSuppressionRequest) => apiRequest<CommentSuppressionResult>(
    path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/comments/' + encodeURIComponent(versionId) + '/suppress',
    { method: 'POST', body },
  ),
  competitorPosts: (workspaceId: string, sourceId: string, cursor?: string) =>
    apiRequest<CompetitorPostsPage>(
      path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/posts',
      { query: { limit: 25, cursor } },
    ),
  importObservations: (workspaceId: string, sourceId: string, rows: ImportObservation[]) =>
    apiRequest<{ imported: number; observed_at: string }>(
      path(workspaceId) + '/sources/' + encodeURIComponent(sourceId) + '/import',
      { method: 'POST', body: { rows } },
    ),
  crawlNow: (workspaceId: string, groupId: string) =>
    apiRequest<ApiAcceptedResponse>(path(workspaceId) + '/groups/' + encodeURIComponent(groupId) + '/crawl', {
      method: 'POST',
    }),
  reports: (workspaceId: string, groupId: string) =>
    apiRequest<MarketReport[]>(path(workspaceId) + '/groups/' + encodeURIComponent(groupId) + '/reports'),
  allReports: (workspaceId: string) =>
    apiRequest<MarketReport[]>(path(workspaceId) + '/reports'),
  webItems: (workspaceId: string, groupId: string, kind: string) =>
    apiRequest<WebItemsPage>(path(workspaceId) + '/groups/' + encodeURIComponent(groupId) + '/web-items', {
      query: { kind, limit: 100 },
    }),
  createDraft: (workspaceId: string, reportId: string, suggestionIndex: number) =>
    apiRequest<{ campaign_id: string; message: string }>(
      path(workspaceId) + '/reports/' + encodeURIComponent(reportId) + '/draft',
      { method: 'POST', body: { suggestion_index: suggestionIndex } },
    ),
};
