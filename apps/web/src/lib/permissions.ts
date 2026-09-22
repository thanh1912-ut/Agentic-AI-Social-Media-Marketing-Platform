/**
 * Ma trận quyền ở tầng UI.
 *
 * ⚠️ ĐÂY KHÔNG PHẢI LỚP BẢO VỆ. Backend kiểm quyền lần cuối cho mọi request.
 * Hàm ở đây chỉ để ẩn/hiện nút và — quan trọng hơn — để GIẢI THÍCH cho người
 * dùng vì sao họ không làm được việc đó.
 */

import {
  PERMISSIONS,
  ROLE_LABELS,
  type Permission,
  type Workspace,
} from '@agentic/contracts';

/** Người dùng hiện tại có quyền này trong workspace không. */
export function hasPermission(
  workspace: Workspace | null | undefined,
  permission: Permission,
): boolean {
  if (!workspace) return false;
  return workspace.permissions.includes(permission);
}

export function hasAnyPermission(
  workspace: Workspace | null | undefined,
  permissions: readonly Permission[],
): boolean {
  return permissions.some((permission) => hasPermission(workspace, permission));
}

/**
 * Câu giải thích khi một nút bị khoá.
 *
 * Nguyên tắc UX: KHÔNG bao giờ khoá một nút mà không nói lý do. Người dùng phải
 * biết là do quyền của mình hay do trạng thái dữ liệu.
 */
export function permissionDeniedReason(
  workspace: Workspace | null | undefined,
  _permission: Permission,
): string {
  const roleLabel = workspace ? ROLE_LABELS[workspace.role] : 'khách';
  return `Vai trò ${roleLabel} không có quyền thực hiện việc này. Hãy nhờ chủ sở hữu doanh nghiệp thực hiện hoặc cấp quyền cho bạn.`;
}

/**
 * Các quyền cần cho từng hành động chính. Khai báo một chỗ để nút và thông báo
 * không lệch nhau.
 */
export const ACTION_REQUIREMENTS = {
  editBrand: PERMISSIONS.BRAND_EDIT,
  confirmBrand: PERMISSIONS.BRAND_CONFIRM,
  uploadDocument: PERMISSIONS.DOCUMENT_UPLOAD,
  createCampaign: PERMISSIONS.CAMPAIGN_CREATE,
  generateContent: PERMISSIONS.POST_GENERATE,
  editPost: PERMISSIONS.POST_EDIT,
  approvePost: PERMISSIONS.POST_APPROVE,
  rejectPost: PERMISSIONS.POST_REJECT,
  createExport: PERMISSIONS.EXPORT_CREATE,
  manageConnection: PERMISSIONS.CONNECTION_MANAGE,
  publish: PERMISSIONS.PUBLISH_CREATE,
  importMetrics: PERMISSIONS.METRIC_IMPORT,
  applyRecommendation: PERMISSIONS.RECOMMENDATION_APPLY,
  inviteMember: PERMISSIONS.MEMBER_INVITE,
} as const satisfies Record<string, Permission>;
