/** Facebook Page pilot endpoints. Credentials stay on the API server. */
import type {
  ApiAcceptedResponse,
  ApiMetaConnection,
  ApiMetaPagePost,
  ApiMetaPagePosts,
  ApiMetaPublication,
  ApiMetaReconcileRequest,
} from './types';
import { apiRequest } from './client';

export type MetaConnection = ApiMetaConnection;

export type MetaPublicationStatus = ApiMetaPublication['status'];

export type MetaPublication = ApiMetaPublication;

export type ReconcileMetaPublicationRequest = ApiMetaReconcileRequest;

export type MetaPagePost = ApiMetaPagePost;

export type MetaPagePostPage = ApiMetaPagePosts;

/** Only turn verified HTTPS Facebook links into clickable links. */
export function facebookPostUrl(value: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' &&
      (url.hostname === 'facebook.com' || url.hostname.endsWith('.facebook.com'))
      ? url.toString() : null;
  } catch {
    return null;
  }
}

export const metaQueryKeys = {
  connection: (workspaceId: string) => ['workspaces', workspaceId, 'meta', 'connection'] as const,
  publications: (workspaceId: string) => ['workspaces', workspaceId, 'meta', 'publications'] as const,
  pagePosts: (workspaceId: string, offset: number, connectionId?: string) =>
    ['workspaces', workspaceId, 'meta', 'page-posts', connectionId ?? 'default', offset] as const,
};

function workspacePath(workspaceId: string): string {
  return `/workspaces/${encodeURIComponent(workspaceId)}/meta`;
}

export const metaApi = {
  connection: (workspaceId: string) =>
    apiRequest<MetaConnection>(`${workspacePath(workspaceId)}/connection`),
  verifyConnection: (workspaceId: string) =>
    apiRequest<MetaConnection>(`${workspacePath(workspaceId)}/connection/verify`, {
      method: 'POST',
    }),
  publications: (workspaceId: string) =>
    apiRequest<MetaPublication[]>(`${workspacePath(workspaceId)}/publications`),
  pagePosts: (workspaceId: string, offset = 0, limit = 25, connectionId?: string) =>
    apiRequest<MetaPagePostPage>(`${workspacePath(workspaceId)}/page-posts`, {
      query: { offset, limit, connection_id: connectionId },
    }),
  publish: (workspaceId: string, postId: string, version: number, connectionId?: string) =>
    apiRequest<ApiAcceptedResponse>(`${workspacePath(workspaceId)}/publications`, {
      method: 'POST',
      body: { post_id: postId, version, connection_id: connectionId },
    }),
  syncMetrics: (workspaceId: string, connectionId?: string) =>
    apiRequest<ApiAcceptedResponse>(`${workspacePath(workspaceId)}/metrics/sync`, {
      method: 'POST',
      query: { connection_id: connectionId },
    }),
  reconcile: (
    workspaceId: string,
    publicationId: string,
    body: ReconcileMetaPublicationRequest,
  ) =>
    apiRequest<MetaPublication>(
      `${workspacePath(workspaceId)}/publications/${encodeURIComponent(publicationId)}/reconcile`,
      { method: 'POST', body },
    ),
};
