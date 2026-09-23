/**
 * DRAFT — Auth, phiên, workspace/doanh nghiệp, thành viên, lời mời.
 * Endpoints đề xuất: `/api/v1/auth/*`, `/api/v1/me`, `/api/v1/workspaces/*`
 */

import type { Id, Timestamp } from './common';
import type { Permission, WorkspaceRole } from './enums';

export interface User {
  id: Id;
  email: string;
  full_name: string;
  avatar_url?: string;
  created_at: Timestamp;
  /** Đã bật 2FA hay chưa (chỉ hiển thị, không tự đổi). */
  two_factor_enabled?: boolean;
}

/** Một doanh nghiệp/brand mà người dùng có quyền truy cập. */
export interface Workspace {
  id: Id;
  name: string;
  slug: string;
  industry?: string;
  logo_url?: string;
  /** Vai trò của NGƯỜI DÙNG HIỆN TẠI trong workspace này. */
  role: WorkspaceRole;
  /** Quyền backend cấp cho người dùng hiện tại — nguồn sự thật để ẩn/hiện nút. */
  permissions: Permission[];
  created_at: Timestamp;
}

/**
 * `GET /api/v1/me` — trạng thái phiên hiện tại.
 * UI gọi endpoint này khi tải app để biết đã đăng nhập chưa và có những workspace nào.
 */
export interface SessionResponse {
  user: User;
  workspaces: Workspace[];
  /** Workspace đang chọn. `null` khi người dùng chưa thuộc workspace nào. */
  active_workspace_id: Id | null;
  expires_at: Timestamp;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  user: User;
  workspaces: Workspace[];
  active_workspace_id: Id | null;
  expires_at: Timestamp;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

/** Chuyển workspace đang làm việc. */
export interface SelectWorkspaceRequest {
  workspace_id: Id;
}

// ---------------------------------------------------------------------------
// Thành viên & lời mời
// ---------------------------------------------------------------------------

export interface Member {
  id: Id;
  /** Null for an invitation that has not yet been accepted. */
  user: User | null;
  role: WorkspaceRole;
  /** Trạng thái lời mời: đã tham gia hay còn chờ. */
  status: 'active' | 'invited' | 'suspended';
  invited_by?: Id;
  joined_at?: Timestamp;
  /** Với lời mời đang chờ. */
  invited_email?: string;
  invitation_expires_at?: Timestamp;
}

export interface InviteMemberRequest {
  email: string;
  role: WorkspaceRole;
}

export interface UpdateMemberRoleRequest {
  role: WorkspaceRole;
}

/** Các trạng thái UI cần xử lý riêng cho luồng mời. */
export const INVITATION_OUTCOMES = {
  SENT: 'sent',
  EMAIL_FAILED: 'email_failed',
  ALREADY_MEMBER: 'already_member',
  ALREADY_INVITED: 'already_invited',
} as const;
export type InvitationOutcome =
  (typeof INVITATION_OUTCOMES)[keyof typeof INVITATION_OUTCOMES];

/**
 * Kết quả mời thành viên. `email_failed` nghĩa là lời mời ĐÃ được tạo nhưng
 * thư không gửi được — UI phải hiện link mời để gửi tay, không báo là thất bại.
 */
export interface InviteMemberResponse {
  member: Member;
  outcome: InvitationOutcome;
  /** Link mời, có khi `outcome = email_failed`. */
  invite_url?: string;
}
