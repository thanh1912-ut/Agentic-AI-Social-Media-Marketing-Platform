/**
 * Điểm vào DUY NHẤT của tầng API. Component không import trực tiếp
 * `client.ts` hay `endpoints.ts` — chỉ import từ đây.
 */

export { api, authApi, brandApi, campaignApi, documentApi, jobApi, mediaApi, workspaceApi } from './endpoints';
export { facebookPostUrl, metaApi, metaQueryKeys } from './meta';
export type { MetaConnection, MetaPublication, MetaPublicationStatus, MetaPagePost, MetaPagePostPage, ReconcileMetaPublicationRequest } from './meta';
export type { User } from './endpoints';
export {
  ApiError,
  apiDownload,
  apiRequest,
  apiUpload,
  newIdempotencyKey,
  saveBlob,
} from './client';
export { apiBaseUrl, useMocks } from './config';
