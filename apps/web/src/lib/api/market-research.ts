/** Tenant-scoped Page groups and market-research API. */

import { apiRequest } from './client';
import type { ApiAcceptedResponse } from './types';

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
    trends?: Array<{
      title: string;
      explanation: string;
      evidence_ids: string[];
      confidence: number;
    }>;
    suggestions?: Array<{
      title: string;
      angle: string;
      hook: string;
      format: string;
      evidence_ids: string[];
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
    metrics_note?: string;
  };
  model_name: string | null;
  created_at: string;
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
};

export const marketResearchApi = {
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
  createDraft: (workspaceId: string, reportId: string, suggestionIndex: number) =>
    apiRequest<{ campaign_id: string; message: string }>(
      path(workspaceId) + '/reports/' + encodeURIComponent(reportId) + '/draft',
      { method: 'POST', body: { suggestion_index: suggestionIndex } },
    ),
};
